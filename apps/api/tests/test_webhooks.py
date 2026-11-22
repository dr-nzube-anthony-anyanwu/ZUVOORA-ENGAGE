"""Phase 4d: Cal.com webhook signatures and parsing (no network, no database)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.services.scheduling import webhooks

SECRET = "whsec_" + "x" * 30
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def body(trigger="BOOKING_CANCELLED", created=NOW, **payload) -> bytes:
    return json.dumps(
        {
            "triggerEvent": trigger,
            "createdAt": created.isoformat().replace("+00:00", "Z"),
            "payload": {
                "uid": "bk_1",
                "startTime": "2026-12-01T09:00:00Z",
                "endTime": "2026-12-01T09:30:00Z",
                **payload,
            },
        }
    ).encode()


def sign(raw: bytes, secret=SECRET) -> bytes:
    return hmac.new(secret.encode(), raw, hashlib.sha256).digest()


@pytest.mark.parametrize(
    "render",
    [lambda d: d.hex(), lambda d: "sha256=" + d.hex(), lambda d: base64.b64encode(d).decode()],
)
def test_accepts_the_hmac_of_the_raw_body(render):
    raw = body()
    assert webhooks.signature_valid(SECRET, raw, render(sign(raw)))


@pytest.mark.parametrize(
    "header",
    [None, "", "deadbeef", sign(b"other body").hex(), sign(body(), "wrong_secret").hex()],
)
def test_rejects_missing_or_wrong_signatures(header):
    assert not webhooks.signature_valid(SECRET, body(), header)


def test_a_changed_body_fails_verification():
    raw = body()
    tampered = raw.replace(b"bk_1", b"bk_2")
    assert not webhooks.signature_valid(SECRET, tampered, sign(raw).hex())


def test_parse_reschedule_and_identity():
    raw = body(
        "BOOKING_RESCHEDULED",
        uid="bk_new",
        rescheduleUid="bk_old",
        metadata={"engage_ref": "ref-1"},
    )
    event = webhooks.parse(raw, now=NOW)
    assert (event.trigger, event.uid, event.old_uid, event.engage_ref) == (
        "BOOKING_RESCHEDULED",
        "bk_new",
        "bk_old",
        "ref-1",
    )
    assert event.start == datetime(2026, 12, 1, 9, tzinfo=UTC)
    assert event.event_key == hashlib.sha256(raw).hexdigest()
    assert webhooks.parse(raw, now=NOW).event_key == event.event_key  # same delivery, same key


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (b"not json", "bad_json"),
        (json.dumps({"triggerEvent": "X"}).encode(), "bad_shape"),
        (body(created=NOW - timedelta(hours=73)), "stale_event"),
        (body(created=NOW + timedelta(hours=1)), "stale_event"),
        (body(uid="../../etc"), "bad_uid"),
        (body(startTime="yesterday"), "bad_time"),
    ],
)
def test_parse_rejects_bad_events(raw, kind):
    with pytest.raises(webhooks.WebhookError) as info:
        webhooks.parse(raw, now=NOW)
    assert info.value.kind == kind
