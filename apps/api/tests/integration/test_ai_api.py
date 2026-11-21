"""Phase 3d: the AI step through the real widget API, RLS and usage ledger (fake model only)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services.ai.answerer import AiAnswerer, Budget
from app.services.ai.gateway import FakeGateway, ModelError, PriceCeiling
from app.services.answering.pipeline import FactsFirstResponder
from tests.integration.test_answering_api import ask, chat  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration

CEILING = PriceCeiling(Decimal("0.50"), Decimal("1.00"))
OPEN_BUDGET = Budget(Decimal("0.20"), Decimal("0.50"), Decimal("2.00"))
QUESTION = "Do I need someone to drive me home after pupil dilation?"


@pytest.fixture(scope="module")
def documents(client, world, chat):  # noqa: F811
    def upload(user, tenant, text, approve=True):
        doc = client.post(
            f"/api/v1/tenants/{tenant}/knowledge",
            headers=user.auth,
            data={"title": "Dilation visits"},
            files={"file": ("dilation.txt", text.encode(), "text/plain")},
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

    upload(
        world.a_owner,
        world.tenant_a,
        "Pupil dilation lasts about 4 hours. Please bring someone to drive you home.",
    )
    upload(world.b_owner, world.tenant_b, "FLAMINGO: Clinic B dilation drivers wait in lot 7.")
    upload(
        world.a_owner,
        world.tenant_a,
        "DRAFTDOC dilation note awaiting review.",
        approve=False,
    )


def use_ai(app_state, script, budget: Budget = OPEN_BUDGET) -> FakeGateway:
    fake = FakeGateway(script)
    ai = AiAnswerer(fake, {"standard": ("fake/s",), "complex": ("fake/c",)}, budget, CEILING)
    app_state("responder", FactsFirstResponder(ai=ai))
    return fake


def usage_rows(admin_db, tenant) -> int:
    return admin_db.execute(
        "select count(*) from public.usage_events where tenant_id = %s and provider = 'fake'",
        (tenant,),
    ).fetchone()[0]


def test_grounded_ai_answer_is_stored_with_usage(
    client,
    chat,
    world,
    documents,
    admin_db,
    app_state,  # noqa: F811
):
    fake = use_ai(app_state, lambda r: "Yes. Dilation lasts about 4 hours, so bring a driver.")
    before = usage_rows(admin_db, world.tenant_a)

    reply = ask(client, chat, world, QUESTION)

    assert reply["source"] == "retrieval_ai"
    assert reply["content"] == "Yes. Dilation lasts about 4 hours, so bring a driver."
    assert reply["offer_handover"] is False
    assert usage_rows(admin_db, world.tenant_a) == before + 1
    stored = admin_db.execute(
        "select model, answer_source from public.messages where tenant_id = %s "
        "and role = 'assistant' order by id desc limit 1",
        (world.tenant_a,),
    ).fetchone()
    assert tuple(stored) == ("fake/standard", "retrieval_ai")

    # The model saw only this clinic's published passages.
    prompt = fake.requests[0].messages[0].content
    assert "Please bring someone to drive you home" in prompt
    assert "FLAMINGO" not in prompt  # other clinic
    assert "DRAFTDOC" not in prompt  # unapproved document


def test_spend_is_visible_to_the_budget_check(client, world, documents):
    db = client.app.state.db
    with db.widget_transaction(uuid.UUID(world.tenant_a)) as conn:
        row = conn.execute("select tenant_today from app_private.ai_spend()").fetchone()
    assert Decimal(row["tenant_today"]) >= FakeGateway.COST


def test_hallucinated_answer_is_replaced_but_still_billed(
    client,
    chat,
    world,
    documents,
    admin_db,
    app_state,  # noqa: F811
):
    use_ai(app_state, lambda r: "Dilation costs ₦45,000 and lasts 6 hours.")
    before = usage_rows(admin_db, world.tenant_a)
    reply = ask(client, chat, world, QUESTION)
    assert reply["source"] == "fallback"
    assert "45,000" not in reply["content"]
    assert reply["offer_handover"] is True
    assert usage_rows(admin_db, world.tenant_a) == before + 1


@pytest.mark.parametrize(
    "budget",
    [
        Budget(Decimal("0"), Decimal("0.50"), Decimal("2.00")),
        Budget(Decimal("0"), Decimal("0"), Decimal("0")),
    ],
)
def test_exhausted_budget_never_calls_the_model(
    client,
    chat,
    world,
    documents,
    app_state,
    budget,  # noqa: F811
):
    fake = use_ai(app_state, lambda r: "should not be called", budget)
    reply = ask(client, chat, world, QUESTION)
    assert reply["source"] == "budget_exhausted"
    assert reply["offer_handover"] is True
    assert fake.requests == []


def test_no_passages_means_no_model_call(client, chat, world, documents, app_state):  # noqa: F811
    fake = use_ai(app_state, lambda r: "should not be called")
    reply = ask(client, chat, world, "Tell me about xylophone recitals")
    assert reply["source"] == "fallback"
    assert fake.requests == []


def test_safety_rules_run_before_the_model(client, chat, world, documents, app_state):  # noqa: F811
    fake = use_ai(app_state, lambda r: "should not be called")
    reply = ask(client, chat, world, "Acid splashed in my eye after dilation!")
    assert reply["source"] == "emergency"
    assert fake.requests == []


def test_model_failure_falls_back(client, chat, world, documents, app_state):  # noqa: F811
    def down(request):
        raise ModelError("http_503")

    use_ai(app_state, down)
    reply = ask(client, chat, world, QUESTION)
    assert reply["source"] == "fallback"
    assert reply["offer_handover"] is True


def test_model_emergency_signal_uses_clinic_guidance(
    client,
    chat,
    world,
    documents,
    app_state,  # noqa: F811
):
    use_ai(app_state, lambda r: "EMERGENCY")
    reply = ask(client, chat, world, QUESTION)
    assert reply["source"] == "emergency"
    assert "Eko Hospital emergency unit" in reply["content"]
