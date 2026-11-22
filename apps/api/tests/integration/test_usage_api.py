"""Phase 5b: metering reconciles with real activity; quotas stop AI and bookings; alerts once."""

from __future__ import annotations

import uuid

import pytest

from tests.integration.test_ai_api import QUESTION, documents, use_ai  # noqa: F401 (fixtures)
from tests.integration.test_answering_api import ask, chat  # noqa: F401
from tests.integration.test_booking_api import book, clinic, drain, visitor  # noqa: F401
from tests.integration.test_worker import FakeSender

pytestmark = pytest.mark.integration


def used(admin_db, tenant, metric) -> float:
    row = admin_db.execute(
        "select quantity from app_private.usage_counters where tenant_id = %s and metric = %s "
        "and period_month = app_private.current_period()", (tenant, metric)).fetchone()
    return float(row[0]) if row else 0.0


def cap(admin_db, tenant, key, value):
    admin_db.execute(
        "insert into public.tenant_overrides (tenant_id, kind, key, limit_value, reason) "
        "values (%s, 'limit', %s, %s, 'quota test') on conflict (tenant_id, kind, key) "
        "do update set limit_value = excluded.limit_value", (tenant, key, value))


@pytest.fixture(autouse=True)
def clear_caps(admin_db, world):
    yield
    admin_db.execute("delete from public.tenant_overrides where tenant_id = any(%s) "
                     "and reason = 'quota test'", ([world.tenant_a, world.tenant_b],))


def test_counters_follow_real_activity(client, world, chat, clinic, admin_db):  # noqa: F811
    messages, bookings = used(admin_db, world.tenant_a, "messages"), used(admin_db, world.tenant_a, "bookings")
    ask(client, chat, world, "What are your opening hours?")
    ask(client, chat, world, "What is your phone number?")
    response = book(client, visitor(client, world, chat), clinic["exam"], clinic["provider"].slot_starts[0])
    assert response.status_code == 200
    assert used(admin_db, world.tenant_a, "messages") == messages + 2
    assert used(admin_db, world.tenant_a, "bookings") == bookings + 1

    usage = client.get(f"/api/v1/tenants/{world.tenant_a}/usage", headers=world.a_owner.auth)
    assert usage.status_code == 200
    monthly = {m["key"]: m for m in usage.json()["monthly"]}
    assert monthly["messages"]["used"] == messages + 2 and monthly["messages"]["limit"] == 50000
    assert {t["key"] for t in usage.json()["totals"]} == {"documents", "staff_seats", "domains", "branches"}
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/usage",
                      headers=world.a_receptionist.auth).status_code == 403


def test_ai_spend_is_metered(client, world, chat, documents, admin_db, app_state):  # noqa: F811
    before = used(admin_db, world.tenant_a, "ai_usd")
    use_ai(app_state, lambda r: "Yes. Dilation lasts about 4 hours, so bring a driver.")
    assert ask(client, chat, world, QUESTION)["source"] == "retrieval_ai"
    assert used(admin_db, world.tenant_a, "ai_usd") > before
    assert used(admin_db, world.tenant_a, "ai_tokens") > 0


@pytest.mark.parametrize("metric", ["messages_month", "ai_usd_month"])
def test_at_the_limit_ai_pauses_but_the_assistant_still_helps(
    client, world, chat, documents, admin_db, app_state, metric  # noqa: F811
):
    cap(admin_db, world.tenant_a, metric, 0)
    fake = use_ai(app_state, lambda r: "should not be called")
    reply = ask(client, chat, world, QUESTION)
    assert fake.requests == []  # no model call, no cost
    assert reply["source"] == "fallback" and reply["offer_handover"] is True
    facts = ask(client, chat, world, "What is your phone number?")
    assert facts["source"] == "facts"  # free answers continue
    emergency = ask(client, chat, world, "Bleach splashed into my eye!")
    assert emergency["source"] == "emergency"  # safety always continues


def test_at_the_booking_limit_new_bookings_pause(client, world, chat, clinic, admin_db):  # noqa: F811
    cap(admin_db, world.tenant_a, "bookings_month", 0)
    token = visitor(client, world, chat)
    assert client.post("/api/v1/public/widget/booking/options", json={"token": token}).json() == {
        "available": False, "types": []}
    response = book(client, token, clinic["exam"], clinic["provider"].slot_starts[1])
    assert response.status_code == 409 and response.json()["error"]["code"] == "quota_reached"
    assert clinic["provider"].bookings == []
    handover = client.post("/api/v1/public/widget/handover", json={
        "token": token, "phone": "+234 801 000 9999", "consent": True})
    assert handover.status_code == 200  # the patient can still ask to be called


def test_crossing_the_limit_alerts_owners_once(client, world, admin_db):
    """Clinic B: a 2-message limit; the 2nd and 3rd messages must produce one 100% alert."""
    cap(admin_db, world.tenant_b, "messages_month", used(admin_db, world.tenant_b, "messages") + 2)
    conversation = uuid.uuid4()
    admin_db.execute("insert into public.conversations (id, tenant_id) values (%s, %s)",
                     (conversation, world.tenant_b))
    for text in ("one", "two", "three"):
        admin_db.execute("insert into public.messages (tenant_id, conversation_id, role, content) "
                         "values (%s, %s, 'visitor', %s)", (world.tenant_b, conversation, text))
    sender = FakeSender()
    drain(client, sender, None)
    alerts = [e for key, e in sender.sent if key.startswith(f"quota_alert/{world.tenant_b}/messages/")
              and key.endswith("/100")]
    assert len(alerts) == 1
    assert world.b_owner.email in alerts[0].to
    assert "AI answers pause" in alerts[0].text
