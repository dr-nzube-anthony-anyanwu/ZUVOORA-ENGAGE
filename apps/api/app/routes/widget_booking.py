"""Booking from the public widget (Phase 4c, ADR-035).

The rule: a visitor is told "booked" only after the provider confirmed it.
  1. Record the attempt (status 'booking'; its id is the provider reference) and commit.
  2. Re-check that the chosen time is still offered by the provider.
  3. Ask the provider to book (no transaction open).
  4. Record the outcome. Provider refused/unreachable -> 'failed' (nothing booked, say so).
     Outcome unknown (timeout/5xx after sending) -> 'unknown': the visitor is told the clinic
     will confirm, a call-back request is created, and a job reconciles with the provider.
All database work runs as the widget role, limited to the visitor's own conversation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.content_schemas import Line
from app.db import Database
from app.deps import get_db
from app.errors import ApiError
from app.routes.scheduling import PURPOSE, get_provider_factory, get_secrets_box
from app.routes.widget_public import (
    _client_ip,
    _conversation,
    _hit,
    _open_conversation,
    get_widget_tokens,
)
from app.schemas import StrictModel
from app.services.scheduling.base import (
    Attendee,
    CredentialRejected,
    OutcomeUnknown,
    ProviderFactory,
    ProviderRejected,
    SchedulingError,
    SchedulingProvider,
)
from app.services.secrets_box import Sealed, SecretsBox, SecretsBoxError
from app.services.widget_tokens import ConversationToken, WidgetTokens

router = APIRouter(prefix="/api/v1/public/widget/booking", tags=["public widget"])

SLOT_HORIZON_DAYS = 14
MIN_NOTICE = timedelta(minutes=30)
MAX_SLOTS = 120
MAX_BOOKINGS_PER_CONVERSATION = 3
UNAVAILABLE = (
    "Online booking is not available right now. You can ask the clinic team to contact you."
)
SLOT_GONE = "Sorry, that time is no longer available. Please choose another time."
UNCONFIRMED = (
    "We could not confirm your booking with the clinic's calendar just now. Nothing is confirmed "
    "yet: the clinic team has your details and will contact you to confirm."
)


# ----- models ------------------------------------------------------------------------------------
class TokenIn(StrictModel):
    token: str = Field(min_length=20, max_length=2000)


class TypeOut(BaseModel):
    id: uuid.UUID
    name: str
    duration_minutes: int
    requires_confirmation: bool


class OptionsOut(BaseModel):
    available: bool
    types: list[TypeOut]


class SlotsIn(TokenIn):
    appointment_type_id: uuid.UUID


class SlotsOut(BaseModel):
    slots: list[datetime]


class BookIn(SlotsIn):
    start: datetime
    name: Line = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30, pattern=r"^\+?[0-9][0-9 ()\-]{4,28}$")
    time_zone: str = Field(min_length=1, max_length=64)
    consent: bool

    @field_validator("consent")
    @classmethod
    def _must_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("consent is required to book")
        return value

    @field_validator("time_zone")
    @classmethod
    def _zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown time zone") from exc
        return value

    @field_validator("start")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("start must include a time zone")
        return value.astimezone(UTC)


class BookOut(BaseModel):
    status: Literal["confirmed", "pending", "unconfirmed"]
    message: str
    start: datetime


# ----- helpers -----------------------------------------------------------------------------------
def _type_and_provider(
    conn: psycopg.Connection, box: SecretsBox, factory: ProviderFactory, type_id: uuid.UUID
) -> tuple[dict, SchedulingProvider]:
    row = conn.execute(
        "select t.id, t.name, t.duration_minutes, t.provider_event_type_id, t.connection_id, "
        "c.provider from public.appointment_types t "
        "join public.scheduling_connections c on c.id = t.connection_id where t.id = %s",
        (type_id,),
    ).fetchone()
    if row is None:  # not this clinic's, disabled, or no active connection (RLS)
        raise ApiError(404, "not_found", "This appointment type is not available.")
    secret = conn.execute(
        "select tenant_id, ciphertext, key_id from app_private.scheduling_credential(%s)",
        (row["connection_id"],),
    ).fetchone()
    if secret is None:
        raise ApiError(503, "booking_unavailable", UNAVAILABLE)
    try:
        key = box.open(
            Sealed(bytes(secret["ciphertext"]), secret["key_id"]),
            purpose=PURPOSE,
            tenant_id=secret["tenant_id"],
            record_id=row["connection_id"],
        )
    except SecretsBoxError as exc:
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    return row, factory(row["provider"], key)


def _report_rejected_key(db: Database, ctx: ConversationToken, connection_id: uuid.UUID) -> None:
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        conn.execute("select app_private.widget_report_credential_rejected(%s)", (connection_id,))


def _when(moment: datetime, zone: str) -> str:
    local = moment.astimezone(ZoneInfo(zone))
    return local.strftime("%A %d %B %Y at %H:%M") + f" ({zone})"


def _finish(
    db: Database,
    ctx: ConversationToken,
    appointment_id: uuid.UUID,
    status: str,
    *,
    provider_booking_id: str | None = None,
    end: datetime | None = None,
    reason: str | None = None,
    message: str | None = None,
) -> None:
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        conn.execute(
            "update public.appointments set status = %s, provider_booking_id = %s, end_at = %s, "
            "failure_reason = %s where id = %s",
            (status, provider_booking_id, end, reason, appointment_id),
        )
        if message:
            conn.execute(
                "insert into public.messages (tenant_id, conversation_id, role, content, "
                "answer_source) values (%s, %s, 'system', %s, 'booking')",
                (ctx.tenant_id, ctx.conversation_id, message),
            )


# ----- routes ------------------------------------------------------------------------------------
@router.post("/options", response_model=OptionsOut)
def booking_options(
    body: TokenIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> OptionsOut:
    ctx = _conversation(tokens, body.token, request)
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        _hit(conn, tokens, request, "booking_ip", _client_ip(request))
        _open_conversation(conn)
        rows = conn.execute(
            "select id, name, duration_minutes, requires_confirmation "
            "from public.appointment_types order by sort_order, name"
        ).fetchall()
    return OptionsOut(available=bool(rows), types=[TypeOut(**r) for r in rows])


@router.post("/slots", response_model=SlotsOut)
def booking_slots(
    body: SlotsIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> SlotsOut:
    ctx = _conversation(tokens, body.token, request)
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        _hit(conn, tokens, request, "booking_ip", _client_ip(request))
        _open_conversation(conn)
        kind, provider = _type_and_provider(conn, box, factory, body.appointment_type_id)
    now = datetime.now(UTC)
    try:  # no transaction open during the provider call
        slots = provider.slots(
            kind["provider_event_type_id"],
            now + MIN_NOTICE,
            now + timedelta(days=SLOT_HORIZON_DAYS),
        )
    except CredentialRejected as exc:
        _report_rejected_key(db, ctx, kind["connection_id"])
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    except SchedulingError as exc:
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    return SlotsOut(slots=[s.start for s in slots if s.start >= now + MIN_NOTICE][:MAX_SLOTS])


@router.post("", response_model=BookOut, responses={202: {"model": BookOut}})
def book(
    body: BookIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> BookOut | JSONResponse:
    ctx = _conversation(tokens, body.token, request)
    appointment_id = uuid.uuid4()
    # 1. Record the attempt first (its id is the provider reference) and commit.
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        _hit(conn, tokens, request, "booking_create_ip", _client_ip(request))
        _hit(conn, tokens, request, "booking_create_conversation", str(ctx.conversation_id))
        conversation = _open_conversation(conn)
        if conversation["status"] == "closed":
            raise ApiError(409, "conversation_closed", "This conversation has been closed.")
        kind, provider = _type_and_provider(conn, box, factory, body.appointment_type_id)
        active = conn.execute(
            "select count(*) as n from public.appointments "
            "where status in ('booking', 'confirmed', 'pending', 'unknown')"
        ).fetchone()["n"]
        if active >= MAX_BOOKINGS_PER_CONVERSATION:
            raise ApiError(
                409,
                "booking_limit",
                "This chat already has several bookings. Please contact the clinic.",
            )
        if body.start < datetime.now(UTC) + MIN_NOTICE:
            raise ApiError(409, "slot_unavailable", SLOT_GONE)
        try:
            with conn.transaction():
                conn.execute(
                    "insert into public.appointments (id, tenant_id, connection_id, "
                    "appointment_type_id, conversation_id, provider, provider_event_type_id, "
                    "type_name, start_at, attendee_name, attendee_email, attendee_phone, "
                    "attendee_time_zone, consent_given) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)",
                    (
                        appointment_id,
                        ctx.tenant_id,
                        kind["connection_id"],
                        kind["id"],
                        ctx.conversation_id,
                        kind["provider"],
                        kind["provider_event_type_id"],
                        kind["name"],
                        body.start,
                        body.name,
                        str(body.email),
                        body.phone,
                        body.time_zone,
                    ),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise ApiError(
                409, "booking_in_progress", "A booking is already in progress in this chat."
            ) from exc

    # 2. Re-check the time is still offered (nothing has been sent to the provider yet).
    try:
        still_free = any(
            s.start == body.start
            for s in provider.slots(
                kind["provider_event_type_id"],
                body.start - timedelta(minutes=1),
                body.start + timedelta(minutes=1),
            )
        )
    except CredentialRejected as exc:
        _finish(db, ctx, appointment_id, "failed", reason="credential_rejected")
        _report_rejected_key(db, ctx, kind["connection_id"])
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    except SchedulingError as exc:
        _finish(db, ctx, appointment_id, "failed", reason=f"revalidate:{exc.kind}"[:100])
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    if not still_free:
        _finish(db, ctx, appointment_id, "failed", reason="slot_unavailable")
        raise ApiError(409, "slot_unavailable", SLOT_GONE)

    # 3. Book (no transaction open). 4. Record exactly what happened.
    attendee = Attendee(body.name, str(body.email), body.time_zone, body.phone)
    when = _when(body.start, body.time_zone)
    try:
        booking = provider.book(
            kind["provider_event_type_id"], body.start, attendee, str(appointment_id)
        )
    except OutcomeUnknown:
        _unconfirmed(db, ctx, appointment_id, body)
        return JSONResponse(
            status_code=202,
            content=BookOut(status="unconfirmed", message=UNCONFIRMED, start=body.start).model_dump(
                mode="json"
            ),
        )
    except ProviderRejected as exc:
        _finish(db, ctx, appointment_id, "failed", reason="provider_rejected")
        raise ApiError(409, "slot_unavailable", SLOT_GONE) from exc
    except CredentialRejected as exc:
        _finish(db, ctx, appointment_id, "failed", reason="credential_rejected")
        _report_rejected_key(db, ctx, kind["connection_id"])
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc
    except SchedulingError as exc:  # unavailable: the request had no effect
        _finish(db, ctx, appointment_id, "failed", reason=f"provider:{exc.kind}"[:100])
        raise ApiError(503, "booking_unavailable", UNAVAILABLE) from exc

    if booking.status not in ("confirmed", "pending"):
        _finish(db, ctx, appointment_id, "failed", reason=f"provider_status:{booking.status}")
        raise ApiError(409, "slot_unavailable", SLOT_GONE)
    if booking.status == "confirmed":
        message = f"Booked: {kind['name']} on {when}. A confirmation email is on its way."
    else:
        message = (
            f"Requested: {kind['name']} on {when}. The clinic will confirm this booking; "
            "you will receive an email."
        )
    _finish(
        db,
        ctx,
        appointment_id,
        booking.status,
        provider_booking_id=booking.provider_booking_id,
        end=booking.end,
        message=message,
    )
    return BookOut(status=booking.status, message=message, start=body.start)


def _unconfirmed(
    db: Database, ctx: ConversationToken, appointment_id: uuid.UUID, body: BookIn
) -> None:
    """Outcome unknown: never claim success. Hand over to the clinic and reconcile."""
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        conn.execute(
            "update public.appointments set status = 'unknown', failure_reason = 'outcome_unknown' "
            "where id = %s",
            (appointment_id,),
        )
        try:
            with conn.transaction():
                conn.execute(
                    "insert into public.handover_requests (tenant_id, conversation_id, "
                    "contact_name, contact_phone, contact_email, note, consent_given) "
                    "values (%s, %s, %s, %s, %s, %s, true)",
                    (
                        ctx.tenant_id,
                        ctx.conversation_id,
                        body.name,
                        body.phone,
                        str(body.email),
                        "Online booking could not be confirmed automatically. Please confirm the "
                        "appointment with the patient.",
                    ),
                )
            conn.execute("update public.conversations set status = 'handover_requested'")
        except psycopg.errors.UniqueViolation:
            pass  # a call-back request already exists for this conversation
        conn.execute(
            "insert into public.messages (tenant_id, conversation_id, role, content, "
            "answer_source) values (%s, %s, 'system', %s, 'booking')",
            (ctx.tenant_id, ctx.conversation_id, UNCONFIRMED),
        )
