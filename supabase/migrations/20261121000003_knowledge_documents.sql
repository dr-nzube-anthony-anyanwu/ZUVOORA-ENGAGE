-- ZUVOORA Engage — Phase 2c: knowledge documents (quarantine, extraction, review, versions).
-- See ADR-023 and docs/security/TENANCY_AND_RLS.md.
--
--   * Originals go to a PRIVATE storage bucket with no access policies: browsers (anon /
--     authenticated keys) can never read or write them; only the backend's secret key can.
--     The object path is derived by the database from tenant/document/version ids.
--   * Each upload becomes an immutable VERSION. Text is extracted in an isolated process and
--     stored for review. Nothing is public until an owner/admin approves a version, which then
--     becomes the document's published version. New uploads never replace the published
--     version until they are approved themselves.
--   * Composite foreign keys tie every version to its document AND tenant, and the published
--     version to the same document; triggers enforce status transitions and server-set fields.

-- ---------------------------------------------------------------------------------------------
-- Private bucket for originals (10 MiB, no public URL, no storage.objects policies).
-- ---------------------------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('knowledge-originals', 'knowledge-originals', false, 10485760,
        array['application/octet-stream'])
on conflict (id) do update
  set public = false, file_size_limit = 10485760,
      allowed_mime_types = array['application/octet-stream'];

-- ---------------------------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------------------------
create type public.knowledge_version_status as enum ('extracted', 'failed', 'approved', 'rejected');

create table public.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  title text not null check (char_length(title) between 2 and 200),
  published_version_id uuid,
  archived_at timestamptz,
  archived_by uuid references auth.users (id) on delete set null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, tenant_id),
  check (archived_at is null or published_version_id is null)
);

create table public.knowledge_document_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  document_id uuid not null,
  version_no integer not null check (version_no >= 1),
  status public.knowledge_version_status not null,
  file_name text not null check (char_length(file_name) between 1 and 200),
  detected_type text not null check (detected_type in ('pdf', 'docx', 'text')),
  size_bytes integer not null check (size_bytes between 1 and 10485760),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  storage_path text not null unique,
  page_count integer check (page_count between 0 and 10000),
  extracted_text text check (char_length(extracted_text) <= 300000),
  extraction_error text check (extraction_error in (
    'no_text', 'too_long', 'encrypted', 'active_content', 'macros', 'embedded_files',
    'too_complex', 'malformed', 'timeout', 'unsupported_encoding', 'extractor_failed')),
  uploaded_by uuid references auth.users (id) on delete set null,
  uploaded_at timestamptz not null default now(),
  reviewed_by uuid references auth.users (id) on delete set null,
  reviewed_at timestamptz,
  review_note text check (char_length(review_note) <= 500),
  unique (document_id, version_no),
  unique (id, document_id, tenant_id),
  foreign key (document_id, tenant_id)
    references public.knowledge_documents (id, tenant_id) on delete cascade,
  check ((status = 'failed') = (extraction_error is not null)),
  check (status = 'failed' or extracted_text is not null),
  check ((status in ('approved', 'rejected')) = (reviewed_at is not null))
);

-- The published version must be a version of the same document in the same tenant.
alter table public.knowledge_documents
  add constraint knowledge_documents_published_version_fk
  foreign key (published_version_id, id, tenant_id)
  references public.knowledge_document_versions (id, document_id, tenant_id);

create index knowledge_documents_tenant_idx on public.knowledge_documents (tenant_id);
create index knowledge_versions_document_idx
  on public.knowledge_document_versions (document_id, version_no desc);
create index knowledge_versions_tenant_idx on public.knowledge_document_versions (tenant_id);

-- ---------------------------------------------------------------------------------------------
-- Triggers: server-owned fields and allowed transitions
-- ---------------------------------------------------------------------------------------------
create or replace function app_private.knowledge_document_before_insert()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.published_version_id := null;
  new.archived_at := null;
  new.archived_by := null;
  new.created_by := app_private.current_user_id();
  new.created_at := now();
  new.updated_at := now();
  return new;
end;
$$;

create or replace function app_private.knowledge_document_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.tenant_id is distinct from old.tenant_id then
    raise exception 'documents cannot move between tenants' using errcode = 'insufficient_privilege';
  end if;

  if new.archived_at is not null and old.archived_at is null then
    new.archived_at := now();
    new.archived_by := app_private.current_user_id();
    new.published_version_id := null;
  elsif new.archived_at is null then
    new.archived_by := null;
  else
    new.archived_at := old.archived_at;
    new.archived_by := old.archived_by;
  end if;

  if new.published_version_id is not null
     and new.published_version_id is distinct from old.published_version_id then
    if new.archived_at is not null then
      raise exception 'archived documents cannot be published' using errcode = 'check_violation';
    end if;
    if not exists (
      select 1 from public.knowledge_document_versions v
      where v.id = new.published_version_id and v.document_id = new.id
        and v.tenant_id = new.tenant_id and v.status = 'approved'
    ) then
      raise exception 'only an approved version can be published' using errcode = 'check_violation';
    end if;
  end if;

  new.updated_at := now();
  return new;
