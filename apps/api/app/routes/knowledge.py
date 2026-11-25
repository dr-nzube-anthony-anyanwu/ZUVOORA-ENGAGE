"""Knowledge document routes (Phase 2c): upload, screen, extract, review, publish, version.

Flow for every upload: authorise (owner/admin) -> screen type from content -> extract text in
an isolated worker (photos and scanned PDFs: page images read by an AI model after plan, quota
and budget checks — Phase 3g, ADR-041) -> in ONE transaction insert the version
(database-generated storage path) and store the original privately -> commit. Rejected files
are never stored (the rejection is audited). Nothing is public until an owner/admin approves a
version, which publishes it.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.content_schemas import Line, Text, _single
from app.db import Database
from app.deps import (
    ALL_ROLES,
    MANAGER_ROLES,
    get_db,
    get_object_store,
    get_principal,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, forbidden, not_found
from app.schemas import StrictModel
from app.security.jwt import Principal
from app.services import entitlements
from app.services.ai.answerer import Budget, over_budget
from app.services.ai.vision import VisionReader
from app.services.answering.chunking import chunk_text
from app.services.extraction import (
    MAX_UPLOAD_BYTES,
    Extraction,
    UploadRejected,
    detect_type,
    extract,
    safe_file_name,
)
from app.services.malware_scan import MalwareScanner, ScannerUnavailable
from app.services.storage import ObjectStore, StorageError

router = APIRouter(prefix="/tenants/{tenant_id}/knowledge", tags=["knowledge"])
log = logging.getLogger("engage.knowledge")

MAX_DOCUMENTS = 100
MAX_VERSIONS = 50

_VERSION_COLUMNS = """id, document_id, version_no, status::text as status, file_name, detected_type,
    extraction_method, size_bytes, sha256, page_count, uploaded_at, reviewed_at, review_note,
    char_length(extracted_text) as text_length"""
_DOC_COLUMNS = "id, title, published_version_id, archived_at, created_at, updated_at"


# ----- models ----------------------------------------------------------------------------------
class VersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    status: Literal["extracted", "failed", "approved", "rejected"]
    is_published: bool
    file_name: str
    detected_type: Literal["pdf", "docx", "text", "image"]
    extraction_method: Literal["text", "vision"]  # "vision": read by AI from an image
    size_bytes: int
    sha256: str
    page_count: int | None
    text_length: int | None
    uploaded_at: datetime
    reviewed_at: datetime | None
    review_note: str | None


class VersionDetailOut(VersionOut):
    extracted_text: str | None


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    state: Literal["awaiting_review", "published", "changes_pending", "unpublished", "archived"]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    published_version: VersionOut | None
    latest_version: VersionOut | None
    awaiting_review: int


class DocumentDetailOut(DocumentOut):
    versions: list[VersionOut]


class RenameIn(StrictModel):
    title: Line = Field(min_length=2, max_length=200)


class ReviewIn(StrictModel):
    note: Text | None = Field(default=None, max_length=500)


# ----- helpers ---------------------------------------------------------------------------------
def _version(row: dict[str, Any], published_id: uuid.UUID | None) -> VersionOut:
    return VersionOut(
        **{k: v for k, v in row.items() if k != "document_id"},
        is_published=row["id"] == published_id,
    )


def _document(doc: dict[str, Any], versions: list[dict[str, Any]], detail: bool = False):
    published_id = doc["published_version_id"]
    items = [_version(v, published_id) for v in sorted(versions, key=lambda v: -v["version_no"])]
    published = next((v for v in items if v.is_published), None)
    latest = items[0] if items else None
    waiting = sum(1 for v in items if v.status == "extracted")
    if doc["archived_at"] is not None:
        state = "archived"
    elif published is None:
        state = "awaiting_review" if waiting else "unpublished"
    else:
        state = "changes_pending" if waiting else "published"
    base = {
        "id": doc["id"],
        "title": doc["title"],
        "state": state,
        "archived_at": doc["archived_at"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
        "published_version": published,
        "latest_version": latest,
        "awaiting_review": waiting,
    }
    return DocumentDetailOut(**base, versions=items) if detail else DocumentOut(**base)


def _load_document(
    conn: psycopg.Connection, tenant_id: uuid.UUID, document_id: uuid.UUID, *, lock: bool = False
) -> dict[str, Any]:
    row = conn.execute(
        f"select {_DOC_COLUMNS} from public.knowledge_documents "  # noqa: S608 - constants
        "where id = %s and tenant_id = %s" + (" for update" if lock else ""),
        (document_id, tenant_id),
    ).fetchone()
    if row is None:
        raise not_found()
    return row


def _versions(
    conn: psycopg.Connection, tenant_id: uuid.UUID, document_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    query = (
        f"select {_VERSION_COLUMNS} from public.knowledge_document_versions "  # noqa: S608
        "where tenant_id = %s"
    )
    params: tuple[Any, ...] = (tenant_id,)
    if document_id is not None:
        query += " and document_id = %s"
        params += (document_id,)
    return conn.execute(query, params).fetchall()


def _detail(conn: psycopg.Connection, tenant_id: uuid.UUID, document_id: uuid.UUID):
    doc = _load_document(conn, tenant_id, document_id)
    return _document(doc, _versions(conn, tenant_id, document_id), detail=True)


def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    return safe_file_name(file.filename), data


def _clean_title(title: str) -> str:
    try:
        value = _single(title)
    except ValueError as exc:
        raise ApiError(
            422, "invalid_title", "The title contains characters that are not allowed."
        ) from exc
    if not 2 <= len(value) <= 200:
        raise ApiError(422, "invalid_title", "The title must be 2 to 200 characters.")
    return value


def _vision_pages(
    request: Request, db: Database, principal: Principal, tenant_id: uuid.UUID, detected: str
) -> int:
    """How many pages may be read by AI: 0 unless AI is configured and the plan includes it."""
    if detected not in ("image", "pdf"):
        return 0
    reader = getattr(request.app.state, "vision_reader", None)
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        if detected == "image":  # photos can only be read by AI
            entitlements.require(conn, tenant_id, "document_reading")
            allowed = True
        else:  # scanned PDFs fall back to "no text found" when AI reading is not available
            allowed = entitlements.load(conn, tenant_id).has("document_reading")
    if reader is None:
        if detected == "image":
            raise UploadRejected("vision_unavailable")
        return 0
    return get_settings().ai_vision_max_pages if allowed else 0


def _read_with_ai(
    request: Request,
    db: Database,
    principal: Principal,
    tenant_id: uuid.UUID,
    extraction: Extraction,
) -> Extraction:
    """Plan, quota and budget checks first; the model call runs with no transaction open; every
    call's usage is recorded (also when it failed)."""
    reader: VisionReader = request.app.state.vision_reader
    budget: Budget = request.app.state.ai_budget
    worst = reader.worst_case(len(extraction.images))
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        ents = entitlements.require(conn, tenant_id, "document_reading")
        spent = conn.execute(
            "select tenant_today, global_today, global_month, tenant_month "
            "from app_private.ai_spend_for(%s)",
            (tenant_id,),
        ).fetchone()
    monthly = ents.limit("ai_usd_month")
    if monthly is not None and float(spent["tenant_month"]) >= monthly:
        raise ApiError(
            409,
            "quota_reached",
            f"This month's AI allowance in the {ents.plan_name} plan is used up. Upload a document "
            "with selectable text, or contact ZUVOORA to upgrade.",
        )
    exceeded = over_budget(
        budget,
        (Decimal(spent["tenant_today"]), Decimal(spent["global_today"]),
         Decimal(spent["global_month"])),
        worst,
    )
    if exceeded:
        log.warning("vision_budget_exhausted scope=%s tenant=%s", exceeded, tenant_id)
        raise ApiError(
            409,
            "ai_budget_reached",
            "Today's AI budget for reading documents is used up. Try again tomorrow, or upload a "
            "document with selectable text.",
        )

    result = reader.read(extraction.images)
    if result.usage:
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            for usage in result.usage:
                conn.execute(
                    "insert into public.usage_events (tenant_id, feature, provider, model, tier, "
                    "prompt_tokens, completion_tokens, cost_usd) "
                    "values (%s, 'document', %s, %s, 'vision', %s, %s, %s)",
                    (tenant_id, usage.provider, usage.model, usage.prompt_tokens,
                     usage.completion_tokens, usage.cost_usd),
                )
    if result.error:
        raise UploadRejected("vision_failed")
    if not result.text:
        raise UploadRejected("no_text")
    return Extraction(
        extraction.detected_type, result.text, extraction.page_count, method="vision"
    )


