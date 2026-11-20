-- ZUVOORA Engage — Phase 1 tenant, membership, platform-admin and audit foundation.
-- Apply only to the dedicated ZUVOORA Engage Supabase project (never ZUVOORA Core).
--
-- Security model (see docs/security/TENANCY_AND_RLS.md):
--   * Every tenant-owned table has RLS enabled and forced; anon has no access at all.
--   * Access requires an ACTIVE membership in a tenant whose status is 'pending' or 'active'.
--     Suspended/closed tenants and revoked memberships lose access immediately.
--   * Platform admins (ZubeVision staff) must hold an active platform_admins row AND an
--     MFA-verified session (JWT aal = 'aal2').
--   * Audit events are append-only: no UPDATE/DELETE/TRUNCATE for anyone.
--   * Supabase's Data API roles (anon, authenticated, service_role) have NO privileges on these
--     tables. Only the FastAPI backend can reach them: it connects as `engage_api` (NOINHERIT,
--     no direct privileges) and switches to `engage_app` with verified JWT claims per
--     transaction, so RLS always applies (ADR-016).

-- ---------------------------------------------------------------------------------------------
-- Default privileges: new objects created by postgres in public are NOT exposed to API roles.
-- ---------------------------------------------------------------------------------------------
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated, service_role;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated, service_role;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated, service_role, public;

-- ---------------------------------------------------------------------------------------------
-- Roles (ADR-016). Supabase's Data API (PostgREST/GraphQL) runs as anon/authenticated; those roles
-- receive NO privileges on Engage tables, so the Data API cannot read or write them whatever the
-- exposed-schema configuration. All access goes through the FastAPI backend:
--   engage_api  LOGIN, NOINHERIT: the backend's connection role; holds no privileges itself.
--   engage_app  NOLOGIN: holds the table privileges and is the target of every RLS policy.
-- Per transaction the backend runs `SET LOCAL ROLE engage_app` and installs the verified JWT
-- claims, so RLS always applies; a missed role switch fails closed with permission errors.
-- engage_api's password is set out-of-band (local: supabase/seed.sql; cloud: founder via SQL).
-- ---------------------------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'engage_app') then
    create role engage_app nologin noinherit nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'engage_api') then
    create role engage_api login noinherit nocreatedb nocreaterole nobypassrls;
  end if;
end;
$$;

grant engage_app to engage_api;
grant usage on schema public to engage_app;

-- Private schema for security helper functions; never exposed through the Data API.
create schema if not exists app_private;
revoke all on schema app_private from public, anon, authenticated;
grant usage on schema app_private to engage_app;

-- ---------------------------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------------------------
create type public.tenant_status as enum ('pending', 'active', 'suspended', 'closed');
create type public.membership_role as enum ('owner', 'admin', 'receptionist', 'viewer');

-- ---------------------------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------------------------
create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  legal_name text not null check (char_length(legal_name) between 2 and 200),
  display_name text not null check (char_length(display_name) between 2 and 120),
  status public.tenant_status not null default 'pending',
  timezone text not null default 'Africa/Lagos' check (char_length(timezone) between 1 and 64),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tenant_domains (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  hostname text not null unique
    check (hostname = lower(hostname) and char_length(hostname) between 3 and 253),
  verification_status text not null default 'pending'
    check (verification_status in ('pending', 'verified', 'rejected')),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.tenant_memberships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role public.membership_role not null default 'viewer',
  is_active boolean not null default true,
  invited_by uuid references auth.users (id) on delete set null,
  revoked_at timestamptz,
  revoked_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, user_id),
  -- A revoked membership must record when it was revoked; an active one must not.
  check ((is_active and revoked_at is null) or (not is_active and revoked_at is not null))
);

create table public.clinic_profiles (
  tenant_id uuid primary key references public.tenants (id) on delete cascade,
  public_phone text check (char_length(public_phone) <= 40),
  public_email text check (char_length(public_email) <= 254),
  public_address text check (char_length(public_address) <= 500),
  opening_hours jsonb not null default '{}'::jsonb check (jsonb_typeof(opening_hours) = 'object'),
  public_description text check (char_length(public_description) <= 2000),
  updated_at timestamptz not null default now()
);

-- ZubeVision platform staff. Managed out-of-band (SQL by a database owner), never via the API.
create table public.platform_admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  note text check (char_length(note) <= 200)
);

-- Append-only audit trail. tenant_id has no FK so events survive tenant deletion.
create table public.audit_events (
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  actor_user_id uuid not null,
  tenant_id uuid,
  action text not null check (action ~ '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$' and char_length(action) <= 100),
  target_type text check (char_length(target_type) <= 60),
  target_id text check (char_length(target_id) <= 200),
  request_id text check (char_length(request_id) <= 100),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object')
);

create index tenant_memberships_user_id_idx on public.tenant_memberships (user_id);
create index tenant_domains_tenant_id_idx on public.tenant_domains (tenant_id);
create index audit_events_tenant_time_idx on public.audit_events (tenant_id, occurred_at desc);
create index audit_events_actor_time_idx on public.audit_events (actor_user_id, occurred_at desc);

