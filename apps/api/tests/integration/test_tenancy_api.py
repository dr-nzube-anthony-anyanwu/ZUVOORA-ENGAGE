"""Phase 1 exit-gate tests through the real API, real Supabase Auth tokens and real RLS.

Covers: anonymous denial, cross-tenant read/write denial, browser-supplied tenant ids,
role restrictions, immediate revocation, tenant suspension, MFA-gated platform actions,
owner protection, the audit trail and Data API isolation.
"""

from __future__ import annotations

import secrets
import uuid

import httpx
import psycopg
import pytest

pytestmark = pytest.mark.integration


def test_backend_connection_role_fails_closed(stack, world):
    """If the API ever skipped `SET LOCAL ROLE engage_app`, it would get errors, not data."""
    with psycopg.connect(stack["ENGAGE_API_DB_URL"]) as conn:
        for table in ("tenants", "tenant_memberships", "clinic_profiles", "audit_events"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"select * from public.{table}")  # noqa: S608
            conn.rollback()


# ----- authentication ------------------------------------------------------------------------
def test_unauthenticated_requests_rejected(client, stack, world):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    # The public (publishable) key is not a user session.
    publishable = {"Authorization": f"Bearer {stack['PUBLISHABLE_KEY']}"}
    assert client.get("/api/v1/me", headers=publishable).status_code == 401
    response = client.get(f"/api/v1/tenants/{world.tenant_a}")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_public_self_signup_is_disabled(stack):
    response = httpx.post(
        f"{stack['API_URL']}/auth/v1/signup",
        headers={"apikey": stack["PUBLISHABLE_KEY"]},
        json={
            "email": f"self.{uuid.uuid4().hex[:8]}@example.com",
            "password": secrets.token_urlsafe(18) + "aA1",
        },
        timeout=10,
    )
    assert response.status_code == 422
    assert response.json().get("error_code") == "signup_disabled"


def test_supabase_data_api_cannot_reach_engage_tables(stack, world):
    """Even with a valid owner session, PostgREST cannot read or write Engage tables."""
    headers = {
        "apikey": stack["PUBLISHABLE_KEY"],
        "Authorization": f"Bearer {world.a_owner.token}",
    }
    for table in ("tenants", "tenant_memberships", "clinic_profiles", "audit_events"):
        response = httpx.get(f"{stack['API_URL']}/rest/v1/{table}", headers=headers, timeout=10)
        assert response.status_code != 200, f"Data API exposed {table}"
    write = httpx.post(
        f"{stack['API_URL']}/rest/v1/audit_events",
        headers=headers,
        json={"actor_user_id": str(world.a_owner.id), "tenant_id": world.tenant_a,
              "action": "bypass.attempt"},
        timeout=10,
    )
    assert write.status_code not in (200, 201)


# ----- tenant isolation ----------------------------------------------------------------------
def test_me_lists_only_own_memberships(client, world):
    body = client.get("/api/v1/me", headers=world.a_owner.auth).json()
    tenant_ids = {m["tenant_id"] for m in body["memberships"]}
    assert tenant_ids == {world.tenant_a}
    assert body["is_platform_admin"] is False


def test_cross_tenant_reads_are_indistinguishable_from_missing(client, world):
    other = client.get(f"/api/v1/tenants/{world.tenant_b}", headers=world.a_owner.auth)
    missing = client.get(f"/api/v1/tenants/{uuid.uuid4()}", headers=world.a_owner.auth)
    assert other.status_code == missing.status_code == 404
    assert other.json()["error"]["code"] == missing.json()["error"]["code"] == "not_found"
    assert client.get(
        f"/api/v1/tenants/{world.tenant_b}/members", headers=world.a_owner.auth
    ).status_code == 404


def test_cross_tenant_writes_denied(client, world):
    b_members = client.get(f"/api/v1/tenants/{world.tenant_b}/members", headers=world.b_owner.auth)
    b_owner_membership = b_members.json()[0]["membership_id"]
    assert client.patch(
        f"/api/v1/tenants/{world.tenant_b}/members/{b_owner_membership}",
        headers=world.a_owner.auth, json={"role": "viewer"},
    ).status_code == 404
    assert client.post(
        f"/api/v1/tenants/{world.tenant_b}/members",
        headers=world.a_owner.auth, json={"email": world.outsider.email, "role": "owner"},
    ).status_code == 404


