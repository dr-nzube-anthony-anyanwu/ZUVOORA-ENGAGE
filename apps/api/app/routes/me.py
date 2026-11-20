from fastapi import APIRouter, Depends

from app.db import Database
from app.deps import get_db, get_principal
from app.schemas import MembershipSummary, MeOut
from app.security.jwt import Principal

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeOut)
def get_me(principal: Principal = Depends(get_principal), db: Database = Depends(get_db)) -> MeOut:
    with db.user_transaction(principal) as conn:
        is_admin = conn.execute("select app_private.is_platform_admin() as ok").fetchone()["ok"]
        rows = conn.execute(
            """
            select tm.tenant_id,
                   tm.role::text as role,
                   tm.is_active as membership_active,
                   t.display_name as tenant_display_name,
                   t.status::text as tenant_status,
                   app_private.tenant_role(tm.tenant_id) is not null as accessible
            from public.tenant_memberships tm
            left join public.tenants t on t.id = tm.tenant_id
            where tm.user_id = (select app_private.current_user_id())
            order by t.display_name nulls last, tm.created_at
            """
        ).fetchall()
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        mfa_verified=principal.mfa_verified,
        is_platform_admin=is_admin,
        memberships=[MembershipSummary(**row) for row in rows],
    )