-- ---------------------------------------------------------------------------------------------
-- Security helper functions (SECURITY DEFINER, empty search_path, fully-qualified names)
-- ---------------------------------------------------------------------------------------------

-- Current user id from the verified JWT claims (wrapper so engage_app needs no auth-schema access).
create or replace function app_private.current_user_id()
returns uuid
language sql stable security definer
set search_path = ''
as $$
  select auth.uid();
$$;

-- Current user's role in a tenant, or NULL if no active membership or tenant is not usable.
create or replace function app_private.tenant_role(target_tenant uuid)
returns public.membership_role
language sql stable security definer
set search_path = ''
as $$
  select tm.role
  from public.tenant_memberships tm
  join public.tenants t on t.id = tm.tenant_id
  where tm.tenant_id = target_tenant
    and tm.user_id = (select auth.uid())
    and tm.is_active
    and t.status in ('pending', 'active');
$$;

create or replace function app_private.has_tenant_role(
  target_tenant uuid,
  allowed public.membership_role[] default array['owner', 'admin', 'receptionist', 'viewer']::public.membership_role[]
)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce(app_private.tenant_role(target_tenant) = any (allowed), false);
$$;

-- Platform admin powers require an active platform_admins row AND an MFA-verified session.
create or replace function app_private.is_platform_admin()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce((select auth.jwt() ->> 'aal'), '') = 'aal2'
     and exists (
       select 1 from public.platform_admins pa
       where pa.user_id = (select auth.uid()) and pa.is_active
     );
$$;

-- Resolve an existing auth user by email for invitations. Only owners/admins of the given tenant
-- (or MFA-verified platform admins) may call it, which limits email enumeration to people who
-- can already invite members to that tenant. Callers must audit the invitation.
create or replace function app_private.find_user_id_for_invite(p_tenant uuid, p_email text)
returns uuid
language plpgsql stable security definer
set search_path = ''
as $$
begin
  if not (
    app_private.is_platform_admin()
    or (p_tenant is not null
        and app_private.has_tenant_role(p_tenant, array['owner', 'admin']::public.membership_role[]))
  ) then
    raise exception 'not authorised to look up users' using errcode = 'insufficient_privilege';
  end if;
  return (select u.id from auth.users u where lower(u.email) = lower(p_email) limit 1);
end;
$$;

-- Member roster with emails (auth.users is not readable by API roles). Owners/admins only.
create or replace function app_private.tenant_member_directory(p_tenant uuid)
returns table (
  membership_id uuid,
  user_id uuid,
  email text,
  role public.membership_role,
  is_active boolean,
  created_at timestamptz,
  revoked_at timestamptz
)
language plpgsql stable security definer
set search_path = ''
as $$
begin
  if not (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(p_tenant, array['owner', 'admin']::public.membership_role[])
  ) then
    raise exception 'not authorised to list members' using errcode = 'insufficient_privilege';
  end if;
  return query
    select tm.id, tm.user_id, u.email::text, tm.role, tm.is_active, tm.created_at, tm.revoked_at
    from public.tenant_memberships tm
    join auth.users u on u.id = tm.user_id
    where tm.tenant_id = p_tenant
    order by tm.created_at, tm.id;
end;
$$;

revoke all on function app_private.tenant_member_directory(uuid) from public, anon, authenticated;
grant execute on function app_private.tenant_member_directory(uuid) to engage_app;

revoke all on function app_private.find_user_id_for_invite(uuid, text) from public, anon, authenticated;
grant execute on function app_private.find_user_id_for_invite(uuid, text) to engage_app;

revoke all on function app_private.current_user_id() from public, anon, authenticated;
grant execute on function app_private.current_user_id() to engage_app;
revoke all on function app_private.tenant_role(uuid) from public, anon, authenticated;
revoke all on function app_private.has_tenant_role(uuid, public.membership_role[]) from public, anon, authenticated;
revoke all on function app_private.is_platform_admin() from public, anon, authenticated;
grant execute on function app_private.tenant_role(uuid) to engage_app;
grant execute on function app_private.has_tenant_role(uuid, public.membership_role[]) to engage_app;
grant execute on function app_private.is_platform_admin() to engage_app;

-- ---------------------------------------------------------------------------------------------
-- Integrity triggers
-- ---------------------------------------------------------------------------------------------
create or replace function app_private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger tenants_set_updated_at before update on public.tenants
  for each row execute function app_private.set_updated_at();
create trigger tenant_memberships_set_updated_at before update on public.tenant_memberships
  for each row execute function app_private.set_updated_at();
create trigger clinic_profiles_set_updated_at before update on public.clinic_profiles
  for each row execute function app_private.set_updated_at();

-- Every tenant must keep at least one active owner.
create or replace function app_private.ensure_tenant_keeps_owner()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  if old.role = 'owner' and old.is_active
     and (new.role <> 'owner' or not new.is_active)
     and not exists (
       select 1 from public.tenant_memberships tm
       where tm.tenant_id = old.tenant_id and tm.id <> old.id
         and tm.role = 'owner' and tm.is_active
     ) then
    raise exception 'A tenant must keep at least one active owner'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

