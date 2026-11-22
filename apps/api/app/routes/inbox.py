"""Conversation inbox and human handover for clinic staff (Phase 3e, ADR-030).

Front desk only (owner, admin, receptionist): message text and contact details are patient data.
RLS enforces the same rule (migration 20261122000002); this layer adds clear 403s and audit
events for reading a transcript and for every status change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.db import Database
from app.deps import get_db, get_principal, record_audit, tenant_transaction
from app.errors import ApiError, not_found
from app.schemas import StrictModel
from app.security.jwt import Principal

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["inbox"])

FRONT_DESK = frozenset({"owner", "admin", "receptionist"})
HandoverStatus = Literal["new", "in_progress", "resolved"]
ConversationStatus = Literal["open", "handover_requested", "closed"]
PREVIEW_CHARS = 140


class HandoverOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: HandoverStatus
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    resolved_by_me: bool


class InboxSummary(BaseModel):
    new: int
    in_progress: int
    open_conversations: int


class ConversationSummary(BaseModel):
    id: uuid.UUID
    status: ConversationStatus
    origin_host: str | None
    started_at: datetime
    last_message_at: datetime
    message_count: int
    preview: str | None
    handover_status: HandoverStatus | None


class MessageOut(BaseModel):
    id: int
    role: Literal["visitor", "assistant", "system"]
    content: str
    answer_source: str | None
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    messages: list[MessageOut]
    handover: HandoverOut | None


class HandoverStatusIn(StrictModel):
    status: HandoverStatus


_HANDOVER_COLUMNS = """
    h.id, h.conversation_id, h.status::text as status, h.contact_name, h.contact_phone,
    h.contact_email, h.note, h.created_at, h.updated_at, h.resolved_at,
    coalesce(h.resolved_by = (select app_private.current_user_id()), false) as resolved_by_me
"""
_CONVERSATION_COLUMNS = """
    c.id, c.status::text as status, c.origin_host, c.started_at, c.last_message_at,
    c.message_count,
    (select left(m.content, %(preview)s) from public.messages m
      where m.conversation_id = c.id and m.role = 'visitor' order by m.id limit 1) as preview,
    (select h.status::text from public.handover_requests h where h.conversation_id = c.id)
      as handover_status
"""


def _handover(conn: psycopg.Connection, handover_id: uuid.UUID) -> HandoverOut:
    row = conn.execute(
        f"select {_HANDOVER_COLUMNS} from public.handover_requests h where h.id = %s",  # noqa: S608
        (handover_id,),
    ).fetchone()
    if row is None:
        raise not_found()
    return HandoverOut(**row)


def _conversation(
    conn: psycopg.Connection, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationSummary:
    row = conn.execute(
        f"select {_CONVERSATION_COLUMNS} from public.conversations c "  # noqa: S608
        "where c.id = %(id)s and c.tenant_id = %(tenant)s",
        {"preview": PREVIEW_CHARS, "id": conversation_id, "tenant": tenant_id},
    ).fetchone()
    if row is None:
        raise not_found()
    return ConversationSummary(**row)


@router.get("/inbox/summary", response_model=InboxSummary)
def inbox_summary(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> InboxSummary:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        row = conn.execute(
            """
            select
              (select count(*) from public.handover_requests
                where tenant_id = %(t)s and status = 'new') as new,
              (select count(*) from public.handover_requests
                where tenant_id = %(t)s and status = 'in_progress') as in_progress,
              (select count(*) from public.conversations
                where tenant_id = %(t)s and status <> 'closed') as open_conversations
            """,
            {"t": tenant_id},
        ).fetchone()
    return InboxSummary(**row)


@router.get("/handovers", response_model=list[HandoverOut])
def list_handovers(
    tenant_id: uuid.UUID,
    request: Request,
    view: Literal["open", "resolved", "all"] = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[HandoverOut]:
    statuses = {
        "open": ["new", "in_progress"],
        "resolved": ["resolved"],
        "all": ["new", "in_progress", "resolved"],
    }[view]
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        rows = conn.execute(
            f"select {_HANDOVER_COLUMNS} from public.handover_requests h "  # noqa: S608
            "where h.tenant_id = %s and h.status::text = any(%s) "
            "order by (h.status = 'new') desc, h.created_at desc limit %s",
            (tenant_id, statuses, limit),
        ).fetchall()
    return [HandoverOut(**r) for r in rows]


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    tenant_id: uuid.UUID,
    request: Request,
    status: ConversationStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[ConversationSummary]:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        rows = conn.execute(
            f"select {_CONVERSATION_COLUMNS} from public.conversations c "  # noqa: S608
            "where c.tenant_id = %(t)s "
            "and (%(status)s::text is null or c.status::text = %(status)s) "
            "order by c.last_message_at desc limit %(limit)s",
            {"preview": PREVIEW_CHARS, "t": tenant_id, "status": status, "limit": limit},
        ).fetchall()
    return [ConversationSummary(**r) for r in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> ConversationDetail:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        conversation = _conversation(conn, tenant_id, conversation_id)
        messages = conn.execute(
            "select id, role::text as role, content, answer_source, created_at "
            "from public.messages where conversation_id = %s and tenant_id = %s order by id",
            (conversation_id, tenant_id),
        ).fetchall()
        handover_row = conn.execute(
            "select id from public.handover_requests where conversation_id = %s and tenant_id = %s",
            (conversation_id, tenant_id),
        ).fetchone()
        handover = _handover(conn, handover_row["id"]) if handover_row else None
        # Reading a patient transcript is an audited access.
        record_audit(
            conn,
            request,
            principal,
            "conversation.viewed",
            tenant_id=tenant_id,
            target_type="conversation",
            target_id=conversation_id,
        )
    return ConversationDetail(
        conversation=conversation,
        messages=[MessageOut(**m) for m in messages],
        handover=handover,
    )


@router.patch("/handovers/{handover_id}", response_model=HandoverOut)
def set_handover_status(
    tenant_id: uuid.UUID,
    handover_id: uuid.UUID,
    body: HandoverStatusIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> HandoverOut:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        current = conn.execute(
            "select status::text as status from public.handover_requests "
            "where id = %s and tenant_id = %s for update",
            (handover_id, tenant_id),
        ).fetchone()
        if current is None:
            raise not_found()
        if current["status"] != body.status:
            conn.execute(
                "update public.handover_requests set status = %s where id = %s and tenant_id = %s",
                (body.status, handover_id, tenant_id),
            )
            record_audit(
                conn,
                request,
                principal,
                "handover.status_changed",
                tenant_id=tenant_id,
                target_type="handover",
                target_id=handover_id,
                metadata={"from": current["status"], "to": body.status},
            )
        return _handover(conn, handover_id)


@router.post("/conversations/{conversation_id}/close", response_model=ConversationSummary)
def close_conversation(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> ConversationSummary:
    with tenant_transaction(request, db, principal, tenant_id, FRONT_DESK) as (conn, _):
        current = _conversation(conn, tenant_id, conversation_id)
        if current.status == "closed":
            raise ApiError(409, "already_closed", "This conversation is already closed.")
        conn.execute(
            "update public.conversations set status = 'closed' where id = %s and tenant_id = %s",
            (conversation_id, tenant_id),
        )
        record_audit(
            conn,
            request,
            principal,
            "conversation.closed",
            tenant_id=tenant_id,
            target_type="conversation",
            target_id=conversation_id,
        )
        return _conversation(conn, tenant_id, conversation_id)
