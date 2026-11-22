"""Analytics (Phase 5c, ADR-040).

* Clinic analytics: owners/admins, computed under their RLS. Basic for every plan
  (analytics_basic); daily trends, rates, AI cost and unanswered topics with analytics_full.
  Unanswered topics are keyword counts from questions the assistant could not answer; a keyword
  must occur at least twice and no sentence or transcript ever leaves the database query.
* Platform overview: MFA platform admins; counts and amounts only.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.db import Database
from app.deps import MANAGER_ROLES, get_db, get_principal, platform_transaction, tenant_transaction
from app.security.jwt import Principal
from app.services import entitlements
from app.services.answering.retrieval import query_terms

router = APIRouter(prefix="/tenants/{tenant_id}/analytics", tags=["analytics"])
platform_router = APIRouter(prefix="/platform/analytics", tags=["platform analytics"])

MIN_TOPIC_COUNT = 2  # a keyword must appear in at least two questions to be shown
TOP_TOPICS = 10


class Handovers(BaseModel):
    total: int
    resolved: int
    open: int
    median_hours_to_resolve: float | None


class DayRow(BaseModel):
    day: date
    conversations: int
    visitor_messages: int
    handovers: int
    bookings: int


class Topic(BaseModel):
    term: str
    count: int


class FullAnalytics(BaseModel):
    daily: list[DayRow]
    cancellation_rate: float | None
    reschedule_rate: float | None
    ai_cost_usd: float
    ai_calls: int
    ai_answer_share: float | None
    unanswered_topics: list[Topic]


class AnalyticsOut(BaseModel):
    days: int
    conversations: int
    visitor_messages: int
    answers: dict[str, int]
    handovers: Handovers
    bookings: dict[str, int]
    full_available: bool
    full: FullAnalytics | None


def _count(conn, sql: str, params: tuple) -> int:
    return int(conn.execute(sql, params).fetchone()["n"])


@router.get("", response_model=AnalyticsOut)
def clinic_analytics(
    tenant_id: uuid.UUID,
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> AnalyticsOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        ents = entitlements.require(conn, tenant_id, "analytics_basic")
        since = conn.execute("select (now() - make_interval(days => %s)) as t", (days,)).fetchone()[
            "t"
        ]
        p = (tenant_id, since)
        conversations = _count(
            conn,
            "select count(*) as n from public.conversations "
            "where tenant_id = %s and started_at >= %s",
            p,
        )
        visitor = _count(
            conn,
            "select count(*) as n from public.messages where tenant_id = %s "
            "and created_at >= %s and role = 'visitor'",
            p,
        )
        answers = {
            r["answer_source"]: int(r["n"])
            for r in conn.execute(
                "select answer_source, count(*) as n from public.messages where tenant_id = %s "
                "and created_at >= %s and role = 'assistant' group by answer_source",
                p,
            ).fetchall()
        }
        h = conn.execute(
            "select count(*) as total, count(*) filter (where status = 'resolved') as resolved, "
            "count(*) filter (where status <> 'resolved') as open, "
            "percentile_cont(0.5) within group "
            "(order by extract(epoch from resolved_at - created_at) / 3600.0) "
            "filter (where status = 'resolved') as median "
            "from public.handover_requests where tenant_id = %s and created_at >= %s",
            p,
        ).fetchone()
        bookings = {
            r["status"]: int(r["n"])
            for r in conn.execute(
                "select status, count(*) as n from public.appointments where tenant_id = %s "
                "and created_at >= %s and status <> 'booking' group by status",
                p,
            ).fetchall()
        }
        full = (
            _full(conn, tenant_id, since, answers, bookings) if ents.has("analytics_full") else None
        )
    return AnalyticsOut(
        days=days,
        conversations=conversations,
        visitor_messages=visitor,
        answers=answers,
        handovers=Handovers(
            total=h["total"],
            resolved=h["resolved"],
            open=h["open"],
            median_hours_to_resolve=round(float(h["median"]), 2)
            if h["median"] is not None
            else None,
        ),
        bookings=bookings,
        full_available=full is not None,
        full=full,
    )


def _full(
    conn, tenant_id: uuid.UUID, since, answers: dict[str, int], bookings: dict[str, int]
) -> FullAnalytics:
    p = {"t": tenant_id, "since": since}
    daily = conn.execute(
        """
        with days as (
          select generate_series(date_trunc('day', %(since)s::timestamptz),
                                 date_trunc('day', now()), interval '1 day')::date as day)
        select d.day,
          (select count(*) from public.conversations c where c.tenant_id = %(t)s
             and c.started_at::date = d.day) as conversations,
          (select count(*) from public.messages m where m.tenant_id = %(t)s and m.role = 'visitor'
             and m.created_at::date = d.day) as visitor_messages,
          (select count(*) from public.handover_requests h where h.tenant_id = %(t)s
             and h.created_at::date = d.day) as handovers,
          (select count(*) from public.appointments a where a.tenant_id = %(t)s
             and a.status not in ('booking', 'failed') and a.created_at::date = d.day) as bookings
        from days d order by d.day
        """,
        p,
    ).fetchall()
    settled = sum(bookings.get(s, 0) for s in ("confirmed", "pending", "cancelled", "rescheduled"))
    ai = conn.execute(
        "select coalesce(sum(cost_usd), 0) as cost, count(*) as calls from public.usage_events "
        "where tenant_id = %(t)s and occurred_at >= %(since)s",
        p,
    ).fetchone()
    answered = sum(answers.values())
    # Visitor questions immediately followed by an honest fallback: keywords only.
    questions = conn.execute(
        """
        select content from (
          select role, content,
                 lead(answer_source) over (partition by conversation_id order by id) as next_source
            from public.messages where tenant_id = %(t)s and created_at >= %(since)s) q
         where role = 'visitor' and next_source = 'fallback'
        """,
        p,
    ).fetchall()
    terms: Counter = Counter()
    for row in questions:
        terms.update(set(query_terms(row["content"])))  # once per question
    topics = [Topic(term=t, count=n) for t, n in terms.most_common() if n >= MIN_TOPIC_COUNT]
    return FullAnalytics(
        daily=[DayRow(**r) for r in daily],
        cancellation_rate=round(bookings.get("cancelled", 0) / settled, 4) if settled else None,
        reschedule_rate=round(bookings.get("rescheduled", 0) / settled, 4) if settled else None,
        ai_cost_usd=float(ai["cost"]),
        ai_calls=int(ai["calls"]),
        ai_answer_share=round(answers.get("retrieval_ai", 0) / answered, 4) if answered else None,
        unanswered_topics=topics[:TOP_TOPICS],
    )


# ----- platform overview -------------------------------------------------------------------------
class ClinicOverview(BaseModel):
    tenant_id: uuid.UUID
    display_name: str
    tenant_status: str
    plan_key: str
    plan_name: str
    subscription_status: str
    monthly_price_ngn: int | None
    messages: float
    ai_usd: float
    emails: float
    bookings: float
    limits: dict[str, float]


class PlatformOverview(BaseModel):
    clinics: list[ClinicOverview]
    estimated_monthly_revenue_ngn: int
    ai_cost_usd_this_month: float
    paying_clinics: int


@platform_router.get("", response_model=PlatformOverview)
def platform_overview(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> PlatformOverview:
    with platform_transaction(request, db, principal) as conn:
        rows = conn.execute("select * from app_private.platform_overview()").fetchall()
    clinics = [
        ClinicOverview(**{**r, "limits": {k: float(v) for k, v in (r["limits"] or {}).items()}})
        for r in rows
    ]
    paying = [
        c
        for c in clinics
        if c.subscription_status in ("active", "past_due") and c.tenant_status == "active"
    ]
    return PlatformOverview(
        clinics=clinics,
        estimated_monthly_revenue_ngn=sum(c.monthly_price_ngn or 0 for c in paying),
        ai_cost_usd_this_month=round(sum(c.ai_usd for c in clinics), 6),
        paying_clinics=len(paying),
    )
