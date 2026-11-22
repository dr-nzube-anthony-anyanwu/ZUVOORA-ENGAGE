"""The single server-side entitlement check (Phase 5a, ADR-038).

Every gated feature and every plan limit is decided by the database function
`app_private.entitlements_internal()` (through role-specific wrappers). Routes call `require()`
or `limit()`; the dashboard only hides what this would refuse anyway. A refusal carries a
reason code and the plan name so clinics know why.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import psycopg

from app.errors import ApiError

FEATURE_NAMES = {
    "booking": "Online booking",
    "reminders": "Appointment reminders",
    "ai_answers": "AI answers",
    "document_reading": "Reading photos and scanned documents",
    "analytics_basic": "Analytics",
    "analytics_full": "Full analytics",
    "chat_widget": "The website chat",
}
LIMIT_NAMES = {
    "domains": "website domains",
    "documents": "documents",
    "staff_seats": "staff accounts",
    "branches": "branches",
}


@dataclass(frozen=True)
class Entitlements:
    plan_key: str
    plan_name: str
    status: str
    features: frozenset[str] = field(default_factory=frozenset)
    limits: dict[str, float] = field(default_factory=dict)

    def has(self, feature: str) -> bool:
        return feature in self.features

    def limit(self, key: str) -> float | None:
        value = self.limits.get(key)
        return float(value) if value is not None else None


def load(conn: psycopg.Connection, tenant_id: uuid.UUID) -> Entitlements:
    """For staff/platform-admin transactions (the database checks the caller)."""
    row = conn.execute(
        "select plan_key, plan_name, status, features, limits "
        "from app_private.tenant_entitlements(%s)",
        (tenant_id,),
    ).fetchone()
    if row is None:
        return Entitlements(plan_key="none", plan_name="No plan", status="cancelled")
    return Entitlements(
        plan_key=row["plan_key"],
        plan_name=row["plan_name"],
        status=row["status"],
        features=frozenset(row["features"] or []),
        limits={k: float(v) for k, v in (row["limits"] or {}).items()},
    )


def require(conn: psycopg.Connection, tenant_id: uuid.UUID, feature: str) -> Entitlements:
    ents = load(conn, tenant_id)
    if not ents.has(feature):
        raise ApiError(
            403,
            "feature_not_in_plan",
            f"{FEATURE_NAMES.get(feature, 'This feature')} is not included in the clinic's "
            f"{ents.plan_name} plan.",
        )
    return ents


def require_below_limit(
    conn: psycopg.Connection, tenant_id: uuid.UUID, key: str, current: int
) -> None:
    """Refuse creating one more item when `current` already reached the plan's limit."""
    ents = load(conn, tenant_id)
    cap = ents.limit(key)
    if cap is not None and current >= cap:
        raise ApiError(
            409,
            "plan_limit_reached",
            f"The {ents.plan_name} plan allows {int(cap)} {LIMIT_NAMES.get(key, key)}. "
            "Contact ZUVOORA to upgrade.",
        )


def widget_has(conn: psycopg.Connection, feature: str) -> bool:
    """For widget-role transactions (the widget's own clinic only)."""
    return bool(
        conn.execute("select app_private.widget_has_feature(%s) as ok", (feature,)).fetchone()["ok"]
    )


def widget_quota_reached(conn: psycopg.Connection, metric: str) -> bool:
    """For widget-role transactions: has the clinic used its monthly allowance of `metric`?"""
    return bool(
        conn.execute(
            "select app_private.widget_quota_reached(%s) as reached", (metric,)
        ).fetchone()["reached"]
    )
