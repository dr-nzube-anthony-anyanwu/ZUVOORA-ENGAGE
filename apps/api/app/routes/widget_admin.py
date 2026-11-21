"""Widget settings for clinic staff (Phase 3b): view, enable/disable, greeting, rotate key."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.content_schemas import Line
from app.db import Database
from app.deps import (
    ALL_ROLES,
    MANAGER_ROLES,
    get_db,
    get_principal,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, forbidden
from app.schemas import StrictModel
from app.security.jwt import Principal

router = APIRouter(prefix="/tenants/{tenant_id}/widget", tags=["widget settings"])


class WidgetOut(BaseModel):
    public_key: str
    enabled: bool
    greeting: str
    verified_hosts: list[str]


class WidgetUpdateIn(StrictModel):
    enabled: bool | None = None
    greeting: Line | None = Field(default=None, min_length=1, max_length=300)


def _load(conn, tenant_id: uuid.UUID) -> WidgetOut:
    row = conn.execute(
        "select public_key, enabled, greeting from public.widget_configs where tenant_id = %s",
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "not_found", "Resource not found.")
    hosts = [
        r["hostname"]
        for r in conn.execute(
            "select hostname from public.tenant_domains where tenant_id = %s "
            "and verification_status = 'verified' and removed_at is null order by hostname",
            (tenant_id,),
        ).fetchall()
    ]
    return WidgetOut(**row, verified_hosts=hosts)


@router.get("", response_model=WidgetOut)
def get_widget(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> WidgetOut:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        return _load(conn, tenant_id)


@router.patch("", response_model=WidgetOut)
def update_widget(
    tenant_id: uuid.UUID,
    body: WidgetUpdateIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> WidgetOut:
    changes = body.model_dump(exclude_none=True)
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        current = _load(conn, tenant_id)
        if changes.get("enabled") and not current.verified_hosts:
            raise ApiError(
                409,
                "no_verified_domain",
                "Verify at least one website domain before turning the chat on.",
            )
        if changes:
            assignments = ", ".join(f"{k} = %s" for k in changes)  # keys from a fixed model
            row = conn.execute(
                f"update public.widget_configs set {assignments} where tenant_id = %s "  # noqa: S608
                "returning tenant_id",
                (*changes.values(), tenant_id),
            ).fetchone()
            if row is None:
                raise forbidden()
            record_audit(
                conn,
                request,
                principal,
                "widget.updated",
                tenant_id=tenant_id,
                target_type="widget",
                target_id=tenant_id,
                metadata={k: v for k, v in changes.items() if k == "enabled"}
                | ({"greeting_changed": True} if "greeting" in changes else {}),
            )
        return _load(conn, tenant_id)


@router.post("/rotate-key", response_model=WidgetOut)
def rotate_key(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> WidgetOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        conn.execute("select app_private.rotate_widget_key(%s)", (tenant_id,))
        record_audit(
            conn,
            request,
            principal,
            "widget.key_rotated",
            tenant_id=tenant_id,
            target_type="widget",
            target_id=tenant_id,
        )
        return _load(conn, tenant_id)
