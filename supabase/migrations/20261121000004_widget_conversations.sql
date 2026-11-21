-- ZUVOORA Engage — Phase 3a: widget configuration, conversations, messages, handover requests,
-- AI usage ledger and rate limiting. See ADR-025 and docs/security/TENANCY_AND_RLS.md.
--
-- Public (anonymous) widget traffic runs as its own role, `engage_widget` (NOLOGIN). The API
-- switches to it per transaction with server-set settings:
--   request.widget.tenant_id        tenant resolved from a verified widget token
--   request.widget.conversation_id  the visitor's own conversation (may be empty at start)
-- engage_widget can read ONLY the published copy of clinic content (column grants), only for
-- its tenant (RLS), and only touch its own conversation. Everything else goes through narrow
-- SECURITY DEFINER functions. Staff (engage_app) see conversations through membership RLS.

-- ---------------------------------------------------------------------------------------------
-- Role and context helpers
-- ---------------------------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'engage_widget') then
    create role engage_widget nologin noinherit nobypassrls;
  end if;
end;
$$;
grant engage_widget to engage_api;
grant usage on schema public to engage_widget;
grant usage on schema app_private to engage_widget;

create or replace function app_private.widget_tenant()
returns uuid
language sql stable
set search_path = ''
as $$
  select nullif(current_setting('request.widget.tenant_id', true), '')::uuid;
$$;

create or replace function app_private.widget_conversation()
returns uuid
language sql stable
set search_path = ''
as $$
  select nullif(current_setting('request.widget.conversation_id', true), '')::uuid;
$$;

-- The widget only works for ACTIVE tenants (not pending, suspended or closed).
create or replace function app_private.widget_tenant_active()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.tenants t
    where t.id = app_private.widget_tenant() and t.status = 'active'
  );
$$;

revoke all on function app_private.widget_tenant() from public, anon, authenticated;
revoke all on function app_private.widget_conversation() from public, anon, authenticated;
revoke all on function app_private.widget_tenant_active() from public, anon, authenticated;
grant execute on function app_private.widget_tenant(), app_private.widget_conversation(),
  app_private.widget_tenant_active() to engage_widget, engage_app;

-- ---------------------------------------------------------------------------------------------
-- Widget configuration (one per tenant)
-- ---------------------------------------------------------------------------------------------
create table public.widget_configs (
  tenant_id uuid primary key references public.tenants (id) on delete cascade,
  public_key text not null unique
    default replace(gen_random_uuid()::text, '-', '') check (public_key ~ '^[0-9a-f]{32}$'),
  enabled boolean not null default false,
  greeting text not null default 'Hello! I can answer questions about our clinic, opening hours and services. How can I help?'
    check (char_length(greeting) between 1 and 300),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------------------------
-- Conversations, messages, handover requests
-- ---------------------------------------------------------------------------------------------
create type public.conversation_status as enum ('open', 'handover_requested', 'closed');
create type public.message_role as enum ('visitor', 'assistant', 'system');
create type public.handover_status as enum ('new', 'in_progress', 'resolved');

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  status public.conversation_status not null default 'open',
  channel text not null default 'widget' check (channel in ('widget')),
  origin_host text check (char_length(origin_host) <= 253),
  started_at timestamptz not null default now(),
  last_message_at timestamptz not null default now(),
  message_count integer not null default 0 check (message_count >= 0),
  closed_at timestamptz,
  closed_by uuid references auth.users (id) on delete set null,
  unique (id, tenant_id)
);

create table public.messages (
  id bigint generated always as identity primary key,
  tenant_id uuid not null,
  conversation_id uuid not null,
  role public.message_role not null,
  content text not null check (char_length(content) between 1 and 4000),
  -- How an assistant answer was produced (visitor messages: null).
  answer_source text check (answer_source in
    ('facts', 'emergency', 'retrieval_ai', 'fallback', 'handover', 'budget_exhausted', 'greeting')),
  model text check (char_length(model) <= 120),
  safety jsonb not null default '{}'::jsonb check (jsonb_typeof(safety) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (conversation_id, tenant_id)
    references public.conversations (id, tenant_id) on delete cascade,
  check ((role = 'visitor') = (answer_source is null))
);

create table public.handover_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  conversation_id uuid not null unique,
  contact_name text check (char_length(contact_name) <= 120),
  contact_phone text check (char_length(contact_phone) <= 40),
  contact_email text check (char_length(contact_email) <= 254),
  note text check (char_length(note) <= 1000),
  consent_given boolean not null check (consent_given),
  status public.handover_status not null default 'new',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references auth.users (id) on delete set null,
  foreign key (conversation_id, tenant_id)
    references public.conversations (id, tenant_id) on delete cascade,
  check (contact_phone is not null or contact_email is not null),
  check ((status = 'resolved') = (resolved_at is not null))
);