def test_browser_supplied_tenant_id_cannot_change_tenant(client, world):
    # Extra authorisation fields in the body are rejected outright.
    smuggled = client.post(
        f"/api/v1/tenants/{world.tenant_a}/members",
        headers=world.a_owner.auth,
        json={"email": world.outsider.email, "role": "viewer", "tenant_id": world.tenant_b},
    )
    assert smuggled.status_code == 422
    # A tenant-B membership id addressed through tenant A's path is not found.
    b_members = client.get(f"/api/v1/tenants/{world.tenant_b}/members", headers=world.b_owner.auth)
    b_membership = b_members.json()[0]["membership_id"]
    assert client.post(
        f"/api/v1/tenants/{world.tenant_a}/members/{b_membership}/revoke",
        headers=world.a_owner.auth,
    ).status_code == 404
    # B's owner is untouched.
    still = client.get(f"/api/v1/tenants/{world.tenant_b}", headers=world.b_owner.auth)
    assert still.status_code == 200


# ----- roles -----------------------------------------------------------------------------------
def test_receptionist_cannot_manage_members_or_use_platform(client, world):
    rec = world.a_receptionist.auth
    assert client.get(f"/api/v1/tenants/{world.tenant_a}", headers=rec).status_code == 200
    assert client.get(f"/api/v1/tenants/{world.tenant_a}/members", headers=rec).status_code == 403
    assert client.post(
        f"/api/v1/tenants/{world.tenant_a}/members", headers=rec,
        json={"email": world.outsider.email, "role": "viewer"},
    ).status_code == 403
    assert client.get("/api/v1/platform/tenants", headers=rec).status_code == 403
    assert client.post(
        "/api/v1/platform/tenants", headers=rec,
        json={"legal_name": "Rogue Ltd", "display_name": "Rogue", "owner_email": "x@example.com"},
    ).status_code == 403


def test_admin_cannot_grant_or_remove_owner(client, world):
    adm = world.a_admin.auth
    members = client.get(f"/api/v1/tenants/{world.tenant_a}/members", headers=adm).json()
    owner_membership = next(m for m in members if m["role"] == "owner")["membership_id"]
    assert client.post(
        f"/api/v1/tenants/{world.tenant_a}/members", headers=adm,
        json={"email": world.outsider.email, "role": "owner"},
    ).status_code == 403
    assert client.patch(
        f"/api/v1/tenants/{world.tenant_a}/members/{owner_membership}",
        headers=adm, json={"role": "viewer"},
    ).status_code == 403
    assert client.post(
        f"/api/v1/tenants/{world.tenant_a}/members/{owner_membership}/revoke", headers=adm
    ).status_code == 403


