"""Answering interface for the public widget.

The widget route calls a `Responder`. Phase 3b ships `UnavailableResponder`, which says plainly
that the assistant is not available yet and offers a handover (an explicit not-implemented state,
never a fake answer). Phase 3c/3d add the facts/emergency/retrieval/AI pipeline behind the same
interface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

import psycopg

AnswerSource = Literal[
    "facts", "emergency", "retrieval_ai", "fallback", "handover", "budget_exhausted", "greeting"
]


@dataclass(frozen=True)
class Turn:
    role: Literal["visitor", "assistant"]
    content: str


@dataclass(frozen=True)
class AnswerContext:
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    history: list[Turn]


@dataclass(frozen=True)
class Answer:
    text: str
    source: AnswerSource
    offer_handover: bool = False
    model: str | None = None
    safety: dict = field(default_factory=dict)


class Responder(Protocol):
    def answer(self, conn: psycopg.Connection, context: AnswerContext) -> Answer:
        """Produce an answer. `conn` is a widget-role transaction (published content only)."""
        ...


class UnavailableResponder:
    TEXT = (
        "I'm sorry, I can't answer questions yet because this assistant is still being set up. "
        "If you'd like, leave your phone number or email and the clinic team will contact you."
    )

    def answer(self, conn: psycopg.Connection, context: AnswerContext) -> Answer:
        return Answer(text=self.TEXT, source="fallback", offer_handover=True)
