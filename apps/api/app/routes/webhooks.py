"""Provider webhooks (Phase 4d, ADR-036):  POST /api/v1/webhooks/calcom/{connection_id}

No user and no tenant from the request: the connection id selects the clinic's webhook secret,
the HMAC signature authenticates the body, and the database applies each verified body once.
Responses never reveal whether a connection exists (unknown or unverifiable -> 401).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from app.db import Database
from app.deps import get_db
from app.errors import ApiError, log_security_event
from app.routes.scheduling import get_secrets_box
from app.routes.widget_public import _client_ip, get_widget_tokens
from app.services.scheduling import webhooks
from app.services.secrets_box import Sealed, SecretsBox, SecretsBoxError
from app.services.widget_tokens import WidgetTokens

router = APIRouter(prefix="/api/v1/webhooks", tags=["provider webhooks"])

WEBHOOK_PURPOSE = "calcom_webhook"
MAX_BODY = 256 * 1024
RATE = (60, 120)  # per source IP per minute (provider retries included)


def _unauthorised(request: Request, reason: str) -> ApiError:
    log_security_event(request, "webhook_rejected", reason=reason)
    return ApiError(401, "invalid_webhook", "Webhook not accepted.")


def _handle(
    db: Database,
    box: SecretsBox,
    tokens: WidgetTokens,
    request: Request,
    connection_id: uuid.UUID,
    body: bytes,
    signature: str | None,
) -> dict:
    with db.jobs_transaction() as conn:
        allowed = conn.execute(
            "select app_private.rate_limit_hit(%s, %s, %s) as ok",
            (tokens.bucket("webhook_ip", _client_ip(request)), *RATE),
        ).fetchone()["ok"]
        if not allowed:
            raise ApiError(429, "rate_limited", "Too many requests.")
        target = conn.execute(
            "select tenant_id, ciphertext, key_id from app_private.webhook_target(%s)",
            (connection_id,),
        ).fetchone()
    if target is None:
        raise _unauthorised(request, "unknown_connection")
    try:
        secret = box.open(
            Sealed(bytes(target["ciphertext"]), target["key_id"]),
            purpose=WEBHOOK_PURPOSE,
            tenant_id=target["tenant_id"],
            record_id=connection_id,
        )
    except SecretsBoxError as exc:
        raise _unauthorised(request, "secret_unreadable") from exc
    if not webhooks.signature_valid(secret, body, signature):
        raise _unauthorised(request, "bad_signature")
    try:
        event = webhooks.parse(body)
    except webhooks.WebhookError as exc:
        log_security_event(request, "webhook_invalid", reason=exc.kind)
        raise ApiError(400, "invalid_event", "Event not accepted.") from exc
    if event.trigger not in webhooks.TRIGGERS:
        return {"result": "ignored"}
    with db.jobs_transaction() as conn:
        result = conn.execute(
            "select app_private.apply_provider_event(%s, %s, %s, %s, %s, %s, %s, %s) as result",
            (
                connection_id,
                event.event_key,
                event.trigger,
                event.uid,
                event.old_uid,
                event.start,
                event.end,
                event.engage_ref,
            ),
        ).fetchone()["result"]
    return {"result": result}


@router.post("/calcom/{connection_id}", include_in_schema=False)
async def calcom_webhook(
    connection_id: uuid.UUID,
    request: Request,
    db: Database = Depends(get_db),
    box: SecretsBox = Depends(get_secrets_box),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> dict:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise ApiError(413, "too_large", "Event too large.")
    signature = request.headers.get("x-cal-signature-256")
    # Database and crypto work off the event loop (the database driver is synchronous).
    return await run_in_threadpool(
        _handle, db, box, tokens, request, connection_id, body, signature
    )
