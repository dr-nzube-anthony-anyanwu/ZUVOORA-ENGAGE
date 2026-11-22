"""Phase 4b: connecting a scheduling account and choosing appointment types (fake provider)."""

from __future__ import annotations

import pytest

from app.services.scheduling.base import ProviderUnavailable
from app.services.secrets_box import Sealed
from tests.scheduling_fakes import REVOKED_KEY, VALID_KEY, FakeWorld

pytestmark = pytest.mark.integration


@pytest.fixture
def provider(app_state):
    world = FakeWorld()
    app_state("scheduling_providers", world)
    return world


@pytest.fixture(autouse=True)
def clean_connections(admin_db, world):
    yield
    admin_db.execute(
        "update public.scheduling_connections set status = 'disconnected' "
        "where tenant_id = any(%s) and status <> 'disconnected'",
        ([world.tenant_a, world.tenant_b],),
    )


def base(tenant) -> str:
    return f"/api/v1/tenants/{tenant}/scheduling"


def connect(client, user, tenant, key=VALID_KEY):
    return client.post(
        f"{base(tenant)}/connect", headers=user.auth, json={"provider": "calcom", "api_key": key}
    )


def test_owner_connects_and_the_key_is_never_returned(client, world, provider, admin_db):
    response = connect(client, world.a_owner, world.tenant_a)
    assert response.status_code == 200, response.text
    assert VALID_KEY not in response.text
    connection = response.json()["connection"]
    assert connection["account_label"] == "dr-ada"
    assert connection["credential_hint"] == VALID_KEY[-4:]
    assert provider.credentials_seen == [VALID_KEY]  # verified with the provider first

    stored = admin_db.execute(
        "select credential_ciphertext, credential_key_id from public.scheduling_connections "
        "where id = %s",
        (connection["id"],),
    ).fetchone()
    assert VALID_KEY.encode() not in bytes(stored[0])
    box = client.app.state.secrets_box
    assert (
        box.open(
            Sealed(bytes(stored[0]), stored[1]),
            purpose="scheduling",
            tenant_id=world.tenant_a,
            record_id=connection["id"],
        )
        == VALID_KEY
    )

    audit = admin_db.execute(
        "select metadata::text from public.audit_events where action = 'scheduling.connected' "
        "and target_id = %s",
        (connection["id"],),
    ).fetchone()[0]
    assert VALID_KEY not in audit and VALID_KEY[-4:] not in audit

    assert connect(client, world.a_owner, world.tenant_a).status_code == 409  # one per clinic


def test_bad_keys_are_refused_and_nothing_is_stored(client, world, provider, admin_db):
    bad_format = connect(client, world.a_owner, world.tenant_a, key="not-a-key-123")
    assert bad_format.status_code == 422 and provider.credentials_seen == []
    rejected = connect(client, world.a_owner, world.tenant_a, key=REVOKED_KEY)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "credential_rejected"
    provider.fail_next = ProviderUnavailable("timeout")
    assert connect(client, world.a_owner, world.tenant_a).status_code == 503
    count = admin_db.execute(
        "select count(*) from public.scheduling_connections where tenant_id = %s "
        "and status <> 'disconnected'",
        (world.tenant_a,),
    ).fetchone()[0]
    assert count == 0


def test_only_owners_and_admins_connect(client, world, provider):
    assert connect(client, world.a_receptionist, world.tenant_a).status_code == 403
    assert connect(client, world.b_owner, world.tenant_a).status_code == 404
    assert connect(client, world.outsider, world.tenant_a).status_code == 404
    assert provider.credentials_seen == []  # refused before any provider call


def test_choosing_appointment_types(client, world, provider):
    connect(client, world.a_admin, world.tenant_a)
    listed = client.get(f"{base(world.tenant_a)}/provider-event-types", headers=world.a_admin.auth)
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == ["101", "102", "103"]
    assert not any(t["offered"] for t in listed.json())

    saved = client.put(
        f"{base(world.tenant_a)}/appointment-types",
        headers=world.a_admin.auth,
        json={
            "items": [
                {"provider_event_type_id": "101", "name": "Full eye check"},
                {"provider_event_type_id": "102", "enabled": False},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    types = saved.json()["appointment_types"]
    assert [(t["name"], t["duration_minutes"], t["enabled"]) for t in types] == [
        ("Full eye check", 45, True),
        ("Contact lens fitting", 30, False),
    ]
    assert types[1]["requires_confirmation"] is True  # snapshot from the provider

    unknown = client.put(
        f"{base(world.tenant_a)}/appointment-types",
        headers=world.a_admin.auth,
        json={"items": [{"provider_event_type_id": "999"}]},
    )
    assert unknown.status_code == 422
    assert (
        client.put(
            f"{base(world.tenant_a)}/appointment-types",
            headers=world.a_receptionist.auth,
            json={"items": []},
        ).status_code
        == 403
    )
    viewer_view = client.get(base(world.tenant_a), headers=world.a_receptionist.auth)
    assert len(viewer_view.json()["appointment_types"]) == 2


def test_revoked_key_marks_the_connection_failing(client, world, provider):
    connect(client, world.a_owner, world.tenant_a)
    provider.revoked.add(VALID_KEY)
    listed = client.get(f"{base(world.tenant_a)}/provider-event-types", headers=world.a_owner.auth)
    assert listed.status_code == 422
    state = client.get(base(world.tenant_a), headers=world.a_owner.auth).json()["connection"]
    assert state["status"] == "failing" and state["last_error"].startswith("credential_rejected")


def test_disconnect_erases_the_credential(client, world, provider, admin_db):
    connection = connect(client, world.a_owner, world.tenant_a).json()["connection"]
    response = client.post(f"{base(world.tenant_a)}/disconnect", headers=world.a_owner.auth)
    assert response.status_code == 200 and response.json()["connection"] is None
    stored = admin_db.execute(
        "select credential_ciphertext, status from public.scheduling_connections where id = %s",
        (connection["id"],),
    ).fetchone()
    assert tuple(stored) == (None, "disconnected")
    assert (
        client.get(
            f"{base(world.tenant_a)}/provider-event-types", headers=world.a_owner.auth
        ).status_code
        == 409
    )


def test_a_credential_copied_to_another_clinic_cannot_be_used(client, world, provider, admin_db):
    a = connect(client, world.a_owner, world.tenant_a).json()["connection"]
    b = connect(client, world.b_owner, world.tenant_b).json()["connection"]
    # Simulate a database-level attack: copy Clinic A's encrypted key into Clinic B's row.
    admin_db.execute(
        "update public.scheduling_connections set credential_ciphertext = "
        "(select credential_ciphertext from public.scheduling_connections where id = %s), "
        "credential_key_id = (select credential_key_id from public.scheduling_connections "
        "where id = %s) where id = %s",
        (a["id"], a["id"], b["id"]),
    )
    provider.credentials_seen.clear()
    response = client.get(
        f"{base(world.tenant_b)}/provider-event-types", headers=world.b_owner.auth
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "credential_unreadable"
    assert provider.credentials_seen == []  # Clinic A's key was never used for Clinic B
