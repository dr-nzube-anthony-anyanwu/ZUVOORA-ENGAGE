"""Transactional email (Phase 4a, ADR-033).

* `ResendSender` sends through the Resend API with an `Idempotency-Key` (the job's key), so a
  retried job never delivers twice within Resend's 24-hour window (the queue stops retrying
  after 23 hours).
* `LogSender` never sends (development default); it logs counts only, never addresses/content.
* `AllowlistSender` limits real sending outside production to approved test recipients.
Errors are classified as temporary (retry) or permanent (dead letter) and never include
provider response bodies or recipients.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger("engage.email")


@dataclass(frozen=True)
class Email:
    to: tuple[str, ...]
    subject: str
    text: str
    html: str


class EmailError(Exception):
    def __init__(self, kind: str, permanent: bool) -> None:
        super().__init__(kind)
        self.kind = kind
        self.permanent = permanent


class EmailSender(Protocol):
    def send(self, email: Email, idempotency_key: str) -> str:
        """Deliver (or deliberately suppress) and return a message id."""
        ...


class ResendSender:
    URL = "https://api.resend.com/emails"

    def __init__(
        self,
        api_key: str,
        sender: str,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sender = sender
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            follow_redirects=False,
        )

    def send(self, email: Email, idempotency_key: str) -> str:
        body = {
            "from": self._sender,
            "to": list(email.to),
            "subject": email.subject,
            "text": email.text,
            "html": email.html,
        }
        try:
            response = self._client.post(
                self.URL, json=body, headers={"Idempotency-Key": idempotency_key[:256]}
            )
        except httpx.TimeoutException as exc:
            raise EmailError("timeout", permanent=False) from exc
        except httpx.HTTPError as exc:
            raise EmailError("transport", permanent=False) from exc
        if response.status_code in (200, 201):
            try:
                return str(response.json()["id"])
            except (ValueError, KeyError, TypeError) as exc:
                raise EmailError("malformed_response", permanent=False) from exc
        # 429 and 5xx are temporary; other 4xx (bad key, unverified domain, invalid address,
        # idempotency conflict) will not succeed on retry.
        temporary = response.status_code == 429 or response.status_code >= 500
        raise EmailError(f"http_{response.status_code}", permanent=not temporary)


class LogSender:
    """Development default: nothing leaves the machine."""

    def send(self, email: Email, idempotency_key: str) -> str:
        log.info("email_not_sent mode=log recipients=%d key=%s", len(email.to), idempotency_key)
        return f"log:{uuid.uuid4()}"


class AllowlistSender:
    """Outside production, only approved test recipients receive real email."""

    def __init__(self, inner: EmailSender, allowed: list[str]) -> None:
        self._inner = inner
        self._allowed = allowed

    def _ok(self, address: str) -> bool:
        address = address.lower()
        domain = "@" + address.rsplit("@", 1)[-1]
        return address in self._allowed or domain in self._allowed

    def send(self, email: Email, idempotency_key: str) -> str:
        allowed = tuple(a for a in email.to if self._ok(a))
        if not allowed:
            log.info("email_suppressed reason=allowlist recipients=%d", len(email.to))
            return "suppressed:allowlist"
        return self._inner.send(
            Email(allowed, email.subject, email.text, email.html), idempotency_key
        )


def build_sender(settings) -> EmailSender:  # noqa: ANN001 - Settings (avoid import cycle)
    if settings.email_delivery != "resend":
        return LogSender()
    sender: EmailSender = ResendSender(
        settings.resend_api_key.get_secret_value(), settings.email_from
    )
    allowlist = settings.email_allowlist
    return sender if allowlist is None else AllowlistSender(sender, allowlist)
