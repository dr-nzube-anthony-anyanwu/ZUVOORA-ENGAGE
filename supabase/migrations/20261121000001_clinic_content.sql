-- ZUVOORA Engage — Phase 2a: clinic content (profile, branches with opening hours, services, FAQs).
--
-- Publication model (see docs/security/TENANCY_AND_RLS.md, ADR-021):
--   * Every content row has a DRAFT (edited by clinic owners/admins) and an optional PUBLISHED
--     copy. Only published content will ever be visible to the public assistant (Phase 3).
--   * Editing a published item changes only its draft; the published copy stays live until an
--     owner/admin publishes the new revision.
--   * The database, not the API, controls the bookkeeping: `revision` increments on every draft
--     change; publishing is only possible when published = draft, and stamps published_revision,
--     published_at and published_by; archiving always unpublishes. Column-level grants mean the
--     API can only write draft, published and archived_at.
--   * Same tenancy rules as Phase 1: RLS forced, policies target engage_app only, receptionists
--     and viewers read, owners/admins (and MFA platform admins) write, no DELETE (archive instead).
--   * Content shape is validated by the API (Pydantic); the database enforces type and size.

-- ---------------------------------------------------------------------------------------------
-- clinic_profiles: replace the unused Phase 1 columns with the draft/published structure.
-- ---------------------------------------------------------------------------------------------
alter table public.clinic_profiles
  drop column public_phone,
  drop column public_email,
  drop column public_address,
  drop column opening_hours,
  drop column public_description;

alter table public.clinic_profiles
  add column draft jsonb not null default '{}'::jsonb,
  add column revision integer not null default 1,
  add column published jsonb,
  add column published_revision integer,
  add column published_at timestamptz,
  add column published_by uuid references auth.users (id) on delete set null,
  add column archived_at timestamptz,
  add column archived_by uuid references auth.users (id) on delete set null,
  add column created_by uuid references auth.users (id) on delete set null,
  add column created_at timestamptz not null default now();

