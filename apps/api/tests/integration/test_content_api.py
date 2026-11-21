"""Phase 2a clinic content through the real API, real Supabase Auth tokens and real RLS.

Covers: role permissions, cross-tenant read/write denial (guessed ids, swapped tenant in the
path), draft/publish lifecycle with optimistic locking, archive/restore, validation, limits,
audit events and Data API isolation for the new tables.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

pytestmark = pytest.mark.integration

WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HOURS = {
    "weekly": [
        {"day": d, "ranges": [{"open": "08:00", "close": "17:00"}]} if d != "sun"
        else {"day": d, "closed": True}
        for d in WEEK
    ],
    "exceptions": [{"date": "2026-12-25", "closed": True, "note": "Christmas Day"}],
}


def faq(question: str = "Do you accept walk-in patients?") -> dict:
    return {"content": {"question": question, "answer": "Yes, from 8am. Please bring your ID."}}


def url(tenant: str, path: str) -> str:
    return f"/api/v1/tenants/{tenant}/{path}"


def create(client, user, tenant, path="faqs", body=None):
    response = client.post(url(tenant, path), headers=user.auth, json=body or faq())
    assert response.status_code == 201, response.text
    return response.json()


# ----- lifecycle -------------------------------------------------------------------------------
def test_draft_publish_edit_cycle_keeps_published_copy_live(client, world):
    item = create(client, world.a_owner, world.tenant_a)
    assert (item["state"], item["revision"], item["published"]) == ("draft", 1, None)
    item_url = url(world.tenant_a, f"faqs/{item['id']}")

    published = client.post(f"{item_url}/publish", headers=world.a_owner.auth, json={"revision": 1})
    assert published.status_code == 200, published.text
    assert published.json()["state"] == "published"
    assert published.json()["published"]["question"] == "Do you accept walk-in patients?"

    edited = client.patch(
        f"{item_url}/draft", headers=world.a_admin.auth,
        json={"revision": 1, "content": {"question": "Do you accept walk-ins on Saturdays?",
                                         "answer": "Yes, 9am to 12pm."}},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["state"], body["revision"], body["published_revision"]) == (
        "changes_pending", 2, 1)
    assert body["published"]["question"] == "Do you accept walk-in patients?"  # still live

    republished = client.post(f"{item_url}/publish", headers=world.a_admin.auth,
                              json={"revision": 2})
    assert republished.json()["published"]["question"] == "Do you accept walk-ins on Saturdays?"
    again = client.post(f"{item_url}/publish", headers=world.a_admin.auth, json={"revision": 2})
    assert again.status_code == 200  # idempotent


def test_stale_revision_cannot_overwrite_or_publish(client, world):
    item = create(client, world.a_owner, world.tenant_a)
    item_url = url(world.tenant_a, f"faqs/{item['id']}")
    first = client.patch(f"{item_url}/draft", headers=world.a_owner.auth,
                         json={"revision": 1, "content": faq("Editor one's change?")["content"]})
    assert first.status_code == 200
    stale = client.patch(f"{item_url}/draft", headers=world.a_admin.auth,
                         json={"revision": 1, "content": faq("Editor two's change?")["content"]})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"
    # Publishing a revision the reviewer never saw is refused.
    unseen = client.post(f"{item_url}/publish", headers=world.a_owner.auth, json={"revision": 1})
    assert unseen.status_code == 409
    current = client.get(item_url, headers=world.a_owner.auth).json()
    assert current["draft"]["question"] == "Editor one's change?"
    assert current["published"] is None


def test_archive_unpublishes_and_blocks_edits_until_restored(client, world):
    item = create(client, world.a_owner, world.tenant_a)
    item_url = url(world.tenant_a, f"faqs/{item['id']}")
    client.post(f"{item_url}/publish", headers=world.a_owner.auth, json={"revision": 1})

    archived = client.post(f"{item_url}/archive", headers=world.a_owner.auth)
    assert archived.status_code == 200
    assert (archived.json()["state"], archived.json()["published"]) == ("archived", None)
    listed = client.get(url(world.tenant_a, "faqs"), headers=world.a_owner.auth).json()
    assert item["id"] not in {i["id"] for i in listed}
    with_archived = client.get(url(world.tenant_a, "faqs?include_archived=true"),
                               headers=world.a_owner.auth).json()
    assert item["id"] in {i["id"] for i in with_archived}

    for call in (
        client.patch(f"{item_url}/draft", headers=world.a_owner.auth,
                     json={"revision": 1, "content": faq()["content"]}),
        client.post(f"{item_url}/publish", headers=world.a_owner.auth, json={"revision": 1}),
    ):
        assert call.status_code == 409
        assert call.json()["error"]["code"] == "archived"

    restored = client.post(f"{item_url}/restore", headers=world.a_owner.auth)
    assert (restored.json()["state"], restored.json()["published"]) == ("draft", None)


def test_profile_and_branch_with_structured_hours(client, world):
    profile = client.get(url(world.tenant_a, "profile"), headers=world.a_receptionist.auth)
    assert profile.status_code == 200, profile.text
    revision = profile.json()["revision"]
    updated = client.patch(
        url(world.tenant_a, "profile/draft"), headers=world.a_owner.auth,
        json={"revision": revision, "content": {
            "about": "Family eye clinic.", "public_phone": "+234 801 000 0000",
            "website_url": "https://clinic-a.example.com",
            "emergency_guidance": "For sudden vision loss or eye injury, go to the nearest A&E.",
        }},
    )
    assert updated.status_code == 200, updated.text
    published = client.post(url(world.tenant_a, "profile/publish"), headers=world.a_owner.auth,
                            json={"revision": updated.json()["revision"]})
    assert published.json()["state"] == "published"

    branch = create(client, world.a_owner, world.tenant_a, "branches",
                    {"content": {"name": "Lekki", "timezone": "Africa/Lagos",
                                 "opening_hours": HOURS}})
    assert branch["draft"]["opening_hours"]["weekly"][6] == {"day": "sun", "closed": True,
                                                            "ranges": []}
    service = create(client, world.a_admin, world.tenant_a, "services",
                     {"content": {"name": "Comprehensive eye exam", "duration_minutes": 45}})
    assert service["draft"]["duration_minutes"] == 45


# ----- permissions -----------------------------------------------------------------------------
def test_receptionist_reads_but_cannot_write_or_publish(client, world):
    item = create(client, world.a_owner, world.tenant_a)
    item_url = url(world.tenant_a, f"faqs/{item['id']}")
    headers = world.a_receptionist.auth
    assert client.get(item_url, headers=headers).status_code == 200
    assert client.get(url(world.tenant_a, "faqs"), headers=headers).status_code == 200
    denied = [
        client.post(url(world.tenant_a, "faqs"), headers=headers, json=faq()),
        client.patch(f"{item_url}/draft", headers=headers,
                     json={"revision": 1, "content": faq()["content"]}),
        client.post(f"{item_url}/publish", headers=headers, json={"revision": 1}),
        client.post(f"{item_url}/archive", headers=headers),
        client.patch(url(world.tenant_a, "profile/draft"), headers=headers,
                     json={"revision": 1, "content": {}}),
    ]
    assert [r.status_code for r in denied] == [403] * 5


def test_other_tenant_cannot_read_or_change_content(client, world):
    item = create(client, world.a_owner, world.tenant_a)
    item_id = item["id"]
    attacker = world.b_owner.auth
    # Directly, with Tenant A in the path: tenant is hidden (404).
    for response in (
        client.get(url(world.tenant_a, "faqs"), headers=attacker),
        client.get(url(world.tenant_a, f"faqs/{item_id}"), headers=attacker),
        client.get(url(world.tenant_a, "profile"), headers=attacker),
        client.patch(url(world.tenant_a, f"faqs/{item_id}/draft"), headers=attacker,
                     json={"revision": 1, "content": faq("Hijacked?")["content"]}),
        client.post(url(world.tenant_a, f"faqs/{item_id}/publish"), headers=attacker,
                    json={"revision": 1}),
    ):
        assert response.status_code == 404
    # Via their own tenant in the path but Tenant A's item id (guessed UUID): not found.
    for response in (
        client.get(url(world.tenant_b, f"faqs/{item_id}"), headers=attacker),
        client.patch(url(world.tenant_b, f"faqs/{item_id}/draft"), headers=attacker,
                     json={"revision": 1, "content": faq("Hijacked?")["content"]}),
        client.post(url(world.tenant_b, f"faqs/{item_id}/archive"), headers=attacker),
    ):
        assert response.status_code == 404
    # Outsiders with no membership get the same answer.
    assert client.get(url(world.tenant_a, "faqs"), headers=world.outsider.auth).status_code == 404
    unchanged = client.get(url(world.tenant_a, f"faqs/{item_id}"), headers=world.a_owner.auth)
    assert unchanged.json()["draft"]["question"] == "Do you accept walk-in patients?"
    assert unchanged.json()["archived_at"] is None


def test_body_cannot_smuggle_tenant_or_publication_fields(client, world):
    for extra in ({"tenant_id": world.tenant_b}, {"published": True}, {"revision": 7}):
        response = client.post(url(world.tenant_a, "faqs"), headers=world.a_owner.auth,
                               json={**faq(), **extra})
        assert response.status_code == 422, extra
    nested = client.post(url(world.tenant_a, "faqs"), headers=world.a_owner.auth,
                         json={"content": {**faq()["content"], "tenant_id": world.tenant_b}})
    assert nested.status_code == 422


def test_invalid_content_is_rejected(client, world):
    bad_hours = {**HOURS, "weekly": HOURS["weekly"][:6]}
    for path, body in (
        ("branches", {"content": {"name": "X1", "opening_hours": bad_hours}}),
        ("branches", {"content": {"name": "Lekki", "timezone": "Not/AZone"}}),
        ("faqs", {"content": {"question": "Two\nlines?", "answer": "a"}}),
        ("services", {"content": {"name": "Exam", "duration_minutes": 100000}}),
    ):
        assert client.post(url(world.tenant_a, path), headers=world.a_owner.auth,
                           json=body).status_code == 422
    assert client.get(url(world.tenant_a, "faqs/not-a-uuid"),
                      headers=world.a_owner.auth).status_code == 422
    missing = client.get(url(world.tenant_a, f"faqs/{uuid.uuid4()}"), headers=world.a_owner.auth)
    assert missing.status_code == 404


def test_content_actions_are_audited(client, world, admin_db):
    item = create(client, world.a_owner, world.tenant_a)
    item_url = url(world.tenant_a, f"faqs/{item['id']}")
    client.post(f"{item_url}/publish", headers=world.a_owner.auth, json={"revision": 1})
    client.post(f"{item_url}/archive", headers=world.a_owner.auth)
    rows = admin_db.execute(
        """select action, actor_user_id, tenant_id::text from public.audit_events
           where target_id = %s order by id""",
        (item["id"],),
    ).fetchall()
    assert [r[0] for r in rows] == ["faq.created", "faq.published", "faq.archived"]
    assert {(r[1], r[2]) for r in rows} == {(world.a_owner.id, world.tenant_a)}


def test_suspended_tenant_content_is_blocked(client, world, admin_db):
    item = create(client, world.a_owner, world.tenant_a)
    admin_db.execute("update public.tenants set status = 'suspended' where id = %s",
                     (world.tenant_a,))
    try:
        assert client.get(url(world.tenant_a, f"faqs/{item['id']}"),
                          headers=world.a_owner.auth).status_code == 404
        assert client.post(url(world.tenant_a, "faqs"), headers=world.a_owner.auth,
                           json=faq()).status_code == 404
    finally:
        admin_db.execute("update public.tenants set status = 'active' where id = %s",
                         (world.tenant_a,))


def test_new_tables_are_closed_to_data_api_and_raw_backend_role(stack, world):
    headers = {"apikey": stack["PUBLISHABLE_KEY"],
               "Authorization": f"Bearer {world.a_owner.token}"}
    for table in ("branches", "services", "faqs", "clinic_profiles"):
        response = httpx.get(f"{stack['API_URL']}/rest/v1/{table}", headers=headers, timeout=10)
        assert response.status_code != 200, f"Data API exposed {table}"
    with psycopg.connect(stack["ENGAGE_API_DB_URL"]) as conn:
        for table in ("branches", "services", "faqs"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"select * from public.{table}")  # noqa: S608 - fixed names
            conn.rollback()