end;
$$;

create or replace function app_private.knowledge_version_before_insert()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status not in ('extracted', 'failed') then
    raise exception 'new versions start as extracted or failed' using errcode = 'check_violation';
  end if;
  -- Serialise version numbering per document (the row lock also requires the document to
  -- be visible to the caller under RLS).
  perform 1 from public.knowledge_documents d
    where d.id = new.document_id and d.tenant_id = new.tenant_id and d.archived_at is null
    for update;
  if not found then
    raise exception 'document not found or archived' using errcode = 'check_violation';
  end if;
  new.id := gen_random_uuid();
  new.version_no := coalesce((select max(v.version_no) from public.knowledge_document_versions v
                              where v.document_id = new.document_id), 0) + 1;
  new.storage_path := new.tenant_id::text || '/' || new.document_id::text || '/' || new.id::text;
  new.uploaded_by := app_private.current_user_id();
  new.uploaded_at := now();
  new.reviewed_by := null;
  new.reviewed_at := null;
  new.review_note := null;
  return new;
end;
$$;

create or replace function app_private.knowledge_version_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Content and identity are immutable; only the review decision may change, once.
  if (new.tenant_id, new.document_id, new.version_no, new.file_name, new.detected_type,
      new.size_bytes, new.sha256, new.storage_path, new.page_count, new.extraction_error)
     is distinct from
     (old.tenant_id, old.document_id, old.version_no, old.file_name, old.detected_type,
      old.size_bytes, old.sha256, old.storage_path, old.page_count, old.extraction_error)
     or new.extracted_text is distinct from old.extracted_text then
    raise exception 'document versions are immutable' using errcode = 'insufficient_privilege';
  end if;
  if new.status is distinct from old.status then
    if not (old.status = 'extracted' and new.status in ('approved', 'rejected')) then
      raise exception 'invalid status transition % -> %', old.status, new.status
        using errcode = 'check_violation';
    end if;
    new.reviewed_by := app_private.current_user_id();
    new.reviewed_at := now();
  else
    new.reviewed_by := old.reviewed_by;
    new.reviewed_at := old.reviewed_at;
    new.review_note := old.review_note;
  end if;
  return new;
end;
$$;

revoke all on function app_private.knowledge_document_before_insert() from public, anon, authenticated;
revoke all on function app_private.knowledge_document_before_update() from public, anon, authenticated;
revoke all on function app_private.knowledge_version_before_insert() from public, anon, authenticated;
revoke all on function app_private.knowledge_version_before_update() from public, anon, authenticated;

create trigger knowledge_documents_insert before insert on public.knowledge_documents
  for each row execute function app_private.knowledge_document_before_insert();
create trigger knowledge_documents_update before update on public.knowledge_documents
  for each row execute function app_private.knowledge_document_before_update();
create trigger knowledge_versions_insert before insert on public.knowledge_document_versions
  for each row execute function app_private.knowledge_version_before_insert();
create trigger knowledge_versions_update before update on public.knowledge_document_versions
  for each row execute function app_private.knowledge_version_before_update();

-- ---------------------------------------------------------------------------------------------
-- RLS: members read; owners/admins (and MFA platform admins) write. No DELETE.
-- ---------------------------------------------------------------------------------------------
alter table public.knowledge_documents enable row level security;
alter table public.knowledge_documents force row level security;
alter table public.knowledge_document_versions enable row level security;
alter table public.knowledge_document_versions force row level security;

do $$
declare
  t text;
begin
  foreach t in array array['knowledge_documents', 'knowledge_document_versions'] loop
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

revoke all on public.knowledge_documents, public.knowledge_document_versions
  from public, anon, authenticated, service_role;

grant select on public.knowledge_documents, public.knowledge_document_versions to engage_app;
grant insert (tenant_id, title) on public.knowledge_documents to engage_app;
grant update (title, published_version_id, archived_at) on public.knowledge_documents to engage_app;
grant insert (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256,
              page_count, extracted_text, extraction_error)
  on public.knowledge_document_versions to engage_app;
grant update (status, review_note) on public.knowledge_document_versions to engage_app;
