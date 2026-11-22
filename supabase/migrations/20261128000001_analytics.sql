-- Phase 5c: analytics support (ADR-040).
--
-- * Clinic analytics are computed by the API under the caller's RLS (owners/admins read their own
--   clinic's messages, call-backs, appointments and AI usage) — no new data access is granted.
-- * The platform overview needs every clinic's monthly usage and plan in one query: a function
--   that only MFA platform admins can get rows from. It returns counts and amounts, never
--   conversation content or patient details.

create index if not exists messages_tenant_created_idx on public.messages (tenant_id, created_at);
create index if not exists appointments_tenant_created_idx on public.appointments (tenant_id, created_at);
create index if not exists handover_tenant_created_idx on public.handover_requests (tenant_id, created_at);

create or replace function app_private.platform_overview()
returns table (
  tenant_id uuid, display_name text, tenant_status text, plan_key text, plan_name text,
  subscription_status text, monthly_price_ngn integer, messages numeric, ai_usd numeric,
  emails numeric, bookings numeric, limits jsonb
)
language sql stable security definer
set search_path = ''
as $$
  select t.id, t.display_name, t.status::text, s.plan_key, p.name, s.status,
         coalesce(s.monthly_price_override_ngn, p.monthly_price_ngn),
         coalesce(max(c.quantity) filter (where c.metric = 'messages'), 0),
         coalesce(max(c.quantity) filter (where c.metric = 'ai_usd'), 0),
         coalesce(max(c.quantity) filter (where c.metric = 'emails'), 0),
         coalesce(max(c.quantity) filter (where c.metric = 'bookings'), 0),
         (select e.limits from app_private.entitlements_internal(t.id) e)
    from public.tenants t
    join public.tenant_subscriptions s on s.tenant_id = t.id
    join public.plans p on p.key = s.plan_key
    left join app_private.usage_counters c
      on c.tenant_id = t.id and c.period_month = app_private.current_period()
   where app_private.is_platform_admin()
   group by t.id, t.display_name, t.status, s.plan_key, p.name, s.status,
            s.monthly_price_override_ngn, p.monthly_price_ngn
   order by t.display_name;
$$;
revoke all on function app_private.platform_overview() from public, anon, authenticated;
grant execute on function app_private.platform_overview() to engage_app;
