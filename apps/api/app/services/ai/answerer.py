"""The AI step of the answering pipeline (Phase 3d).

Inside the widget transaction (`prepare`): choose a tier, build the grounded prompt, and check the
budgets against the worst-case cost of this call. The model call itself (`PendingAnswer`) runs
after that transaction has committed; its usage is recorded even when the answer is rejected,
because the provider still charged for it.

Budgets are enforced before each call from the immutable usage ledger. Concurrent calls can each
pass the check, so the overshoot is bounded by (concurrent calls × one call's worst case, about
$0.002); the OpenRouter key's own credit limit is the independent hard stop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

import psycopg

from app.services.ai import guard, prompting
from app.services.ai.gateway import (
    ModelError,
    ModelGateway,
    ModelRequest,
    ModelResult,
    PriceCeiling,
    Tier,
    estimate_prompt_tokens,
)
from app.services.answering import safety
from app.services.answering.retrieval import Passage
from app.services.assistant import (
    FALLBACK,
    Answer,
    AnswerContext,
    Completed,
    PendingAnswer,
    Usage,
)

log = logging.getLogger("engage.ai")


@dataclass(frozen=True)
class Budget:
    tenant_daily: Decimal
    global_daily: Decimal
    global_monthly: Decimal


@dataclass(frozen=True)
class ClinicContext:
    name: str
    phone: str | None
    emergency_guidance: str | None


def spend(conn: psycopg.Connection) -> tuple[Decimal, Decimal, Decimal]:
    row = conn.execute(
        "select tenant_today, global_today, global_month from app_private.ai_spend()"
    ).fetchone()
    return (
        Decimal(row["tenant_today"]),
        Decimal(row["global_today"]),
        Decimal(row["global_month"]),
    )


def over_budget(
    budget: Budget, current: tuple[Decimal, Decimal, Decimal], cost: Decimal
) -> str | None:
    tenant_today, global_today, global_month = current
    if tenant_today + cost > budget.tenant_daily:
        return "tenant_daily"
    if global_today + cost > budget.global_daily:
        return "global_daily"
    if global_month + cost > budget.global_monthly:
        return "global_monthly"
    return None


class AiAnswerer:
    def __init__(
        self,
        gateway: ModelGateway,
        tiers: dict[Tier, tuple[str, ...]],
        budget: Budget,
        ceiling: PriceCeiling,
        max_output_tokens: int = 300,
    ) -> None:
        self.gateway = gateway
        self.tiers = tiers
        self.budget = budget
        self.ceiling = ceiling
        self.max_output_tokens = max_output_tokens

    def prepare(
        self,
        conn: psycopg.Connection,
        context: AnswerContext,
        clinic: ClinicContext,
        passages: list[Passage],
    ) -> Answer | PendingAnswer:
        tier = prompting.choose_tier(context.question, passages)
        grounding = prompting.build_grounding(passages, clinic.phone)
        messages = prompting.build_messages(
            clinic.name, grounding, context.history, context.question
        )
        request = ModelRequest(
            tier=tier,
            models=self.tiers[tier],
            messages=messages,
            max_output_tokens=self.max_output_tokens,
        )
        worst = self.ceiling.cost(estimate_prompt_tokens(messages), self.max_output_tokens)
        exceeded = over_budget(self.budget, spend(conn), worst)
        if exceeded:
            log.warning("ai_budget_exhausted scope=%s tenant=%s", exceeded, context.tenant_id)
            return Answer(
                text=FALLBACK.format(clinic=clinic.name),
                source="budget_exhausted",
                offer_handover=True,
                safety={"budget": exceeded},
            )
        return PendingAnswer(lambda: self._run(request, grounding.text, clinic))

    def _usage(self, tier: Tier, result: ModelResult) -> Usage:
        return Usage(
            provider=self.gateway.provider,
            model=result.model,
            tier=tier,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cost_usd=result.cost_usd,
        )

    def _run(self, request: ModelRequest, sources: str, clinic: ClinicContext) -> Completed:
        fallback = Answer(
            text=FALLBACK.format(clinic=clinic.name), source="fallback", offer_handover=True
        )
        try:
            result = self.gateway.complete(request)
        except ModelError as exc:
            log.warning("ai_model_error kind=%s tier=%s", exc.kind, request.tier)
            usage = self._usage(request.tier, exc.billed_estimate) if exc.billed_estimate else None
            return Completed(
                Answer(
                    text=fallback.text,
                    source="fallback",
                    offer_handover=True,
                    safety={"ai_error": exc.kind, "tier": request.tier},
                ),
                usage,
            )
        usage = self._usage(request.tier, result)
        verdict = guard.check(result.text, sources)
        audit = {"tier": request.tier, "guard": verdict.verdict}
        if verdict.ok:
            return Completed(
                Answer(text=verdict.text, source="retrieval_ai", model=result.model, safety=audit),
                usage,
            )
        if verdict.verdict == "emergency":
            text = safety.emergency_reply(clinic.emergency_guidance, clinic.phone)
            return Completed(
                Answer(text=text, source="emergency", offer_handover=True, safety=audit), usage
            )
        if verdict.verdict in {"medical", "medical_content"}:
            text = safety.medical_advice_reply(clinic.name, clinic.phone)
            return Completed(
                Answer(text=text, source="facts", offer_handover=True, safety=audit), usage
            )
        if verdict.verdict != "no_answer":
            log.warning("ai_answer_rejected verdict=%s tier=%s", verdict.verdict, request.tier)
        return Completed(
            Answer(text=fallback.text, source="fallback", offer_handover=True, safety=audit),
            usage,
        )
