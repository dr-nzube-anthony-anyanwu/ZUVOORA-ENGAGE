"""Phase 3b public widget through the real API and real RLS (engage_widget role).

Covers: frame-ancestors and verified-host checks, frame tickets, conversation tokens (tamper,
wrong audience, cross-tenant forgery), messages, handover with consent, rate limits, closed and
disabled states, static asset allow-list, and staff widget settings.
"""

from __future__ import annotations

import uuid

import pytest

from app.routes import widget_public
from app.services.widget_tokens import WidgetTokens

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def site(world, admin_db):
    """Enable Clinic A's widget on a verified test host; Clinic B has none.

    The widget only serves ACTIVE clinics; platform-created clinics start as 'pending'.
    """
    host = f"www.widget-{uuid.uuid4().hex[:8]}.example.com"
    original = admin_db.execute(
        "select status::text from public.tenants where id = %s", (world.tenant_a,)
    ).fetchone()[0]
    admin_db.execute("update public.tenants set status = 'active' where id = %s", (world.tenant_a,))
    admin_db.execute(
        "insert into public.tenant_domains (tenant_id, hostname) values (%s, %s)",
        (world.tenant_a, host),
    )
    admin_db.execute(
        "update public.tenant_domains set verification_status = 'verified' where hostname = %s",
        (host,),
    )
    admin_db.execute(
        "update public.widget_configs set enabled = true, greeting = 'Hi from Clinic A' "
        "where tenant_id = %s",
        (world.tenant_a,),
    )
    key = admin_db.execute(
        "select public_key from public.widget_configs where tenant_id = %s", (world.tenant_a,)
    ).fetchone()[0]
    b_key = admin_db.execute(
        "select public_key from public.widget_configs where tenant_id = %s", (world.tenant_b,)
    ).fetchone()[0]
    yield {"host": host, "key": key, "b_key": b_key}
    admin_db.execute(
        "update public.widget_configs set enabled = false where tenant_id = %s", (world.tenant_a,)
    )
    admin_db.execute(
        "update public.tenants set status = %s where id = %s", (original, world.tenant_a)
    )


def ancestors(response) -> list[str]:
    csp = response.headers["content-security-policy"]
    return csp.split("frame-ancestors", 1)[1].strip().split()


def frame(client, key):
    return client.get("/widget/v1/frame", params={"key": key})


def config(client, key, host):
    return client.post("/api/v1/public/widget/frame-config", json={"key": key, "host": host})


def ticket_for(client, site) -> str:
    response = config(client, site["key"], site["host"])
    assert response.status_code == 200, response.text
    return response.json()["ticket"]


