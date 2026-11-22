"""Phase 3c answering through the real widget API and RLS: published data only, per clinic."""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.answering import retrieval

pytestmark = pytest.mark.integration

HOURS = {
    "weekly": [
        {"day": d, "closed": False, "ranges": [{"open": "08:00", "close": "17:00"}]}
        for d in ("mon", "tue", "wed", "thu", "fri", "sat")
    ]
    + [{"day": "sun", "closed": True, "ranges": []}],
    "exceptions": [],
}


def publish(admin_db, table, tenant, content, published=True):
    row = admin_db.execute(
        f"insert into public.{table} (tenant_id, draft) values (%s, %s::jsonb) returning id",  # noqa: S608
        (tenant, json.dumps(content)),
    ).fetchone()
    if published:
        admin_db.execute(
            f"update public.{table} set published = draft where id = %s",  # noqa: S608
            (row[0],),
        )
    return row[0]


@pytest.fixture(scope="module")
def chat(client, world, admin_db):
    """Clinic A: active, widget on a verified host, published facts; Clinic B: a distinctive FAQ."""
    host = f"www.answers-{uuid.uuid4().hex[:8]}.example.com"
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
        "update public.widget_configs set enabled = true where tenant_id = %s", (world.tenant_a,)
    )
    admin_db.execute(
        "update public.clinic_profiles set draft = %s::jsonb where tenant_id = %s",
        (
            json.dumps(
                {
                    "public_phone": "+234 801 555 0101",
                    "emergency_guidance": "Go straight to the Eko Hospital emergency unit.",
                }
            ),
            world.tenant_a,
        ),
    )
    admin_db.execute(
        "update public.clinic_profiles set published = draft where tenant_id = %s",
        (world.tenant_a,),
    )
    publish(
        admin_db,
        "branches",
        world.tenant_a,
        {
            "name": "Ikoyi",
            "address": "2 Awolowo Road",
            "city": "Lagos",
            "timezone": "Africa/Lagos",
            "opening_hours": HOURS,
        },
    )
    publish(
        admin_db,
        "faqs",
        world.tenant_a,
        {
            "question": "Do you accept HMO insurance plans?",
            "answer": "Yes, we accept most HMO plans including Reliance HMO.",
            "category": None,
            "sort_order": 0,
        },
    )
    publish(
        admin_db,
        "faqs",
        world.tenant_a,
        {
            "question": "Is there parking at the clinic?",
            "answer": "UNPUBLISHED DRAFT ANSWER about parking.",
            "category": None,
            "sort_order": 0,
        },
        published=False,
    )
    publish(
        admin_db,
        "faqs",
        world.tenant_b,
        {
            "question": "Where can patients park their cars?",
            "answer": "Clinic B parking: the Zebra garage on Bourdillon Road.",
            "category": None,
            "sort_order": 0,
        },
    )
    yield {"host": host}
    admin_db.execute(
        "update public.widget_configs set enabled = false where tenant_id = %s", (world.tenant_a,)
    )
    # Modules reuse this fixture: release the domain so the clinic stays under its limit.
    admin_db.execute(
        "update public.tenant_domains set removed_at = now() where hostname = %s", (host,)
    )
    admin_db.execute(
        "update public.tenants set status = %s where id = %s", (original, world.tenant_a)
    )


def ask(client, chat, world, question: str) -> dict:
    key = client.get(f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.a_owner.auth).json()[
        "public_key"
    ]
    config = client.post(
        "/api/v1/public/widget/frame-config", json={"key": key, "host": chat["host"]}
    )
    session = client.post("/api/v1/public/widget/session", json={"ticket": config.json()["ticket"]})
    reply = client.post(
        "/api/v1/public/widget/messages", json={"token": session.json()["token"], "text": question}
    )
    assert reply.status_code == 200, reply.text
    return reply.json()["reply"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What are your opening hours?", "Mon–Sat 08:00–17:00"),
        ("What is your phone number?", "+234 801 555 0101"),
        ("Where are you located?", "2 Awolowo Road"),
        ("Do you accept HMO insurance plans?", "Reliance HMO"),
    ],
)
def test_answers_come_from_published_clinic_data(client, chat, world, question, expected):
    reply = ask(client, chat, world, question)
    assert reply["source"] == "facts"
    assert expected in reply["content"]


def test_emergency_uses_clinic_guidance(client, chat, world):
    reply = ask(client, chat, world, "Bleach splashed into my eye!")
    assert reply["source"] == "emergency"
    assert "Eko Hospital emergency unit" in reply["content"]
    assert "+234 801 555 0101" in reply["content"]
    assert reply["offer_handover"] is True


def test_medical_advice_is_refused(client, chat, world):
    reply = ask(client, chat, world, "What drops should I use for my red eye?")
    assert "not able to give medical advice" in reply["content"]
    assert reply["offer_handover"] is True


def test_other_clinic_and_unpublished_content_never_used(client, chat, world):
    reply = ask(client, chat, world, "Where can I park my car? Is there a garage?")
    assert "Zebra" not in reply["content"]  # Clinic B's FAQ
    assert "UNPUBLISHED" not in reply["content"]  # Clinic A's draft
    assert reply["source"] == "fallback"
    assert reply["offer_handover"] is True


def test_document_passages_are_tenant_scoped_and_published_only(client, chat, world):
    def upload_and_approve(user, tenant, text, approve=True):
        doc = client.post(
            f"/api/v1/tenants/{tenant}/knowledge",
            headers=user.auth,
            data={"title": "Visitor information"},
            files={"file": ("info.txt", text.encode(), "text/plain")},
        ).json()
        if approve:
            version = doc["versions"][0]["id"]
            approved = client.post(
                f"/api/v1/tenants/{tenant}/knowledge/{doc['id']}/versions/{version}/approve",
                headers=user.auth,
                json={},
            )
            assert approved.status_code == 200, approved.text
        return doc["id"]

    a_doc = upload_and_approve(
        world.a_owner,
        world.tenant_a,
        "Patients may use the courtyard lot behind the Ikoyi building.",
    )
    upload_and_approve(
        world.b_owner,
        world.tenant_b,
        "Clinic B visitors use the courtyard lot at the Flamingo mall.",
    )
    upload_and_approve(
        world.a_owner,
        world.tenant_a,
        "DRAFTDOC courtyard information not yet reviewed.",
        approve=False,
    )

    db = client.app.state.db
    with db.widget_transaction(uuid.UUID(world.tenant_a)) as conn:
        texts = [p.text for p in retrieval.search(conn, "courtyard lot")]
    assert any("Ikoyi building" in t for t in texts)
    assert not any("Flamingo" in t for t in texts)
    assert not any("DRAFTDOC" in t for t in texts)

    client.post(
        f"/api/v1/tenants/{world.tenant_a}/knowledge/{a_doc}/unpublish", headers=world.a_owner.auth
    )
    with db.widget_transaction(uuid.UUID(world.tenant_a)) as conn:
        texts = [p.text for p in retrieval.search(conn, "courtyard lot")]
    assert not any("Ikoyi building" in t for t in texts)  # unpublished -> gone from retrieval
