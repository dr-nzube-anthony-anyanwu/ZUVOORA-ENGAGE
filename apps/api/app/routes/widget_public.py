"""Public widget endpoints (Phase 3b, ADR-027). No user authentication.

Trust model:
  * The iframe page carries `Content-Security-Policy: frame-ancestors <verified hosts>`, so
    browsers refuse to display it on any other site. The embedding host (from the Referer) must
    also be a verified domain before a frame ticket is issued.
  * A conversation is identified only by a signed token; tenant/conversation ids never come from
    request bodies. Every database call runs as `engage_widget` (published content only, own
    conversation only).
  * Rate limits per visitor IP (keyed hash), per conversation and per clinic; length caps.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.config import Settings, get_settings
from app.content_schemas import Line, Text
from app.db import Database
from app.deps import get_db
from app.errors import ApiError, log_security_event
from app.schemas import StrictModel
from app.services.assistant import AnswerContext, Responder, Turn, UnavailableResponder
from app.services.widget_tokens import ConversationToken, WidgetTokenError, WidgetTokens

router = APIRouter(tags=["public widget"])

KEY_RE = re.compile(r"^[0-9a-f]{32}$")
_RESOLVE = "select tenant_id, greeting, display_name from app_private.resolve_widget(%s, %s)"
MAX_MESSAGES_PER_CONVERSATION = 50
HISTORY_TURNS = 8

# (window seconds, max hits)
LIMITS = {
    "frame_ip": (60, 30),
    "session_ip": (3600, 20),
    "session_tenant": (86400, 2000),
    "message_ip": (3600, 120),
    "message_conversation": (3600, 40),
    "message_tenant": (86400, 5000),
    "handover_ip": (3600, 5),
}


# ----- dependencies ------------------------------------------------------------------------------
def get_widget_tokens(request: Request) -> WidgetTokens:
    tokens: WidgetTokens | None = getattr(request.app.state, "widget_tokens", None)
    if tokens is None:
        raise ApiError(503, "widget_unavailable", "The chat is not available right now.")
    return tokens


def get_responder(request: Request) -> Responder:
    return getattr(request.app.state, "responder", None) or UnavailableResponder()


def _client_ip(request: Request) -> str:
    # Behind the production reverse proxy, uvicorn's --proxy-headers sets this (Phase 6).
    return request.client.host if request.client else "unknown"


def _hit(
    conn: psycopg.Connection, tokens: WidgetTokens, request: Request, kind: str, value: str
) -> None:
    window, limit = LIMITS[kind]
    allowed = conn.execute(
        "select app_private.rate_limit_hit(%s, %s, %s) as ok",
        (tokens.bucket(kind, value), window, limit),
    ).fetchone()["ok"]
    if not allowed:
        log_security_event(request, "widget_rate_limited", kind=kind)
        raise ApiError(
            429, "rate_limited", "Too many requests. Please wait a moment and try again."
        )


def _conversation(tokens: WidgetTokens, token: str, request: Request) -> ConversationToken:
    try:
        return tokens.verify_conversation(token)
    except WidgetTokenError as exc:
        log_security_event(request, "widget_token_rejected", reason="conversation")
        raise ApiError(
            401, "session_expired", "This chat session has expired. Please reload the page."
        ) from exc


# ----- static assets -----------------------------------------------------------------------------
def _dist_dir(settings: Settings) -> Path:
    if settings.widget_dist_dir:
        return Path(settings.widget_dist_dir)
    return Path(__file__).resolve().parents[3] / "widget" / "dist"


# ----- iframe page -------------------------------------------------------------------------------
def _frame_ancestors(hosts: list[str], allow_http: bool) -> str:
    if not hosts:
        return "'none'"
    sources = [f"https://{h}" for h in hosts]
    if allow_http:
        sources += [f"http://{h}:*" for h in hosts]
    return " ".join(sources)


def _frame_csp(hosts: list[str], allow_http: bool) -> str:
    return (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
        f"frame-ancestors {_frame_ancestors(hosts, allow_http)}"
    )


@router.get("/widget/v1/frame", include_in_schema=False)
def widget_frame(
    request: Request,
    key: str = Query(default="", max_length=64),
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> FileResponse:
    """The static chat page. Browsers display it only inside the clinic's verified domains.

    No clinic data is rendered into HTML here: the page's script fetches its configuration
    from `frame-config`, which issues a ticket only for a verified host.
    """
    settings = get_settings()
    hosts: list[str] = []
    with db.widget_transaction() as conn:
        _hit(conn, tokens, request, "frame_ip", _client_ip(request))
        if KEY_RE.match(key):
            hosts = [
                r["widget_allowed_hosts"]
                for r in conn.execute(
                    "select app_private.widget_allowed_hosts(%s)", (key,)
                ).fetchall()
            ]
    path = _dist_dir(settings) / "frame.html"
    if not path.is_file():
        raise ApiError(503, "widget_not_built", "The widget is not available.")
    headers = {
        "Content-Security-Policy": _frame_csp(hosts, settings.widget_allow_http_frames),
        "Referrer-Policy": "no-referrer",
    }
    return FileResponse(path, media_type="text/html; charset=utf-8", headers=headers)


class FrameConfigIn(StrictModel):
    key: str = Field(pattern=r"^[0-9a-f]{32}$")
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")


class FrameConfigOut(BaseModel):
    ticket: str
    clinic: str
    greeting: str


@router.post("/api/v1/public/widget/frame-config", response_model=FrameConfigOut)
def frame_config(
    body: FrameConfigIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> FrameConfigOut:
    """Issue a frame ticket if `host` is a verified domain of an enabled, active clinic.

    `host` comes from the loader (the embedding page's hostname). A non-browser client can claim
    any host, exactly as it could forge a Referer; browsers are bound by frame-ancestors, and the
    public API is rate-limited and budget-capped regardless.
    """
    host = body.host.lower()
    with db.widget_transaction() as conn:
        _hit(conn, tokens, request, "frame_ip", _client_ip(request))
        clinic = conn.execute(_RESOLVE, (body.key, host)).fetchone()
    if clinic is None:
        log_security_event(request, "widget_frame_refused", host=host)
        raise ApiError(403, "widget_unavailable", "This chat is not available on this website.")
    return FrameConfigOut(
        ticket=tokens.issue_ticket(body.key, host),
        clinic=clinic["display_name"],
        greeting=clinic["greeting"],
    )


# ----- API: session, messages, handover ----------------------------------------------------------
class SessionIn(StrictModel):
    ticket: str = Field(min_length=20, max_length=2000)


class SessionOut(BaseModel):
    token: str
    clinic: str
    greeting: str


class MessageIn(StrictModel):
    token: str = Field(min_length=20, max_length=2000)
    text: Text = Field(min_length=1, max_length=1000)


class ReplyOut(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    source: str
    offer_handover: bool


class MessageOut(BaseModel):
    reply: ReplyOut
    conversation_status: str


class HandoverIn(StrictModel):
    token: str = Field(min_length=20, max_length=2000)
    name: Line | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30, pattern=r"^\+?[0-9][0-9 ()\-]{4,28}$")
    email: EmailStr | None = None
    note: Text | None = Field(default=None, max_length=1000)
    consent: bool

    @field_validator("consent")
    @classmethod
    def _must_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("consent is required to pass your details to the clinic")
        return value


class HandoverOut(BaseModel):
    status: Literal["handover_requested"] = "handover_requested"
    message: str


@router.post("/api/v1/public/widget/session", response_model=SessionOut)
def start_session(
    body: SessionIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> SessionOut:
    try:
        ticket = tokens.verify_ticket(body.ticket)
    except WidgetTokenError as exc:
        log_security_event(request, "widget_token_rejected", reason="ticket")
        raise ApiError(401, "session_expired", "Please reload the page to start a chat.") from exc
    with db.widget_transaction() as conn:
        _hit(conn, tokens, request, "session_ip", _client_ip(request))
        clinic = conn.execute(
            _RESOLVE,
            (ticket.public_key, ticket.host),
        ).fetchone()
    if clinic is None:  # disabled, suspended or domain removed since the page loaded
        raise ApiError(403, "widget_unavailable", "The chat is not available on this website.")
    tenant_id: uuid.UUID = clinic["tenant_id"]
    conversation_id = uuid.uuid4()  # server-generated; set as the widget context before insert
    with db.widget_transaction(tenant_id, conversation_id) as conn:
        _hit(conn, tokens, request, "session_tenant", str(tenant_id))
        conn.execute(
            "insert into public.conversations (id, tenant_id, origin_host) values (%s, %s, %s)",
            (conversation_id, tenant_id, ticket.host),
        )
    return SessionOut(
        token=tokens.issue_conversation(tenant_id, conversation_id, ticket.host),
        clinic=clinic["display_name"],
        greeting=clinic["greeting"],
    )


def _open_conversation(conn: psycopg.Connection) -> dict:
    """The token's conversation, if the widget is still enabled for an active clinic."""
    if conn.execute("select 1 from public.widget_configs").fetchone() is None:
        raise ApiError(403, "widget_unavailable", "The chat is not available right now.")
    row = conn.execute(
        "select status::text as status, message_count from public.conversations"
    ).fetchone()
    if row is None:
        raise ApiError(
            401, "session_expired", "This chat session has expired. Please reload the page."
        )
    return row


@router.post("/api/v1/public/widget/messages", response_model=MessageOut)
def send_message(
    body: MessageIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
    responder: Responder = Depends(get_responder),
) -> MessageOut:
    ctx = _conversation(tokens, body.token, request)
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        _hit(conn, tokens, request, "message_ip", _client_ip(request))
        _hit(conn, tokens, request, "message_conversation", str(ctx.conversation_id))
        _hit(conn, tokens, request, "message_tenant", str(ctx.tenant_id))
        conversation = _open_conversation(conn)
        if conversation["status"] == "closed":
            raise ApiError(409, "conversation_closed", "This conversation has been closed.")
        if conversation["message_count"] >= MAX_MESSAGES_PER_CONVERSATION:
            raise ApiError(
                409,
                "conversation_full",
                "This conversation is very long. Please reload the page to start a new one.",
            )
        history = [
            Turn(r["role"], r["content"])
            for r in reversed(
                conn.execute(
                    "select role::text as role, content from public.messages "
                    "where role in ('visitor', 'assistant') order by id desc limit %s",
                    (HISTORY_TURNS,),
                ).fetchall()
            )
        ]
        conn.execute(
            "insert into public.messages (tenant_id, conversation_id, role, content) "
            "values (%s, %s, 'visitor', %s)",
            (ctx.tenant_id, ctx.conversation_id, body.text),
        )
        answer = responder.answer(
            conn,
            AnswerContext(
                tenant_id=ctx.tenant_id,
                conversation_id=ctx.conversation_id,
                question=body.text,
                history=history,
            ),
        )
        conn.execute(
            "insert into public.messages "
            "(tenant_id, conversation_id, role, content, answer_source, model, safety) "
            "values (%s, %s, 'assistant', %s, %s, %s, %s::jsonb)",
            (
                ctx.tenant_id,
                ctx.conversation_id,
                answer.text,
                answer.source,
                answer.model,
                json.dumps(answer.safety),
            ),
        )
    return MessageOut(
        reply=ReplyOut(
            content=answer.text, source=answer.source, offer_handover=answer.offer_handover
        ),
        conversation_status=conversation["status"],
    )


@router.post("/api/v1/public/widget/handover", response_model=HandoverOut)
def request_handover(
    body: HandoverIn,
    request: Request,
    db: Database = Depends(get_db),
    tokens: WidgetTokens = Depends(get_widget_tokens),
) -> HandoverOut:
    if not body.phone and not body.email:
        raise ApiError(422, "contact_required", "Please give a phone number or an email address.")
    ctx = _conversation(tokens, body.token, request)
    message = (
        "Thank you. The clinic team has your details and will contact you. "
        "If this is an emergency, please call the clinic or go to the nearest emergency department."
    )
    with db.widget_transaction(ctx.tenant_id, ctx.conversation_id) as conn:
        _hit(conn, tokens, request, "handover_ip", _client_ip(request))
        conversation = _open_conversation(conn)
        if conversation["status"] == "closed":
            raise ApiError(409, "conversation_closed", "This conversation has been closed.")
        try:
            with conn.transaction():
                conn.execute(
                    "insert into public.handover_requests (tenant_id, conversation_id, "
                    "contact_name, contact_phone, contact_email, note, consent_given) "
                    "values (%s, %s, %s, %s, %s, %s, true)",
                    (
                        ctx.tenant_id,
                        ctx.conversation_id,
                        body.name,
                        body.phone,
                        str(body.email) if body.email else None,
                        body.note,
                    ),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise ApiError(
                409, "handover_exists", "The clinic already has your details for this conversation."
            ) from exc
        conn.execute("update public.conversations set status = 'handover_requested'")
        conn.execute(
            "insert into public.messages "
            "(tenant_id, conversation_id, role, content, answer_source) "
            "values (%s, %s, 'system', %s, 'handover')",
            (ctx.tenant_id, ctx.conversation_id, message),
        )
    return HandoverOut(message=message)


# ----- static assets (registered last so /widget/v1/frame is matched first) -----------------
_ASSETS = {"loader.js": "text/javascript", "frame.js": "text/javascript", "frame.css": "text/css"}


@router.get("/widget/v1/{asset}", include_in_schema=False)
def widget_asset(asset: str) -> FileResponse:
    if asset not in _ASSETS:  # fixed allow-list: no path traversal
        raise ApiError(404, "not_found", "Resource not found.")
    path = _dist_dir(get_settings()) / asset
    if not path.is_file():
        raise ApiError(503, "widget_not_built", "The widget is not available.")
    return FileResponse(path, media_type=_ASSETS[asset])
