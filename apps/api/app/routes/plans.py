"""Plans and subscriptions (Phase 5a, ADR-038).

* Clinics (owner/admin) read their plan, features and limits.
* MFA platform admins edit the catalogue and assign a clinic's subscription or overrides.
  Changing plan never touches the clinic's identity, data or widget. Every change is audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.db import Database
from app.deps import (
    MANAGER_ROLES,
    get_db,
    get_principal,
    platform_transaction,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, not_found
from app.schemas import StrictModel
from app.security.jwt import Principal
from app.services import entitlements

clinic_router = APIRouter(prefix="/tenants/{tenant_id}/plan", tags=["plans"])
platform_router = APIRouter(prefix="/platform", tags=["platform plans"])

LimitKey = Literal[
    "messages_month",
    "ai_usd_month",
    "emails_month",
    "bookings_month",
    "documents",
    "staff_seats",
    "domains",
    "branches",
]
Status = Literal["trialing", "active", "past_due", "cancelled"]


class FeatureOut(BaseModel):
    key: str
    name: str
    description: str | None
    available: bool
    included: bool


class ClinicPlanOut(BaseModel):
    plan_key: str
    plan_name: str
    status: Status
    current_period_end: datetime | None
    features: list[FeatureOut]
    limits: dict[str, float]


class PlanOut(BaseModel):
    key: str
    name: str
    description: str | None
    tier_order: int
    monthly_price_ngn: int | None
    setup_fee_ngn: int | None
    is_public: bool
    features: list[str]
    limits: dict[str, float]


class CatalogueOut(BaseModel):
    plans: list[PlanOut]
    features: list[FeatureOut]


class PlanUpdateIn(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    monthly_price_ngn: int | None = Field(default=None, ge=0, le=100_000_000)
    setup_fee_ngn: int | None = Field(default=None, ge=0, le=1_000_000_000)
    features: list[str] | None = Field(default=None, max_length=50)
    limits: dict[LimitKey, float] | None = None


class SubscriptionOut(BaseModel):
    tenant_id: uuid.UUID
    display_name: str
    tenant_status: str
    plan_key: str
    status: Status
    current_period_end: datetime | None
    monthly_price_override_ngn: int | None
    notes: str | None


class SubscriptionIn(StrictModel):
    plan_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    status: Status
    current_period_end: datetime | None = None
    monthly_price_override_ngn: int | None = Field(default=None, ge=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=500)


class OverrideIn(StrictModel):
    kind: Literal["feature", "limit"]
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    feature_enabled: bool | None = None
    limit_value: float | None = Field(default=None, ge=0, le=100_000_000)
    reason: str = Field(min_length=3, max_length=300)


# ----- clinic ------------------------------------------------------------------------------------
def _features(conn: psycopg.Connection, included: frozenset[str]) -> list[FeatureOut]:
    rows = conn.execute(
        "select key, name, description, available from public.features order by sort_order"
    ).fetchall()
    return [FeatureOut(**r, included=r["key"] in included) for r in rows]


@clinic_router.get("", response_model=ClinicPlanOut)
def clinic_plan(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> ClinicPlanOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        ents = entitlements.load(conn, tenant_id)
        sub = conn.execute(
            "select current_period_end from public.tenant_subscriptions where tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        # Plan features as sold (incl. "not yet available"), then what is actually granted.
        sold = {
            r["feature_key"]
            for r in conn.execute(
                "select feature_key from public.plan_features where plan_key = %s", (ents.plan_key,)
            ).fetchall()
        }
        features = _features(conn, frozenset(sold) | ents.features)
        for f in features:
            f.included = f.key in ents.features or (f.key in sold and not f.available)
        return ClinicPlanOut(
            plan_key=ents.plan_key,
            plan_name=ents.plan_name,
            status=ents.status,
            current_period_end=sub["current_period_end"] if sub else None,
            features=features,
            limits=ents.limits,
        )


# ----- platform admin ----------------------------------------------------------------------------
def _catalogue(conn: psycopg.Connection) -> CatalogueOut:
    plans = conn.execute(
        "select key, name, description, tier_order, monthly_price_ngn, setup_fee_ngn, is_public "
        "from public.plans order by tier_order"
    ).fetchall()
    features = {p["key"]: [] for p in plans}
    for r in conn.execute("select plan_key, feature_key from public.plan_features").fetchall():
        features[r["plan_key"]].append(r["feature_key"])
    limits: dict[str, dict[str, float]] = {p["key"]: {} for p in plans}
    for r in conn.execute("select plan_key, limit_key, value from public.plan_limits").fetchall():
        limits[r["plan_key"]][r["limit_key"]] = float(r["value"])
    return CatalogueOut(
        plans=[
            PlanOut(**p, features=sorted(features[p["key"]]), limits=limits[p["key"]])
            for p in plans
        ],
        features=_features(conn, frozenset()),
    )


@platform_router.get("/plans", response_model=CatalogueOut)
def get_catalogue(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> CatalogueOut:
    with platform_transaction(request, db, principal) as conn:
        return _catalogue(conn)


@platform_router.put("/plans/{plan_key}", response_model=CatalogueOut)
def update_plan(
    plan_key: str,
    body: PlanUpdateIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> CatalogueOut:
    with platform_transaction(request, db, principal) as conn:
        if (
            conn.execute("select 1 from public.plans where key = %s", (plan_key,)).fetchone()
            is None
        ):
            raise not_found()
        fields = body.model_dump(
            exclude_none=True, include={"name", "description", "monthly_price_ngn", "setup_fee_ngn"}
        )
        for column, value in fields.items():  # fixed column names from the model
            conn.execute(
                f"update public.plans set {column} = %s, updated_at = now() where key = %s",  # noqa: S608
                (value, plan_key),
            )
        if body.features is not None:
            known = {r["key"] for r in conn.execute("select key from public.features").fetchall()}
            unknown = set(body.features) - known
            if unknown:
                raise ApiError(422, "unknown_feature", "Unknown feature in the list.")
            conn.execute("delete from public.plan_features where plan_key = %s", (plan_key,))
            for feature in sorted(set(body.features)):
                conn.execute(
                    "insert into public.plan_features (plan_key, feature_key) values (%s, %s)",
                    (plan_key, feature),
                )
        for key, value in (body.limits or {}).items():
            conn.execute(
                "insert into public.plan_limits (plan_key, limit_key, value) values (%s, %s, %s) "
                "on conflict (plan_key, limit_key) do update set value = excluded.value",
                (plan_key, key, value),
            )
        record_audit(
            conn,
            request,
            principal,
            "plan.updated",
            target_type="plan",
            target_id=plan_key,
            metadata=body.model_dump(exclude_none=True),
        )
        return _catalogue(conn)


_SUBSCRIPTIONS = """select s.tenant_id, t.display_name, t.status::text as tenant_status,
    s.plan_key, s.status, s.current_period_end, s.monthly_price_override_ngn, s.notes
    from public.tenant_subscriptions s join public.tenants t on t.id = s.tenant_id"""


@platform_router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[SubscriptionOut]:
    with platform_transaction(request, db, principal) as conn:
        rows = conn.execute(_SUBSCRIPTIONS + " order by t.display_name limit 1000").fetchall()
    return [SubscriptionOut(**r) for r in rows]


@platform_router.put("/tenants/{tenant_id}/subscription", response_model=SubscriptionOut)
def set_subscription(
    tenant_id: uuid.UUID,
    body: SubscriptionIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> SubscriptionOut:
    with platform_transaction(request, db, principal) as conn:
        before = conn.execute(
            "select plan_key, status from public.tenant_subscriptions where tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        if before is None:
            raise not_found()
        try:
            with conn.transaction():
                conn.execute(
                    "update public.tenant_subscriptions set plan_key = %s, status = %s, "
                    "current_period_end = %s, monthly_price_override_ngn = %s, notes = %s "
                    "where tenant_id = %s",
                    (
                        body.plan_key,
                        body.status,
                        body.current_period_end,
                        body.monthly_price_override_ngn,
                        body.notes,
                        tenant_id,
                    ),
                )
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ApiError(422, "unknown_plan", "Unknown plan.") from exc
        record_audit(
            conn,
            request,
            principal,
            "subscription.changed",
            tenant_id=tenant_id,
            target_type="tenant",
            target_id=tenant_id,
            metadata={
                "from": dict(before),
                "to": {"plan_key": body.plan_key, "status": body.status},
            },
        )
        row = conn.execute(_SUBSCRIPTIONS + " where s.tenant_id = %s", (tenant_id,)).fetchone()
    return SubscriptionOut(**row)


@platform_router.put("/tenants/{tenant_id}/overrides", response_model=ClinicPlanOut)
def set_override(
    tenant_id: uuid.UUID,
    body: OverrideIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> ClinicPlanOut:
    if (body.kind == "feature") != (body.feature_enabled is not None) or (body.kind == "limit") != (
        body.limit_value is not None
    ):
        raise ApiError(
            422, "invalid_override", "Give feature_enabled for a feature, limit_value for a limit."
        )
    with platform_transaction(request, db, principal) as conn:
        conn.execute(
            "delete from public.tenant_overrides where tenant_id = %s and kind = %s and key = %s",
            (tenant_id, body.kind, body.key),
        )
        try:
            with conn.transaction():
                conn.execute(
                    "insert into public.tenant_overrides (tenant_id, kind, key, feature_enabled, "
                    "limit_value, reason) values (%s, %s, %s, %s, %s, %s)",
                    (
                        tenant_id,
                        body.kind,
                        body.key,
                        body.feature_enabled,
                        body.limit_value,
                        body.reason,
                    ),
                )
        except psycopg.errors.ForeignKeyViolation as exc:
            raise not_found() from exc
        record_audit(
            conn,
            request,
            principal,
            "subscription.override_set",
            tenant_id=tenant_id,
            target_type="tenant",
            target_id=tenant_id,
            metadata=body.model_dump(),
        )
        ents = entitlements.load(conn, tenant_id)
        return ClinicPlanOut(
            plan_key=ents.plan_key,
            plan_name=ents.plan_name,
            status=ents.status,
            current_period_end=None,
            features=_features(conn, ents.features),
            limits=ents.limits,
        )


@platform_router.delete("/tenants/{tenant_id}/overrides/{kind}/{key}", status_code=204)
def delete_override(
    tenant_id: uuid.UUID,
    kind: Literal["feature", "limit"],
    key: str,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> None:
    with platform_transaction(request, db, principal) as conn:
        deleted = conn.execute(
            "delete from public.tenant_overrides where tenant_id = %s "
            "and kind = %s and key = %s returning 1",
            (tenant_id, kind, key),
        ).fetchone()
        if deleted is None:
            raise not_found()
        record_audit(
            conn,
            request,
            principal,
            "subscription.override_removed",
            tenant_id=tenant_id,
            target_type="tenant",
            target_id=tenant_id,
            metadata={"kind": kind, "key": key},
        )


# ----- usage (Phase 5b) --------------------------------------------------------------------------
usage_router = APIRouter(prefix="/tenants/{tenant_id}/usage", tags=["plans"])

METERED = {  # metric -> (plan limit key, label)
    "messages": ("messages_month", "Chat messages"),
    "ai_usd": ("ai_usd_month", "AI spend (USD)"),
    "emails": ("emails_month", "Emails"),
    "bookings": ("bookings_month", "Bookings"),
}
COUNTED = {  # current count query -> (plan limit key, label)
    "documents": (
        "select count(*) from public.knowledge_documents where tenant_id = %s "
        "and archived_at is null",
        "Knowledge documents",
    ),
    "staff_seats": (
        "select count(*) from public.tenant_memberships where tenant_id = %s and is_active",
        "Staff accounts",
    ),
    "domains": (
        "select count(*) from public.tenant_domains where tenant_id = %s and removed_at is null",
        "Website domains",
    ),
    "branches": (
        "select count(*) from public.branches where tenant_id = %s and archived_at is null",
        "Branches",
    ),
}


class UsageItem(BaseModel):
    key: str
    label: str
    used: float
    limit: float | None


class UsageOut(BaseModel):
    period: str
    monthly: list[UsageItem]
    totals: list[UsageItem]
    ai_tokens: float


@usage_router.get("", response_model=UsageOut)
def clinic_usage(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> UsageOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        ents = entitlements.load(conn, tenant_id)
        used = {
            r["metric"]: float(r["quantity"])
            for r in conn.execute(
                "select metric, quantity from app_private.tenant_usage(%s)", (tenant_id,)
            ).fetchall()
        }
        period = conn.execute(
            "select to_char(date_trunc('month', now() at time zone 'UTC'), 'YYYY-MM') as p"
        ).fetchone()["p"]
        totals = []
        for key, (query, label) in COUNTED.items():
            count = conn.execute(query, (tenant_id,)).fetchone()["count"]
            totals.append(UsageItem(key=key, label=label, used=count, limit=ents.limit(key)))
    return UsageOut(
        period=period,
        monthly=[
            UsageItem(key=m, label=label, used=used.get(m, 0.0), limit=ents.limit(limit_key))
            for m, (limit_key, label) in METERED.items()
        ],
        totals=totals,
        ai_tokens=used.get("ai_tokens", 0.0),
    )
