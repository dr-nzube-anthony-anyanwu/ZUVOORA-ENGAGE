"""Signed tokens for the public widget (Phase 3b, ADR-027).

Two token types, both HS256 with the dedicated WIDGET_TOKEN_SECRET (never the Supabase keys):
  * frame ticket  — issued with the iframe page after the embedding host was checked against the
                    clinic's verified domains; valid 15 minutes; needed to start a conversation.
  * conversation  — identifies one visitor conversation; valid 2 hours.
Each type has its own audience, so one can never be used as the other. Tokens carry ids only.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass

import jwt

ISSUER = "zuvoora-engage-widget"
TICKET_AUDIENCE = "engage-widget-frame"
CONVERSATION_AUDIENCE = "engage-widget-conversation"
TICKET_TTL_SECONDS = 15 * 60
CONVERSATION_TTL_SECONDS = 2 * 60 * 60


class WidgetTokenError(Exception):
    pass


@dataclass(frozen=True)
class FrameTicket:
    public_key: str
    host: str


@dataclass(frozen=True)
class ConversationToken:
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    host: str


class WidgetTokens:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("widget token secret must be at least 32 characters")
        self._secret = secret

    def _encode(self, audience: str, claims: dict, ttl: int) -> str:
        now = int(time.time())
        payload = {"iss": ISSUER, "aud": audience, "iat": now, "exp": now + ttl, **claims}
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def _decode(self, token: str, audience: str) -> dict:
        try:
            return jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=audience,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise WidgetTokenError(str(exc)) from exc

    # ----- frame tickets ------------------------------------------------------------------------
    def issue_ticket(self, public_key: str, host: str) -> str:
        return self._encode(TICKET_AUDIENCE, {"k": public_key, "h": host}, TICKET_TTL_SECONDS)

    def verify_ticket(self, token: str) -> FrameTicket:
        claims = self._decode(token, TICKET_AUDIENCE)
        try:
            return FrameTicket(public_key=str(claims["k"]), host=str(claims["h"]))
        except KeyError as exc:
            raise WidgetTokenError("malformed ticket") from exc

    # ----- conversation tokens ------------------------------------------------------------------
    def issue_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, host: str
    ) -> str:
        return self._encode(
            CONVERSATION_AUDIENCE,
            {"t": str(tenant_id), "c": str(conversation_id), "h": host},
            CONVERSATION_TTL_SECONDS,
        )

    def verify_conversation(self, token: str) -> ConversationToken:
        claims = self._decode(token, CONVERSATION_AUDIENCE)
        try:
            return ConversationToken(
                tenant_id=uuid.UUID(claims["t"]),
                conversation_id=uuid.UUID(claims["c"]),
                host=str(claims["h"]),
            )
        except (KeyError, ValueError) as exc:
            raise WidgetTokenError("malformed conversation token") from exc

    # ----- rate-limit keys ----------------------------------------------------------------------
    def bucket(self, kind: str, value: str) -> str:
        """Keyed hash for rate-limit buckets, so raw IP addresses are never stored."""
        digest = hmac.new(self._secret.encode(), f"{kind}:{value}".encode(), hashlib.sha256)
        return f"{kind}:{digest.hexdigest()[:40]}"
