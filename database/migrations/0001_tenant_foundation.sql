-- Apply only to a dedicated ZUVOORA Engage Supabase project after review.
create extension if not exists pgcrypto;

create type public.tenant_status as enum ('pending','active','suspended','closed');
create type public.membership_role as enum ('owner','admin','receptionist','viewer');

create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  legal_name text not null,
  display_name text not null,
  status public.tenant_status not null default 'pending',
  timezone text not null default 'Africa/Lagos',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tenant_domains (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  hostname text not null unique,
  verification_status text not null default 'pending'
    check (verification_status in ('pending','verified','rejected')),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.tenant_memberships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role public.membership_role not null default 'viewer',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id,user_id)
);

create table public.clinic_profiles (
  tenant_id uuid primary key references public.tenants(id) on delete cascade,
  public_phone text,
  public_email text,
  public_address text,
  opening_hours jsonb not null default '{}'::jsonb,
  public_description text,
  updated_at timestamptz not null default now()
);

create index tenant_memberships_user_id_idx on public.tenant_memberships(user_id);
create index tenant_domains_tenant_id_idx on public.tenant_domains(tenant_id);

alter table public.tenants enable row level security;
alter table public.tenant_domains enable row level security;
alter table public.tenant_memberships enable row level security;
alter table public.clinic_profiles enable row level security;

create or replace function public.is_active_tenant_member(target_tenant uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.tenant_memberships tm
    where tm.tenant_id = target_tenant
      and tm.user_id = (select auth.uid())
      and tm.is_active = true
  );
$$;

revoke all on function public.is_active_tenant_member(uuid) from public;
grant execute on function public.is_active_tenant_member(uuid) to authenticated;

create policy "members can read their tenants"
on public.tenants for select to authenticated
using (public.is_active_tenant_member(id));

create policy "members can read their domains"
on public.tenant_domains for select to authenticated
using (public.is_active_tenant_member(tenant_id));

create policy "members can read their memberships"
on public.tenant_memberships for select to authenticated
using (public.is_active_tenant_member(tenant_id));

create policy "members can read their clinic profile"
on public.clinic_profiles for select to authenticated
using (public.is_active_tenant_member(tenant_id));

-- No anonymous policies and no write policies yet. Add narrowly scoped role policies
-- only with corresponding positive and negative security tests.
