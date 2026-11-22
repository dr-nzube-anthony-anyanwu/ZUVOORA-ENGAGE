"""Phase 5c: clinic analytics reconcile with the data, follow the plan, and expose no transcripts."""

from __future__ import annotations

import pytest

from tests.integration.test_answering_api import ask, chat  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def restore(admin_db, world):
    yield
    admin_db.execute("delete from public.tenant_overrides where tenant_id = %s and reason = 'analytics test'",
                     (world.tenant_a,))
    admin_db.execute("update public.tenant_subscriptions set plan_key = 'full_zuvoora', status = 'active' "
                     "where tenant_id = %s", (world.tenant_a,))


def analytics(client, world, user=None, days=30):
    return client.get(f"/api/v1/tenants/{world.tenant_a}/analytics?days={days}",
                      headers=(user or world.a_owner).auth)


def scalar(admin_db, sql, *params):
    return admin_db.execute(sql, params).fetchone()[0]


def test_numbers_reconcile_with_the_database(client, world, chat, admin_db):  # noqa: F811
    ask(client, chat, world, "What are your opening hours?")
    body = analytics(client, world).json()
    since = "now() - interval '30 days'"
    t = world.tenant_a
    assert body["conversations"] == scalar(
        admin_db, f"select count(*) from public.conversations where tenant_id = %s and started_at >= {since}", t)  # noqa: S608
    assert body["visitor_messages"] == scalar(
        admin_db, f"select count(*) from public.messages where tenant_id = %s and role = 'visitor' "  # noqa: S608
                  f"and created_at >= {since}", t)
    assert body["answers"].get("facts", 0) == scalar(
        admin_db, f"select count(*) from public.messages where tenant_id = %s and role = 'assistant' "  # noqa: S608
                  f"and answer_source = 'facts' and created_at >= {since}", t)
    assert body["handovers"]["total"] == scalar(
        admin_db, f"select count(*) from public.handover_requests where tenant_id = %s and created_at >= {since}", t)  # noqa: S608
    assert body["handovers"]["total"] == body["handovers"]["resolved"] + body["handovers"]["open"]


def test_full_analytics_follow_the_plan(client, world, admin_db):
    full = analytics(client, world).json()
    assert full["full_available"] is True
    assert len(full["full"]["daily"]) == 31  # 30 days back, inclusive of today
    assert sum(d["visitor_messages"] for d in full["full"]["daily"]) >= full["visitor_messages"]
    admin_db.execute("update public.tenant_subscriptions set plan_key = 'essentials' where tenant_id = %s",
                     (world.tenant_a,))
    basic = analytics(client, world).json()
    assert basic["full_available"] is False and basic["full"] is None
    assert basic["conversations"] == full["conversations"]  # basic numbers stay


def test_unanswered_topics_are_keyword_counts_only(client, world, chat):  # noqa: F811
    for question in ("Do you sell xylophone straps?", "Any xylophone lessons for kids?",
                     "Do you stock zither strings?"):
        assert ask(client, chat, world, question)["source"] == "fallback"
    topics = analytics(client, world).json()["full"]["unanswered_topics"]
    terms = {t["term"]: t["count"] for t in topics}
    assert terms.get("xylophone", 0) >= 2
    assert "zither" not in terms  # asked once: never shown
    assert all(" " not in t for t in terms)  # words, never sentences


def test_access_and_plan_gate(client, world, admin_db):
    assert analytics(client, world, world.a_receptionist).status_code == 403
    assert analytics(client, world, world.b_owner).status_code == 404
    admin_db.execute("insert into public.tenant_overrides (tenant_id, kind, key, feature_enabled, reason) "
                     "values (%s, 'feature', 'analytics_basic', false, 'analytics test')", (world.tenant_a,))
    refused = analytics(client, world)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "feature_not_in_plan"

def test_day_range_is_validated(client, world):
    assert analytics(client, world, days=0).status_code == 422
    assert analytics(client, world, days=366).status_code == 422


def test_platform_overview_is_for_mfa_platform_admins(client, world):
    assert client.get("/api/v1/platform/analytics", headers=world.a_owner.auth).status_code == 403
    assert client.get("/api/v1/platform/analytics", headers=world.platform_admin.auth).status_code == 403
    overview = client.get("/api/v1/platform/analytics", headers=world.platform_admin.auth_mfa)
    assert overview.status_code == 200
    body = overview.json()
    mine = next(c for c in body["clinics"] if c["tenant_id"] == world.tenant_a)
    assert mine["plan_key"] == "full_zuvoora" and mine["limits"]["messages_month"] == 50000
    assert body["ai_cost_usd_this_month"] >= mine["ai_usd"]
    assert "content" not in str(body) and "attendee" not in str(body)
