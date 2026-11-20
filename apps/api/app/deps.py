"""Request dependencies: authentication, database and tenant/platform authorisation."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import Database
from app.errors import ApiError, forbidden, log_security_event, not_found, request_id_of
from app.security.jwt import Principal, TokenError, TokenVerifier
from app.services.supabase_admin import SupabaseAuthAdmin

ALL_ROLES = frozenset({"owner", "admin", "receptionist", "viewer"})
MANAGER_ROLES = frozenset({"owner", "admin"})

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    db: Database | None = getattr(request.app.state, "db", None)
    if db is None:
        raise ApiError(503, "database_unavailable", "Database is not configured.")
    return db


def get_auth_admin(request: Request) -> SupabaseAuthAdmin:
    admin: SupabaseAuthAdmin | None = getattr(request.app.state, "auth_admin", None)
    if admin is None:
        raise ApiError(503, "auth_admin_unavailable", "Auth administration is not configured.")
    return admin


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    verifier: TokenVerifier | None = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise ApiError(503, "auth_unavailable", "Authentication is not configured.")
    if credentials is None:
        raise ApiError(401, "unauthenticated", "Authentication required.")
    try:
        return verifier.verify(credentials.credentials)
    except TokenError as exc:
        log_security_event(request, "token_rejected", reason=str(exc))
        raise ApiError(401, "unauthenticated", "Invalid or expired session.") from exc


@contextmanager
def tenant_transaction(
    request: Request,
    db: Database,
    principal: Principal,
    tenant_id: uuid.UUID,
    allowed_roles: frozenset[str] = ALL_ROLES,
) -> Iterator[tuple[psycopg.Connection, str]]:
    """Open an RLS transaction and require an allowed role in an accessible tenant.

    The tenant comes only from the URL path and is re-checked against the database. Requests
    for tenants the user cannot access return 404 so tenant existence is never disclosed.
    """
    with db.user_transaction(principal) as conn:
        row = conn.execute(
            "select app_private.tenant_role(%s) as role", (tenant_id,)
        ).fetchone()
        role = row["role"] if row else None
        if role is None:
            log_security_event(
                request, "tenant_access_denied", user=principal.user_id, tenant=tenant_id
            )
            raise not_found()
        if role not in allowed_roles:
            log_security_event(
                request, "role_denied", user=principal.user_id, tenant=tenant_id, role=role
            )
            raise forbidden()
        yield conn, role


@contextmanager
def platform_transaction(
    request: Request, db: Database, principal: Principal
) -> Iterator[psycopg.Connection]:
    """Open an RLS transaction and require an MFA-verified, active platform admin."""
    with db.user_transaction(principal) as conn:
        row = conn.execute(
            """
            select app_private.is_platform_admin() as ok,
                   exists (select 1 from public.platform_admins
                           where user_id = (select app_private.current_user_id())
                             and is_active) as listed
            """
        ).fetchone()
        if not row["ok"]:
            log_security_event(
                request,
                "platform_access_denied",
                user=principal.user_id,
                listed=row["listed"],
                aal=principal.aal,
            )
            if row["listed"] and not principal.mfa_verified:
                raise ApiError(403, "mfa_required", "Multi-factor authentication is required.")
            raise forbidden()
        yield conn


def record_audit(
    conn: psycopg.Connection,
    request: Request,
    principal: Principal,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit event in the same transaction as the action it describes."""
    conn.execute(
        """
        insert into public.audit_events
          (actor_user_id, tenant_id, action, target_type, target_id, request_id, metadata)
        values (%s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            principal.user_id,
            tenant_id,
            action,
            target_type,
            str(target_id) if target_id is not None else None,
            request_id_of(request),
            json.dumps(metadata or {}),
        ),
    )
