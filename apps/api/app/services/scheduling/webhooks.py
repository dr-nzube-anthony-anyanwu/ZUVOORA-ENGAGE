"""Cal.com webhook verification and parsing (Phase 4d, ADR-036).

Cal.com signs the raw request body with HMAC-SHA256 using the webhook secret and sends it in
`x-cal-signature-256`. Its docs do not state the encoding, so both the hex and base64 renderings
of that single HMAC are accepted (an optional "sha256=" prefix is ignored); comparison is
constant-time. Cal.com sends no timestamp header: replays are stopped by recording each
verified body hash once per connection, and the signed `createdAt` must be recent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MAX_AGE = timedelta(hours=72)
MAX_FUTURE_SKEW = timedelta(minutes=5)
TRIGGERS = (
    "BOOKING_CREATED",
    "BOOKING_REQUESTED",
    "BOOKING_CANCELLED",
    "BOOKING_RESCHEDULED",
    "BOOKING_REJECTED",
)


class WebhookError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class CalcomEvent:
    trigger: str
    created_at: datetime
    uid: str | None
    old_uid: str | None
    start: datetime | None
    end: datetime | None
    engage_ref: str | None
    event_key: str  # sha256 of the exact body: one delivery = one effect


def signature_valid(secret: str, body: bytes, header: str | None) -> bool:
    if not header:
        return False
    received = header.strip()
    if received.lower().startswith("sha256="):
        received = received[7:]
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    candidates = (digest.hex(), base64.b64encode(digest).decode())
    return any(hmac.compare_digest(received.encode(), c.encode()) for c in candidates)


def _time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WebhookError("bad_time") from exc
    if moment.tzinfo is None:
        raise WebhookError("bad_time")
    return moment.astimezone(UTC)


def _uid(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not (1 <= len(text) <= 100) or not all(c.isalnum() or c in "_-" for c in text):
        raise WebhookError("bad_uid")
    return text


def parse(body: bytes, now: datetime | None = None) -> CalcomEvent:
    now = now or datetime.now(UTC)
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise WebhookError("bad_json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
        raise WebhookError("bad_shape")
    trigger = str(data.get("triggerEvent", ""))
    created = _time(data.get("createdAt"))
    if created is None:
        raise WebhookError("missing_created_at")
    if created < now - MAX_AGE or created > now + MAX_FUTURE_SKEW:
        raise WebhookError("stale_event")
    payload = data["payload"]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    ref = metadata.get("engage_ref")
    return CalcomEvent(
        trigger=trigger[:60],
        created_at=created,
        uid=_uid(payload.get("uid")),
        old_uid=_uid(payload.get("rescheduleUid")),
        start=_time(payload.get("startTime")),
        end=_time(payload.get("endTime")),
        engage_ref=str(ref)[:64] if ref else None,
        event_key=hashlib.sha256(body).hexdigest(),
    )


# ----- Calendly (Phase 4e) -----------------------------------------------------------------------
# Header "Calendly-Webhook-Signature: t=<unix>,v1=<hex HMAC-SHA256 of '<t>.<raw body>'>"; Calendly
# documents a 3-minute tolerance. Body hashes are also recorded once (as for Cal.com).
CALENDLY_TOLERANCE = timedelta(minutes=3)

ProviderEvent = CalcomEvent  # one canonical event shape for every provider


def calendly_signature_valid(
    secret: str, body: bytes, header: str | None, now: datetime | None = None
) -> bool:
    if not header:
        return False
    parts = dict(p.split("=", 1) for p in header.replace(" ", "").split(",") if "=" in p)
    stamp, received = parts.get("t"), parts.get("v1")
    if not stamp or not received or not stamp.isdigit():
        return False
    sent = datetime.fromtimestamp(int(stamp), UTC)
    if abs((now or datetime.now(UTC)) - sent) > CALENDLY_TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received.encode(), expected.encode())


def _calendly_uuid(uri: object, collection: str) -> str | None:
    if not isinstance(uri, str):
        return None
    parts = uri.rstrip("/").split("/")
    if collection not in parts or parts.index(collection) + 1 >= len(parts):
        raise WebhookError("bad_uri")
    return _uid(parts[parts.index(collection) + 1])


def parse_calendly(body: bytes, now: datetime | None = None) -> ProviderEvent:
    """Translate invitee.created / invitee.canceled into the canonical booking triggers."""
    now = now or datetime.now(UTC)
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise WebhookError("bad_json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
        raise WebhookError("bad_shape")
    created = _time(data.get("created_at"))
    if created is None:
        raise WebhookError("missing_created_at")
    if created < now - MAX_AGE or created > now + MAX_FUTURE_SKEW:
        raise WebhookError("stale_event")
    payload = data["payload"]
    scheduled = (
        payload.get("scheduled_event") if isinstance(payload.get("scheduled_event"), dict) else {}
    )
    uid = _calendly_uuid(payload.get("event") or scheduled.get("uri"), "scheduled_events")
    event = str(data.get("event", ""))
    trigger, old_uid = "IGNORED", None
    if event == "invitee.canceled":
        # A reschedule cancels the old invitee (rescheduled=true) and creates a new one; the
        # created event carries the link, so the cancellation half is ignored here.
        trigger = "IGNORED" if payload.get("rescheduled") else "BOOKING_CANCELLED"
    elif event == "invitee.created":
        old_uid = _calendly_uuid(payload.get("old_invitee"), "scheduled_events")
        trigger = "BOOKING_RESCHEDULED" if old_uid else "BOOKING_CREATED"
    return ProviderEvent(
        trigger=trigger,
        created_at=created,
        uid=uid,
        old_uid=old_uid,
        start=_time(scheduled.get("start_time")),
        end=_time(scheduled.get("end_time")),
        engage_ref=None,
        event_key=hashlib.sha256(body).hexdigest(),
    )
