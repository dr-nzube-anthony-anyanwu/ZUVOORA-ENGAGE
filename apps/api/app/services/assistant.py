"""Answering interface for the public widget.

The widget route calls a `Responder`. `UnavailableResponder` says plainly that the assistant is
not available and offers a handover (an explicit not-implemented state, never a fake answer).
The facts/emergency/retrieval pipeline (3c) and the AI step (3d) sit behind the same interface.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
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


@dataclass(frozen=True)
class Usage:
    """One model call for the usage ledger (`public.usage_events`)."""

    provider: Literal["openrouter", "fake"]
    model: str
    tier: Literal["standard", "complex"]
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class Completed:
    answer: Answer
    usage: Usage | None = None


@dataclass(frozen=True)
class PendingAnswer:
    """Work that must run WITHOUT a database transaction open (a model call).

    The route commits the visitor's message first, calls `complete()`, then stores the answer and
    its usage in a second short transaction, so no row locks are held during the network call.
    """

    complete: Callable[[], Completed]


class Responder(Protocol):
    def answer(self, conn: psycopg.Connection, context: AnswerContext) -> Answer | PendingAnswer:
        """Produce an answer. `conn` is a widget-role transaction (published content only)."""
        ...


FALLBACK = (
    "I'm sorry, I don't have that information. I can only answer from what {clinic} has "
    "published. Would you like the clinic team to contact you?"
)


class UnavailableResponder:
    TEXT = (
        "I'm sorry, I can't answer questions yet because this assistant is still being set up. "
        "If you'd like, leave your phone number or email and the clinic team will contact you."
    )

    def answer(self, conn: psycopg.Connection, context: AnswerContext) -> Answer:
        return Answer(text=self.TEXT, source="fallback", offer_handover=True)
