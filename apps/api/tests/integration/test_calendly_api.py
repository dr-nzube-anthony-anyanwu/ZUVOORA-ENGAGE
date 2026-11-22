"""Phase 4e: a Calendly-connected clinic through the real API (fake provider, Calendly webhooks)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)
from tests.integration.test_booking_api import book, visitor
from tests.scheduling_fakes import FakeWorld

pytestmark = pytest.mark.integration

# Obviously fake, low-entropy, JWT-shaped token (never a real credential).
TOKEN = "a" * 20 + "." + "b" * 20 + "." + "c" * 20


@pytest.fixture
def calendly_clinic(client, world, chat, app_state, admin_db):  # noqa: F811
    provider = FakeWorld()
    app_state("scheduling_providers", provider)
    base = f"/api/v1/tenants/{world.tenant_a}/scheduling"
    connected = client.post(f"{base}/connect", headers=world.a_owner.auth,
                            json={"provider": "calendly", "api_key": TOKEN})
    assert connected.status_code == 200, connected.text
    assert connected.json()["connection"]["provider"] == "calendly"
    saved = client.put(f"{base}/appointment-types", headers=world.a_owner.auth,
                       json={"items": [{"provider_event_type_id": "101"}]})
    yield {"provider": provider, "exam": saved.json()["appointment_types"][0]["id"],
           "connection": connected.json()["connection"]["id"]}
    admin_db.execute(
        "update public.scheduling_connections set status = 'disconnected' "
        "where tenant_id = %s and status <> 'disconnected'", (world.tenant_a,),
    )


def calendly_delivery(secret: str, uid: str, name: str = "invitee.canceled", **payload):
    raw = json.dumps({"event": name, "created_at": datetime.now(UTC).isoformat(), "payload": {
        "event": f"https://api.calendly.com/scheduled_events/{uid}", "rescheduled": False,
        "scheduled_event": {"start_time": datetime.now(UTC).isoformat()}, **payload}}).encode()
    stamp = str(int(datetime.now(UTC).timestamp()))
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, f"t={stamp},v1={sig}"


def test_calendly_token_format_is_checked(client, world, chat, app_state):  # noqa: F811
    app_state("scheduling_providers", FakeWorld())
    response = client.post(f"/api/v1/tenants/{world.tenant_a}/scheduling/connect",
                           headers=world.a_owner.auth,
                           json={"provider": "calendly", "api_key": "cal_not_a_calendly_token"})
    assert response.status_code == 422
    assert "Calendly" in response.json()["error"]["message"]


def test_booking_and_calendly_cancellation_webhook(client, world, chat, calendly_clinic, admin_db):  # noqa: F811
    provider = calendly_clinic["provider"]
    response = book(client, visitor(client, world, chat), calendly_clinic["exam"], provider.slot_starts[0])
    assert response.status_code == 200 and response.json()["status"] == "confirmed"
    booking = provider.bookings[-1]

    setup = client.post(f"/api/v1/tenants/{world.tenant_a}/scheduling/webhook", headers=world.a_owner.auth)
    assert setup.status_code == 200
    hook = setup.json()
    assert hook["subscriber_url"].endswith(f"/api/v1/webhooks/calendly/{calendly_clinic['connection']}")
    assert hook["triggers"] == ["invitee.created", "invitee.canceled"]

    raw, signature = calendly_delivery(hook["secret"], booking.uid)
    url = f"/api/v1/webhooks/calendly/{calendly_clinic['connection']}"
    first = client.post(url, content=raw, headers={"calendly-webhook-signature": signature})
    assert first.json() == {"result": "cancelled"}
    again = client.post(url, content=raw, headers={"calendly-webhook-signature": signature})
    assert again.json() == {"result": "duplicate"}
    status = admin_db.execute("select status from public.appointments where id = %s",
                              (booking.reference,)).fetchone()[0]
    assert status == "cancelled"

    # A Calendly connection does not accept deliveries on the Cal.com address (and vice versa).
    wrong = client.post(f"/api/v1/webhooks/calcom/{calendly_clinic['connection']}", content=raw,
                        headers={"x-cal-signature-256": signature})
    assert wrong.status_code == 401