def test_last_owner_cannot_be_removed(client, world):
    members = client.get(
        f"/api/v1/tenants/{world.tenant_a}/members", headers=world.a_owner.auth
    ).json()
    own = next(m for m in members if m["user_id"] == str(world.a_owner.id))["membership_id"]
    for response in (
        client.patch(f"/api/v1/tenants/{world.tenant_a}/members/{own}",
                     headers=world.a_owner.auth, json={"role": "admin"}),
        client.post(f"/api/v1/tenants/{world.tenant_a}/members/{own}/revoke",
                    headers=world.a_owner.auth),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "last_owner"


# ----- revocation and suspension ---------------------------------------------------------------
def test_revoked_member_loses_access_immediately(client, gotrue, world):
    member = gotrue.create_user("revokee")
    added = client.post(
        f"/api/v1/tenants/{world.tenant_a}/members", headers=world.a_owner.auth,
        json={"email": member.email, "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert client.get(f"/api/v1/tenants/{world.tenant_a}", headers=member.auth).status_code == 200

    revoked = client.post(
        f"/api/v1/tenants/{world.tenant_a}/members/{added.json()['membership_id']}/revoke",
        headers=world.a_owner.auth,
    )
    assert revoked.status_code == 200 and revoked.json()["is_active"] is False

    # Same, still-unexpired token: access is gone on the very next request.
    assert client.get(f"/api/v1/tenants/{world.tenant_a}", headers=member.auth).status_code == 404
    me = client.get("/api/v1/me", headers=member.auth).json()
    assert me["memberships"][0]["accessible"] is False


def test_suspended_tenant_is_blocked_then_restored(client, gotrue, world):
    owner = gotrue.create_user("c-owner")
    created = client.post(
        "/api/v1/platform/tenants", headers=world.platform_admin.auth_mfa,
        json={"legal_name": "Clinic C Test Ltd", "display_name": "Clinic C",
              "owner_email": owner.email},
    )
    assert created.status_code == 201, created.text
    tenant_c = created.json()["tenant"]["id"]
    world.created_tenants.append(tenant_c)
    assert client.get(f"/api/v1/tenants/{tenant_c}", headers=owner.auth).status_code == 200

    suspended = client.post(
        f"/api/v1/platform/tenants/{tenant_c}/suspend", headers=world.platform_admin.auth_mfa
    )
    assert suspended.status_code == 200 and suspended.json()["status"] == "suspended"
    assert client.get(f"/api/v1/tenants/{tenant_c}", headers=owner.auth).status_code == 404
    assert client.get(f"/api/v1/tenants/{tenant_c}/members", headers=owner.auth).status_code == 404
    me = client.get("/api/v1/me", headers=owner.auth).json()
    assert me["memberships"][0]["accessible"] is False

    restored = client.post(
        f"/api/v1/platform/tenants/{tenant_c}/reactivate", headers=world.platform_admin.auth_mfa
    )
    assert restored.status_code == 200
    assert client.get(f"/api/v1/tenants/{tenant_c}", headers=owner.auth).status_code == 200


# ----- platform admin and MFA ------------------------------------------------------------------
def test_platform_actions_require_mfa(client, world):
    without_mfa = client.get("/api/v1/platform/tenants", headers=world.platform_admin.auth)
    assert without_mfa.status_code == 403
    assert without_mfa.json()["error"]["code"] == "mfa_required"
    with_mfa = client.get("/api/v1/platform/tenants", headers=world.platform_admin.auth_mfa)
    assert with_mfa.status_code == 200
    me = client.get("/api/v1/me", headers=world.platform_admin.auth_mfa).json()
    assert me["is_platform_admin"] is True and me["mfa_verified"] is True


def test_mfa_alone_does_not_grant_platform_powers(client, gotrue, world):
    gotrue.enable_mfa(world.outsider)
    response = client.get("/api/v1/platform/tenants", headers=world.outsider.auth_mfa)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_new_owner_receives_invitation(client, stack, world):
    email = f"new-owner.{uuid.uuid4().hex[:10]}@example.com"
    created = client.post(
        "/api/v1/platform/tenants", headers=world.platform_admin.auth_mfa,
        json={"legal_name": "Clinic D Test Ltd", "display_name": "Clinic D", "owner_email": email},
    )
    assert created.status_code == 201, created.text
    world.created_tenants.append(created.json()["tenant"]["id"])
    assert created.json()["owner_invited"] is True


# ----- audit -----------------------------------------------------------------------------------
def test_privileged_actions_are_audited(client, admin_db, world):
    rows = admin_db.execute(
        """select action, actor_user_id, request_id from public.audit_events
           where tenant_id = %s order by id""",
        (world.tenant_a,),
    ).fetchall()
    actions = [row[0] for row in rows]
    assert "tenant.created" in actions
    assert actions.count("membership.invited") >= 2
    assert all(row[2] for row in rows), "every audit event carries a request id"
    created_by = next(row[1] for row in rows if row[0] == "tenant.created")
    assert created_by == world.platform_admin.id


def test_audit_events_cannot_be_altered(admin_db, world):
    with pytest.raises(Exception, match="append-only"):
        admin_db.execute(
            "update public.audit_events set action = 'tampered.event' where tenant_id = %s",
            (world.tenant_a,),
        )