def _scan_for_malware(request: Request, data: bytes) -> None:
    """Virus scan before anything parses the file (Phase 6, D5). Fails closed when required."""
    scanner: MalwareScanner | None = getattr(request.app.state, "malware_scanner", None)
    if scanner is None:
        if get_settings().malware_scan_required:
            log.error("malware_scan_unavailable kind=not_configured")
            raise _scan_unavailable()
        return
    try:
        result = scanner.scan(data)
    except ScannerUnavailable as exc:
        log.warning("malware_scan_unavailable kind=%s", exc.kind)
        if get_settings().malware_scan_required:
            raise _scan_unavailable() from exc
        return
    if not result.clean:
        raise UploadRejected("malware", signature=result.signature or "unknown")


def _scan_unavailable() -> ApiError:
    return ApiError(
        503,
        "scan_unavailable",
        "Virus scanning is unavailable at the moment, so the file was not accepted. "
        "Please try again in a few minutes.",
    )


def _screen(
    request: Request,
    db: Database,
    principal: Principal,
    tenant_id: uuid.UUID,
    file_name: str,
    data: bytes,
) -> Extraction:
    """Detect type and extract text (by AI for photos/scans); on rejection, audit it and 422."""
    try:
        detected = detect_type(file_name, data)
        _scan_for_malware(request, data)
        pages = _vision_pages(request, db, principal, tenant_id, detected)
        extraction = extract(detected, data, pages)
        if extraction.images:
            extraction = _read_with_ai(request, db, principal, tenant_id, extraction)
        return extraction
    except UploadRejected as rejected:
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            record_audit(
                conn,
                request,
                principal,
                "knowledge.upload_rejected",
                tenant_id=tenant_id,
                target_type="knowledge_document",
                metadata={
                    "reason": rejected.code,
                    "size_bytes": len(data),
                    **(
                        {"signature": str(rejected.details.get("signature"))}
                        if rejected.code == "malware"
                        else {}
                    ),
                },
            )
        raise ApiError(422, f"upload_{rejected.code}", rejected.message) from rejected


