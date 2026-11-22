-- Phase 4c: appointments booked from the widget (ADR-035).
--
-- * An appointment row is written BEFORE the provider is called (status 'booking'); its id is
--   the reference sent to the provider (Cal.com metadata.engage_ref), so a lost response can be
--   reconciled. At most one booking may be in flight per conversation.
-- * Status changes follow a fixed state machine enforced here. 'confirmed'/'pending' require the
--   provider's booking id. Only those states enqueue the patient confirmation and clinic alert
--   (same transaction, unique keys: never twice). 'unknown' enqueues reconciliation.
-- * Attendee details are patient data: readable by the clinic's front desk and by the visitor's
--   own conversation only; immutable after creation.

alter table public.messages drop constraint messages_answer_source_check;
alter table public.messages add constraint messages_answer_source_check check (answer_source in
  ('facts', 'emergency', 'retrieval_ai', 'fallback', 'handover', 'budget_exhausted', 'greeting',
   'booking'));

alter table app_private.jobs drop constraint jobs_kind_check;
alter table app_private.jobs add constraint jobs_kind_check check (kind in
  ('handover_alert', 'domain_lapsed', 'booking_confirmation', 'booking_alert', 'booking_reconcile'));

alter table public.appointment_types add constraint appointment_types_id_tenant_key unique (id, tenant_id);

