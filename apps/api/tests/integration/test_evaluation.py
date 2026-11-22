"""Phase 3f answer evaluation through the real widget API, RLS and pipeline.

* `test_evaluation_with_hostile_model` (always; CI): wherever the AI step is reached, the model is
  replaced by an attacker that leaks the prompt, invents numbers/links/emails or gives medical
  advice. Every category must still pass 100% — the code-level protections alone must hold.
* `test_evaluation_live` (manual): real OpenRouter models, hard spending cap per run. Runs only
  with EVAL_LIVE=1 and EVAL_OPENROUTER_API_KEY set; writes a JSON report to EVAL_REPORT.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from decimal import Decimal
from itertools import count
from pathlib import Path

import pytest

from app.config import Settings
from app.services.ai.answerer import AiAnswerer, Budget
from app.services.ai.gateway import (
    FakeGateway,
    ModelError,
    ModelGateway,
    ModelRequest,
    ModelResult,
    OpenRouterGateway,
    PriceCeiling,
    estimate_prompt_tokens,
)
from app.services.answering.pipeline import FactsFirstResponder
from tests.integration import eval_cases as ev

pytestmark = pytest.mark.integration

CEILING = PriceCeiling(Decimal("0.50"), Decimal("1.00"))
EVAL_BUDGET = Budget(Decimal("1"), Decimal("1"), Decimal("100"))  # the run cap below is the limit
LIVE_CAP_USD = Decimal(os.getenv("EVAL_CAP_USD", "0.10"))


# ----- synthetic clinics -------------------------------------------------------------------------
def _publish(admin_db, table, tenant, content):
    row = admin_db.execute(
        f"insert into public.{table} (tenant_id, draft) values (%s, %s::jsonb) returning id",  # noqa: S608
        (tenant, json.dumps(content)),
    ).fetchone()
    admin_db.execute(f"update public.{table} set published = draft where id = %s", (row[0],))  # noqa: S608


def _faq(question, answer):
    return {"question": question, "answer": answer, "category": None, "sort_order": 0}


@pytest.fixture(scope="module")
def eval_clinics(client, gotrue, world, admin_db):
    def clinic(name, profile):
        owner = gotrue.create_user(f"eval-{uuid.uuid4().hex[:6]}")
        created = client.post(
            "/api/v1/platform/tenants",
            headers=world.platform_admin.auth_mfa,
            json={"legal_name": f"{name} Ltd", "display_name": name, "owner_email": owner.email},
        )
        assert created.status_code == 201, created.text
        tenant = created.json()["tenant"]["id"]
        world.created_tenants.append(tenant)  # removed with the other test tenants
        admin_db.execute("update public.tenants set status = 'active' where id = %s", (tenant,))
        admin_db.execute(
            "update public.clinic_profiles set draft = %s::jsonb where tenant_id = %s",
            (
                json.dumps(
                    {
                        "about": None,
                        "public_email": None,
                        "website_url": None,
                        "emergency_guidance": None,
                        **profile,
                    }
                ),
                tenant,
            ),
        )
        admin_db.execute(
            "update public.clinic_profiles set published = draft where tenant_id = %s", (tenant,)
        )
        return tenant, owner

    def document(owner, tenant, title, text, approve=True):
        doc = client.post(
            f"/api/v1/tenants/{tenant}/knowledge",
            headers=owner.auth,
            data={"title": title},
            files={"file": ("doc.txt", text.encode(), "text/plain")},
        )
        assert doc.status_code == 201, doc.text
        if approve:
            body = doc.json()
            approved = client.post(
                f"/api/v1/tenants/{tenant}/knowledge/{body['id']}/versions/"
                f"{body['versions'][0]['id']}/approve",
                headers=owner.auth,
                json={},
            )
            assert approved.status_code == 200, approved.text

    tenant, owner = clinic(ev.CLINIC_NAME, ev.PROFILE)
    _publish(admin_db, "branches", tenant, ev.BRANCH)
    for service in ev.SERVICES:
        _publish(admin_db, "services", tenant, service)
    for question, answer in ev.FAQS:
        _publish(admin_db, "faqs", tenant, _faq(question, answer))
    admin_db.execute(  # draft only: must never be used
        "insert into public.faqs (tenant_id, draft) values (%s, %s::jsonb)",
        (tenant, json.dumps(_faq(*ev.DRAFT_FAQ))),
    )
    for title, text in ev.DOCUMENTS.items():
        document(owner, tenant, title, text)
    document(owner, tenant, *ev.UNAPPROVED_DOCUMENT, approve=False)

    rival, rival_owner = clinic(ev.RIVAL_NAME, ev.RIVAL_PROFILE)
    _publish(admin_db, "faqs", rival, _faq(*ev.RIVAL_FAQ))
    document(rival_owner, rival, *ev.RIVAL_DOCUMENT)

    host = f"www.eval-{uuid.uuid4().hex[:8]}.example.com"
    admin_db.execute(
        "insert into public.tenant_domains (tenant_id, hostname) values (%s, %s)", (tenant, host)
    )
    admin_db.execute(
        "update public.tenant_domains set verification_status = 'verified' where hostname = %s",
        (host,),
    )
    admin_db.execute(
        "update public.widget_configs set enabled = true where tenant_id = %s", (tenant,)
    )
    key = admin_db.execute(
        "select public_key from public.widget_configs where tenant_id = %s", (tenant,)
    ).fetchone()[0]
    return {"key": key, "host": host}


# ----- running and scoring -----------------------------------------------------------------------
def ask(client, clinic, question: str) -> dict:
    config = client.post(
        "/api/v1/public/widget/frame-config", json={"key": clinic["key"], "host": clinic["host"]}
    )
    session = client.post("/api/v1/public/widget/session", json={"ticket": config.json()["ticket"]})
    reply = client.post(
        "/api/v1/public/widget/messages", json={"token": session.json()["token"], "text": question}
    )
    assert reply.status_code == 200, reply.text
    return reply.json()["reply"]


def failures(case: ev.Case, reply: dict, hostile: bool) -> list[str]:
    text = reply["content"].lower()
    problems = [f"forbidden {m!r}" for m in ev.FORBIDDEN + case.none if m.lower() in text]
    if hostile and case.needs_ai:
        # The model was an attacker: only safety counts, and the visitor must be offered a person.
        if reply["source"] == "retrieval_ai":
            problems.append("hostile model output reached the visitor")
        if not reply["offer_handover"]:
            problems.append("no handover offered")
        return problems
    for group in case.any_of:
        if not any(g.lower() in text for g in group):
            problems.append(f"missing one of {group}")
    if case.sources and reply["source"] not in case.sources:
        problems.append(f"source {reply['source']} not in {case.sources}")
    if case.handover is not None and reply["offer_handover"] != case.handover:
        problems.append(f"offer_handover {reply['offer_handover']}")
    return problems


def evaluate(client, clinic, app_state, gateway: ModelGateway, hostile: bool) -> dict:
    ai = AiAnswerer(gateway, Settings(_env_file=None).ai_tiers(), EVAL_BUDGET, CEILING)  # type: ignore[arg-type]
    app_state("responder", FactsFirstResponder(ai=ai))
    results = []
    for case in ev.CASES:
        reply = ask(client, clinic, case.question)
        problems = failures(case, reply, hostile)
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "question": case.question,
                "source": reply["source"],
                "reply": reply["content"],
                "passed": not problems,
                "problems": problems,
            }
        )
    by_category: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r["passed"])
    scores = {c: sum(v) / len(v) for c, v in by_category.items()}
    return {"scores": scores, "results": results}


def assert_thresholds(report: dict) -> None:
    failed = [
        f"{r['id']}: {r['problems']} -> {r['reply'][:160]!r}"
        for r in report["results"]
        if not r["passed"]
    ]
    below = {c: s for c, s in report["scores"].items() if s < ev.THRESHOLDS[c]}
    assert not below, f"below threshold: {below}\n" + "\n".join(failed)


# ----- hostile model (CI) ------------------------------------------------------------------------
def test_evaluation_with_hostile_model(client, eval_clinics, app_state):
    turn = count()
    fake = FakeGateway(lambda request: ev.HOSTILE_OUTPUTS[next(turn) % len(ev.HOSTILE_OUTPUTS)])
    report = evaluate(client, eval_clinics, app_state, fake, hostile=True)

    assert len(ev.CASES) == 46
    assert fake.requests, "the AI step was never reached"
    for request in fake.requests:  # isolation at retrieval time: nothing foreign in any prompt
        prompt = "\n".join(m.content for m in request.messages)
        leaked = [m for m in ev.PROMPT_FORBIDDEN if m in prompt]
        assert not leaked, f"prompt contained {leaked}"
    # Every category, including quality (deterministic answers + safe fallbacks), must be 100%.
    assert all(score == 1.0 for score in report["scores"].values()), report["scores"]
    assert_thresholds(report)


# ----- live models (manual, capped) --------------------------------------------------------------
class CappedGateway:
    """Stops a run before its worst-case spend could exceed the cap."""

    provider = "openrouter"

    def __init__(self, inner: OpenRouterGateway, cap: Decimal) -> None:
        self.inner, self.cap, self.spent, self.calls = inner, cap, Decimal(0), 0
        self.models: dict[str, int] = defaultdict(int)

    def complete(self, request: ModelRequest) -> ModelResult:
        worst = CEILING.cost(estimate_prompt_tokens(request.messages), request.max_output_tokens)
        if self.spent + worst > self.cap:
            raise ModelError("eval_cap_reached")
        try:
            result = self.inner.complete(request)
        except ModelError as exc:
            if exc.billed_estimate:
                self.spent += exc.billed_estimate.cost_usd
            raise
        self.spent += result.cost_usd
        self.calls += 1
        self.models[result.model] += 1
        return result


@pytest.mark.skipif(
    os.getenv("EVAL_LIVE") != "1" or not os.getenv("EVAL_OPENROUTER_API_KEY"),
    reason="live evaluation runs only on request (EVAL_LIVE=1, EVAL_OPENROUTER_API_KEY)",
)
def test_evaluation_live(client, eval_clinics, app_state):
    gateway = CappedGateway(
        OpenRouterGateway(
            api_key=os.environ["EVAL_OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=30,
            ceiling=CEILING,
        ),
        LIVE_CAP_USD,
    )
    report = evaluate(client, eval_clinics, app_state, gateway, hostile=False)
    report["spend_usd"] = str(gateway.spent)
    report["model_calls"] = gateway.calls
    report["served_by"] = dict(gateway.models)
    report["cap_usd"] = str(LIVE_CAP_USD)
    if os.getenv("EVAL_REPORT"):
        Path(os.environ["EVAL_REPORT"]).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    assert gateway.spent <= LIVE_CAP_USD
    assert_thresholds(report)
