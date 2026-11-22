"""Phase 4e: the Calendly adapter and its webhooks, from the documented API (mock HTTP only)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services.scheduling import webhooks
from app.services.scheduling.base import (
    Attendee,
    CredentialRejected,
    OutcomeUnknown,
    ProviderRejected,
    ProviderUnavailable,
)
from app.services.scheduling.calendly import CalendlyProvider, uuid_from_uri

API = "https://api.calendly.com"
ME = {"resource": {"uri": f"{API}/users/U1", "slug": "dr-ada", "email": "ada@example.com",
                   "timezone": "Africa/Lagos", "current_organization": f"{API}/organizations/O1"}}
ET = f"{API}/event_types/ET1"
ATTENDEE = Attendee("Ada Test", "ada@example.com", "Africa/Lagos", "+2348010000000")


def provider(routes: dict, seen: list | None = None) -> CalendlyProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        key = f"{request.method} {request.url.path}"
        response = routes.get(key)
        if response is None:
            return httpx.Response(404, json={"title": "not found"})
        return response(request) if callable(response) else response
    return CalendlyProvider("tok", transport=httpx.MockTransport(handler))


def test_account_and_active_event_types_with_pagination():
    pages = iter([
        {"collection": [{"uri": ET, "name": "Eye exam", "duration": 30, "secret": False}],
         "pagination": {"next_page_token": "p2"}},
        {"collection": [{"uri": f"{API}/event_types/ET2", "name": "Hidden", "duration": 15, "secret": True},
                        {"uri": "https://evil.example.com/x", "name": "Bad", "duration": 5}],
         "pagination": {"next_page_token": None}},
    ])
    seen: list[httpx.Request] = []
    p = provider({"GET /users/me": httpx.Response(200, json=ME),
                  "GET /event_types": lambda r: httpx.Response(200, json=next(pages))}, seen)
    assert p.account().label == "dr-ada"
    types = p.event_types()
    assert [(t.id, t.duration_minutes, t.hidden) for t in types] == [(ET, 30, False), (f"{API}/event_types/ET2", 15, True)]
    event_type_requests = [r for r in seen if r.url.path == "/event_types"]
    assert event_type_requests[0].url.params["user"] == f"{API}/users/U1"
    assert event_type_requests[1].url.params["page_token"] == "p2"
    assert seen[0].headers["authorization"] == "Bearer tok"


def test_slots_are_fetched_in_windows_within_the_documented_limit():
    seen: list[httpx.Request] = []
    start = datetime.now(UTC) + timedelta(hours=1)

    def times(request):
        return httpx.Response(200, json={"collection": [
            {"status": "available", "start_time": request.url.params["start_time"]}]})

    slots = provider({"GET /event_type_available_times": times}, seen).slots(ET, start, start + timedelta(days=15))
    assert len(seen) == 3  # 7 + 7 + 1 days
    for request in seen:
        begin = datetime.fromisoformat(request.url.params["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(request.url.params["end_time"].replace("Z", "+00:00"))
        assert end - begin <= timedelta(days=7) and request.url.params["event_type"] == ET
    assert len(slots) == 3


def test_booking_sends_the_documented_body_and_maps_the_event_uuid():
    seen: list[httpx.Request] = []
    p = provider({
        "GET /event_types/ET1": httpx.Response(200, json={"resource": {
            "uri": ET, "locations": [{"kind": "physical", "location": "Ikoyi"}]}}),
        "POST /invitees": httpx.Response(201, json={"resource": {
            "uri": f"{API}/scheduled_events/EV9/invitees/IN1", "status": "active",
            "event": f"{API}/scheduled_events/EV9"}}),
    }, seen)
    start = datetime(2026, 12, 1, 9, tzinfo=UTC)
    booking = p.book(ET, start, ATTENDEE, "ref")
    body = json.loads(seen[-1].content)
    assert body == {"event_type": ET, "start_time": "2026-12-01T09:00:00.000000Z",
                    "invitee": {"name": "Ada Test", "email": "ada@example.com", "timezone": "Africa/Lagos"},
                    "location": {"kind": "physical"}}
    assert (booking.provider_booking_id, booking.status, booking.start) == ("EV9", "confirmed", start)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401), CredentialRejected),
        (httpx.Response(400, json={"message": "Event types that require payment cannot be scheduled via the API."}), ProviderRejected),
        (httpx.Response(429), ProviderUnavailable),
        (httpx.Response(503), OutcomeUnknown),
    ],
)
def test_booking_errors(response, error):
    p = provider({"GET /event_types/ET1": httpx.Response(200, json={"resource": {"uri": ET}}),
                  "POST /invitees": response})
    with pytest.raises(error):
        p.book(ET, datetime(2026, 12, 1, tzinfo=UTC), ATTENDEE, "ref")


def test_find_booking_matches_type_time_and_email():
    start = datetime(2026, 12, 1, 9, tzinfo=UTC)
    seen: list[httpx.Request] = []
    p = provider({
        "GET /users/me": httpx.Response(200, json=ME),
        "GET /scheduled_events": httpx.Response(200, json={"collection": [
            {"uri": f"{API}/scheduled_events/OTHER", "event_type": f"{API}/event_types/ETX",
             "start_time": "2026-12-01T09:00:00.000000Z", "end_time": "2026-12-01T09:30:00.000000Z"},
            {"uri": f"{API}/scheduled_events/EV9", "event_type": ET,
             "start_time": "2026-12-01T09:00:00.000000Z", "end_time": "2026-12-01T09:30:00.000000Z"},
        ]}),
    }, seen)
    found = p.find_booking("ignored", ET, start, "ada@example.com")
    assert found.provider_booking_id == "EV9"
    assert seen[-1].url.params["invitee_email"] == "ada@example.com"


def test_cancel_and_unsupported_reschedule():
    seen: list[httpx.Request] = []
    p = provider({"POST /scheduled_events/EV9/cancellation": httpx.Response(201, json={"resource": {}})}, seen)
    p.cancel("EV9", "Patient asked")
    assert json.loads(seen[-1].content) == {"reason": "Patient asked"}
    with pytest.raises(ProviderRejected):
        p.cancel("../users/me", None)
    with pytest.raises(ProviderRejected):
        p.reschedule("EV9", datetime(2026, 12, 2, tzinfo=UTC))


def test_uuid_from_uri():
    assert uuid_from_uri(f"{API}/scheduled_events/EV9/invitees/IN1", "scheduled_events") == "EV9"
    with pytest.raises(ProviderRejected):
        uuid_from_uri(f"{API}/users/U1", "scheduled_events")


# ----- webhooks ----------------------------------------------------------------------------------
SECRET = "calendly-signing-key-" + "z" * 20
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def signed(raw: bytes, at: datetime = NOW, secret: str = SECRET) -> str:
    stamp = str(int(at.timestamp()))
    return f"t={stamp},v1=" + hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()


def event(name: str, **payload) -> bytes:
    return json.dumps({"event": name, "created_at": NOW.isoformat(), "payload": {
        "event": f"{API}/scheduled_events/EV9",
        "scheduled_event": {"start_time": "2026-12-01T09:00:00.000000Z", "end_time": "2026-12-01T09:30:00.000000Z"},
        **payload}}).encode()


def test_calendly_signature():
    raw = event("invitee.canceled")
    assert webhooks.calendly_signature_valid(SECRET, raw, signed(raw), now=NOW)
    assert not webhooks.calendly_signature_valid(SECRET, raw, signed(raw, secret="other"), now=NOW)
    assert not webhooks.calendly_signature_valid(SECRET, raw + b" ", signed(raw), now=NOW)
    old = signed(raw, at=NOW - timedelta(minutes=4))  # outside the documented 3 minutes
    assert not webhooks.calendly_signature_valid(SECRET, raw, old, now=NOW)
    assert not webhooks.calendly_signature_valid(SECRET, raw, None, now=NOW)


def test_calendly_events_map_to_booking_triggers():
    cancelled = webhooks.parse_calendly(event("invitee.canceled", rescheduled=False), now=NOW)
    assert (cancelled.trigger, cancelled.uid) == ("BOOKING_CANCELLED", "EV9")
    half = webhooks.parse_calendly(event("invitee.canceled", rescheduled=True), now=NOW)
    assert half.trigger == "IGNORED"  # the matching invitee.created carries the reschedule
    moved = webhooks.parse_calendly(event("invitee.created",
                                          old_invitee=f"{API}/scheduled_events/EV1/invitees/IN0"), now=NOW)
    assert (moved.trigger, moved.uid, moved.old_uid) == ("BOOKING_RESCHEDULED", "EV9", "EV1")
    assert moved.start == datetime(2026, 12, 1, 9, tzinfo=UTC)
    created = webhooks.parse_calendly(event("invitee.created"), now=NOW)
    assert created.trigger == "BOOKING_CREATED"
