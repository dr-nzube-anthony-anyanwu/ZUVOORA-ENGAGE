"""Phase 3e: staff inbox and handover lifecycle through the real API and RLS."""

from __future__ import annotations

import pytest

from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration


def visitor_session(client, world, chat) -> str:
    key = client.get(f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.a_owner.auth).json()[
        "public_key"
    ]
    config = client.post(
        "/api/v1/public/widget/frame-config", json={"key": key, "host": chat["host"]}
    )
    session = client.post("/api/v1/public/widget/session", json={"ticket": config.json()["ticket"]})
    return session.json()["token"]


@pytest.fixture(scope="module")
def viewer(client, gotrue, world):
    user = gotrue.create_user("a-viewer")
    response = client.post(
        f"/api/v1/tenants/{world.tenant_a}/members",
        headers=world.a_owner.auth,
        json={"email": user.email, "role": "viewer"},
    )
    assert response.status_code == 201, response.text
    return user


@pytest.fixture
def handover(client, world, chat):
    """A fresh visitor conversation with a question, an answer and a handover request."""
    token = visitor_session(client, world, chat)
    said = client.post(
        "/api/v1/public/widget/messages",
        json={"token": token, "text": "Can someone call me about lens options?"},
    )
    assert said.status_code == 200, said.text
    asked = client.post(
        "/api/v1/public/widget/handover",
        json={"token": token, "name": "Ada Test", "phone": "+234 801 000 1234", "consent": True},
    )
    assert asked.status_code == 200, asked.text
    listed = client.get(
        f"/api/v1/tenants/{world.tenant_a}/handovers", headers=world.a_receptionist.auth
    ).json()
    item = next(
        h for h in listed if h["contact_phone"] == "+234 801 000 1234" and h["status"] == "new"
    )
    return {"token": token, **item}


def base(world) -> str:
    return f"/api/v1/tenants/{world.tenant_a}"


def test_front_desk_sees_new_handovers_with_contact_details(client, world, handover):
    summary = client.get(f"{base(world)}/inbox/summary", headers=world.a_receptionist.auth)
    assert summary.status_code == 200
    assert summary.json()["new"] >= 1
    assert handover["contact_name"] == "Ada Test"
    assert handover["resolved_by_me"] is False


def test_transcript_is_shown_and_its_viewing_audited(client, world, handover, admin_db):
    path = f"{base(world)}/conversations/{handover['conversation_id']}"
    detail = client.get(path, headers=world.a_admin.auth)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["visitor", "assistant", "system"]
    assert body["messages"][0]["content"] == "Can someone call me about lens options?"
    assert body["handover"]["id"] == handover["id"]
    assert body["conversation"]["status"] == "handover_requested"
    audited = admin_db.execute(
        "select count(*) from public.audit_events where action = 'conversation.viewed' "
        "and target_id = %s and actor_user_id = %s",
        (handover["conversation_id"], world.a_admin.id),
    ).fetchone()[0]
    assert audited == 1


def test_handover_lifecycle_is_stamped_and_audited(client, world, handover, admin_db):
    path = f"{base(world)}/handovers/{handover['id']}"
    auth = world.a_receptionist.auth
    started = client.patch(path, headers=auth, json={"status": "in_progress"})
    assert started.status_code == 200 and started.json()["status"] == "in_progress"
    done = client.patch(path, headers=auth, json={"status": "resolved"})
    assert done.json()["status"] == "resolved"
    assert done.json()["resolved_at"] is not None
    assert done.json()["resolved_by_me"] is True

    open_ids = [h["id"] for h in client.get(f"{base(world)}/handovers", headers=auth).json()]
    resolved_ids = [
        h["id"] for h in client.get(f"{base(world)}/handovers?view=resolved", headers=auth).json()
    ]
    assert handover["id"] not in open_ids
    assert handover["id"] in resolved_ids

    reopened = client.patch(path, headers=auth, json={"status": "new"})
    assert reopened.json()["resolved_at"] is None
    changes = admin_db.execute(
        "select metadata->>'from', metadata->>'to' from public.audit_events "
        "where action = 'handover.status_changed' and target_id = %s order by id",
        (handover["id"],),
    ).fetchall()
    assert [tuple(c) for c in changes] == [
        ("new", "in_progress"),
        ("in_progress", "resolved"),
        ("resolved", "new"),
    ]


def test_unchanged_status_is_not_audited_twice(client, world, handover, admin_db):
    path = f"{base(world)}/handovers/{handover['id']}"
    for _ in range(2):
        client.patch(path, headers=world.a_owner.auth, json={"status": "in_progress"})
    count = admin_db.execute(
        "select count(*) from public.audit_events where action = 'handover.status_changed' "
        "and target_id = %s",
        (handover["id"],),
    ).fetchone()[0]
    assert count == 1


def test_closing_a_conversation_stops_the_visitor(client, world, handover):
    path = f"{base(world)}/conversations/{handover['conversation_id']}/close"
    closed = client.post(path, headers=world.a_receptionist.auth)
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    again = client.post(path, headers=world.a_receptionist.auth)
    assert again.status_code == 409
    reply = client.post(
        "/api/v1/public/widget/messages", json={"token": handover["token"], "text": "hello?"}
    )
    assert reply.status_code == 409
    assert reply.json()["error"]["code"] == "conversation_closed"


def test_invalid_status_is_rejected(client, world, handover):
    response = client.patch(
        f"{base(world)}/handovers/{handover['id']}",
        headers=world.a_owner.auth,
        json={"status": "deleted"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/inbox/summary",
        "/handovers",
        "/conversations",
        "/conversations/{conversation_id}",
    ],
)
def test_viewer_cannot_open_the_inbox(client, world, handover, viewer, path):
    url = base(world) + path.format(conversation_id=handover["conversation_id"])
    assert client.get(url, headers=viewer.auth).status_code == 403


def test_viewer_cannot_change_a_handover(client, world, handover, viewer):
    response = client.patch(
        f"{base(world)}/handovers/{handover['id']}",
        headers=viewer.auth,
        json={"status": "resolved"},
    )
    assert response.status_code == 403


def test_other_clinics_and_outsiders_get_not_found(client, world, handover):
    a_detail = f"{base(world)}/conversations/{handover['conversation_id']}"
    assert client.get(a_detail, headers=world.b_owner.auth).status_code == 404
    assert client.get(a_detail, headers=world.outsider.auth).status_code == 404
    # Platform admins are not clinic members: no access to patient conversations.
    assert client.get(a_detail, headers=world.platform_admin.auth_mfa).status_code == 404
    # Clinic B's own URL with Clinic A's ids.
    b_base = f"/api/v1/tenants/{world.tenant_b}"
    assert (
        client.get(
            f"{b_base}/conversations/{handover['conversation_id']}", headers=world.b_owner.auth
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{b_base}/handovers/{handover['id']}",
            headers=world.b_owner.auth,
            json={"status": "resolved"},
        ).status_code
        == 404
    )
    assert all(
        h["id"] != handover["id"]
        for h in client.get(f"{b_base}/handovers?view=all", headers=world.b_owner.auth).json()
    )


def test_conversation_list_shows_previews(client, world, handover):
    listed = client.get(f"{base(world)}/conversations", headers=world.a_owner.auth)
    assert listed.status_code == 200
    item = next(c for c in listed.json() if c["id"] == handover["conversation_id"])
    assert item["preview"] == "Can someone call me about lens options?"
    assert item["handover_status"] == "new"