create table public.appointments (
  id uuid primary key,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  connection_id uuid not null,
  appointment_type_id uuid,
  conversation_id uuid,
  provider text not null check (provider in ('calcom', 'calendly')),
  provider_event_type_id text not null check (provider_event_type_id ~ '^[A-Za-z0-9_.:/-]{1,200}$'),
  type_name text not null check (char_length(type_name) between 1 and 120),
  status text not null default 'booking'
    check (status in ('booking', 'confirmed', 'pending', 'unknown', 'failed', 'cancelled')),
  start_at timestamptz not null,
  end_at timestamptz,
  attendee_name text not null check (char_length(attendee_name) between 1 and 120),
  attendee_email text not null check (char_length(attendee_email) between 3 and 254),
  attendee_phone text check (char_length(attendee_phone) <= 30),
  attendee_time_zone text not null check (char_length(attendee_time_zone) between 1 and 64),
  consent_given boolean not null check (consent_given),
  provider_booking_id text check (provider_booking_id ~ '^[A-Za-z0-9_-]{1,100}$'),
  failure_reason text check (char_length(failure_reason) <= 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  confirmed_at timestamptz,
  cancelled_at timestamptz,
  foreign key (connection_id, tenant_id)
    references public.scheduling_connections (id, tenant_id) on delete cascade,
  foreign key (conversation_id, tenant_id)
    references public.conversations (id, tenant_id) on delete set null (conversation_id),
  -- The appointment type must belong to the same clinic.
  foreign key (appointment_type_id, tenant_id)
    references public.appointment_types (id, tenant_id) on delete set null (appointment_type_id),
  check (status not in ('confirmed', 'pending') or provider_booking_id is not null),
  check (end_at is null or end_at > start_at)
);
create unique index appointments_provider_booking_unique
  on public.appointments (connection_id, provider_booking_id) where provider_booking_id is not null;
create unique index appointments_one_in_flight
  on public.appointments (conversation_id) where status = 'booking';
create index appointments_tenant_start_idx on public.appointments (tenant_id, start_at);

-- ----- state machine and server-owned fields --------------------------------------------------
create or replace function app_private.appointment_before_write()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  allowed text[];
begin
  if tg_op = 'INSERT' then
    if new.status <> 'booking' then
      raise exception 'appointments start as booking' using errcode = 'check_violation';
    end if;
    new.created_at := now();
    new.confirmed_at := null;
    new.cancelled_at := null;
  else
    if (new.id, new.tenant_id, new.connection_id, new.conversation_id, new.provider,
        new.provider_event_type_id, new.attendee_name, new.attendee_email, new.attendee_phone,
        new.attendee_time_zone, new.consent_given, new.created_at)
       is distinct from
       (old.id, old.tenant_id, old.connection_id, old.conversation_id, old.provider,
        old.provider_event_type_id, old.attendee_name, old.attendee_email, old.attendee_phone,
        old.attendee_time_zone, old.consent_given, old.created_at)
       and not (old.conversation_id is not null and new.conversation_id is null) then
      raise exception 'appointment identity is immutable' using errcode = 'insufficient_privilege';
    end if;
    if new.status is distinct from old.status then
      allowed := case old.status
        when 'booking' then array['confirmed', 'pending', 'unknown', 'failed']
        when 'unknown' then array['confirmed', 'pending', 'failed']
        when 'pending' then array['confirmed', 'cancelled', 'failed']
        when 'confirmed' then array['cancelled']
        else array[]::text[] end;
      if not (new.status = any (allowed)) then
        raise exception 'appointment cannot move from % to %', old.status, new.status
          using errcode = 'check_violation';
      end if;
      if new.status = 'confirmed' then new.confirmed_at := now(); end if;
      if new.status = 'cancelled' then new.cancelled_at := now(); end if;
    end if;
    if old.provider_booking_id is not null
       and new.provider_booking_id is distinct from old.provider_booking_id then
      raise exception 'provider booking id is immutable' using errcode = 'insufficient_privilege';
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;
create trigger appointments_write before insert or update on public.appointments
  for each row execute function app_private.appointment_before_write();

create or replace function app_private.appointment_after_update()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  if new.status in ('confirmed', 'pending') and old.status in ('booking', 'unknown') then
    perform app_private.enqueue_job('booking_confirmation', new.tenant_id,
      jsonb_build_object('appointment_id', new.id), 'booking_confirmation/' || new.id::text);
    perform app_private.enqueue_job('booking_alert', new.tenant_id,
      jsonb_build_object('appointment_id', new.id), 'booking_alert/' || new.id::text);
  elsif new.status = 'unknown' and old.status = 'booking' then
    perform app_private.enqueue_job('booking_reconcile', new.tenant_id,
      jsonb_build_object('appointment_id', new.id, 'attempt', 1),
      'booking_reconcile/' || new.id::text || '/1', now() + interval '1 minute');
  end if;
  return null;
end;
$$;
create trigger appointments_after_update after update on public.appointments
  for each row execute function app_private.appointment_after_update();

revoke all on function app_private.appointment_before_write() from public, anon, authenticated;
revoke all on function app_private.appointment_after_update() from public, anon, authenticated;

-- ----- RLS -------------------------------------------------------------------------------------
alter table public.appointments enable row level security;
alter table public.appointments force row level security;

create policy appointments_staff_select on public.appointments for select to engage_app
  using (app_private.has_tenant_role(tenant_id,
    array['owner', 'admin', 'receptionist']::public.membership_role[]));
create policy appointments_staff_update on public.appointments for update to engage_app
  using (app_private.has_tenant_role(tenant_id,
    array['owner', 'admin', 'receptionist']::public.membership_role[]))
  with check (app_private.has_tenant_role(tenant_id,
    array['owner', 'admin', 'receptionist']::public.membership_role[]));

create policy appointments_widget_select on public.appointments for select to engage_widget
  using (tenant_id = app_private.widget_tenant()
         and conversation_id = app_private.widget_conversation());
create policy appointments_widget_insert on public.appointments for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant()
              and conversation_id = app_private.widget_conversation()
              and app_private.widget_tenant_active()
              and exists (select 1 from public.scheduling_connections c
                           where c.id = connection_id and c.status = 'active'));
create policy appointments_widget_update on public.appointments for update to engage_widget
  using (tenant_id = app_private.widget_tenant()
         and conversation_id = app_private.widget_conversation())
  with check (tenant_id = app_private.widget_tenant()
              and conversation_id = app_private.widget_conversation());

revoke all on public.appointments from public, anon, authenticated, service_role;
grant select on public.appointments to engage_app;
grant update (status, failure_reason) on public.appointments to engage_app;
grant select (id, tenant_id, conversation_id, type_name, status, start_at, end_at,
              provider_booking_id) on public.appointments to engage_widget;
grant insert (id, tenant_id, connection_id, appointment_type_id, conversation_id, provider,
              provider_event_type_id, type_name, start_at, end_at, attendee_name, attendee_email,
              attendee_phone, attendee_time_zone, consent_given)
  on public.appointments to engage_widget;
grant update (status, provider_booking_id, end_at, failure_reason)
  on public.appointments to engage_widget;

