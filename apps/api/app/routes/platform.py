"""Platform-admin routes (ZubeVision staff).

Require an active platform_admins row AND an MFA-verified session (aal2).
"""

import uuid

from fastapi import APIRouter, Depends, Request, status

from app.db import Database
from app.deps import get_auth_admin, get_db, get_principal, platform_transaction, record_audit
from app.errors import ApiError, not_found
from app.schemas import CreatedTenantOut, CreateTenantIn, TenantOut
from app.security.jwt import Principal
from app.services.supabase_admin import AuthAdminError, SupabaseAuthAdmin

router = APIRouter(prefix="/platform", tags=["platform"])

_TENANT_COLUMNS = "id, legal_name, display_name, status::text as status, timezone, created_at"


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> list[TenantOut]:
    with platform_transaction(request, db, principal) as conn:
        rows = conn.execute(
            f"select {_TENANT_COLUMNS} from public.tenants order by created_at desc limit 500"  # noqa: S608
        ).fetchall()
    return [TenantOut(**row) for row in rows]


@router.post("/tenants", response_model=CreatedTenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: CreateTenantIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
    auth_admin: SupabaseAuthAdmin = Depends(get_auth_admin),
) -> CreatedTenantOut:
    with platform_transaction(request, db, principal) as conn:
        tenant = conn.execute(
            f"""insert into public.tenants (legal_name, display_name, timezone, created_by)
                values (%s, %s, %s, %s) returning {_TENANT_COLUMNS}""",  # noqa: S608
            (body.legal_name, body.display_name, body.timezone, principal.user_id),
        ).fetchone()
        conn.execute("insert into public.clinic_profiles (tenant_id) values (%s)", (tenant["id"],))

        owner_id = conn.execute(
            "select app_private.find_user_id_for_invite(%s, %s) as id",
            (tenant["id"], body.owner_email),
        ).fetchone()["id"]
        invited = False
        if owner_id is None:
            try:
                owner_id = auth_admin.invite_user(body.owner_email)
            except AuthAdminError as exc:
                raise ApiError(
                    502, "invite_failed", "The owner invitation could not be sent."
                ) from exc
            invited = True

        conn.execute(
            """insert into public.tenant_memberships (tenant_id, user_id, role, invited_by)
               values (%s, %s, 'owner', %s)""",
            (tenant["id"], owner_id, principal.user_id),
        )
        record_audit(
            conn, request, principal, "tenant.created",
            tenant_id=tenant["id"], target_type="tenant", target_id=tenant["id"],
            metadata={"owner_user_id": str(owner_id), "invitation_sent": invited},
        )
    return CreatedTenantOut(
        tenant=TenantOut(**tenant), owner_user_id=owner_id, owner_invited=invited
    )


def _set_status(
    request: Request, db: Database, principal: Principal, tenant_id: uuid.UUID, new_status: str
) -> TenantOut:
    with platform_transaction(request, db, principal) as conn:
        row = conn.execute(
            f"""update public.tenants set status = %s
                where id = %s and status <> 'closed' returning {_TENANT_COLUMNS}""",  # noqa: S608
            (new_status, tenant_id),
        ).fetchone()
        if row is None:
            raise not_found()
        record_audit(
            conn, request, principal,
            "tenant.suspended" if new_status == "suspended" else "tenant.reactivated",
            tenant_id=tenant_id, target_type="tenant", target_id=tenant_id,
        )
    return TenantOut(**row)


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> TenantOut:
    return _set_status(request, db, principal, tenant_id, "suspended")


@router.post("/tenants/{tenant_id}/reactivate", response_model=TenantOut)
def reactivate_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Database = Depends(get_db),
) -> TenantOut:
    return _set_status(request, db, principal, tenant_id, "active")