def start(client, site) -> str:
    response = client.post(
        "/api/v1/public/widget/session", json={"ticket": ticket_for(client, site)}
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def say(client, token, text="Are you open on Saturday?"):
    return client.post("/api/v1/public/widget/messages", json={"token": token, "text": text})


# ----- iframe page and configuration -----------------------------------------------------------
def test_frame_page_is_static_and_locked_to_verified_hosts(client, site):
    response = frame(client, site["key"])
    assert response.status_code in (200, 503)  # 503 only if the widget was not built
    if response.status_code == 200:
        assert "engage-app" in response.text
        assert "Hi from Clinic A" not in response.text  # no clinic data rendered into HTML
    csp = response.headers.get("content-security-policy", "")
    if response.status_code == 200:
        assert f"https://{site['host']}" in ancestors(response)
        assert "script-src 'self'" in csp and "default-src 'none'" in csp
        assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("key", ["0" * 32, "not-a-key", ""])
def test_unknown_key_cannot_be_framed_anywhere(client, site, key):
    response = frame(client, key)
    if response.status_code == 200:
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_config_issued_only_for_a_verified_host(client, site):
    ok = config(client, site["key"], site["host"].upper())
    assert ok.status_code == 200
    body = ok.json()
    assert body["greeting"] == "Hi from Clinic A" and body["ticket"]
    for host in ("evil.example.net", "pending.example.com", "localhost"):
        refused = config(client, site["key"], host)
        assert refused.status_code == 403, host
        assert "ticket" not in refused.text
    assert config(client, "0" * 32, site["host"]).status_code == 403
    assert (
        client.post(
            "/api/v1/public/widget/frame-config", json={"key": site["key"], "host": "a/b"}
        ).status_code
        == 422
    )


def test_disabled_widget_is_refused(client, site, world, admin_db):
    assert config(client, site["b_key"], "b-site.example.com").status_code == 403


# ----- conversation ---------------------------------------------------------------------------
def test_conversation_flow_and_storage(client, site, world, admin_db):
    token = start(client, site)
    reply = say(client, token)
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["reply"]["source"] == "fallback"  # honest "not available yet" until Phase 3c/3d
    assert body["reply"]["offer_handover"] is True
    rows = admin_db.execute(
        "select m.role::text, m.content, c.origin_host from public.messages m "
        "join public.conversations c on c.id = m.conversation_id "
        "where c.tenant_id = %s and m.content = 'Are you open on Saturday?'",
        (world.tenant_a,),
    ).fetchall()
    assert rows and rows[0][2] == site["host"]


def test_tokens_cannot_be_tampered_or_confused(client, site, world, admin_db):
    token = start(client, site)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert say(client, tampered).status_code == 401
    foreign = WidgetTokens("x" * 48).issue_conversation(world.tenant_a, uuid.uuid4(), site["host"])
    assert say(client, foreign).status_code == 401
    assert (
        say(client, ticket_for(client, site)).status_code == 401
    )  # a ticket is not a conversation
    assert (
        client.post("/api/v1/public/widget/session", json={"ticket": token}).status_code == 401
    )  # and vice versa


def test_forged_cross_tenant_token_cannot_reach_another_conversation(client, site, world, admin_db):
    """Even with the real signing key, RLS blocks a token pairing tenant B with A's conversation."""
    token = start(client, site)
    tokens: WidgetTokens = client.app.state.widget_tokens
    conversation_a = tokens.verify_conversation(token).conversation_id
    forged = tokens.issue_conversation(uuid.UUID(world.tenant_b), conversation_a, site["host"])
    before = admin_db.execute(
        "select count(*) from public.messages where conversation_id = %s", (conversation_a,)
    ).fetchone()[0]
    response = say(client, forged, "inject into A")
    assert response.status_code in (401, 403)
    after = admin_db.execute(
        "select count(*) from public.messages where conversation_id = %s", (conversation_a,)
    ).fetchone()[0]
    assert after == before


@pytest.mark.parametrize(
    "payload",
    [{"text": ""}, {"text": "x" * 1001}, {"text": "hi", "tenant_id": "x"}, {"text": "a\x00b"}],
    ids=["empty", "too-long", "extra-field", "control-char"],
)
def test_message_validation(client, site, payload):
    token = start(client, site)
    assert (
        client.post("/api/v1/public/widget/messages", json={"token": token, **payload}).status_code
        == 422
    )


def test_handover_requires_consent_and_contact(client, site, world, admin_db):
    token = start(client, site)
    url = "/api/v1/public/widget/handover"
    assert (
        client.post(
            url, json={"token": token, "phone": "+234 801 000 0000", "consent": False}
        ).status_code
        == 422
    )
    assert client.post(url, json={"token": token, "consent": True}).status_code == 422
    ok = client.post(
        url,
        json={
            "token": token,
            "name": "Test Visitor",
            "phone": "+234 801 000 0000",
            "consent": True,
        },
    )
    assert ok.status_code == 200, ok.text
    assert (
        client.post(
            url, json={"token": token, "email": "v@example.com", "consent": True}
        ).status_code
        == 409
    )
    conversation = client.app.state.widget_tokens.verify_conversation(token).conversation_id
    row = admin_db.execute(
        "select h.status::text, c.status::text from public.handover_requests h "
        "join public.conversations c on c.id = h.conversation_id where c.id = %s",
        (conversation,),
    ).fetchone()
    assert row == ("new", "handover_requested")


def test_rate_limit_per_conversation(client, site, monkeypatch):
    monkeypatch.setitem(widget_public.LIMITS, "message_conversation", (3600, 2))
    token = start(client, site)
    codes = [say(client, token, f"question {i}").status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_closed_conversation_and_disabled_widget_stop_messages(client, site, world, admin_db):
    token = start(client, site)
    conversation = client.app.state.widget_tokens.verify_conversation(token).conversation_id
    admin_db.execute(
        "update public.conversations set status = 'closed' where id = %s", (conversation,)
    )
    assert say(client, token).status_code == 409
    token2 = start(client, site)
    admin_db.execute(
        "update public.widget_configs set enabled = false where tenant_id = %s", (world.tenant_a,)
    )
    try:
        assert say(client, token2).status_code == 403
    finally:
        admin_db.execute(
            "update public.widget_configs set enabled = true where tenant_id = %s",
            (world.tenant_a,),
        )


def test_suspended_clinic_widget_stops(client, site, world, admin_db):
    token = start(client, site)
    admin_db.execute(
        "update public.tenants set status = 'suspended' where id = %s", (world.tenant_a,)
    )
    try:
        assert say(client, token).status_code == 403
        assert config(client, site["key"], site["host"]).status_code == 403
    finally:
        admin_db.execute(
            "update public.tenants set status = 'active' where id = %s", (world.tenant_a,)
        )


# ----- static assets ----------------------------------------------------------------------------
def test_static_assets_allow_list(client):
    for asset in ("loader.js", "frame.js", "frame.css"):
        response = client.get(f"/widget/v1/{asset}")
        assert response.status_code in (200, 503)  # 503 only if the widget was not built
    for bad in ("../config.py", "..%2Fmain.py", "app.py", "frame.html"):
        assert client.get(f"/widget/v1/{bad}").status_code == 404


# ----- staff settings ---------------------------------------------------------------------------
def test_widget_settings_permissions_and_key_rotation(client, site, world):
    base = f"/api/v1/tenants/{world.tenant_a}/widget"
    view = client.get(base, headers=world.a_receptionist.auth)
    assert view.status_code == 200
    assert site["host"] in view.json()["verified_hosts"]
    assert (
        client.patch(base, headers=world.a_receptionist.auth, json={"enabled": False}).status_code
        == 403
    )
    assert client.post(f"{base}/rotate-key", headers=world.a_receptionist.auth).status_code == 403
    assert (
        client.get(
            f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.b_owner.auth
        ).status_code
        == 404
    )
    old_key = view.json()["public_key"]
    rotated = client.post(f"{base}/rotate-key", headers=world.a_owner.auth)
    assert rotated.status_code == 200
    new_key = rotated.json()["public_key"]
    assert new_key != old_key
    assert config(client, old_key, site["host"]).status_code == 403
    assert config(client, new_key, site["host"]).status_code == 200
    site["key"] = new_key


def test_widget_cannot_be_enabled_without_a_verified_domain(client, world, admin_db):
    """A fresh clinic with no verified domain cannot switch the chat on."""
    tenant = str(uuid.uuid4())
    admin_db.execute(
        "insert into public.tenants (id, legal_name, display_name, status) "
        "values (%s, 'No Domain Ltd', 'No Domain', 'active')",
        (tenant,),
    )
    admin_db.execute(
        "insert into public.tenant_memberships (tenant_id, user_id, role) values (%s, %s, 'owner')",
        (tenant, world.outsider.id),
    )
    try:
        response = client.patch(
            f"/api/v1/tenants/{tenant}/widget", headers=world.outsider.auth, json={"enabled": True}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_verified_domain"
    finally:
        admin_db.execute("delete from public.tenants where id = %s", (tenant,))
