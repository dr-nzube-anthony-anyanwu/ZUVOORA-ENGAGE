"""Demo and pilot requests from the public website (design track D3, ADR-042).

* `POST /api/v1/public/demo-requests` — anonymous. Minimal business-contact fields, no health
  information. Rate limited per IP, per email address and globally; a hidden honeypot field
  silently discards bot submissions. Stored through `app_private.submit_demo_request()` as the
  restricted public role; visitors can never read anything back.
* `GET/PATCH /api/v1/platform/demo-requests` — MFA platform admins only; status changes audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.content_schemas import Line, Text
from app.db import Database
from app.deps import get_db, get_principal, platform_transaction, record_audit
from app.errors import ApiError, log_security_event, not_found
from app.routes.widget_public import _client_ip, get_widget_tokens
from app.schemas import StrictModel
from app.security.jwt import Principal
from app.services.widget_tokens import WidgetTokens

public_router = APIRouter(prefix="/api/v1/public/demo-requests", tags=["demo-requests"])
platform_router = APIRouter(prefix="/platform/demo-requests", tags=["platform"])

Interest = Literal["demo", "pilot", "pricing", "accessibility", "other"]
Status = Literal["new", "contacted", "closed"]

# (window seconds, max hits). Per-IP limiting needs the real visitor address: requests arrive via
# the dashboard server, which forwards it; uvicorn honours it only for trusted proxies (Phase 6).
LIMITS = {
    "demo_ip": (3600, 10),
    "demo_email": (86400, 3),
    "demo_all": (3600, 60),
}


class DemoRequestIn(StrictModel):
    name: Line = Field(min_length=2, max_length=120)
    role: Line | None = Field(default=None, max_length=80)
    clinic_name: Line = Field(min_length=2, max_length=160)
    city: Line | None = Field(default=None, max_length=80)
    country: Line | None = Field(default=None, max_length=80)
    email: EmailStr = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=30, pattern=r"^$|^[0-9+() .-]{6,30}$")
    interest: Interest = "demo"
    message: Text | None = Field(default=None, max_length=1000)
    consent: bool
    website: str = Field(default="", max_length=200)  # honeypot: humans never see or fill it


class Received(BaseModel):
    status: Literal["received"] = "received"


class DemoRequestOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str | None
    clinic_name: str
    city: str | None
    country: str | None
    email: str
    phone: str | None
    interest: Interest
    message: str | None
    status: Status
    created_at: datetime
    updated_at: datetime


class StatusIn(StrictModel):
    status: Status


def _limit(conn, tokens: WidgetTokens, request: Request, kind: str, value: str) -> None:
    window, limit = LIMITS[kind]
    allowed = conn.execute(
        "select app_private.rate_limit_hit(%s, %s, %s) as ok",
        (tokens.bucket(kind, value), window, limit),
    ).fetchone()["ok"]
    if not allowed:
        log_security_event(request, "demo_request_rate_limited", kind=kind)
        raise ApiError(
            429, "rate_limited",
            "We have received several requests already. Please try again later.",
        )


@public_router.post("", response_model=Received, status_code=status.HTTP_202_ACCEPTED)
def submit_demo_request(
    body: DemoRequestIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> Received:
    if not body.consent:
        raise ApiError(422, "consent_required", "Please agree to be contacted about your request.")
    with db.widget_transaction() as conn:
        _limit(conn, tokens, request, "demo_ip", _client_ip(request))
        if body.website:  # a bot filled the hidden field: accept silently, store nothing
            log_security_event(request, "demo_request_honeypot")
            return Received()
        _limit(conn, tokens, request, "demo_email", str(body.email).lower())
        _limit(conn, tokens, request, "demo_all", "all")
        conn.execute(
            "select app_private.submit_demo_request(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (body.name, body.role, body.clinic_name, body.city, body.country, str(body.email),
             body.phone or None, body.interest, body.message, body.consent),
        )
    return Received()


_COLUMNS = ("id, name, role, clinic_name, city, country, email, phone, interest, message, status, "
            "created_at, updated_at")


@platform_router.get("", response_model=list[DemoRequestOut])
def list_demo_requests(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[DemoRequestOut]:
    with platform_transaction(request, db, principal) as conn:
        rows = conn.execute(
            f"select {_COLUMNS} from public.demo_requests "  # noqa: S608 - constant columns
            "order by (status = 'new') desc, created_at desc limit 500"
        ).fetchall()
    return [DemoRequestOut(**r) for r in rows]


@platform_router.patch("/{request_id}", response_model=DemoRequestOut)
def update_demo_request(
    request_id: uuid.UUID,
    body: StatusIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> DemoRequestOut:
    with platform_transaction(request, db, principal) as conn:
        row = conn.execute(
            f"update public.demo_requests set status = %s where id = %s returning {_COLUMNS}",  # noqa: S608
            (body.status, request_id),
        ).fetchone()
        if row is None:
            raise not_found()
        record_audit(conn, request, principal, "demo_request.status_changed",
                     target_type="demo_request", target_id=request_id,
                     metadata={"status": body.status})
    return DemoRequestOut(**row)