def _store_version(
    conn: psycopg.Connection,
    store: ObjectStore,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    file_name: str,
    data: bytes,
    extraction: Extraction,
) -> dict[str, Any]:
    try:
        row = conn.execute(
            """insert into public.knowledge_document_versions
                 (tenant_id, document_id, status, file_name, detected_type, extraction_method,
                  size_bytes, sha256, page_count, extracted_text)
               values (%s, %s, 'extracted', %s, %s, %s, %s, %s, %s, %s)
               returning id, version_no, storage_path""",
            (
                tenant_id,
                document_id,
                file_name,
                extraction.detected_type,
                extraction.method,
                len(data),
                hashlib.sha256(data).hexdigest(),
                extraction.page_count or None,
                extraction.text,
            ),
        ).fetchone()
    except psycopg.errors.InsufficientPrivilege as exc:
        raise forbidden() from exc
    try:
        store.put(row["storage_path"], data)  # still inside the transaction: fails -> rollback
    except StorageError as exc:
        raise ApiError(
            503, "storage_unavailable", "The file could not be stored. Please try again."
        ) from exc
    return row


# ----- routes ----------------------------------------------------------------------------------
@router.get("", response_model=list[DocumentOut])
def list_documents(
    tenant_id: uuid.UUID,
    request: Request,
    include_archived: bool = False,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[DocumentOut]:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        docs = conn.execute(
            f"select {_DOC_COLUMNS} from public.knowledge_documents where tenant_id = %s "  # noqa: S608
            + ("" if include_archived else "and archived_at is null ")
            + "order by created_at, id",
            (tenant_id,),
        ).fetchall()
        grouped: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
        for version in _versions(conn, tenant_id):
            grouped[version["document_id"]].append(version)
    return [_document(d, grouped[d["id"]]) for d in docs]


@router.post("", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    tenant_id: uuid.UUID,
    request: Request,
    title: str = Form(max_length=300),
    file: UploadFile = File(),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> DocumentDetailOut:
    clean_title = _clean_title(title)
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        active = conn.execute(
            "select count(*) as n from public.knowledge_documents "
            "where tenant_id = %s and archived_at is null",
            (tenant_id,),
        ).fetchone()["n"]
        entitlements.require_below_limit(conn, tenant_id, "documents", active)  # plan limit
    if active >= MAX_DOCUMENTS:
        raise ApiError(
            409, "limit_reached", f"A clinic can have at most {MAX_DOCUMENTS} documents."
        )
    file_name, data = _read_upload(file)
    extraction = _screen(request, db, principal, tenant_id, file_name, data)

    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        try:
            doc = conn.execute(
                "insert into public.knowledge_documents (tenant_id, title) values (%s, %s) "
                "returning id",
                (tenant_id, clean_title),
            ).fetchone()
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        version = _store_version(conn, store, tenant_id, doc["id"], file_name, data, extraction)
        record_audit(
            conn,
            request,
            principal,
            "knowledge.uploaded",
            tenant_id=tenant_id,
            target_type="knowledge_document",
            target_id=doc["id"],
            metadata={
                "version_no": version["version_no"],
                "detected_type": extraction.detected_type,
                "extraction_method": extraction.method,
                "size_bytes": len(data),
            },
        )
        return _detail(conn, tenant_id, doc["id"])


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DocumentDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        return _detail(conn, tenant_id, document_id)


@router.post(
    "/{document_id}/versions", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED
)
def upload_version(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> DocumentDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        doc = _load_document(conn, tenant_id, document_id)
        if doc["archived_at"] is not None:
            raise ApiError(409, "archived", "Restore this document before uploading a new version.")
        existing = _versions(conn, tenant_id, document_id)
    if len(existing) >= MAX_VERSIONS:
        raise ApiError(
            409, "limit_reached", f"A document can have at most {MAX_VERSIONS} versions."
        )
    file_name, data = _read_upload(file)
    digest = hashlib.sha256(data).hexdigest()
    latest = max(existing, key=lambda v: v["version_no"], default=None)
    if latest is not None and latest["sha256"] == digest:
        raise ApiError(
            409, "duplicate_version", f"This file is identical to version {latest['version_no']}."
        )
    extraction = _screen(request, db, principal, tenant_id, file_name, data)

    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        try:
            version = _store_version(
                conn, store, tenant_id, document_id, file_name, data, extraction
            )
        except psycopg.errors.CheckViolation as exc:  # archived/removed meanwhile
            raise ApiError(409, "archived", "This document can no longer be changed.") from exc
        record_audit(
            conn,
            request,
            principal,
            "knowledge.version_uploaded",
            tenant_id=tenant_id,
            target_type="knowledge_document",
            target_id=document_id,
            metadata={
                "version_no": version["version_no"],
                "detected_type": extraction.detected_type,
                "extraction_method": extraction.method,
                "size_bytes": len(data),
            },
        )
        return _detail(conn, tenant_id, document_id)


@router.get("/{document_id}/versions/{version_id}", response_model=VersionDetailOut)
def get_version(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> VersionDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        doc = _load_document(conn, tenant_id, document_id)
        row = conn.execute(
            f"select {_VERSION_COLUMNS}, extracted_text from public.knowledge_document_versions "  # noqa: S608
            "where id = %s and document_id = %s and tenant_id = %s",
            (version_id, document_id, tenant_id),
        ).fetchone()
    if row is None:
        raise not_found()
    base = _version(
        {k: v for k, v in row.items() if k != "extracted_text"}, doc["published_version_id"]
    )
    return VersionDetailOut(**base.model_dump(), extracted_text=row["extracted_text"])


def _index_version(
    conn: psycopg.Connection,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    """Split an approved version into retrieval passages (once per version, same transaction)."""
    if conn.execute(
        "select 1 from public.knowledge_chunks where version_id = %s limit 1", (version_id,)
    ).fetchone():
        return
    text = (
        conn.execute(
            "select extracted_text from public.knowledge_document_versions where id = %s",
            (version_id,),
        ).fetchone()["extracted_text"]
        or ""
    )
    with conn.cursor() as cur:
        cur.executemany(
            "insert into public.knowledge_chunks "
            "(tenant_id, document_id, version_id, ordinal, content) values (%s, %s, %s, %s, %s)",
            [
                (tenant_id, document_id, version_id, i, chunk)
                for i, chunk in enumerate(chunk_text(text))
            ],
        )


def _review(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    principal: Principal,
    db: Database,
    *,
    approve: bool,
    note: str | None,
) -> DocumentDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        doc = _load_document(conn, tenant_id, document_id, lock=True)
        if doc["archived_at"] is not None:
            raise ApiError(409, "archived", "Restore this document first.")
        version = conn.execute(
            "select id, version_no, status::text as status from public.knowledge_document_versions "
            "where id = %s and document_id = %s and tenant_id = %s",
            (version_id, document_id, tenant_id),
        ).fetchone()
        if version is None:
            raise not_found()
        if (
            approve
            and version["status"] == "approved"
            and doc["published_version_id"] == version_id
        ):
            return _detail(conn, tenant_id, document_id)  # already live
        allowed = ("extracted", "approved") if approve else ("extracted",)
        if version["status"] not in allowed:
            raise ApiError(
                409, "invalid_state", f"Version {version['version_no']} is {version['status']}."
            )
        try:
            if version["status"] == "extracted":
                conn.execute(
                    "update public.knowledge_document_versions set status = %s, review_note = %s "
                    "where id = %s and document_id = %s and tenant_id = %s",
                    (
                        "approved" if approve else "rejected",
                        note,
                        version_id,
                        document_id,
                        tenant_id,
                    ),
                )
            if approve:
                _index_version(conn, tenant_id, document_id, version_id)
                conn.execute(
                    "update public.knowledge_documents set published_version_id = %s "
                    "where id = %s and tenant_id = %s",
                    (version_id, document_id, tenant_id),
                )
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        except psycopg.errors.CheckViolation as exc:
            raise ApiError(409, "invalid_state", "This version cannot be changed.") from exc
        record_audit(
            conn,
            request,
            principal,
            "knowledge.published" if approve else "knowledge.rejected",
            tenant_id=tenant_id,
            target_type="knowledge_document",
            target_id=document_id,
            metadata={"version_no": version["version_no"]},
        )
        return _detail(conn, tenant_id, document_id)


@router.post("/{document_id}/versions/{version_id}/approve", response_model=DocumentDetailOut)
def approve_version(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DocumentDetailOut:
    """Approve a version after reviewing its extracted text; it becomes the published version."""
    return _review(
        tenant_id, document_id, version_id, request, principal, db, approve=True, note=body.note
    )


@router.post("/{document_id}/versions/{version_id}/reject", response_model=DocumentDetailOut)
def reject_version(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DocumentDetailOut:
    return _review(
        tenant_id, document_id, version_id, request, principal, db, approve=False, note=body.note
    )


def _document_action(path: str, action: str, assignment: str, check) -> None:
    @router.post(
        f"/{{document_id}}/{path}",
        response_model=DocumentDetailOut,
        name=f"{path}_knowledge_document",
    )
    def handler(
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        request: Request,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ) -> DocumentDetailOut:
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            doc = _load_document(conn, tenant_id, document_id, lock=True)
            if check(doc):
                try:
                    conn.execute(
                        f"update public.knowledge_documents set {assignment} "  # noqa: S608
                        "where id = %s and tenant_id = %s",
                        (document_id, tenant_id),
                    )
                except psycopg.errors.InsufficientPrivilege as exc:
                    raise forbidden() from exc
                record_audit(
                    conn,
                    request,
                    principal,
                    f"knowledge.{action}",
                    tenant_id=tenant_id,
                    target_type="knowledge_document",
                    target_id=document_id,
                )
            return _detail(conn, tenant_id, document_id)


_document_action(
    "unpublish",
    "unpublished",
    "published_version_id = null",
    lambda d: d["published_version_id"] is not None,
)
_document_action("archive", "archived", "archived_at = now()", lambda d: d["archived_at"] is None)
_document_action(
    "restore", "restored", "archived_at = null", lambda d: d["archived_at"] is not None
)


@router.patch("/{document_id}", response_model=DocumentDetailOut)
def rename_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    body: RenameIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DocumentDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        doc = _load_document(conn, tenant_id, document_id, lock=True)
        if doc["archived_at"] is not None:
            raise ApiError(409, "archived", "Restore this document first.")
        conn.execute(
            "update public.knowledge_documents set title = %s where id = %s and tenant_id = %s",
            (body.title, document_id, tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "knowledge.renamed",
            tenant_id=tenant_id,
            target_type="knowledge_document",
            target_id=document_id,
        )
        return _detail(conn, tenant_id, document_id)