-- ---------------------------------------------------------------------------------------------
-- Branches (locations, with structured opening hours inside the content), services, FAQs.
-- ---------------------------------------------------------------------------------------------
create table public.branches (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  draft jsonb not null,
  revision integer not null default 1,
  published jsonb,
  published_revision integer,
  published_at timestamptz,
  published_by uuid references auth.users (id) on delete set null,
  archived_at timestamptz,
  archived_by uuid references auth.users (id) on delete set null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.services (like public.branches including defaults);
alter table public.services add primary key (id);
alter table public.services
  add foreign key (tenant_id) references public.tenants (id) on delete cascade,
  add foreign key (published_by) references auth.users (id) on delete set null,
  add foreign key (archived_by) references auth.users (id) on delete set null,
  add foreign key (created_by) references auth.users (id) on delete set null;

create table public.faqs (like public.branches including defaults);
alter table public.faqs add primary key (id);
alter table public.faqs
  add foreign key (tenant_id) references public.tenants (id) on delete cascade,
  add foreign key (published_by) references auth.users (id) on delete set null,
  add foreign key (archived_by) references auth.users (id) on delete set null,
  add foreign key (created_by) references auth.users (id) on delete set null;

-- Shared integrity checks for all four content tables.
do $$
declare
  t text;
begin
  foreach t in array array['clinic_profiles', 'branches', 'services', 'faqs'] loop
    execute format($f$
      alter table public.%1$I
        add constraint %1$s_draft_shape
          check (jsonb_typeof(draft) = 'object' and pg_column_size(draft) <= 65536),
        add constraint %1$s_published_shape
          check (published is null
                 or (jsonb_typeof(published) = 'object' and pg_column_size(published) <= 65536)),
        add constraint %1$s_revision_positive check (revision >= 1),
        add constraint %1$s_publication_consistent check (
          (published is null and published_revision is null and published_at is null)
          or (published is not null and published_revision is not null
              and published_at is not null and published_revision <= revision)),
        add constraint %1$s_archive_consistent check (
          archived_at is null or published is null)
    $f$, t);
  end loop;
end;
$$;

create index branches_tenant_idx on public.branches (tenant_id);
create index services_tenant_idx on public.services (tenant_id);
create index faqs_tenant_idx on public.faqs (tenant_id);

-- ---------------------------------------------------------------------------------------------
-- Publication bookkeeping (runs as the invoking role; only touches the row being written).
-- ---------------------------------------------------------------------------------------------
create or replace function app_private.content_before_insert()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.revision := 1;
  new.published := null;
  new.published_revision := null;
  new.published_at := null;
  new.published_by := null;
  new.archived_at := null;
  new.archived_by := null;
  new.created_by := app_private.current_user_id();
  new.created_at := now();
  return new;
end;
$$;

create or replace function app_private.content_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Defence in depth: engage_app has no UPDATE grant on tenant_id/id columns either.
  if new.tenant_id is distinct from old.tenant_id then
    raise exception 'content cannot move between tenants' using errcode = 'insufficient_privilege';
  end if;

  -- Revision is server-controlled: +1 whenever the draft changes.
  new.revision := case when new.draft is distinct from old.draft then old.revision + 1
                       else old.revision end;

  -- Archiving always unpublishes; archived content cannot be published.
  if new.archived_at is not null and old.archived_at is null then
    new.archived_at := now();
    new.archived_by := app_private.current_user_id();
    new.published := null;
  elsif new.archived_at is null then
    new.archived_by := null;
  else
    new.archived_at := old.archived_at;
    new.archived_by := old.archived_by;
  end if;

  if new.published is null then
    new.published_revision := null;
    new.published_at := null;
    new.published_by := null;
  elsif new.published is distinct from old.published then
    if new.archived_at is not null then
      raise exception 'archived content cannot be published' using errcode = 'check_violation';
    end if;
    if new.published is distinct from new.draft then
      raise exception 'only the current draft can be published' using errcode = 'check_violation';
    end if;
    new.published_revision := new.revision;
    new.published_at := now();
    new.published_by := app_private.current_user_id();
  else
    new.published_revision := old.published_revision;
    new.published_at := old.published_at;
    new.published_by := old.published_by;
  end if;

  new.updated_at := now();
  return new;
end;
$$;

revoke all on function app_private.content_before_insert() from public, anon, authenticated;
revoke all on function app_private.content_before_update() from public, anon, authenticated;

drop trigger clinic_profiles_set_updated_at on public.clinic_profiles;

do $$
declare
  t text;
begin
  foreach t in array array['clinic_profiles', 'branches', 'services', 'faqs'] loop
    execute format(
      'create trigger %1$s_content_insert before insert on public.%1$I
         for each row execute function app_private.content_before_insert()', t);
    execute format(
      'create trigger %1$s_content_update before update on public.%1$I
         for each row execute function app_private.content_before_update()', t);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- Row-level security: members read; owners/admins (and MFA platform admins) write.
-- ---------------------------------------------------------------------------------------------
alter table public.branches enable row level security;
alter table public.services enable row level security;
alter table public.faqs enable row level security;
alter table public.branches force row level security;
alter table public.services force row level security;
alter table public.faqs force row level security;

do $$
declare
  t text;
begin
  foreach t in array array['branches', 'services', 'faqs'] loop
    execute format($f$
      create policy %1$s_select on public.%1$I for select to engage_app
        using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
      create policy %1$s_insert on public.%1$I for insert to engage_app
        with check (app_private.is_platform_admin()
          or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
      create policy %1$s_update on public.%1$I for update to engage_app
        using (app_private.is_platform_admin()
          or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
        with check (app_private.is_platform_admin()
          or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
    $f$, t);
  end loop;
end;
$$;
-- clinic_profiles keeps its Phase 1 policies (same rules).

-- ---------------------------------------------------------------------------------------------
-- Privileges: explicit and column-level. No DELETE. Bookkeeping columns are trigger-owned.
-- ---------------------------------------------------------------------------------------------
revoke all on public.branches, public.services, public.faqs
  from public, anon, authenticated, service_role;
revoke update on public.clinic_profiles from engage_app;
revoke insert on public.clinic_profiles from engage_app;

grant select on public.branches, public.services, public.faqs to engage_app;
grant insert (tenant_id, draft) on public.branches, public.services, public.faqs to engage_app;
grant update (draft, published, archived_at)
  on public.branches, public.services, public.faqs to engage_app;

grant insert (tenant_id, draft) on public.clinic_profiles to engage_app;
grant update (draft, published) on public.clinic_profiles to engage_app;
