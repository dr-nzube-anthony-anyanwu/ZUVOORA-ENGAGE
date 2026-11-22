"""Phase 4b unit tests: credential encryption and the Cal.com adapter (mock HTTP, no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.services.scheduling.base import (
    Attendee,
    CredentialRejected,
    OutcomeUnknown,
    ProviderRejected,
    ProviderUnavailable,
)
from app.services.scheduling.calcom import CalcomProvider
from app.services.secrets_box import Sealed, SecretsBox, SecretsBoxError, generate_key

KEY_A, KEY_B = generate_key(), generate_key()
T1, T2 = "10000000-0000-4000-8000-00000000000a", "10000000-0000-4000-8000-00000000000b"


# ----- encryption -------------------------------------------------------------------------------
def test_round_trip_and_no_plaintext_in_ciphertext():
    box = SecretsBox(KEY_A)
    sealed = box.seal("cal_secret_value", purpose="scheduling", tenant_id=T1, record_id="c1")
    assert b"cal_secret_value" not in sealed.ciphertext
    assert (
        box.open(sealed, purpose="scheduling", tenant_id=T1, record_id="c1") == "cal_secret_value"
    )


@pytest.mark.parametrize(
    "context",
    [
        {"purpose": "scheduling", "tenant_id": T2, "record_id": "c1"},  # copied to another clinic
        {"purpose": "scheduling", "tenant_id": T1, "record_id": "c2"},  # copied to another row
        {"purpose": "email", "tenant_id": T1, "record_id": "c1"},  # used for another purpose
    ],
)
def test_ciphertext_is_bound_to_its_row(context):
    box = SecretsBox(KEY_A)
    sealed = box.seal("cal_secret_value", purpose="scheduling", tenant_id=T1, record_id="c1")
    with pytest.raises(SecretsBoxError):
        box.open(sealed, **context)


def test_tampering_is_detected():
    box = SecretsBox(KEY_A)
    sealed = box.seal("cal_secret_value", purpose="scheduling", tenant_id=T1, record_id="c1")
    flipped = bytearray(sealed.ciphertext)
    flipped[-1] ^= 1
    with pytest.raises(SecretsBoxError):
        box.open(
            Sealed(bytes(flipped), sealed.key_id),
            purpose="scheduling",
            tenant_id=T1,
            record_id="c1",
        )


def test_key_rotation_keeps_old_credentials_readable():
    old = SecretsBox(KEY_A).seal("v", purpose="scheduling", tenant_id=T1, record_id="c1")
    rotated = SecretsBox(KEY_B, previous=KEY_A)
    assert rotated.open(old, purpose="scheduling", tenant_id=T1, record_id="c1") == "v"
    assert (
        rotated.seal("v", purpose="scheduling", tenant_id=T1, record_id="c1").key_id
        == rotated.current_key_id
    )
    with pytest.raises(SecretsBoxError):  # without the previous key it cannot be read
        SecretsBox(KEY_B).open(old, purpose="scheduling", tenant_id=T1, record_id="c1")


@pytest.mark.parametrize("bad", ["short", "not base64 !!", "A" * 20])
def test_bad_keys_are_refused(bad):
    with pytest.raises(SecretsBoxError):
        SecretsBox(bad)


# ----- Cal.com adapter ---------------------------------------------------------------------------
def calcom(handler) -> CalcomProvider:
    return CalcomProvider(
        "cal_test_key", "https://cal.test", transport=httpx.MockTransport(handler)
    )


def ok(data) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", "data": data})


def test_account_and_event_types():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v2/me":
            return ok(
                {
                    "id": 1,
                    "username": "dr-ada",
                    "email": "ada@example.com",
                    "timeZone": "Africa/Lagos",
                }
            )
        return ok(
            [
                {
                    "id": 101,
                    "title": "Eye exam",
                    "lengthInMinutes": 45,
                    "hidden": False,
                    "confirmationPolicy": {"disabled": True},
                },
                {
                    "id": 102,
                    "title": "Lens fitting",
                    "lengthInMinutes": 30,
                    "hidden": True,
                    "confirmationPolicy": {"type": "always"},
                },
                {"id": "broken"},  # unknown shape: skipped, not guessed
            ]
        )

    provider = calcom(handler)
    account = provider.account()
    types = provider.event_types()
    assert account.label == "dr-ada" and account.time_zone == "Africa/Lagos"
    assert [(t.id, t.duration_minutes, t.requires_confirmation, t.hidden) for t in types] == [
        ("101", 45, False, False),
        ("102", 30, True, True),
    ]
    assert seen[0].headers["authorization"] == "Bearer cal_test_key"
    assert "cal-api-version" not in seen[0].headers
    assert seen[1].headers["cal-api-version"] == "2026-06-12"
    assert seen[1].url.params["username"] == "dr-ada"


def test_slots_request_and_both_response_shapes():
    seen = {}

    def handler(request):
        seen["request"] = request
        return ok(
            {
                "2026-12-01": [
                    {
                        "start": "2026-12-01T09:00:00.000+01:00",
                        "end": "2026-12-01T09:45:00.000+01:00",
                    }
                ],
                "2026-12-02": ["2026-12-02T08:00:00Z"],
            }
        )

    slots = calcom(handler).slots(
        "101", datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 3, tzinfo=UTC)
    )
    request = seen["request"]
    assert request.headers["cal-api-version"] == "2024-09-04"
    assert request.url.params["eventTypeId"] == "101"
    assert request.url.params["start"] == "2026-12-01T00:00:00Z"
    assert [s.start for s in slots] == [
        datetime(2026, 12, 1, 8, 0, tzinfo=UTC),
        datetime(2026, 12, 2, 8, 0, tzinfo=UTC),
    ]
    assert slots[0].end == datetime(2026, 12, 1, 8, 45, tzinfo=UTC)


ATTENDEE = Attendee("Ada Test", "ada@example.com", "Africa/Lagos", "+2348010000000")


def test_booking_request_and_status_mapping():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(
            201,
            json={
                "status": "success",
                "data": {
                    "uid": "bk_123",
                    "status": "pending",
                    "start": "2026-12-01T08:00:00.000Z",
                    "end": "2026-12-01T08:45:00.000Z",
                },
            },
        )

    booking = calcom(handler).book(
        "101", datetime(2026, 12, 1, 9, tzinfo=UTC), ATTENDEE, "attempt-1"
    )
    body = json.loads(seen["request"].content)
    assert seen["request"].headers["cal-api-version"] == "2026-02-25"
    assert body == {
        "start": "2026-12-01T09:00:00Z",
        "eventTypeId": 101,
        "attendee": {
            "name": "Ada Test",
            "email": "ada@example.com",
            "timeZone": "Africa/Lagos",
            "phoneNumber": "+2348010000000",
        },
        "metadata": {"engage_ref": "attempt-1"},
    }
    assert (booking.provider_booking_id, booking.status) == ("bk_123", "pending")


@pytest.mark.parametrize(
    ("respond", "error", "write"),
    [
        (lambda r: httpx.Response(401, json={"error": "secret"}), CredentialRejected, True),
        (
            lambda r: httpx.Response(400, json={"message": "slot taken by ada@example.com"}),
            ProviderRejected,
            True,
        ),
        (lambda r: httpx.Response(429), ProviderUnavailable, True),
        (lambda r: httpx.Response(503), OutcomeUnknown, True),  # booking may exist
        (lambda r: httpx.Response(503), ProviderUnavailable, False),  # reads are safe to retry
    ],
)
def test_errors_tell_callers_what_they_may_claim(respond, error, write):
    provider = calcom(respond)
    call = (
        (lambda: provider.book("101", datetime(2026, 12, 1, tzinfo=UTC), ATTENDEE, "r"))
        if write
        else (
            lambda: provider.slots(
                "101", datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 2, tzinfo=UTC)
            )
        )
    )
    with pytest.raises(error) as info:
        call()
    assert "ada@example.com" not in str(info.value) and "secret" not in str(info.value)


def test_write_timeout_is_an_unknown_outcome_but_connect_failure_is_not():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OutcomeUnknown):
        calcom(timeout).book("101", datetime(2026, 12, 1, tzinfo=UTC), ATTENDEE, "r")
    with pytest.raises(ProviderUnavailable):
        calcom(refused).book("101", datetime(2026, 12, 1, tzinfo=UTC), ATTENDEE, "r")


@pytest.mark.parametrize("uid", ["../../v2/me", "a/b", "x?y=1", ""])
def test_booking_ids_cannot_escape_the_path(uid):
    with pytest.raises(ProviderRejected):
        calcom(lambda r: ok({})).cancel(uid, None)


def test_find_booking_matches_our_reference_only():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"status": "success", "pagination": {"hasMore": False}, "data": [
            {"uid": "other", "status": "accepted", "start": "2026-12-01T09:00:00Z", "metadata": {"engage_ref": "x"}},
            {"uid": "mine", "status": "accepted", "start": "2026-12-01T09:00:00Z", "end": "2026-12-01T09:30:00Z",
             "metadata": {"engage_ref": "ref-1"}},
        ]})

    found = calcom(handler).find_booking("ref-1", "101", datetime(2026, 12, 1, 9, tzinfo=UTC), "ada@example.com")
    request = seen["request"]
    assert request.headers["cal-api-version"] == "2026-05-01"
    assert request.url.params["attendeeEmail"] == "ada@example.com"
    assert request.url.params["eventTypeId"] == "101"
    assert (found.provider_booking_id, found.status) == ("mine", "confirmed")
    assert calcom(handler).find_booking("missing", "101", datetime(2026, 12, 1, tzinfo=UTC), "a@b.c") is None
