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
