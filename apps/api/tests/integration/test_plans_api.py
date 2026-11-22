"""Phase 5a: plans, subscriptions and server-side gates through the real API (direct API calls)."""

from __future__ import annotations

import pytest

from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)
from tests.integration.test_booking_api import clinic, visitor  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def restore_plans(admin_db, world):
    yield
    admin_db.execute("delete from public.tenant_overrides where tenant_id = any(%s)",
                     ([world.tenant_a, world.tenant_b],))
    admin_db.execute("update public.tenant_subscriptions set plan_key = 'full_zuvoora', "
                     "status = 'active' where tenant_id = any(%s)", ([world.tenant_a, world.tenant_b],))


def set_plan(client, world, tenant, plan, status="active"):
    response = client.put(f"/api/v1/platform/tenants/{tenant}/subscription",
                          headers=world.platform_admin.auth_mfa,
                          json={"plan_key": plan, "status": status})
    assert response.status_code == 200, response.text
    return response.json()


def override(client, world, tenant, **body):
    response = client.put(f"/api/v1/platform/tenants/{tenant}/overrides",
                          headers=world.platform_admin.auth_mfa, json={"reason": "test", **body})
    assert response.status_code == 200, response.text


# ----- who may see and change plans ---------------------------------------------------------------
def test_clinic_plan_view_is_for_owners_and_admins(client, world):
    response = client.get(f"/api/v1/tenants/{world.tenant_a}/plan", headers=world.a_owner.auth)
    assert response.status_code == 200
    body = response.json()
    assert body["plan_key"] == "full_zuvoora" and body["limits"]["domains"] == 10
    whatsapp = next(f for f in body["features"] if f["key"] == "whatsapp")
    assert whatsapp["available"] is False and whatsapp["included"] is True  # sold, not built
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/plan",
                      headers=world.a_receptionist.auth).status_code == 403
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/plan",
                      headers=world.b_owner.auth).status_code == 404


def test_only_mfa_platform_admins_manage_plans(client, world, admin_db):
    assert client.get("/api/v1/platform/plans", headers=world.a_owner.auth).status_code == 403
    assert client.get("/api/v1/platform/plans", headers=world.platform_admin.auth).status_code == 403  # no MFA
    assert client.put(f"/api/v1/platform/tenants/{world.tenant_a}/subscription",
                      headers=world.a_owner.auth,
                      json={"plan_key": "premium", "status": "active"}).status_code == 403
    catalogue = client.get("/api/v1/platform/plans", headers=world.platform_admin.auth_mfa).json()
    assert [p["key"] for p in catalogue["plans"]] == ["essentials", "professional", "premium", "full_zuvoora"]
    changed = set_plan(client, world, world.tenant_a, "premium")
    assert changed["plan_key"] == "premium"
    audit = admin_db.execute(
        "select metadata->'to'->>'plan_key' from public.audit_events "
        "where action = 'subscription.changed' and tenant_id = %s order by id desc limit 1",
        (world.tenant_a,)).fetchone()[0]
    assert audit == "premium"
    assert client.put(f"/api/v1/platform/tenants/{world.tenant_a}/subscription",
                      headers=world.platform_admin.auth_mfa,
                      json={"plan_key": "gold", "status": "active"}).status_code == 422


def test_plan_change_keeps_identity_data_and_widget(client, world, admin_db):
    before = admin_db.execute(
        "select w.public_key, (select count(*) from public.faqs f where f.tenant_id = w.tenant_id) "
        "from public.widget_configs w where w.tenant_id = %s", (world.tenant_a,)).fetchone()
    for plan in ("essentials", "premium", "full_zuvoora"):
        set_plan(client, world, world.tenant_a, plan)
    after = admin_db.execute(
        "select w.public_key, (select count(*) from public.faqs f where f.tenant_id = w.tenant_id) "
        "from public.widget_configs w where w.tenant_id = %s", (world.tenant_a,)).fetchone()
    assert tuple(after) == tuple(before)


