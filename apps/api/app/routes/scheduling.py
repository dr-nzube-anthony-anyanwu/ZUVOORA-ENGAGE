"""Scheduling connection and appointment types for clinic staff (Phase 4b, ADR-034).

Owners/admins connect a provider account with an API key. The key is verified with the provider
first, encrypted (bound to tenant + connection id) and stored; it is never returned. All provider
calls happen with no database transaction open.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.config import get_settings
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
from app.errors import ApiError, not_found
from app.schemas import StrictModel
from app.security.jwt import Principal
from app.services import entitlements
from app.services.scheduling import webhooks
from app.services.scheduling.base import (
    CredentialRejected,
    EventType,
    ProviderFactory,
    ProviderRejected,
    SchedulingError,
    SchedulingProvider,
)
from app.services.secrets_box import Sealed, SecretsBox, SecretsBoxError

router = APIRouter(prefix="/tenants/{tenant_id}/scheduling", tags=["scheduling"])

PURPOSE = "scheduling"
KEY_PATTERNS = {
    "calcom": re.compile(r"^cal_[A-Za-z0-9_-]{8,250}$"),
    # Calendly personal access tokens are JWT-like (header.payload.signature).
    "calendly": re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$"),
}
PROVIDER_NAMES = {"calcom": "Cal.com", "calendly": "Calendly"}
MAX_TYPES = 20


# ----- dependencies ------------------------------------------------------------------------------
def get_secrets_box(request: Request) -> SecretsBox:
    box = getattr(request.app.state, "secrets_box", None)
    if box is None:
        raise ApiError(503, "integrations_unavailable", "Integrations are not configured.")
    return box


def get_provider_factory(request: Request) -> ProviderFactory:
    factory = getattr(request.app.state, "scheduling_providers", None)
    if factory is None:
        raise ApiError(503, "integrations_unavailable", "Integrations are not configured.")
    return factory


def provider_error(exc: SchedulingError) -> ApiError:
    if isinstance(exc, CredentialRejected):
        return ApiError(
            422,
            "credential_rejected",
            "The scheduling provider did not accept the clinic's API key. Connect again with a "
            "valid key.",
        )
    if isinstance(exc, ProviderRejected):
        return ApiError(502, "provider_rejected", "The scheduling provider refused the request.")
    return ApiError(
        503,
        "provider_unavailable",
        "The scheduling provider is not reachable right now. Please try again.",
    )


def open_connection(
    conn: psycopg.Connection, box: SecretsBox, factory: ProviderFactory, connection_id: uuid.UUID
) -> SchedulingProvider:
    """Decrypt a connection's credential (the database checks the caller) and build its adapter."""
    row = conn.execute(
        "select tenant_id, provider, ciphertext, key_id from app_private.scheduling_credential(%s)",
        (connection_id,),
    ).fetchone()
    if row is None:
        raise ApiError(409, "not_connected", "No scheduling account is connected.")
    try:
        secret = box.open(
            Sealed(bytes(row["ciphertext"]), row["key_id"]),
            purpose=PURPOSE,
            tenant_id=row["tenant_id"],
            record_id=connection_id,
        )
    except SecretsBoxError as exc:
        raise ApiError(
            409,
            "credential_unreadable",
            "The stored scheduling key cannot be used. Please connect the account again.",
        ) from exc
    return factory(row["provider"], secret)


# ----- models ------------------------------------------------------------------------------------
class ConnectionOut(BaseModel):
    id: uuid.UUID
    provider: Literal["calcom", "calendly"]
    status: Literal["active", "failing"]
    account_label: str | None
    account_time_zone: str | None
    credential_hint: str | None
    connected_at: datetime
    last_verified_at: datetime | None
    last_error: str | None
    webhook_configured_at: datetime | None = None
    provider_webhook_id: str | None = None
    reminder_2h: bool = False


class AppointmentTypeOut(BaseModel):
    id: uuid.UUID
    provider_event_type_id: str
    name: str
    duration_minutes: int
    requires_confirmation: bool
    enabled: bool
    sort_order: int


class SchedulingOut(BaseModel):
    connection: ConnectionOut | None
    appointment_types: list[AppointmentTypeOut]


