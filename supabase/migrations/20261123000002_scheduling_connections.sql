-- Phase 4b: scheduling provider connections and bookable appointment types (ADR-034).
--
-- * A clinic connects one scheduling account (Cal.com first). Its API key is encrypted by the
--   API (AES-256-GCM, bound to tenant + connection) before it reaches the database. No role can
--   SELECT the ciphertext column; it is read only through app_private.scheduling_credential(),
--   which checks the caller (clinic staff of that tenant, or the widget of that active tenant).
-- * Disconnecting wipes the ciphertext. Identity columns are immutable; actor/time server-set.
-- * Appointment types are the provider event types a clinic chooses to offer, with a snapshot of
--   their name and duration. The widget sees only enabled types of an active connection.

create table public.scheduling_connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  provider text not null check (provider in ('calcom', 'calendly')),
  status text not null default 'active' check (status in ('active', 'failing', 'disconnected')),
  account_label text check (char_length(account_label) <= 200),
  account_time_zone text check (char_length(account_time_zone) <= 64),
  credential_ciphertext bytea check (octet_length(credential_ciphertext) <= 4096),
  credential_key_id text check (credential_key_id ~ '^[0-9a-f]{12}$'),
  credential_hint text check (char_length(credential_hint) <= 8),
  connected_by uuid references auth.users (id) on delete set null,
  connected_at timestamptz not null default now(),
  disconnected_by uuid references auth.users (id) on delete set null,
  disconnected_at timestamptz,
  last_verified_at timestamptz,
  last_error text check (char_length(last_error) <= 200),
  updated_at timestamptz not null default now(),
  unique (id, tenant_id),
  check ((status = 'disconnected') = (credential_ciphertext is null)),
  check ((credential_ciphertext is null) = (credential_key_id is null))
);
create unique index scheduling_connections_one_live
  on public.scheduling_connections (tenant_id) where status <> 'disconnected';

create table public.appointment_types (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  connection_id uuid not null,
  provider_event_type_id text not null check (provider_event_type_id ~ '^[A-Za-z0-9_.:/-]{1,200}$'),
  name text not null check (char_length(name) between 1 and 120),
  duration_minutes integer not null check (duration_minutes between 5 and 720),
  requires_confirmation boolean not null default false,
  enabled boolean not null default true,
  sort_order integer not null default 0 check (sort_order between 0 and 1000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (connection_id, tenant_id)
    references public.scheduling_connections (id, tenant_id) on delete cascade,
  unique (connection_id, provider_event_type_id)
);
create index appointment_types_tenant_idx on public.appointment_types (tenant_id);

-- ----- triggers: server-owned fields ---------------------------------------------------------
create or replace function app_private.scheduling_connection_before_write()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    new.connected_by := app_private.current_user_id();
    new.connected_at := now();
    new.disconnected_by := null;
    new.disconnected_at := null;
    if new.status = 'disconnected' then
      raise exception 'a new connection cannot start disconnected' using errcode = 'check_violation';
    end if;
  else
    if (new.tenant_id, new.provider, new.connected_by, new.connected_at)
       is distinct from (old.tenant_id, old.provider, old.connected_by, old.connected_at) then
      raise exception 'connection identity is immutable' using errcode = 'insufficient_privilege';
    end if;
    if old.status = 'disconnected' then
      raise exception 'a disconnected connection cannot be changed' using errcode = 'check_violation';
    end if;
    if new.status = 'disconnected' then
      new.credential_ciphertext := null;
      new.credential_key_id := null;
      new.credential_hint := null;
      new.disconnected_by := app_private.current_user_id();
      new.disconnected_at := now();
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;
create trigger scheduling_connections_write before insert or update on public.scheduling_connections
  for each row execute function app_private.scheduling_connection_before_write();

create trigger appointment_types_set_updated_at before update on public.appointment_types
  for each row execute function app_private.set_updated_at();

create or replace function app_private.appointment_type_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (new.tenant_id, new.connection_id, new.provider_event_type_id)
     is distinct from (old.tenant_id, old.connection_id, old.provider_event_type_id) then
    raise exception 'appointment type identity is immutable' using errcode = 'insufficient_privilege';
  end if;
  return new;
end;
$$;
create trigger appointment_types_identity before update on public.appointment_types
  for each row execute function app_private.appointment_type_before_update();

revoke all on function app_private.scheduling_connection_before_write() from public, anon, authenticated;
revoke all on function app_private.appointment_type_before_update() from public, anon, authenticated;

-- ----- credential access (the only way to read the ciphertext) ---------------------------------
-- Staff: owner/admin/receptionist of the connection's clinic (booking management).
-- Widget: the active clinic of the current widget context only.
create or replace function app_private.scheduling_credential(p_connection uuid)
returns table (tenant_id uuid, provider text, ciphertext bytea, key_id text)
language sql stable security definer
set search_path = ''
as $$
  select c.tenant_id, c.provider, c.credential_ciphertext, c.credential_key_id
    from public.scheduling_connections c
   where c.id = p_connection
     and c.status <> 'disconnected'
     and (
       app_private.has_tenant_role(c.tenant_id,
         array['owner', 'admin', 'receptionist']::public.membership_role[])
       or (c.tenant_id = app_private.widget_tenant() and app_private.widget_tenant_active())
     );
$$;
revoke all on function app_private.scheduling_credential(uuid) from public, anon, authenticated;
grant execute on function app_private.scheduling_credential(uuid) to engage_app, engage_widget;

-- ----- row-level security ----------------------------------------------------------------------
alter table public.scheduling_connections enable row level security;
alter table public.scheduling_connections force row level security;
alter table public.appointment_types enable row level security;
alter table public.appointment_types force row level security;

create policy scheduling_connections_staff_select on public.scheduling_connections
  for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
create policy scheduling_connections_manage_insert on public.scheduling_connections
  for insert to engage_app
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
create policy scheduling_connections_manage_update on public.scheduling_connections
  for update to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
-- The widget needs to know which connection serves its clinic (no credential columns granted).
create policy scheduling_connections_widget_select on public.scheduling_connections
  for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and app_private.widget_tenant_active()
         and status = 'active');

