"""Appointments for clinic staff (Phase 4d, ADR-036). Front desk only: these are patient details.

Cancelling goes through the provider first; the local status changes only after the provider
confirmed the cancellation. If the outcome is unknown nothing changes here — the provider's
webhook (or the next look) brings the truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.db import Database
from app.deps import get_db, get_principal, record_audit, tenant_transaction
from app.errors import ApiError, not_found
from app.routes.inbox import FRONT_DESK
from app.routes.scheduling import (
    get_provider_factory,
    get_secrets_box,
    open_connection,
    provider_error,
)
from app.security.jwt import Principal
from app.services.scheduling.base import OutcomeUnknown, ProviderFactory, SchedulingError
from app.services.secrets_box import SecretsBox

router = APIRouter(prefix="/tenants/{tenant_id}/appointments", tags=["appointments"])

Status = Literal["booking", "confirmed", "pending", "unknown", "failed", "cancelled", "rescheduled"]


class AppointmentOut(BaseModel):
    id: uuid.UUID
    type_name: str
    status: Status
    start_at: datetime
    end_at: datetime | None
    attendee_name: str
    attendee_email: str
    attendee_phone: str | None
    attendee_time_zone: str
    conversation_id: uuid.UUID | None
    rescheduled_to: uuid.UUID | None
    failure_reason: str | None
    created_at: datetime


_COLUMNS = """id, type_name, status, start_at, end_at, attendee_name, attendee_email,
    attendee_phone, attendee_time_zone, conversation_id, rescheduled_to, failure_reason,
    created_at"""


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    tenant_id: uuid.UUID,
    request: Request,
    view: Literal["upcoming", "past", "all"] = Query(default="upcoming"),
    limit: int = Query(default=100, ge=1, le=300),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[AppointmentOut]:
    where = {
        "upcoming": "start_at >= now() - interval '1 hour' "
        "and status in ('confirmed', 'pending', 'unknown')",
        "past": "not (start_at >= now() - interval '1 hour' "
        "and status in ('confirmed', 'pending', 'unknown')) and status <> 'booking'",
        "all": "status <> 'booking'",
    }[view]
    order = "start_at" if view == "upcoming" else "start_at desc"
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        rows = conn.execute(
            f"select {_COLUMNS} from public.appointments where tenant_id = %s and {where} "  # noqa: S608
            f"order by {order} limit %s",
            (tenant_id, limit),
        ).fetchall()
    return [AppointmentOut(**r) for r in rows]


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> AppointmentOut:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        row = conn.execute(
            "select status, provider_booking_id, connection_id from public.appointments "
            "where id = %s and tenant_id = %s",
            (appointment_id, tenant_id),
        ).fetchone()
        if row is None:
            raise not_found()
        if row["status"] not in ("confirmed", "pending") or not row["provider_booking_id"]:
            raise ApiError(
                409,
                "not_cancellable",
                "Only upcoming confirmed or requested appointments can be cancelled here.",
            )
        provider = open_connection(conn, box, factory, row["connection_id"])
    try:  # the provider first, with no transaction open
        provider.cancel(row["provider_booking_id"], "Cancelled by the clinic")
    except OutcomeUnknown as exc:
        raise ApiError(
            502,
            "cancellation_unconfirmed",
            "The scheduling provider did not confirm the cancellation. Check the booking there; "
            "this list updates when the provider reports it.",
        ) from exc
    except SchedulingError as exc:
        raise provider_error(exc) from exc
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        conn.execute(
            "update public.appointments set status = 'cancelled', "
            "failure_reason = 'cancelled_by_clinic' where id = %s and tenant_id = %s "
            "and status in ('confirmed', 'pending')",
            (appointment_id, tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "appointment.cancelled",
            tenant_id=tenant_id,
            target_type="appointment",
            target_id=appointment_id,
        )
        updated = conn.execute(
            f"select {_COLUMNS} from public.appointments where id = %s",  # noqa: S608
            (appointment_id,),
        ).fetchone()
    return AppointmentOut(**updated)