class ConnectIn(StrictModel):
    provider: Literal["calcom", "calendly"]
    api_key: SecretStr = Field(min_length=10, max_length=3000)


class ProviderEventTypeOut(BaseModel):
    id: str
    name: str
    duration_minutes: int
    requires_confirmation: bool
    hidden: bool
    offered: bool


class OfferIn(StrictModel):
    provider_event_type_id: str = Field(pattern=r"^[A-Za-z0-9_.:/-]{1,200}$")
    name: Line | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool = True


class OffersIn(StrictModel):
    items: list[OfferIn] = Field(max_length=MAX_TYPES)

    @field_validator("items")
    @classmethod
    def _unique(cls, items: list[OfferIn]) -> list[OfferIn]:
        ids = [i.provider_event_type_id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("each appointment type can be listed once")
        return items


# ----- helpers -----------------------------------------------------------------------------------
_CONNECTION_COLUMNS = """id, provider, status, account_label, account_time_zone, credential_hint,
    connected_at, last_verified_at, last_error, webhook_configured_at, provider_webhook_id,
    reminder_2h"""


def _live_connection(conn: psycopg.Connection, tenant_id: uuid.UUID) -> dict | None:
    return conn.execute(
        f"select {_CONNECTION_COLUMNS} from public.scheduling_connections "  # noqa: S608
        "where tenant_id = %s and status <> 'disconnected'",
        (tenant_id,),
    ).fetchone()


def _load(conn: psycopg.Connection, tenant_id: uuid.UUID) -> SchedulingOut:
    connection = _live_connection(conn, tenant_id)
    types = []
    if connection:
        types = conn.execute(
            "select id, provider_event_type_id, name, duration_minutes, requires_confirmation, "
            "enabled, sort_order from public.appointment_types where connection_id = %s "
            "order by sort_order, name",
            (connection["id"],),
        ).fetchall()
    return SchedulingOut(
        connection=ConnectionOut(**connection) if connection else None,
        appointment_types=[AppointmentTypeOut(**t) for t in types],
    )


def _provider_types(
    db: Database,
    request: Request,
    principal: Principal,
    tenant_id: uuid.UUID,
    box: SecretsBox,
    factory: ProviderFactory,
) -> tuple[uuid.UUID, list[EventType]]:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        entitlements.require(conn, tenant_id, "booking")
        connection = _live_connection(conn, tenant_id)
        if connection is None:
            raise ApiError(409, "not_connected", "No scheduling account is connected.")
        provider = open_connection(conn, box, factory, connection["id"])
    try:
        types = provider.event_types()  # network call, no transaction open
    except CredentialRejected as exc:
        _mark_failing(db, request, principal, tenant_id, connection["id"], exc.kind)
        raise provider_error(exc) from exc
    except SchedulingError as exc:
        raise provider_error(exc) from exc
    return connection["id"], types


def _mark_failing(
    db: Database,
    request: Request,
    principal: Principal,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    kind: str,
) -> None:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        conn.execute(
            "update public.scheduling_connections set status = 'failing', last_error = %s "
            "where id = %s and tenant_id = %s and status <> 'disconnected'",
            (f"credential_rejected:{kind}"[:200], connection_id, tenant_id),
        )


# ----- routes ------------------------------------------------------------------------------------
@router.get("", response_model=SchedulingOut)
def get_scheduling(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> SchedulingOut:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, _):
        return _load(conn, tenant_id)


@router.post("/connect", response_model=SchedulingOut)
def connect(
    tenant_id: uuid.UUID,
    body: ConnectIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> SchedulingOut:
    key = body.api_key.get_secret_value().strip()
    if not KEY_PATTERNS[body.provider].match(key):
        raise ApiError(
            422,
            "invalid_key_format",
            f"That does not look like a {PROVIDER_NAMES[body.provider]} API key.",
        )
    # 1. Authorise before touching the provider.
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        entitlements.require(conn, tenant_id, "booking")
        if _live_connection(conn, tenant_id):
            raise ApiError(
                409,
                "already_connected",
                "A scheduling account is already connected. Disconnect it first.",
            )
    # 2. Verify the key with the provider (no transaction open).
    try:
        account = factory(body.provider, key).account()
    except SchedulingError as exc:
        raise provider_error(exc) from exc
    # 3. Store it encrypted and bound to this clinic and connection.
    connection_id = uuid.uuid4()
    sealed = box.seal(key, purpose=PURPOSE, tenant_id=tenant_id, record_id=connection_id)
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        try:
            with conn.transaction():
                conn.execute(
                    "insert into public.scheduling_connections (id, tenant_id, provider, "
                    "account_label, account_time_zone, credential_ciphertext, credential_key_id, "
                    "credential_hint, last_verified_at) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, now())",
                    (
                        connection_id,
                        tenant_id,
                        body.provider,
                        account.label,
                        account.time_zone,
                        sealed.ciphertext,
                        sealed.key_id,
                        key[-4:],
                    ),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise ApiError(
                409, "already_connected", "A scheduling account is already connected."
            ) from exc
        record_audit(
            conn,
            request,
            principal,
            "scheduling.connected",
            tenant_id=tenant_id,
            target_type="scheduling_connection",
            target_id=connection_id,
            metadata={"provider": body.provider, "account": account.label},
        )
        return _load(conn, tenant_id)


@router.post("/disconnect", response_model=SchedulingOut)
def disconnect(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> SchedulingOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        connection = _live_connection(conn, tenant_id)
        if connection is None:
            raise not_found()
        conn.execute(
            "update public.scheduling_connections set status = 'disconnected' "
            "where id = %s and tenant_id = %s",
            (connection["id"], tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "scheduling.disconnected",
            tenant_id=tenant_id,
            target_type="scheduling_connection",
            target_id=connection["id"],
            metadata={"provider": connection["provider"]},
        )
        return _load(conn, tenant_id)


@router.get("/provider-event-types", response_model=list[ProviderEventTypeOut])
def provider_event_types(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> list[ProviderEventTypeOut]:
    connection_id, types = _provider_types(db, request, principal, tenant_id, box, factory)
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        offered = {
            r["provider_event_type_id"]
            for r in conn.execute(
                "select provider_event_type_id from public.appointment_types "
                "where connection_id = %s and enabled",
                (connection_id,),
            ).fetchall()
        }
    return [
        ProviderEventTypeOut(
            id=t.id,
            name=t.name,
            duration_minutes=t.duration_minutes,
            requires_confirmation=t.requires_confirmation,
            hidden=t.hidden,
            offered=t.id in offered,
        )
        for t in types
    ]


@router.put("/appointment-types", response_model=SchedulingOut)
def set_appointment_types(
    tenant_id: uuid.UUID,
    body: OffersIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> SchedulingOut:
    connection_id, types = _provider_types(db, request, principal, tenant_id, box, factory)
    by_id = {t.id: t for t in types}
    unknown = [
        i.provider_event_type_id for i in body.items if i.provider_event_type_id not in by_id
    ]
    if unknown:
        raise ApiError(
            422,
            "unknown_event_type",
            "Some appointment types no longer exist in the scheduling account.",
        )
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        if _live_connection(conn, tenant_id) is None:
            raise ApiError(409, "not_connected", "No scheduling account is connected.")
        keep = [i.provider_event_type_id for i in body.items]
        conn.execute(
            "delete from public.appointment_types where connection_id = %s and tenant_id = %s "
            "and not (provider_event_type_id = any(%s))",
            (connection_id, tenant_id, keep),
        )
        for order, item in enumerate(body.items):
            source = by_id[item.provider_event_type_id]
            conn.execute(
                "insert into public.appointment_types (tenant_id, connection_id, "
                "provider_event_type_id, name, duration_minutes, requires_confirmation, enabled, "
                "sort_order) values (%s, %s, %s, %s, %s, %s, %s, %s) "
                "on conflict (connection_id, provider_event_type_id) do update set "
                "name = excluded.name, duration_minutes = excluded.duration_minutes, "
                "requires_confirmation = excluded.requires_confirmation, "
                "enabled = excluded.enabled, sort_order = excluded.sort_order",
                (
                    tenant_id,
                    connection_id,
                    source.id,
                    item.name or source.name,
                    source.duration_minutes,
                    source.requires_confirmation,
                    item.enabled,
                    order,
                ),
            )
        record_audit(
            conn,
            request,
            principal,
            "scheduling.appointment_types_updated",
            tenant_id=tenant_id,
            target_type="scheduling_connection",
            target_id=connection_id,
            metadata={"offered": [i.provider_event_type_id for i in body.items if i.enabled]},
        )
        return _load(conn, tenant_id)


# ----- Phase 4d: booking updates (webhook) and reminder settings --------------------------------
# Events each provider is asked to send (Calendly reports reschedules as cancel + create).
PROVIDER_EVENTS = {"calcom": webhooks.TRIGGERS, "calendly": ("invitee.created", "invitee.canceled")}


class WebhookOut(BaseModel):
    mode: Literal["automatic", "manual"]
    subscriber_url: str
    triggers: list[str]
    # Only in manual mode, shown once so the owner can paste it into Cal.com.
    secret: str | None = None


class SettingsIn(StrictModel):
    reminder_2h: bool


def _subscriber_url(provider: str, connection_id: uuid.UUID) -> str:
    base = (get_settings().public_api_url or "").rstrip("/") or "http://127.0.0.1:8073"
    return f"{base}/api/v1/webhooks/{provider}/{connection_id}"


@router.post("/webhook", response_model=WebhookOut)
def configure_webhook(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    factory: ProviderFactory = Depends(get_provider_factory),
) -> WebhookOut:
    """Create (or rotate) the connection's webhook secret and register it with the provider.

    With a public https API URL the webhook is created in Cal.com automatically; otherwise the
    owner adds it by hand with the URL and secret returned once.
    """
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        entitlements.require(conn, tenant_id, "booking")
        connection = _live_connection(conn, tenant_id)
        if connection is None:
            raise ApiError(409, "not_connected", "No scheduling account is connected.")
        provider = open_connection(conn, box, factory, connection["id"])
    connection_id = connection["id"]
    url = _subscriber_url(connection["provider"], connection_id)
    secret = secrets.token_urlsafe(32)
    automatic = url.startswith("https://")
    provider_webhook_id: str | None = None
    if automatic:  # provider calls with no transaction open
        try:
            if connection["provider_webhook_id"]:
                try:
                    provider.delete_webhook(connection["provider_webhook_id"])
                except ProviderRejected:
                    pass  # already removed in Cal.com
            provider_webhook_id = provider.create_webhook(url, webhooks.TRIGGERS, secret)
        except SchedulingError as exc:
            raise provider_error(exc) from exc
    sealed = box.seal(
        secret,
        purpose=f"{connection['provider']}_webhook",
        tenant_id=tenant_id,
        record_id=connection_id,
    )
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        conn.execute(
            "update public.scheduling_connections set webhook_secret_ciphertext = %s, "
            "webhook_key_id = %s, provider_webhook_id = %s where id = %s and tenant_id = %s",
            (sealed.ciphertext, sealed.key_id, provider_webhook_id, connection_id, tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "scheduling.webhook_configured",
            tenant_id=tenant_id,
            target_type="scheduling_connection",
            target_id=connection_id,
            metadata={"mode": "automatic" if automatic else "manual"},
        )
    return WebhookOut(
        mode="automatic" if automatic else "manual",
        subscriber_url=url,
        triggers=list(PROVIDER_EVENTS[connection["provider"]]),
        secret=None if automatic else secret,
    )


@router.patch("", response_model=SchedulingOut)
def update_settings(
    tenant_id: uuid.UUID,
    body: SettingsIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> SchedulingOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        entitlements.require(conn, tenant_id, "reminders")
        connection = _live_connection(conn, tenant_id)
        if connection is None:
            raise ApiError(409, "not_connected", "No scheduling account is connected.")
        conn.execute(
            "update public.scheduling_connections set reminder_2h = %s where id = %s "
            "and tenant_id = %s",
            (body.reminder_2h, connection["id"], tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "scheduling.settings_updated",
            tenant_id=tenant_id,
            target_type="scheduling_connection",
            target_id=connection["id"],
            metadata={"reminder_2h": body.reminder_2h},
        )
        return _load(conn, tenant_id)