# ----- feature gates (direct API calls) -----------------------------------------------------------
def test_reminders_are_refused_outside_the_plan(client, world, clinic):  # noqa: F811
    set_plan(client, world, world.tenant_a, "essentials")
    response = client.patch(f"/api/v1/tenants/{world.tenant_a}/scheduling",
                            headers=world.a_owner.auth, json={"reminder_2h": True})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "feature_not_in_plan"
    assert "Essentials" in response.json()["error"]["message"]
    set_plan(client, world, world.tenant_a, "professional")
    assert client.patch(f"/api/v1/tenants/{world.tenant_a}/scheduling",
                        headers=world.a_owner.auth, json={"reminder_2h": True}).status_code == 200


def test_booking_gate_covers_staff_and_widget_endpoints(client, world, chat, clinic):  # noqa: F811
    override(client, world, world.tenant_a, kind="feature", key="booking", feature_enabled=False)
    base = f"/api/v1/tenants/{world.tenant_a}/scheduling"
    assert client.get(f"{base}/provider-event-types", headers=world.a_owner.auth).status_code == 403
    assert client.post(f"{base}/webhook", headers=world.a_owner.auth).status_code == 403
    token = visitor(client, world, chat)
    options = client.post("/api/v1/public/widget/booking/options", json={"token": token}).json()
    assert options == {"available": False, "types": []}
    slots = client.post("/api/v1/public/widget/booking/slots",
                        json={"token": token, "appointment_type_id": clinic["exam"]})
    assert slots.status_code == 403 and slots.json()["error"]["code"] == "booking_unavailable"
    assert clinic["provider"].bookings == []


def test_cancelled_subscription_stops_the_widget_but_keeps_data(client, world, chat, admin_db):  # noqa: F811
    key = client.get(f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.a_owner.auth).json()["public_key"]
    config = {"key": key, "host": chat["host"]}
    assert client.post("/api/v1/public/widget/frame-config", json=config).status_code == 200
    set_plan(client, world, world.tenant_a, "professional", status="cancelled")
    assert client.post("/api/v1/public/widget/frame-config", json=config).status_code == 403
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/faqs", headers=world.a_owner.auth).status_code == 200
    set_plan(client, world, world.tenant_a, "professional", status="active")
    assert client.post("/api/v1/public/widget/frame-config", json=config).status_code == 200


# ----- limits --------------------------------------------------------------------------------------
def test_domain_limit_comes_from_the_plan(client, world, admin_db):
    current = admin_db.execute("select count(*) from public.tenant_domains where tenant_id = %s "
                               "and removed_at is null", (world.tenant_b,)).fetchone()[0]
    override(client, world, world.tenant_b, kind="limit", key="domains", limit_value=current)
    response = client.post(f"/api/v1/tenants/{world.tenant_b}/domains", headers=world.b_owner.auth,
                           json={"hostname": "www.limit-test.example.com"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "plan_limit_reached"


def test_staff_seat_limit_is_checked_before_any_invitation(client, world, gotrue, admin_db):
    seats = admin_db.execute("select count(*) from public.tenant_memberships where tenant_id = %s "
                             "and is_active", (world.tenant_b,)).fetchone()[0]
    override(client, world, world.tenant_b, kind="limit", key="staff_seats", limit_value=seats)
    newcomer = "seat-limit-test@example.com"
    response = client.post(f"/api/v1/tenants/{world.tenant_b}/members", headers=world.b_owner.auth,
                           json={"email": newcomer, "role": "viewer"})
    assert response.status_code == 409
    invited = admin_db.execute("select count(*) from auth.users where email = %s", (newcomer,)).fetchone()[0]
    assert invited == 0  # refused before any invitation was sent


def test_new_clinics_start_on_the_requested_plan(client, world, gotrue):
    owner = gotrue.create_user("plan-owner")
    created = client.post("/api/v1/platform/tenants", headers=world.platform_admin.auth_mfa,
                          json={"legal_name": "Plan Test Ltd", "display_name": "Plan Test",
                                "owner_email": owner.email, "plan_key": "professional"})
    assert created.status_code == 201
    tenant = created.json()["tenant"]["id"]
    world.created_tenants.append(tenant)
    plan = client.get(f"/api/v1/tenants/{tenant}/plan", headers=owner.auth).json()
    assert (plan["plan_key"], plan["status"]) == ("professional", "active")
    bad = client.post("/api/v1/platform/tenants", headers=world.platform_admin.auth_mfa,
                      json={"legal_name": "X Ltd", "display_name": "X", "owner_email": owner.email,
                            "plan_key": "gold"})
    assert bad.status_code == 422
