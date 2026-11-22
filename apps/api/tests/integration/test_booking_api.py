"""Phase 4c: booking from the widget through the real API, RLS, queue and worker (fake provider).

The invariant under test: a visitor is told "booked" only after the provider confirmed it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import worker
from app.config import get_settings
from app.services.scheduling.base import OutcomeUnknown, ProviderRejected, ProviderUnavailable
from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)
from tests.integration.test_inbox_api import visitor_session
from tests.integration.test_worker import FakeSender
from tests.scheduling_fakes import VALID_KEY, FakeWorld

pytestmark = pytest.mark.integration


@pytest.fixture
def clinic(client, world, chat, app_state, admin_db):  # noqa: F811
    """Clinic A connected to a fake Cal.com, offering an exam and a confirmation-required type."""
    provider = FakeWorld()
    app_state("scheduling_providers", provider)
    base = f"/api/v1/tenants/{world.tenant_a}/scheduling"
    connected = client.post(f"{base}/connect", headers=world.a_owner.auth,
                            json={"provider": "calcom", "api_key": VALID_KEY})
    assert connected.status_code == 200, connected.text
    saved = client.put(f"{base}/appointment-types", headers=world.a_owner.auth,
                       json={"items": [{"provider_event_type_id": "101"},
                                       {"provider_event_type_id": "102"}]})
    types = {t["provider_event_type_id"]: t["id"] for t in saved.json()["appointment_types"]}
    yield {"provider": provider, "exam": types["101"], "fitting": types["102"]}
    admin_db.execute(
        "update public.scheduling_connections set status = 'disconnected' "
        "where tenant_id = %s and status <> 'disconnected'", (world.tenant_a,),
    )


def visitor(client, world, chat):  # noqa: F811
    return visitor_session(client, world, chat)


def book(client, token, type_id, start, **extra):
    body = {"token": token, "appointment_type_id": type_id, "start": start.isoformat(),
            "name": "Ada Test", "email": "ada.patient@example.com", "phone": "+234 801 000 4444",
            "time_zone": "Africa/Lagos", "consent": True, **extra}
    return client.post("/api/v1/public/widget/booking", json=body)


def appointment(admin_db, provider_reference_or_id):
    return admin_db.execute(
        "select id, status, provider_booking_id, failure_reason, conversation_id "
        "from public.appointments where id = %s", (provider_reference_or_id,),
    ).fetchone()


def jobs(admin_db, appointment_id):
    return {r[0] for r in admin_db.execute(
        "select split_part(idempotency_key, '/', 1) from app_private.jobs "
        "where idempotency_key like %s", (f"%/{appointment_id}%",),
    ).fetchall()}


def drain(client, sender, provider):
    for _ in range(50):
        if not worker.process_batch(client.app.state.db, sender, get_settings(),
                                    client.app.state.secrets_box, provider):
            return
    raise AssertionError("queue did not drain")


# ----- happy paths ------------------------------------------------------------------------------
def test_options_and_slots(client, world, chat, clinic):  # noqa: F811
    token = visitor(client, world, chat)
    options = client.post("/api/v1/public/widget/booking/options", json={"token": token}).json()
    assert options["available"] is True
    assert {t["name"] for t in options["types"]} == {"Comprehensive eye exam", "Contact lens fitting"}
    slots = client.post("/api/v1/public/widget/booking/slots",
                        json={"token": token, "appointment_type_id": clinic["exam"]})
    assert slots.status_code == 200
    assert [datetime.fromisoformat(s) for s in slots.json()["slots"]] == clinic["provider"].slot_starts


def test_confirmed_booking_is_recorded_announced_and_emailed(client, world, chat, clinic, admin_db):  # noqa: F811
    provider = clinic["provider"]
    start = provider.slot_starts[0]
    response = book(client, visitor(client, world, chat), clinic["exam"], start)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    assert response.json()["message"].startswith("Booked: Comprehensive eye exam")

    sent = provider.bookings[-1]
    row = appointment(admin_db, sent.reference)  # the provider reference IS our appointment id
    assert (row[1], row[2]) == ("confirmed", sent.uid)
    assert jobs(admin_db, row[0]) == {"booking_confirmation", "booking_alert"}

    sender = FakeSender()
    drain(client, sender, provider)
    mine = {key.split("/")[0]: email for key, email in sender.sent if str(row[0]) in key}
    patient, staff = mine["booking_confirmation"], mine["booking_alert"]
    assert patient.to == ("ada.patient@example.com",)
    assert "Comprehensive eye exam" in patient.text and "is booked for" in patient.text
    assert world.a_owner.email in staff.to
    for private in ("Ada Test", "ada.patient@example.com", "+234 801 000 4444"):
        assert private not in staff.text and private not in staff.html


def test_confirmation_required_type_is_pending(client, world, chat, clinic, admin_db):  # noqa: F811
    clinic["provider"].book_status = "pending"
    response = book(client, visitor(client, world, chat), clinic["fitting"], clinic["provider"].slot_starts[1])
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert "will confirm" in response.json()["message"]


# ----- never a false confirmation ---------------------------------------------------------------
def test_a_taken_slot_is_caught_before_booking(client, world, chat, clinic, admin_db):  # noqa: F811
    provider = clinic["provider"]
    start = provider.slot_starts[2]
    assert book(client, visitor(client, world, chat), clinic["exam"], start).status_code == 200
    second = book(client, visitor(client, world, chat), clinic["exam"], start)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "slot_unavailable"
    assert len(provider.bookings) == 1  # the re-check stopped it before any provider write
    failed = admin_db.execute(
        "select status, failure_reason from public.appointments where start_at = %s "
        "and status = 'failed'", (start,),
    ).fetchone()
    assert tuple(failed) == ("failed", "slot_unavailable")


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ProviderRejected("http_409"), 409, "slot_unavailable"),
        (ProviderUnavailable("connect_error"), 503, "booking_unavailable"),
    ],
)
def test_provider_refusal_or_outage_books_nothing(client, world, chat, clinic, admin_db, error, status, code):  # noqa: F811
    clinic["provider"].fail_on["book"] = error
    response = book(client, visitor(client, world, chat), clinic["exam"], clinic["provider"].slot_starts[3])
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    row = admin_db.execute(
        "select id, status from public.appointments where start_at = %s order by created_at desc limit 1",
        (clinic["provider"].slot_starts[3],),
    ).fetchone()
    assert row[1] == "failed"
    assert jobs(admin_db, row[0]) == set()  # no confirmation, no alert


def test_lost_response_is_never_reported_as_booked_and_is_reconciled(client, world, chat, clinic, admin_db):  # noqa: F811
    provider = clinic["provider"]
    provider.lose_response = True  # Cal.com creates the booking but the reply is lost
    response = book(client, visitor(client, world, chat), clinic["exam"], provider.slot_starts[0])
    assert response.status_code == 202
    assert response.json()["status"] == "unconfirmed"
    assert "Nothing is confirmed" in response.json()["message"]

    reference = provider.bookings[-1].reference
    row = appointment(admin_db, reference)
    assert row[1] == "unknown"
    assert jobs(admin_db, row[0]) == {"booking_reconcile"}  # no confirmation yet
    handover = admin_db.execute(
        "select contact_email, note from public.handover_requests where conversation_id = %s",
        (row[4],),
    ).fetchone()
    assert handover[0] == "ada.patient@example.com" and "could not be confirmed" in handover[1]

    admin_db.execute("update app_private.jobs set run_at = now() where idempotency_key like %s",
                     (f"booking_reconcile/{row[0]}/%",))
    sender = FakeSender()
    drain(client, sender, provider)
    assert appointment(admin_db, reference)[1:3] == ("confirmed", provider.bookings[-1].uid)
    assert any(key == f"booking_confirmation/{row[0]}" for key, _ in sender.sent)


def test_unknown_outcome_that_never_happened_ends_failed(client, world, chat, clinic, admin_db):  # noqa: F811
    provider = clinic["provider"]
    provider.fail_on["book"] = OutcomeUnknown("timeout")  # nothing was created
    response = book(client, visitor(client, world, chat), clinic["exam"], provider.slot_starts[1])
    assert response.status_code == 202
    row_id = admin_db.execute(
        "select id from public.appointments where status = 'unknown' order by created_at desc limit 1"
    ).fetchone()[0]
    for _ in range(3):  # attempts 1, 2, 3
        admin_db.execute("update app_private.jobs set run_at = now() where idempotency_key like %s",
                         (f"booking_reconcile/{row_id}/%",))
        drain(client, FakeSender(), provider)
    status, _, reason = appointment(admin_db, row_id)[1:4]
    assert (status, reason) == ("failed", "not_found_after_reconcile")
    assert "booking_confirmation" not in jobs(admin_db, row_id)


# ----- validation and isolation -----------------------------------------------------------------
def test_revoked_key_stops_booking_and_flags_the_connection(client, world, chat, clinic):  # noqa: F811
    clinic["provider"].revoked.add(VALID_KEY)
    token = visitor(client, world, chat)
    slots = client.post("/api/v1/public/widget/booking/slots",
                        json={"token": token, "appointment_type_id": clinic["exam"]})
    assert slots.status_code == 503
    state = client.get(f"/api/v1/tenants/{world.tenant_a}/scheduling", headers=world.a_owner.auth)
    assert state.json()["connection"]["status"] == "failing"


def test_other_clinics_types_and_bad_input_are_refused(client, world, chat, clinic):  # noqa: F811
    token = visitor(client, world, chat)
    start = clinic["provider"].slot_starts[0]
    assert book(client, token, str(uuid.uuid4()), start).status_code == 404
    assert book(client, token, clinic["exam"], start, consent=False).status_code == 422
    assert book(client, token, clinic["exam"], start, time_zone="Mars/Olympus").status_code == 422
    past = datetime.now(UTC) - timedelta(hours=1)
    assert book(client, token, clinic["exam"], past).status_code == 409
    assert clinic["provider"].bookings == []


def test_booking_limit_per_conversation(client, world, chat, clinic):  # noqa: F811
    token = visitor(client, world, chat)
    provider = clinic["provider"]
    for start in provider.slot_starts[:3]:
        assert book(client, token, clinic["exam"], start).status_code == 200
    over = book(client, token, clinic["exam"], provider.slot_starts[3])
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "booking_limit"