-- AI usage ledger: one row per model call (append-only). Cost as reported by the provider.
create table public.usage_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  conversation_id uuid,
  feature text not null check (feature in ('chat')),
  provider text not null check (provider in ('openrouter', 'fake')),
  model text not null check (char_length(model) <= 120),
  tier text not null check (tier in ('standard', 'complex')),
  prompt_tokens integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  cost_usd numeric(12, 6) not null default 0 check (cost_usd >= 0),
  occurred_at timestamptz not null default now()
);

create index conversations_tenant_recent_idx on public.conversations (tenant_id, last_message_at desc);
create index messages_conversation_idx on public.messages (conversation_id, id);
create index handover_tenant_status_idx on public.handover_requests (tenant_id, status, created_at desc);
create index usage_events_time_idx on public.usage_events (occurred_at);
create index usage_events_tenant_time_idx on public.usage_events (tenant_id, occurred_at);

-- Rate limiting counters (fixed windows). Keys are HMACs computed by the API; no raw IPs.
create table app_private.rate_limits (
  bucket text not null check (char_length(bucket) <= 200),
  window_start timestamptz not null,
  hits integer not null default 0,
  primary key (bucket, window_start)
);
revoke all on app_private.rate_limits from public, anon, authenticated, service_role;
create index rate_limits_window_idx on app_private.rate_limits (window_start);

-- ---------------------------------------------------------------------------------------------
-- Triggers: server-owned fields and append-only rows
-- ---------------------------------------------------------------------------------------------
create trigger widget_configs_set_updated_at before update on public.widget_configs
  for each row execute function app_private.set_updated_at();
create trigger handover_requests_set_updated_at before update on public.handover_requests
  for each row execute function app_private.set_updated_at();

create or replace function app_private.message_after_insert()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  update public.conversations
     set last_message_at = new.created_at, message_count = message_count + 1
   where id = new.conversation_id and tenant_id = new.tenant_id;
  return null;
end;
$$;
revoke all on function app_private.message_after_insert() from public, anon, authenticated;
create trigger messages_touch_conversation after insert on public.messages
  for each row execute function app_private.message_after_insert();

create or replace function app_private.reject_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception '% is append-only', tg_table_name using errcode = 'insufficient_privilege';
end;
$$;
create trigger messages_append_only before update or delete on public.messages
  for each row execute function app_private.reject_mutation();
create trigger usage_events_append_only before update or delete on public.usage_events
  for each row execute function app_private.reject_mutation();

-- Conversation/handover status changes are stamped by the server.
create or replace function app_private.conversation_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.tenant_id is distinct from old.tenant_id then
    raise exception 'conversations cannot move between tenants' using errcode = 'insufficient_privilege';
  end if;
  if new.status = 'closed' and old.status <> 'closed' then
    new.closed_at := now();
    new.closed_by := app_private.current_user_id();
  elsif new.status <> 'closed' then
    new.closed_at := null;
    new.closed_by := null;
  end if;
  return new;
end;
$$;
create trigger conversations_before_update before update on public.conversations
  for each row execute function app_private.conversation_before_update();

create or replace function app_private.handover_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (new.tenant_id, new.conversation_id, new.contact_name, new.contact_phone,
      new.contact_email, new.note, new.consent_given, new.created_at)
     is distinct from
     (old.tenant_id, old.conversation_id, old.contact_name, old.contact_phone,
      old.contact_email, old.note, old.consent_given, old.created_at) then
    raise exception 'handover details are immutable' using errcode = 'insufficient_privilege';
  end if;
  if new.status = 'resolved' and old.status <> 'resolved' then
    new.resolved_at := now();
    new.resolved_by := app_private.current_user_id();
  elsif new.status <> 'resolved' then
    new.resolved_at := null;
    new.resolved_by := null;
  end if;
  return new;
end;
$$;
create trigger handover_requests_before_update before update on public.handover_requests
  for each row execute function app_private.handover_before_update();

revoke all on function app_private.reject_mutation() from public, anon, authenticated;
revoke all on function app_private.conversation_before_update() from public, anon, authenticated;
revoke all on function app_private.handover_before_update() from public, anon, authenticated;

-- ---------------------------------------------------------------------------------------------
-- Narrow functions for the public widget path
-- ---------------------------------------------------------------------------------------------

-- Resolve a public widget key for a page on `p_host`. Returns the tenant only when the widget
-- is enabled, the tenant is active and the host is one of the tenant's VERIFIED domains.
create or replace function app_private.resolve_widget(p_public_key text, p_host text)
returns table (tenant_id uuid, greeting text, display_name text)
language sql stable security definer
set search_path = ''
as $$
  select w.tenant_id, w.greeting, t.display_name
  from public.widget_configs w
  join public.tenants t on t.id = w.tenant_id
  where w.public_key = p_public_key
    and w.enabled
    and t.status = 'active'
    and exists (
      select 1 from public.tenant_domains d
      where d.tenant_id = w.tenant_id and d.hostname = lower(p_host)
        and d.verification_status = 'verified' and d.removed_at is null
    );