create trigger tenant_memberships_keep_owner before update on public.tenant_memberships
  for each row execute function app_private.ensure_tenant_keeps_owner();

-- Audit log is append-only for every role, including table owners.
create or replace function app_private.reject_audit_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_events is append-only' using errcode = 'insufficient_privilege';
end;
$$;

create trigger audit_events_no_update before update or delete on public.audit_events
  for each row execute function app_private.reject_audit_mutation();
create trigger audit_events_no_truncate before truncate on public.audit_events
  for each statement execute function app_private.reject_audit_mutation();

-- ---------------------------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------------------------
alter table public.tenants enable row level security;
alter table public.tenant_domains enable row level security;
alter table public.tenant_memberships enable row level security;
alter table public.clinic_profiles enable row level security;
alter table public.platform_admins enable row level security;
alter table public.audit_events enable row level security;

alter table public.tenants force row level security;
alter table public.tenant_domains force row level security;
alter table public.tenant_memberships force row level security;
alter table public.clinic_profiles force row level security;
alter table public.platform_admins force row level security;
alter table public.audit_events force row level security;

-- tenants ----------------------------------------------------------------------------------------
create policy tenants_select on public.tenants for select to engage_app
  using (app_private.has_tenant_role(id) or app_private.is_platform_admin());

create policy tenants_insert on public.tenants for insert to engage_app
  with check (app_private.is_platform_admin());

create policy tenants_update on public.tenants for update to engage_app
  using (app_private.is_platform_admin())
  with check (app_private.is_platform_admin());

-- tenant_domains (write policies arrive with Phase 2 domain verification) -----------------------
create policy tenant_domains_select on public.tenant_domains for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());

-- tenant_memberships ------------------------------------------------------------------------------
-- Users always see their own membership rows (so the dashboard can explain revoked access);
-- members of a usable tenant see that tenant's roster.
create policy tenant_memberships_select on public.tenant_memberships for select to engage_app
  using (
    user_id = (select app_private.current_user_id())
    or app_private.has_tenant_role(tenant_id)
    or app_private.is_platform_admin()
  );

-- Owners may grant any role; admins may grant admin/receptionist/viewer but never owner.
create policy tenant_memberships_insert on public.tenant_memberships for insert to engage_app
  with check (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner']::public.membership_role[])
    or (
      app_private.has_tenant_role(tenant_id, array['admin']::public.membership_role[])
      and role <> 'owner'
    )
  );

-- Admins cannot modify owner rows, nor promote anyone to owner.
create policy tenant_memberships_update on public.tenant_memberships for update to engage_app
  using (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner']::public.membership_role[])
    or (
      app_private.has_tenant_role(tenant_id, array['admin']::public.membership_role[])
      and role <> 'owner'
    )
  )
  with check (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner']::public.membership_role[])
    or (
      app_private.has_tenant_role(tenant_id, array['admin']::public.membership_role[])
      and role <> 'owner'
    )
  );

-- clinic_profiles -----------------------------------------------------------------------------------
create policy clinic_profiles_select on public.clinic_profiles for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());

create policy clinic_profiles_insert on public.clinic_profiles for insert to engage_app
  with check (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[])
  );

create policy clinic_profiles_update on public.clinic_profiles for update to engage_app
  using (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[])
  )
  with check (
    app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[])
  );

-- platform_admins: a user may only see whether they themselves are a platform admin --------------
create policy platform_admins_select_self on public.platform_admins for select to engage_app
  using (user_id = (select app_private.current_user_id()));

-- audit_events ------------------------------------------------------------------------------------
create policy audit_events_select on public.audit_events for select to engage_app
  using (
    app_private.is_platform_admin()
    or (tenant_id is not null
        and app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
  );

-- Events can only be written as yourself, about a tenant you belong to (or by a platform admin).
create policy audit_events_insert on public.audit_events for insert to engage_app
  with check (
    actor_user_id = (select app_private.current_user_id())
    and (
      app_private.is_platform_admin()
      or (tenant_id is not null and app_private.has_tenant_role(tenant_id))
    )
  );

-- ---------------------------------------------------------------------------------------------
-- Table privileges: explicit, least privilege. anon gets nothing. No DELETE anywhere.
-- Column-level UPDATE grants make identity columns (ids, tenant_id, user_id) immutable.
-- ---------------------------------------------------------------------------------------------
revoke all on public.tenants, public.tenant_domains, public.tenant_memberships,
  public.clinic_profiles, public.platform_admins, public.audit_events
  from public, anon, authenticated, service_role;

grant select, insert on public.tenants to engage_app;
grant update (legal_name, display_name, status, timezone) on public.tenants to engage_app;

grant select on public.tenant_domains to engage_app;

grant select, insert on public.tenant_memberships to engage_app;
grant update (role, is_active, revoked_at, revoked_by) on public.tenant_memberships to engage_app;

grant select, insert on public.clinic_profiles to engage_app;
grant update (public_phone, public_email, public_address, opening_hours, public_description)
  on public.clinic_profiles to engage_app;

grant select on public.platform_admins to engage_app;

grant select, insert on public.audit_events to engage_app;
