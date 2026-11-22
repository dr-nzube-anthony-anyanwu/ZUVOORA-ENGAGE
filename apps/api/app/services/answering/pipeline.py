"""The answering pipeline (Phase 3c): free, deterministic steps first.

Order: emergency → medical-advice refusal → structured facts → strong FAQ match → AI grounded in
the retrieved passages (3d; only when configured, passages exist and budgets allow) → honest
fallback with a handover offer. Everything reads only the widget tenant's PUBLISHED content
through the widget-role transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import psycopg

from app.services import entitlements
from app.services.ai.answerer import AiAnswerer, ClinicContext
from app.services.answering import facts as facts_mod
from app.services.answering import retrieval, safety
from app.services.assistant import FALLBACK, Answer, AnswerContext, PendingAnswer

__all__ = ["FALLBACK", "FAQ_MIN_COVERAGE", "FactsFirstResponder"]

FAQ_MIN_COVERAGE = 0.6


class FactsFirstResponder:
    """Deterministic answers first; the optional AI step only when nothing else applies."""

    def __init__(
        self, clock: Callable[[], datetime] | None = None, ai: AiAnswerer | None = None
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ai = ai

    def _clinic(self, conn: psycopg.Connection) -> str:
        row = conn.execute("select app_private.widget_clinic_name() as name").fetchone()
        return row["name"] if row and row["name"] else "the clinic"

    def answer(self, conn: psycopg.Connection, context: AnswerContext) -> Answer | PendingAnswer:
        question = context.question
        clinic = self._clinic(conn)
        facts = facts_mod.load_facts(conn, clinic)

        if safety.is_emergency(question):
            return Answer(
                text=safety.emergency_reply(facts.profile.get("emergency_guidance"), facts.phone),
                source="emergency",
                offer_handover=True,
                safety={"rule": "emergency"},
            )
        if safety.asks_for_medical_advice(question):
            return Answer(
                text=safety.medical_advice_reply(clinic, facts.phone),
                source="facts",
                offer_handover=True,
                safety={"rule": "medical_advice_refused"},
            )

        reply, found = facts_mod.answer_from_facts(facts, question, self._clock())
        if reply is not None:
            missing = reply.startswith("I'm sorry")
            return Answer(
                text=reply, source="facts", offer_handover=missing, safety={"intents": found}
            )

        passages = retrieval.search(conn, question)
        best_faq = next((p for p in passages if p.kind == "faq"), None)
        if best_faq and best_faq.coverage >= FAQ_MIN_COVERAGE and passages[0] is best_faq:
            return Answer(text=best_faq.text, source="facts", safety={"faq": best_faq.title})

        # Nothing retrieved -> nothing to ground on. The plan must include AI answers (Phase 5).
        # Over the monthly message or AI allowance: no model (the free answers and the honest
        # fallback still work — "soft for safety, hard for cost", ADR-039).
        if (
            self._ai is not None
            and passages
            and entitlements.widget_has(conn, "ai_answers")
            and not entitlements.widget_quota_reached(conn, "messages")
            and not entitlements.widget_quota_reached(conn, "ai_usd")
        ):
            return self._ai.prepare(
                conn,
                context,
                ClinicContext(clinic, facts.phone, facts.profile.get("emergency_guidance")),
                passages,
            )
        return Answer(
            text=FALLBACK.format(clinic=clinic),
            source="fallback",
            offer_handover=True,
            safety={"passages": len(passages)},
        )
