"""Phase 5d acceptance: every gate refuses a direct API call; plan changes keep all data; meters
reconcile with their source tables; quota alerts fire once per threshold."""

from __future__ import annotations

import uuid

import pytest

from tests import samples
from tests.integration.test_ai_api import QUESTION, documents, use_ai  # noqa: F401 (fixtures)
from tests.integration.test_answering_api import ask, chat  # noqa: F401
from tests.integration.test_booking_api import book, clinic, drain, visitor  # noqa: F401
from tests.integration.test_worker import FakeSender
from tests.scheduling_fakes import VALID_KEY

pytestmark = pytest.mark.integration

REASON = "phase 5 acceptance"


@pytest.fixture(autouse=True)
def restore(admin_db, world):
    yield
    admin_db.execute("delete from public.tenant_overrides where tenant_id = any(%s) and reason = %s",
                     ([world.tenant_a, world.tenant_b], REASON))
    admin_db.execute("update public.tenant_subscriptions set plan_key = 'full_zuvoora', "
                     "status = 'active' where tenant_id = any(%s)", ([world.tenant_a, world.tenant_b],))


def set_plan(client, world, tenant, plan, status="active"):
    response = client.put(f"/api/v1/platform/tenants/{tenant}/subscription",
                          headers=world.platform_admin.auth_mfa, json={"plan_key": plan, "status": status})
    assert response.status_code == 200, response.text


def override(client, world, tenant, **body):
    response = client.put(f"/api/v1/platform/tenants/{tenant}/overrides",
                          headers=world.platform_admin.auth_mfa, json={"reason": REASON, **body})
    assert response.status_code == 200, response.text


