-- ZUVOORA Engage — Phase 3c: tenant-scoped full-text retrieval (no embeddings; ADR-026/028).
--
--   * knowledge_chunks: passages of APPROVED document versions, created by the API in the same
--     transaction as the approval. Immutable for application roles.
--   * The widget can read only chunks of a document's currently PUBLISHED version, of its own
--     active tenant. Staff read their tenant's chunks.
--   * Full-text indexes on the published copies of FAQs and services.

create table public.knowledge_chunks (
  id bigint generated always as identity primary key,
  tenant_id uuid not null,
  document_id uuid not null,
  version_id uuid not null,
  ordinal integer not null check (ordinal >= 0 and ordinal < 5000),
  content text not null check (char_length(content) between 1 and 4000),
  search tsvector generated always as (to_tsvector('english', content)) stored,
  created_at timestamptz not null default now(),
  unique (version_id, ordinal),
  foreign key (version_id, document_id, tenant_id)
    references public.knowledge_document_versions (id, document_id, tenant_id) on delete cascade
);

create index knowledge_chunks_search_idx on public.knowledge_chunks using gin (search);
create index knowledge_chunks_version_idx on public.knowledge_chunks (version_id, ordinal);
create index knowledge_chunks_tenant_idx on public.knowledge_chunks (tenant_id);

create index faqs_published_search_idx on public.faqs using gin (
  to_tsvector('english', coalesce(published ->> 'question', '') || ' ' || coalesce(published ->> 'answer', ''))
) where published is not null and archived_at is null;

create index services_published_search_idx on public.services using gin (
  to_tsvector('english', coalesce(published ->> 'name', '') || ' ' || coalesce(published ->> 'category', '')
                         || ' ' || coalesce(published ->> 'description', ''))
) where published is not null and archived_at is null;

create trigger knowledge_chunks_append_only before update or delete on public.knowledge_chunks
  for each row execute function app_private.reject_app_mutation();

alter table public.knowledge_chunks enable row level security;
alter table public.knowledge_chunks force row level security;

create policy knowledge_chunks_staff_select on public.knowledge_chunks for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());

-- Chunks may only be written for an APPROVED version, by owners/admins of that tenant.
create policy knowledge_chunks_staff_insert on public.knowledge_chunks for insert to engage_app
  with check (
    (app_private.is_platform_admin()
     or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
    and exists (
      select 1 from public.knowledge_document_versions v
      where v.id = version_id and v.tenant_id = knowledge_chunks.tenant_id and v.status = 'approved'));

create policy knowledge_chunks_widget_select on public.knowledge_chunks for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and app_private.widget_tenant_active()
         and exists (
           select 1 from public.knowledge_documents d
           where d.id = document_id and d.published_version_id = version_id
             and d.archived_at is null));

revoke all on public.knowledge_chunks from public, anon, authenticated, service_role;
grant select on public.knowledge_chunks to engage_app;
grant insert (tenant_id, document_id, version_id, ordinal, content) on public.knowledge_chunks to engage_app;
grant select (id, tenant_id, document_id, version_id, ordinal, content, search)
  on public.knowledge_chunks to engage_widget;

-- The widget's clinic display name (the widget role cannot read public.tenants).
create or replace function app_private.widget_clinic_name()
returns text
language sql stable security definer
set search_path = ''
as $$
  select t.display_name from public.tenants t
  where t.id = app_private.widget_tenant() and t.status = 'active';
$$;
revoke all on function app_private.widget_clinic_name() from public, anon, authenticated;
grant execute on function app_private.widget_clinic_name() to engage_widget;