create policy appointment_types_staff_select on public.appointment_types for select to engage_app
  using (app_private.has_tenant_role(tenant_id) or app_private.is_platform_admin());
create policy appointment_types_manage_insert on public.appointment_types for insert to engage_app
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
create policy appointment_types_manage_update on public.appointment_types for update to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]))
  with check (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
create policy appointment_types_manage_delete on public.appointment_types for delete to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[]));
create policy appointment_types_widget_select on public.appointment_types for select to engage_widget
  using (tenant_id = app_private.widget_tenant() and app_private.widget_tenant_active() and enabled
         and exists (select 1 from public.scheduling_connections c
                      where c.id = connection_id and c.status = 'active'));

-- ----- grants ----------------------------------------------------------------------------------
revoke all on public.scheduling_connections, public.appointment_types
  from public, anon, authenticated, service_role;

-- Staff never select the ciphertext or key id.
grant select (id, tenant_id, provider, status, account_label, account_time_zone, credential_hint,
              connected_by, connected_at, disconnected_by, disconnected_at, last_verified_at,
              last_error, updated_at)
  on public.scheduling_connections to engage_app;
-- The API generates the id first: the ciphertext is bound to it (associated data).
grant insert (id, tenant_id, provider, status, account_label, account_time_zone,
              credential_ciphertext, credential_key_id, credential_hint, last_verified_at)
  on public.scheduling_connections to engage_app;
grant update (status, account_label, account_time_zone, credential_ciphertext, credential_key_id,
              credential_hint, last_verified_at, last_error)
  on public.scheduling_connections to engage_app;
grant select (id, tenant_id, provider, status) on public.scheduling_connections to engage_widget;

grant select, delete on public.appointment_types to engage_app;
grant insert (tenant_id, connection_id, provider_event_type_id, name, duration_minutes,
              requires_confirmation, enabled, sort_order)
  on public.appointment_types to engage_app;
grant update (name, duration_minutes, requires_confirmation, enabled, sort_order)
  on public.appointment_types to engage_app;
grant select (id, tenant_id, connection_id, provider_event_type_id, name, duration_minutes,
              requires_confirmation, sort_order, enabled)
  on public.appointment_types to engage_widget;