def refused(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def count(admin_db, query, tenant) -> int:
    return admin_db.execute(query, (tenant,)).fetchone()[0]


# ----- gates: each one refuses a direct API call ---------------------------------------------------
def test_ai_answers_switched_off_means_no_model_call(client, world, chat, documents, app_state):  # noqa: F811
    override(client, world, world.tenant_a, kind="feature", key="ai_answers", feature_enabled=False)
    fake = use_ai(app_state, lambda r: "should not be called")
    reply = ask(client, chat, world, QUESTION)
    assert fake.requests == []
    assert reply["source"] == "fallback" and reply["offer_handover"] is True
    assert ask(client, chat, world, "What is your phone number?")["source"] == "facts"


def test_booking_switched_off_refuses_every_booking_call(client, world, chat, clinic):  # noqa: F811
    override(client, world, world.tenant_a, kind="feature", key="booking", feature_enabled=False)
    key = client.get(f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.a_owner.auth).json()["public_key"]
    frame = client.post("/api/v1/public/widget/frame-config", json={"key": key, "host": chat["host"]})
    assert frame.status_code == 200 and frame.json()["booking"] is False
    response = book(client, visitor(client, world, chat), clinic["exam"], clinic["provider"].slot_starts[2])
    refused(response, 403, "booking_unavailable")
    assert clinic["provider"].bookings == []  # the provider was never called
    connect = client.post(f"/api/v1/tenants/{world.tenant_a}/scheduling/connect", headers=world.a_owner.auth,
                          json={"provider": "calcom", "api_key": VALID_KEY})
    refused(connect, 403, "feature_not_in_plan")  # refused before "already connected" is checked


def test_document_limit_refuses_before_storing(client, world, admin_db):
    query = "select count(*) from public.knowledge_documents where tenant_id = %s and archived_at is null"
    every = "select count(*) from public.knowledge_documents where tenant_id = %s"
    active, total = count(admin_db, query, world.tenant_b), count(admin_db, every, world.tenant_b)
    override(client, world, world.tenant_b, kind="limit", key="documents", limit_value=active)
    response = client.post(f"/api/v1/tenants/{world.tenant_b}/knowledge", headers=world.b_owner.auth,
                           data={"title": "Over the limit"},
                           files={"file": ("limit.pdf", samples.pdf(), "application/pdf")})
    refused(response, 409, "plan_limit_reached")
    assert count(admin_db, every, world.tenant_b) == total  # nothing stored


def test_branch_limit_comes_from_the_plan(client, world, admin_db):
    active = count(admin_db, "select count(*) from public.branches where tenant_id = %s "
                             "and archived_at is null", world.tenant_b)
    override(client, world, world.tenant_b, kind="limit", key="branches", limit_value=active)
    response = client.post(f"/api/v1/tenants/{world.tenant_b}/branches", headers=world.b_owner.auth,
                           json={"content": {"name": "Ikeja", "timezone": "Africa/Lagos"}})
    refused(response, 409, "plan_limit_reached")
    assert count(admin_db, "select count(*) from public.branches where tenant_id = %s "
                           "and archived_at is null", world.tenant_b) == active


# ----- upgrades and downgrades keep everything ------------------------------------------------------
SNAPSHOT = {
    "tenant": "select id::text || '/' || status from public.tenants where id = %s",
    "widget_key": "select public_key from public.widget_configs where tenant_id = %s",
    "faqs": "select count(*) from public.faqs where tenant_id = %s",
    "branches": "select count(*) from public.branches where tenant_id = %s",
    "documents": "select count(*) from public.knowledge_documents where tenant_id = %s",
    "domains": "select count(*) from public.tenant_domains where tenant_id = %s",
    "members": "select count(*) from public.tenant_memberships where tenant_id = %s",
    "conversations": "select count(*) from public.conversations where tenant_id = %s",
    "messages": "select count(*) from public.messages where tenant_id = %s",
    "appointments": "select count(*) from public.appointments where tenant_id = %s",
    "scheduling": "select count(*) from public.scheduling_connections where tenant_id = %s",
    "usage": "select coalesce(sum(quantity), 0) from app_private.usage_counters where tenant_id = %s",
}


def test_any_plan_change_keeps_identity_data_and_widget(client, world, chat, admin_db):  # noqa: F811
    tenant = world.tenant_a
    before = {name: admin_db.execute(q, (tenant,)).fetchone()[0] for name, q in SNAPSHOT.items()}
    for plan, status in (("essentials", "active"), ("premium", "active"),
                         ("professional", "cancelled"), ("professional", "active"),
                         ("full_zuvoora", "active")):
        set_plan(client, world, tenant, plan, status)
    after = {name: admin_db.execute(q, (tenant,)).fetchone()[0] for name, q in SNAPSHOT.items()}
    assert after == before
    key = before["widget_key"]
    frame = client.post("/api/v1/public/widget/frame-config", json={"key": key, "host": chat["host"]})
    assert frame.status_code == 200  # the same embed code still works after the round trip


# ----- meters reconcile with their source tables -----------------------------------------------------
SOURCES = {
    "messages": "select count(*) from public.messages where tenant_id = %s and role = 'visitor' "
                "and created_at >= app_private.current_period()",
    "ai_usd": "select coalesce(sum(cost_usd), 0) from public.usage_events where tenant_id = %s "
              "and occurred_at >= app_private.current_period()",
    "ai_tokens": "select coalesce(sum(prompt_tokens + completion_tokens), 0) from public.usage_events "
                 "where tenant_id = %s and occurred_at >= app_private.current_period()",
    "bookings": "select count(*) from public.appointments where tenant_id = %s "
                "and status in ('confirmed', 'pending') and created_at >= app_private.current_period()",
    "emails": "select count(*) from app_private.jobs where tenant_id = %s and status = 'done' "
              "and kind <> 'booking_reconcile' and finished_at >= app_private.current_period() "
              "and coalesce(result->>'message_id', '') <> '' "
              "and result->>'message_id' not like 'log:%%' and result->>'message_id' not like 'suppressed:%%'",
}


def counters(admin_db, tenant) -> dict[str, float]:
    rows = admin_db.execute("select metric, quantity from app_private.usage_counters where tenant_id = %s "
                            "and period_month = app_private.current_period()", (tenant,)).fetchall()
    found = {row[0]: float(row[1]) for row in rows}
    return {metric: found.get(metric, 0.0) for metric in SOURCES}


def sources(admin_db, tenant) -> dict[str, float]:
    return {metric: float(admin_db.execute(q, (tenant,)).fetchone()[0]) for metric, q in SOURCES.items()}


def test_meters_reconcile_with_source_tables(
    client, world, chat, clinic, documents, admin_db, app_state  # noqa: F811
):
    tenant = world.tenant_a
    drain(client, FakeSender(), clinic["provider"])  # start from an empty queue
    meters_before, sources_before = counters(admin_db, tenant), sources(admin_db, tenant)

    use_ai(app_state, lambda r: "Yes. Dilation lasts about 4 hours, so bring a driver.")
    assert ask(client, chat, world, QUESTION)["source"] == "retrieval_ai"
    ask(client, chat, world, "What are your opening hours?")
    booked = book(client, visitor(client, world, chat), clinic["exam"], clinic["provider"].slot_starts[3])
    assert booked.status_code == 200, booked.text
    sender = FakeSender()
    drain(client, sender, clinic["provider"])  # confirmation and clinic alert emails

    meters = {m: counters(admin_db, tenant)[m] - meters_before[m] for m in SOURCES}
    actual = {m: sources(admin_db, tenant)[m] - sources_before[m] for m in SOURCES}
    assert meters == pytest.approx(actual)
    assert meters["messages"] == 2 and meters["bookings"] == 1  # booking is not a chat message
    assert meters["ai_tokens"] > 0 and meters["emails"] >= 1


# ----- quota alerts: once per threshold ----------------------------------------------------------
def test_eighty_percent_alert_fires_once_and_not_the_hundred(client, world, admin_db):
    used = float(admin_db.execute(
        "select coalesce((select quantity from app_private.usage_counters where tenant_id = %s "
        "and metric = 'messages' and period_month = app_private.current_period()), 0)",
        (world.tenant_b,)).fetchone()[0])
    limit = int(used) + 10  # 8 more messages crosses 80%, never 100%
    override(client, world, world.tenant_b, kind="limit", key="messages_month", limit_value=limit)
    drain(client, FakeSender(), None)
    conversation = uuid.uuid4()
    admin_db.execute("insert into public.conversations (id, tenant_id) values (%s, %s)",
                     (conversation, world.tenant_b))
    for n in range(9):
        admin_db.execute("insert into public.messages (tenant_id, conversation_id, role, content) "
                         "values (%s, %s, 'visitor', %s)", (world.tenant_b, conversation, f"m{n}"))
    sender = FakeSender()
    drain(client, sender, None)
    prefix = f"quota_alert/{world.tenant_b}/messages/"
    keys = [key for key, _ in sender.sent if key.startswith(prefix)]
    assert [k.rsplit("/", 1)[1] for k in keys] == ["80"]
    assert world.b_owner.email in next(e for k, e in sender.sent if k.startswith(prefix)).to