$$;

-- Verified hostnames for a public widget key (for the iframe's frame-ancestors policy).
create or replace function app_private.widget_allowed_hosts(p_public_key text)
returns setof text
language sql stable security definer
set search_path = ''
as $$
  select d.hostname
  from public.widget_configs w
  join public.tenants t on t.id = w.tenant_id and t.status = 'active'
  join public.tenant_domains d on d.tenant_id = w.tenant_id
  where w.public_key = p_public_key and w.enabled
    and d.verification_status = 'verified' and d.removed_at is null;
$$;

-- Fixed-window rate limit: records a hit and returns true while within the limit.
create or replace function app_private.rate_limit_hit(p_bucket text, p_window_seconds integer, p_limit integer)
returns boolean
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_window timestamptz := to_timestamp(floor(extract(epoch from now()) / p_window_seconds) * p_window_seconds);
  v_hits integer;
begin
  if p_window_seconds < 1 or p_window_seconds > 86400 or p_limit < 1 then
    raise exception 'invalid rate limit' using errcode = 'invalid_parameter_value';
  end if;
  insert into app_private.rate_limits as r (bucket, window_start, hits)
  values (p_bucket, v_window, 1)
  on conflict (bucket, window_start) do update set hits = r.hits + 1
  returning hits into v_hits;
  -- Opportunistic cleanup of old windows (cheap, bounded).
  delete from app_private.rate_limits where window_start < now() - interval '2 days';
  return v_hits <= p_limit;
end;
$$;

-- AI spend in USD for the widget's tenant and for the whole platform (budget enforcement).
create or replace function app_private.ai_spend()
returns table (tenant_today numeric, global_today numeric, global_month numeric)
language sql stable security definer
set search_path = ''
as $$
  select
    coalesce(sum(cost_usd) filter (where tenant_id = app_private.widget_tenant()
                                     and occurred_at >= date_trunc('day', now())), 0),
    coalesce(sum(cost_usd) filter (where occurred_at >= date_trunc('day', now())), 0),
    coalesce(sum(cost_usd) filter (where occurred_at >= date_trunc('month', now())), 0)
  from public.usage_events
  where occurred_at >= date_trunc('month', now()) - interval '1 day';
$$;

-- Staff: rotate a tenant's public widget key (owners/admins and MFA platform admins).
create or replace function app_private.rotate_widget_key(p_tenant uuid)
returns text
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_key text := replace(gen_random_uuid()::text, '-', '');
begin
  if not (app_private.is_platform_admin()
          or app_private.has_tenant_role(p_tenant, array['owner', 'admin']::public.membership_role[])) then
    raise exception 'not authorised' using errcode = 'insufficient_privilege';
  end if;
  update public.widget_configs set public_key = v_key where tenant_id = p_tenant;
  return v_key;
end;
$$;

revoke all on function app_private.resolve_widget(text, text) from public, anon, authenticated;
revoke all on function app_private.widget_allowed_hosts(text) from public, anon, authenticated;
revoke all on function app_private.rate_limit_hit(text, integer, integer) from public, anon, authenticated;
revoke all on function app_private.ai_spend() from public, anon, authenticated;
revoke all on function app_private.rotate_widget_key(uuid) from public, anon, authenticated;
grant execute on function app_private.resolve_widget(text, text),
  app_private.widget_allowed_hosts(text), app_private.rate_limit_hit(text, integer, integer),
  app_private.ai_spend() to engage_widget;
grant execute on function app_private.rotate_widget_key(uuid) to engage_app;

-- ---------------------------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------------------------
alter table public.widget_configs enable row level security;
alter table public.widget_configs force row level security;
alter table public.conversations enable row level security;
alter table public.conversations force row level security;
alter table public.messages enable row level security;
alter table public.messages force row level security;
alter table public.handover_requests enable row level security;
alter table public.handover_requests force row level security;
alter table public.usage_events enable row level security;
alter table public.usage_events force row level security;

-- Staff ----------------------------------------------------------------------------------------
create policy widget_configs_staff_select on public.widget_configs for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
create policy widget_configs_staff_insert on public.widget_configs for insert to engage_app
  with check (app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
create policy widget_configs_staff_update on public.widget_configs for update to engage_app
  using (app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
  with check (app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));

create policy conversations_staff_select on public.conversations for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
-- Handling conversations is front-desk work: receptionists too (not viewers).
create policy conversations_staff_update on public.conversations for update to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]))
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]));

create policy messages_staff_select on public.messages for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());

create policy handover_staff_select on public.handover_requests for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
create policy handover_staff_update on public.handover_requests for update to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]))
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]));