-- The widget may report that the clinic's provider key was rejected (marks the connection).
create or replace function app_private.widget_report_credential_rejected(p_connection uuid)
returns void
language sql volatile security definer
set search_path = ''
as $$
  update public.scheduling_connections
     set status = 'failing', last_error = 'credential_rejected:widget'
   where id = p_connection and tenant_id = app_private.widget_tenant() and status = 'active';
$$;
revoke all on function app_private.widget_report_credential_rejected(uuid) from public, anon, authenticated;
grant execute on function app_private.widget_report_credential_rejected(uuid) to engage_widget;

-- ----- worker functions (engage_jobs) ----------------------------------------------------------
-- Email data, re-checked at send time. Clinic phone comes from the PUBLISHED profile only.
create or replace function app_private.job_booking(p_appointment uuid)
returns table (tenant_id uuid, clinic text, clinic_time_zone text, clinic_phone text,
               type_name text, start_at timestamptz, end_at timestamptz, status text,
               attendee_name text, attendee_email text, attendee_time_zone text,
               conversation_id uuid)
language sql stable security definer
set search_path = ''
as $$
  select a.tenant_id, t.display_name, t.timezone, p.published->>'public_phone',
         a.type_name, a.start_at, a.end_at, a.status, a.attendee_name, a.attendee_email,
         a.attendee_time_zone, a.conversation_id
    from public.appointments a
    join public.tenants t on t.id = a.tenant_id
    left join public.clinic_profiles p on p.tenant_id = a.tenant_id
   where a.id = p_appointment and t.status in ('pending', 'active');
$$;

-- Reconciliation input and credential (the jobs role never sees other columns or rows).
create or replace function app_private.job_booking_reconcile(p_appointment uuid)
returns table (tenant_id uuid, connection_id uuid, provider text, ciphertext bytea, key_id text,
               provider_event_type_id text, start_at timestamptz, attendee_email text,
               status text)
language sql stable security definer
set search_path = ''
as $$
  select a.tenant_id, a.connection_id, c.provider, c.credential_ciphertext, c.credential_key_id,
         a.provider_event_type_id, a.start_at, a.attendee_email, a.status
    from public.appointments a
    join public.scheduling_connections c on c.id = a.connection_id
    join public.tenants t on t.id = a.tenant_id
   where a.id = p_appointment and c.status <> 'disconnected' and t.status in ('pending', 'active');
$$;

-- Record a reconciliation result for an appointment still in 'unknown'.
create or replace function app_private.job_resolve_booking(
  p_appointment uuid, p_status text, p_provider_booking_id text, p_reason text default null
)
returns text
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_status text;
begin
  if p_status not in ('confirmed', 'pending', 'failed') then
    raise exception 'invalid resolution' using errcode = 'check_violation';
  end if;
  update public.appointments
     set status = p_status,
         provider_booking_id = coalesce(p_provider_booking_id, provider_booking_id),
         failure_reason = case when p_status = 'failed' then left(p_reason, 100) else failure_reason end
   where id = p_appointment and status = 'unknown'
  returning status into v_status;
  return v_status;
end;
$$;

-- Schedule the next reconciliation attempt.
create or replace function app_private.job_retry_reconcile(
  p_appointment uuid, p_attempt integer, p_delay_seconds integer
)
returns void
language sql volatile security definer
set search_path = ''
as $$
  select app_private.enqueue_job('booking_reconcile', a.tenant_id,
           jsonb_build_object('appointment_id', a.id, 'attempt', p_attempt),
           'booking_reconcile/' || a.id::text || '/' || p_attempt::text,
           now() + make_interval(secs => greatest(p_delay_seconds, 10)))
    from public.appointments a
   where a.id = p_appointment and a.status = 'unknown';
$$;

revoke all on function app_private.job_booking(uuid) from public, anon, authenticated;
revoke all on function app_private.job_booking_reconcile(uuid) from public, anon, authenticated;
revoke all on function app_private.job_resolve_booking(uuid, text, text, text) from public, anon, authenticated;
revoke all on function app_private.job_retry_reconcile(uuid, integer, integer) from public, anon, authenticated;
grant execute on function app_private.job_booking(uuid), app_private.job_booking_reconcile(uuid),
  app_private.job_resolve_booking(uuid, text, text, text),
  app_private.job_retry_reconcile(uuid, integer, integer)
  to engage_jobs;
