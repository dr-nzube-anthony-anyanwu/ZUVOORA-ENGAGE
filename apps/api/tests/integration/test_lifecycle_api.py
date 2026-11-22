"""Phase 4d: webhooks, cancel/reschedule lifecycle and reminders through the real API and worker."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.services.scheduling.base import OutcomeUnknown, ProviderUnavailable
from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)
from tests.integration.test_booking_api import book, clinic, drain, visitor  # noqa: F401
from tests.integration.test_worker import FakeSender

pytestmark = pytest.mark.integration


def scheduling(world) -> str:
    return f"/api/v1/tenants/{world.tenant_a}/scheduling"


def setup_webhook(client, world) -> dict:
    response = client.post(f"{scheduling(world)}/webhook", headers=world.a_owner.auth)
    assert response.status_code == 200, response.text
    return response.json()


def connection_id(client, world) -> str:
    return client.get(scheduling(world), headers=world.a_owner.auth).json()["connection"]["id"]


def deliver(client, world, secret, trigger, payload, created=None, signature=None):
    raw = json.dumps({
        "triggerEvent": trigger,
        "createdAt": (created or datetime.now(UTC)).isoformat(),
        "payload": payload,
    }).encode()
    sig = signature or hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(f"/api/v1/webhooks/calcom/{connection_id(client, world)}", content=raw,
                       headers={"x-cal-signature-256": sig, "content-type": "application/json"})


def booked(client, world, chat, clinic, index=0):  # noqa: F811
    start = clinic["provider"].slot_starts[index]
    response = book(client, visitor(client, world, chat), clinic["exam"], start)
    assert response.status_code == 200, response.text
    return clinic["provider"].bookings[-1]


def status_of(admin_db, appointment_id):
    return admin_db.execute("select status from public.appointments where id = %s",
                            (appointment_id,)).fetchone()[0]


# ----- webhook setup -----------------------------------------------------------------------------
def test_manual_setup_shows_the_secret_once_and_rotation_replaces_it(client, world, clinic):
    first = setup_webhook(client, world)
    assert first["mode"] == "manual" and first["secret"]
    assert first["subscriber_url"].endswith(f"/api/v1/webhooks/calcom/{connection_id(client, world)}")
    assert "BOOKING_CANCELLED" in first["triggers"]
    second = setup_webhook(client, world)
    assert second["secret"] != first["secret"]
    old = deliver(client, world, first["secret"], "BOOKING_CANCELLED", {"uid": "nobody"})
    assert old.status_code == 401  # the rotated-out secret no longer verifies
    assert deliver(client, world, second["secret"], "BOOKING_CANCELLED", {"uid": "nobody"}).json() == {"result": "ignored"}
    state = client.get(scheduling(world), headers=world.a_owner.auth).json()["connection"]
    assert state["webhook_configured_at"] is not None and "secret" not in json.dumps(state)


def test_automatic_setup_registers_the_webhook_with_the_provider(client, world, clinic, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_api_url", "https://engage.example.com")
    first = setup_webhook(client, world)
    assert first["mode"] == "automatic" and first["secret"] is None
    url, triggers, secret = clinic["provider"].webhooks[-1]
    assert url == f"https://engage.example.com/api/v1/webhooks/calcom/{connection_id(client, world)}"
    assert "BOOKING_RESCHEDULED" in triggers and len(secret) >= 32
    setup_webhook(client, world)
    assert clinic["provider"].deleted_webhooks == ["wh1"]  # rotation removes the old webhook


def test_only_managers_configure_webhooks(client, world, clinic):
    assert client.post(f"{scheduling(world)}/webhook", headers=world.a_receptionist.auth).status_code == 403


# ----- verification ------------------------------------------------------------------------------
def test_unverifiable_deliveries_are_refused(client, world, clinic):
    secret = setup_webhook(client, world)["secret"]
    assert deliver(client, world, secret, "BOOKING_CANCELLED", {"uid": "x"}, signature="00" * 32).status_code == 401
    assert deliver(client, world, "not-the-secret", "BOOKING_CANCELLED", {"uid": "x"}).status_code == 401
    stale = deliver(client, world, secret, "BOOKING_CANCELLED", {"uid": "x"},
                    created=datetime.now(UTC) - timedelta(days=4))
    assert stale.status_code == 400
    unknown = client.post("/api/v1/webhooks/calcom/00000000-0000-4000-8000-000000000000",
                          content=b"{}", headers={"x-cal-signature-256": "00"})
    assert unknown.status_code == 401  # never reveals whether a connection exists


# ----- lifecycle ---------------------------------------------------------------------------------
def test_cancellation_in_calcom_is_applied_once_and_the_patient_told(client, world, chat, clinic, admin_db):  # noqa: F811
    secret = setup_webhook(client, world)["secret"]
    booking = booked(client, world, chat, clinic)
    payload = {"uid": booking.uid, "startTime": booking.start.isoformat()}
    created = datetime.now(UTC)
    first = deliver(client, world, secret, "BOOKING_CANCELLED", payload, created=created)
    again = deliver(client, world, secret, "BOOKING_CANCELLED", payload, created=created)
    assert first.json() == {"result": "cancelled"}
    assert again.json() == {"result": "duplicate"}
    assert status_of(admin_db, booking.reference) == "cancelled"
    sender = FakeSender()
    drain(client, sender, clinic["provider"])
    sent = [e for key, e in sender.sent if key == f"booking_cancelled/{booking.reference}"]
    assert len(sent) == 1 and sent[0].to == ("ada.patient@example.com",)
    assert "has been cancelled" in sent[0].text


def test_reschedule_in_calcom_moves_the_appointment(client, world, chat, clinic, admin_db):  # noqa: F811
    secret = setup_webhook(client, world)["secret"]
    booking = booked(client, world, chat, clinic)
    new_start = booking.start + timedelta(days=2)
    result = deliver(client, world, secret, "BOOKING_RESCHEDULED", {
        "uid": "bknew1", "rescheduleUid": booking.uid, "startTime": new_start.isoformat(),
        "endTime": (new_start + timedelta(minutes=45)).isoformat()})
    assert result.json() == {"result": "rescheduled"}
    old = admin_db.execute("select status, rescheduled_to from public.appointments where id = %s",
                           (booking.reference,)).fetchone()
    assert old[0] == "rescheduled"
    new = admin_db.execute("select status, provider_booking_id, start_at from public.appointments "
                           "where id = %s", (old[1],)).fetchone()
    assert tuple(new) == ("confirmed", "bknew1", new_start)


def test_reminders_go_out_for_the_right_time_only(client, world, chat, clinic, admin_db):  # noqa: F811
    provider = clinic["provider"]
    in_three_days = (datetime.now(UTC) + timedelta(days=3)).replace(second=0, microsecond=0)
    provider.slot_starts = [in_three_days]
    booking = booked(client, world, chat, clinic)
    key = f"booking_reminder/{booking.reference}/24h"
    assert admin_db.execute("select status from app_private.jobs where idempotency_key = %s",
                            (key,)).fetchone()[0] == "queued"
    admin_db.execute("update app_private.jobs set run_at = now() where idempotency_key = %s", (key,))
    sender = FakeSender()
    drain(client, sender, provider)
    reminders = [e for k, e in sender.sent if k == key]
    assert len(reminders) == 1 and "this is a reminder" in reminders[0].text


def test_staff_cancel_goes_through_calcom_first(client, world, chat, clinic, admin_db):  # noqa: F811
    booking = booked(client, world, chat, clinic)
    url = f"/api/v1/tenants/{world.tenant_a}/appointments/{booking.reference}/cancel"

    clinic["provider"].fail_on["cancel"] = ProviderUnavailable("timeout")
    assert client.post(url, headers=world.a_receptionist.auth).status_code == 503
    clinic["provider"].fail_on["cancel"] = OutcomeUnknown("timeout")
    assert client.post(url, headers=world.a_receptionist.auth).status_code == 502
    assert status_of(admin_db, booking.reference) == "confirmed"  # nothing claimed

    response = client.post(url, headers=world.a_receptionist.auth)
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert booking.uid in clinic["provider"].cancelled
    assert client.post(url, headers=world.a_receptionist.auth).status_code == 409
    assert client.post(url, headers=world.b_owner.auth).status_code == 404


def test_appointments_list_is_front_desk_only(client, world, chat, clinic):  # noqa: F811
    booking = booked(client, world, chat, clinic)
    listed = client.get(f"/api/v1/tenants/{world.tenant_a}/appointments", headers=world.a_receptionist.auth)
    assert listed.status_code == 200
    mine = next(a for a in listed.json() if a["id"] == booking.reference)
    assert mine["attendee_email"] == "ada.patient@example.com" and mine["status"] == "confirmed"
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/appointments",
                      headers=world.outsider.auth).status_code == 404
