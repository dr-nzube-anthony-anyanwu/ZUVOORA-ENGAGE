"""Website domain routes (Phase 2b): register, verify by DNS TXT, remove.

Tenant from the URL path only; owners/admins manage, all members read. The DNS lookup runs
outside any database transaction so no connection is held during network I/O.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.db import Database
from app.deps import (
    ALL_ROLES,
    MANAGER_ROLES,
    get_db,
    get_domain_verifier,
    get_principal,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, forbidden, not_found
from app.schemas import StrictModel
from app.security.jwt import Principal
from app.services.domain_verification import (
    CheckResult,
    DomainVerifier,
    HostnameError,
    normalise_hostname,
    txt_record,
)

router = APIRouter(prefix="/tenants/{tenant_id}/domains", tags=["domains"])

MAX_DOMAINS = 10
_COLUMNS = """id, hostname, verification_status, verification_token, verified_at,
              last_checked_at, last_check_result, created_at, removed_at"""
_INSERT = (
    "insert into public.tenant_domains (tenant_id, hostname) values (%s, %s) "  # noqa: S608
    f"returning {_COLUMNS}"  # constant column list; values are bound parameters
)


class AddDomainIn(StrictModel):
    hostname: str = Field(min_length=1, max_length=300)

    @field_validator("hostname")
    @classmethod
    def _normalise(cls, value: str) -> str:
        try:
            return normalise_hostname(value)
        except HostnameError as exc:
            raise ValueError(str(exc)) from exc


class DnsRecordOut(BaseModel):
    type: Literal["TXT"] = "TXT"
    name: str
    value: str


class DomainOut(BaseModel):
    id: uuid.UUID
    hostname: str
    status: Literal["pending", "verified", "rejected"]
    verified_at: datetime | None
    last_checked_at: datetime | None
    last_check_result: CheckResult | None
    created_at: datetime
    dns_record: DnsRecordOut


def _out(row: dict[str, Any]) -> DomainOut:
    name, value = txt_record(row["hostname"], row["verification_token"])
    return DomainOut(
        id=row["id"], hostname=row["hostname"], status=row["verification_status"],
        verified_at=row["verified_at"], last_checked_at=row["last_checked_at"],
        last_check_result=row["last_check_result"], created_at=row["created_at"],
        dns_record=DnsRecordOut(name=name, value=value),
    )


def _load(conn: psycopg.Connection, tenant_id: uuid.UUID, domain_id: uuid.UUID) -> dict:
    row = conn.execute(
        f"select {_COLUMNS}, extract(epoch from now() - last_checked_at) as since_check "  # noqa: S608
        "from public.tenant_domains where id = %s and tenant_id = %s and removed_at is null",
        (domain_id, tenant_id),
    ).fetchone()
    if row is None:
        raise not_found()
    return row


@router.get("", response_model=list[DomainOut])
def list_domains(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[DomainOut]:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        rows = conn.execute(
            f"select {_COLUMNS} from public.tenant_domains "  # noqa: S608 - constant columns
            "where tenant_id = %s and removed_at is null order by created_at, id",
            (tenant_id,),
        ).fetchall()
    return [_out(r) for r in rows]


@router.post("", response_model=DomainOut, status_code=status.HTTP_201_CREATED)
def add_domain(
    tenant_id: uuid.UUID,
    body: AddDomainIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DomainOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        count = conn.execute(
            "select count(*) as n from public.tenant_domains "
            "where tenant_id = %s and removed_at is null",
            (tenant_id,),
        ).fetchone()["n"]
        if count >= MAX_DOMAINS:
            raise ApiError(
                409, "limit_reached", f"A clinic can register at most {MAX_DOMAINS} domains."
            )
        try:
            with conn.transaction():
                row = conn.execute(
                    _INSERT, (tenant_id, body.hostname)
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise ApiError(409, "already_added", "This domain is already registered.") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        record_audit(conn, request, principal, "domain.added", tenant_id=tenant_id,
                     target_type="domain", target_id=row["id"],
                     metadata={"hostname": row["hostname"]})
        return _out(row)


@router.post("/{domain_id}/verify", response_model=DomainOut)
def verify_domain(
    tenant_id: uuid.UUID,
    domain_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    verifier: DomainVerifier = Depends(get_domain_verifier),
) -> DomainOut:
    cooldown = get_settings().domain_verify_cooldown_seconds
    # 1. Authorise, rate-limit and record the attempt.
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        row = _load(conn, tenant_id, domain_id)
        if row["verification_status"] == "verified":
            return _out(row)
        if row["since_check"] is not None and row["since_check"] < cooldown:
            wait = int(cooldown - float(row["since_check"])) + 1
            raise ApiError(
                429, "too_many_checks", f"Please wait {wait} seconds before checking again."
            )
        conn.execute(
            "update public.tenant_domains set last_checked_at = now(), "
            "check_count = check_count + 1 where id = %s and tenant_id = %s",
            (domain_id, tenant_id),
        )
        hostname, token = row["hostname"], row["verification_token"]

    # 2. DNS lookup with no database transaction open.
    result: CheckResult = verifier.check(hostname, token)

    # 3. Record the outcome (re-authorised: membership could have changed meanwhile).
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        _load(conn, tenant_id, domain_id)
        taken = False
        if result == "verified":
            try:
                with conn.transaction():
                    conn.execute(
                        "update public.tenant_domains set verification_status = 'verified', "
                        "last_check_result = 'verified' where id = %s and tenant_id = %s",
                        (domain_id, tenant_id),
                    )
            except psycopg.errors.UniqueViolation:
                taken = True
        if result != "verified" or taken:
            conn.execute(
                "update public.tenant_domains set last_check_result = %s "
                "where id = %s and tenant_id = %s",
                ("mismatch" if taken else result, domain_id, tenant_id),
            )
        record_audit(
            conn, request, principal,
            "domain.verified" if result == "verified" and not taken
            else "domain.verification_failed",
            tenant_id=tenant_id, target_type="domain", target_id=domain_id,
            metadata={"hostname": hostname, "result": result, "already_verified_elsewhere": taken},
        )
        out = _out(_load(conn, tenant_id, domain_id))
    if taken:  # raised after commit so the attempt and audit event are kept
        raise ApiError(409, "domain_taken",
                       "This domain is already verified by another clinic. Contact support.")
    return out


@router.post("/{domain_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_domain(
    tenant_id: uuid.UUID,
    domain_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> None:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        row = _load(conn, tenant_id, domain_id)
        try:
            conn.execute(
                "update public.tenant_domains set removed_at = now() "
                "where id = %s and tenant_id = %s",
                (domain_id, tenant_id),
            )
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        record_audit(conn, request, principal, "domain.removed", tenant_id=tenant_id,
                     target_type="domain", target_id=domain_id,
                     metadata={"hostname": row["hostname"]})
