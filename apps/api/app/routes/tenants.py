"""Tenant (clinic) routes.

The tenant id comes only from the URL path and is re-authorised against the database on every
request; request bodies cannot carry tenant ids, roles or status.
"""

import uuid

import psycopg
from fastapi import APIRouter, Depends, Request, status

from app.db import Database
from app.deps import (
    ALL_ROLES,
    MANAGER_ROLES,
    get_auth_admin,
    get_db,
    get_principal,
    record_audit,
    tenant_transaction,
)
from app.errors import ApiError, forbidden, not_found
from app.schemas import (
    InviteMemberIn,
    MemberOut,
    TenantDetailOut,
    TenantOut,
    UpdateMemberRoleIn,
)
from app.security.jwt import Principal
from app.services.supabase_admin import AuthAdminError, SupabaseAuthAdmin

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["tenants"])

_TENANT_COLUMNS = "id, legal_name, display_name, status::text as status, timezone, created_at"
_MEMBER_QUERY = (
    "select membership_id, user_id, email, role::text as role, is_active, created_at, revoked_at "
    "from app_private.tenant_member_directory(%s)"
)


def _member(conn: psycopg.Connection, tenant_id: uuid.UUID, membership_id: uuid.UUID) -> MemberOut:
    row = conn.execute(
        _MEMBER_QUERY + " where membership_id = %s", (tenant_id, membership_id)
    ).fetchone()
    if row is None:
        raise not_found()
    return MemberOut(**row)


@router.get("", response_model=TenantDetailOut)
def get_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> TenantDetailOut:
    with tenant_transaction(request, db, principal, tenant_id, ALL_ROLES) as (conn, role):
        tenant = conn.execute(
            f"select {_TENANT_COLUMNS} from public.tenants where id = %s", (tenant_id,)  # noqa: S608
        ).fetchone()
    if tenant is None:
        raise not_found()
    return TenantDetailOut(
        tenant=TenantOut(**tenant),
        my_role=role,
    )


@router.get("/members", response_model=list[MemberOut])
def list_members(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[MemberOut]:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        rows = conn.execute(_MEMBER_QUERY, (tenant_id,)).fetchall()
    return [MemberOut(**row) for row in rows]


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def invite_member(
    tenant_id: uuid.UUID,
    body: InviteMemberIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    auth_admin: SupabaseAuthAdmin = Depends(get_auth_admin),
) -> MemberOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, my_role):
        if body.role == "owner" and my_role != "owner":
            raise forbidden("Only an owner can grant the owner role.")

        user_id = conn.execute(
            "select app_private.find_user_id_for_invite(%s, %s) as id", (tenant_id, body.email)
        ).fetchone()["id"]
        invited = False
        if user_id is None:
            try:
                user_id = auth_admin.invite_user(body.email)
            except AuthAdminError as exc:
                raise ApiError(502, "invite_failed", "The invitation could not be sent.") from exc
            invited = True

        existing = conn.execute(
            """select id, is_active from public.tenant_memberships
               where tenant_id = %s and user_id = %s""",
            (tenant_id, user_id),
        ).fetchone()
        if existing and existing["is_active"]:
            raise ApiError(409, "already_member", "This user is already a member of the clinic.")

        try:
            if existing:
                row = conn.execute(
                    """update public.tenant_memberships
                       set role = %s, is_active = true, revoked_at = null, revoked_by = null
                       where id = %s and tenant_id = %s returning id""",
                    (body.role, existing["id"], tenant_id),
                ).fetchone()
                action = "membership.reactivated"
            else:
                row = conn.execute(
                    """insert into public.tenant_memberships (tenant_id, user_id, role, invited_by)
                       values (%s, %s, %s, %s) returning id""",
                    (tenant_id, user_id, body.role, principal.user_id),
                ).fetchone()
                action = "membership.invited"
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        if row is None:
            raise forbidden()

        record_audit(
            conn, request, principal, action,
            tenant_id=tenant_id, target_type="membership", target_id=row["id"],
            metadata={"role": body.role, "user_id": str(user_id), "invitation_sent": invited},
        )
        return _member(conn, tenant_id, row["id"])


@router.patch("/members/{membership_id}", response_model=MemberOut)
def update_member_role(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: UpdateMemberRoleIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> MemberOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        target = conn.execute(
            """select id, role::text as role, is_active from public.tenant_memberships
               where id = %s and tenant_id = %s""",
            (membership_id, tenant_id),
        ).fetchone()
        if target is None:
            raise not_found()
        if not target["is_active"]:
            raise ApiError(409, "membership_revoked", "This membership has been revoked.")
        try:
            row = conn.execute(
                """update public.tenant_memberships set role = %s
                   where id = %s and tenant_id = %s returning id""",
                (body.role, membership_id, tenant_id),
            ).fetchone()
        except psycopg.errors.CheckViolation as exc:
            raise ApiError(409, "last_owner", "A clinic must keep at least one owner.") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        if row is None:  # RLS: e.g. an admin targeting an owner or granting owner
            raise forbidden()
        record_audit(
            conn, request, principal, "membership.role_changed",
            tenant_id=tenant_id, target_type="membership", target_id=membership_id,
            metadata={"from": target["role"], "to": body.role},
        )
        return _member(conn, tenant_id, membership_id)


@router.post("/members/{membership_id}/revoke", response_model=MemberOut)
def revoke_member(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> MemberOut:
    with tenant_transaction(request, db, principal, tenant_id, MANAGER_ROLES) as (conn, _):
        target = conn.execute(
            "select id, is_active from public.tenant_memberships where id = %s and tenant_id = %s",
            (membership_id, tenant_id),
        ).fetchone()
        if target is None:
            raise not_found()
        if not target["is_active"]:
            raise ApiError(409, "membership_revoked", "This membership is already revoked.")
        try:
            row = conn.execute(
                """update public.tenant_memberships
                   set is_active = false, revoked_at = now(), revoked_by = %s
                   where id = %s and tenant_id = %s returning id""",
                (principal.user_id, membership_id, tenant_id),
            ).fetchone()
        except psycopg.errors.CheckViolation as exc:
            raise ApiError(409, "last_owner", "A clinic must keep at least one owner.") from exc
        except psycopg.errors.InsufficientPrivilege as exc:
            raise forbidden() from exc
        if row is None:
            raise forbidden()
        record_audit(
            conn, request, principal, "membership.revoked",
            tenant_id=tenant_id, target_type="membership", target_id=membership_id,
        )
        return _member(conn, tenant_id, membership_id)