create policy usage_events_staff_select on public.usage_events for select to engage_app
  using (app_private.is_platform_admin()
    or app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));

-- Widget (anonymous visitor, tenant from a verified token) ------------------------------------
create policy widget_configs_widget_select on public.widget_configs for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and enabled and app_private.widget_tenant_active());

create policy conversations_widget_select on public.conversations for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and id = app_private.widget_conversation());
create policy conversations_widget_insert on public.conversations for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant() and status = 'open'
              and app_private.widget_tenant_active());
create policy conversations_widget_update on public.conversations for update to engage_widget
  using (tenant_id = app_private.widget_tenant() and id = app_private.widget_conversation()
         and status <> 'closed')
  with check (tenant_id = app_private.widget_tenant() and id = app_private.widget_conversation()
              and status = 'handover_requested');

create policy messages_widget_select on public.messages for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and conversation_id = app_private.widget_conversation());
create policy messages_widget_insert on public.messages for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant()
              and conversation_id = app_private.widget_conversation()
              and app_private.widget_tenant_active());

create policy handover_widget_insert on public.handover_requests for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant()
              and conversation_id = app_private.widget_conversation()
              and status = 'new');
create policy handover_widget_select on public.handover_requests for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and conversation_id = app_private.widget_conversation());

create policy usage_events_widget_insert on public.usage_events for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant()
              and (conversation_id is null or conversation_id = app_private.widget_conversation()));

-- Published clinic content for the widget: only the published copy, only its tenant ----------
do $$
declare
  t text;
begin
  foreach t in array array['branches', 'services', 'faqs'] loop
    execute format($f$
      create policy %1$s_widget_select on public.%1$I for select to engage_widget
        using (tenant_id = app_private.widget_tenant() and published is not null
               and archived_at is null and app_private.widget_tenant_active());
      grant select (id, tenant_id, published) on public.%1$I to engage_widget;
    $f$, t);
  end loop;
end;
$$;
create policy clinic_profiles_widget_select on public.clinic_profiles for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and published is not null
         and app_private.widget_tenant_active());
grant select (tenant_id, published) on public.clinic_profiles to engage_widget;

create policy knowledge_documents_widget_select on public.knowledge_documents for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and published_version_id is not null
         and archived_at is null and app_private.widget_tenant_active());
grant select (id, tenant_id, title, published_version_id, archived_at) on public.knowledge_documents to engage_widget;
-- Versions: only the published one (the policy joins back to the document).
create policy knowledge_versions_widget_select on public.knowledge_document_versions for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and exists (
    select 1 from public.knowledge_documents d
    where d.id = document_id and d.published_version_id = knowledge_document_versions.id
      and d.archived_at is null));
grant select (id, tenant_id, document_id, extracted_text) on public.knowledge_document_versions to engage_widget;

-- ---------------------------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------------------------
revoke all on public.widget_configs, public.conversations, public.messages,
  public.handover_requests, public.usage_events from public, anon, authenticated, service_role;

grant select on public.widget_configs, public.conversations, public.messages,
  public.handover_requests, public.usage_events to engage_app;
grant insert (tenant_id) on public.widget_configs to engage_app;
grant update (enabled, greeting) on public.widget_configs to engage_app;
grant update (status) on public.conversations to engage_app;
grant update (status) on public.handover_requests to engage_app;

grant select (tenant_id, enabled, greeting) on public.widget_configs to engage_widget;
grant select on public.conversations, public.messages to engage_widget;
grant insert (tenant_id, origin_host) on public.conversations to engage_widget;
grant update (status) on public.conversations to engage_widget;
grant insert (tenant_id, conversation_id, role, content, answer_source, model, safety)
  on public.messages to engage_widget;
grant select (id, tenant_id, conversation_id, status, created_at) on public.handover_requests to engage_widget;
grant insert (tenant_id, conversation_id, contact_name, contact_phone, contact_email, note, consent_given)
  on public.handover_requests to engage_widget;
grant insert (tenant_id, conversation_id, feature, provider, model, tier, prompt_tokens,
              completion_tokens, cost_usd) on public.usage_events to engage_widget;
grant usage on sequence public.messages_id_seq, public.usage_events_id_seq to engage_widget;

-- Every tenant has a (disabled) widget configuration, including tenants created later.
create or replace function app_private.tenant_after_insert_widget()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  insert into public.widget_configs (tenant_id) values (new.id) on conflict (tenant_id) do nothing;
  return null;
end;
$$;
revoke all on function app_private.tenant_after_insert_widget() from public, anon, authenticated;
create trigger tenants_create_widget_config after insert on public.tenants
  for each row execute function app_private.tenant_after_insert_widget();

insert into public.widget_configs (tenant_id)
select id from public.tenants on conflict (tenant_id) do nothing;
