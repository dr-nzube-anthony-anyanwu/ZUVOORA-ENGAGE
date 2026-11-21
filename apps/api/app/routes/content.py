"""Clinic content routes (Phase 2a): profile, branches, services and FAQs with draft/publish.

Every route is tenant-scoped from the URL path and re-authorised against the database
(`tenant_transaction`). All members may read drafts; only owners/admins write. The database
enforces the publication invariants (see migration 20261121000001_clinic_content.sql); these
routes add optimistic locking so nobody overwrites or publishes changes they have not seen.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, Query, Request, status
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.content_schemas import (
    BranchContent,
    ContentItemOut,
    CreateContentIn,
    FaqContent,
    ProfileContent,
    PublishIn,
    ServiceContent,
    UpdateDraftIn,
)
from app.db import Database
from app.deps import (
    ALL_ROLES,
    MANAGER_ROLES,
    get_db,
    get_principal,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, forbidden, not_found
from app.security.jwt import Principal

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["clinic content"])

_COLUMNS = (
    "{key} as id, draft, published, revision, published_revision, published_at, "
    "archived_at, updated_at"
)


@dataclass(frozen=True)
class Kind:
    path: str  # URL segment
    table: str  # fixed table name (never user input)
    audit: str  # audit action prefix
    model: type[BaseModel]
    max_items: int = 0  # 0 = singleton (clinic profile)

    @property
    def singleton(self) -> bool:
        return self.max_items == 0

    @property
    def key(self) -> str:
        return "tenant_id" if self.singleton else "id"


PROFILE = Kind("profile", "clinic_profiles", "clinic_profile", ProfileContent)
COLLECTIONS = (
    Kind("branches", "branches", "branch", BranchContent, max_items=50),
    Kind("services", "services", "service", ServiceContent, max_items=200),
    Kind("faqs", "faqs", "faq", FaqContent, max_items=500),
)


def _state(row: dict[str, Any]) -> str:
    if row["archived_at"] is not None:
        return "archived"
    if row["published_revision"] is None:
        return "draft"
    return "published" if row["published_revision"] == row["revision"] else "changes_pending"


def _out(kind: Kind, row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "state": _state(row),
        "draft": kind.model.model_validate(row["draft"]),
        "published": kind.model.model_validate(row["published"]) if row["published"] else None,
    }


def _select(kind: Kind, where: str) -> sql.Composed:
    # S608: every fragment is a constant from this module; identifiers use sql.Identifier.
    return sql.SQL("select " + _COLUMNS + " from {table} where " + where).format(  # noqa: S608
        key=sql.Identifier(kind.key), table=sql.Identifier("public", kind.table)
    )


def _load(conn: psycopg.Connection, kind: Kind, tenant_id: uuid.UUID, item_id: uuid.UUID):
    query = _select(kind, "tenant_id = %s" + ("" if kind.singleton else " and id = %s"))
    params = (tenant_id,) if kind.singleton else (tenant_id, item_id)
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise not_found()
    return row


def _write(
    conn: psycopg.Connection,
    kind: Kind,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    assignment: str,
    params: tuple[Any, ...],
    *,
    expected_revision: int | None = None,
    require_active: bool = True,
) -> dict[str, Any]:
    """Run one guarded UPDATE; translate a miss into 404/409 without leaking other tenants."""
    current = _load(conn, kind, tenant_id, item_id)
    if require_active and current["archived_at"] is not None:
        raise ApiError(409, "archived", "Restore this item before changing it.")
    if expected_revision is not None and current["revision"] != expected_revision:
        raise ApiError(
            409, "revision_conflict",
            "This item changed since you loaded it. Reload to see the latest version.",
        )
    where = "tenant_id = %s" + ("" if kind.singleton else " and id = %s") + " and revision = %s"
    query = sql.SQL(  # constant fragments only; identifiers via sql.Identifier
        "update {table} set " + assignment + " where " + where + " returning " + _COLUMNS  # noqa: S608
    ).format(key=sql.Identifier(kind.key), table=sql.Identifier("public", kind.table))
    keys = (tenant_id,) if kind.singleton else (tenant_id, item_id)
    try:
        row = conn.execute(query, (*params, *keys, current["revision"])).fetchone()
    except psycopg.errors.InsufficientPrivilege as exc:
        raise forbidden() from exc
    except psycopg.errors.CheckViolation as exc:
        raise ApiError(
            409, "invalid_state", "This change is not allowed in the item's state."
        ) from exc
    if row is None:  # concurrent edit between the read and the update
        raise ApiError(409, "revision_conflict", "This item changed while saving. Reload.")
    return row


def _target_dependency(kind: Kind):
    """The row key: the tenant for the singleton profile, else the {item_id} path parameter."""
    if kind.singleton:
        def target(tenant_id: uuid.UUID) -> uuid.UUID:
            return tenant_id
    else:
        def target(item_id: uuid.UUID) -> uuid.UUID:
            return item_id
    return target


def _register_item_actions(kind: Kind, item_path: str) -> None:
    """Draft update, publish and unpublish (shared by collections and the profile)."""
    Model = kind.model  # noqa: N806
    Out = ContentItemOut[Model]  # type: ignore[valid-type]  # noqa: N806
    Target = Depends(_target_dependency(kind))  # noqa: N806

    @router.patch(f"{item_path}/draft", response_model=Out, name=f"update_{kind.audit}_draft")
    def update_draft(
        tenant_id: uuid.UUID,
        body: UpdateDraftIn[Model],  # type: ignore[valid-type]
        request: Request,
        target: uuid.UUID = Target,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            row = _write(
                conn, kind, tenant_id, target, "draft = %s",
                (Jsonb(body.content.model_dump(mode="json")),),
                expected_revision=body.revision,
            )
            record_audit(conn, request, principal, f"{kind.audit}.draft_updated",
                         tenant_id=tenant_id, target_type=kind.audit, target_id=row["id"],
                         metadata={"revision": row["revision"]})
            return _out(kind, row)

    @router.post(f"{item_path}/publish", response_model=Out, name=f"publish_{kind.audit}")
    def publish(
        tenant_id: uuid.UUID,
        body: PublishIn,
        request: Request,
        target: uuid.UUID = Target,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            current = _load(conn, kind, tenant_id, target)
            if current["published_revision"] == body.revision == current["revision"]:
                return _out(kind, current)  # already live; idempotent
            row = _write(conn, kind, tenant_id, target, "published = draft", (),
                         expected_revision=body.revision)
            record_audit(conn, request, principal, f"{kind.audit}.published",
                         tenant_id=tenant_id, target_type=kind.audit, target_id=row["id"],
                         metadata={"revision": row["revision"]})
            return _out(kind, row)

    @router.post(f"{item_path}/unpublish", response_model=Out, name=f"unpublish_{kind.audit}")
    def unpublish(
        tenant_id: uuid.UUID,
        request: Request,
        target: uuid.UUID = Target,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            current = _load(conn, kind, tenant_id, target)
            if current["published"] is None:
                return _out(kind, current)
            row = _write(conn, kind, tenant_id, target, "published = null", ())
            record_audit(conn, request, principal, f"{kind.audit}.unpublished",
                         tenant_id=tenant_id, target_type=kind.audit, target_id=row["id"])
            return _out(kind, row)


# ----- clinic profile (one per tenant) ---------------------------------------------------------
ProfileOut = ContentItemOut[ProfileContent]


@router.get("/profile", response_model=ProfileOut)
def get_profile(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
):
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        return _out(PROFILE, _load(conn, PROFILE, tenant_id, tenant_id))


_register_item_actions(PROFILE, "/profile")


# ----- collections: branches, services, faqs ---------------------------------------------------
def _register_collection(kind: Kind) -> None:
    Model = kind.model  # noqa: N806
    Out = ContentItemOut[Model]  # type: ignore[valid-type]  # noqa: N806
    base = f"/{kind.path}"

    @router.get(base, response_model=list[Out], name=f"list_{kind.path}")
    def list_items(
        tenant_id: uuid.UUID,
        request: Request,
        include_archived: bool = Query(default=False),
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        where = "tenant_id = %s" + ("" if include_archived else " and archived_at is null")
        with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
            rows = conn.execute(
                _select(kind, where) + sql.SQL(" order by created_at, id"), (tenant_id,)
            ).fetchall()
        return [_out(kind, r) for r in rows]

    @router.post(base, response_model=Out, status_code=status.HTTP_201_CREATED,
                 name=f"create_{kind.audit}")
    def create_item(
        tenant_id: uuid.UUID,
        body: CreateContentIn[Model],  # type: ignore[valid-type]
        request: Request,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
            count = conn.execute(
                sql.SQL("select count(*) as n from {} where tenant_id = %s and archived_at is null")
                .format(sql.Identifier("public", kind.table)), (tenant_id,),
            ).fetchone()["n"]
            if count >= kind.max_items:
                raise ApiError(409, "limit_reached",
                               f"A clinic can have at most {kind.max_items} active {kind.path}.")
            try:
                row = conn.execute(
                    sql.SQL("insert into {} (tenant_id, draft) values (%s, %s) returning "  # noqa: S608
                            + _COLUMNS).format(sql.Identifier("public", kind.table),
                                               key=sql.Identifier("id")),
                    (tenant_id, Jsonb(body.content.model_dump(mode="json"))),
                ).fetchone()
            except psycopg.errors.InsufficientPrivilege as exc:
                raise forbidden() from exc
            record_audit(conn, request, principal, f"{kind.audit}.created",
                         tenant_id=tenant_id, target_type=kind.audit, target_id=row["id"])
            return _out(kind, row)

    @router.get(f"{base}/{{item_id}}", response_model=Out, name=f"get_{kind.audit}")
    def get_item(
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        request: Request,
        principal: Principal = Depends(get_principal),
        db: Database = Depends(get_db),
    ):
        with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
            return _out(kind, _load(conn, kind, tenant_id, item_id))

    def _archive_action(action: str, assignment: str, to_archived: bool):
        @router.post(f"{base}/{{item_id}}/{action}", response_model=Out,
                     name=f"{action}_{kind.audit}")
        def handler(
            tenant_id: uuid.UUID,
            item_id: uuid.UUID,
            request: Request,
            principal: Principal = Depends(get_principal),
            db: Database = Depends(get_db),
        ):
            with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
                current = _load(conn, kind, tenant_id, item_id)
                if (current["archived_at"] is not None) == to_archived:  # already there
                    return _out(kind, current)
                row = _write(conn, kind, tenant_id, item_id, assignment, (),
                             require_active=to_archived)
                record_audit(conn, request, principal, f"{kind.audit}.{action}d",
                             tenant_id=tenant_id, target_type=kind.audit, target_id=item_id)
                return _out(kind, row)

        return handler

    _archive_action("archive", "archived_at = now()", to_archived=True)
    _archive_action("restore", "archived_at = null", to_archived=False)
    _register_item_actions(kind, f"{base}/{{item_id}}")


for _kind in COLLECTIONS:
    _register_collection(_kind)
