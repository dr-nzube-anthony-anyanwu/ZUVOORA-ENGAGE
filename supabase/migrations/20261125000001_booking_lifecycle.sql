-- Phase 4d: provider webhooks, cancellation/reschedule lifecycle and reminders (ADR-036).
--
-- * Each connection has its own webhook secret, encrypted by the API like the API key.
-- * Verified webhook deliveries are recorded once per connection by body hash; a repeated
--   delivery is a no-op. Events change appointments only through app_private functions.
-- * Confirmation schedules reminders (24 h, optional 2 h). Cancellation, rejection or
--   reschedule skips every queued email for that appointment immediately, and the worker
--   re-checks status and time before sending anything.

-- ----- connection: webhook secret and reminder preference ------------------------------------
alter table public.scheduling_connections
  add column webhook_secret_ciphertext bytea check (octet_length(webhook_secret_ciphertext) <= 4096),
  add column webhook_key_id text check (webhook_key_id ~ '^[0-9a-f]{12}$'),
  add column provider_webhook_id text check (provider_webhook_id ~ '^[A-Za-z0-9_-]{1,100}$'),
  add column webhook_configured_at timestamptz,
  add column reminder_2h boolean not null default false,
  add constraint scheduling_connections_webhook_pair
    check ((webhook_secret_ciphertext is null) = (webhook_key_id is null));

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
      new.webhook_secret_ciphertext := null;
      new.webhook_key_id := null;
      new.disconnected_by := app_private.current_user_id();
      new.disconnected_at := now();
    end if;
    if new.webhook_secret_ciphertext is distinct from old.webhook_secret_ciphertext
       and new.webhook_secret_ciphertext is not null then
      new.webhook_configured_at := now();
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

grant select (provider_webhook_id, webhook_configured_at, reminder_2h)
  on public.scheduling_connections to engage_app;
grant update (webhook_secret_ciphertext, webhook_key_id, provider_webhook_id, reminder_2h)
  on public.scheduling_connections to engage_app;

-- Owners/admins read back the webhook ciphertext only to rotate it (delete the old one).
create or replace function app_private.scheduling_webhook_secret(p_connection uuid)
returns table (tenant_id uuid, ciphertext bytea, key_id text, provider_webhook_id text)
language sql stable security definer
set search_path = ''
as $$
  select c.tenant_id, c.webhook_secret_ciphertext, c.webhook_key_id, c.provider_webhook_id
    from public.scheduling_connections c
   where c.id = p_connection and c.status <> 'disconnected'
     and app_private.has_tenant_role(c.tenant_id, array['owner', 'admin']::public.membership_role[]);
$$;
revoke all on function app_private.scheduling_webhook_secret(uuid) from public, anon, authenticated;
grant execute on function app_private.scheduling_webhook_secret(uuid) to engage_app;

-- ----- appointments: rescheduled state ---------------------------------------------------------
alter table public.appointments drop constraint appointments_status_check;
alter table public.appointments add constraint appointments_status_check check (status in
  ('booking', 'confirmed', 'pending', 'unknown', 'failed', 'cancelled', 'rescheduled'));
alter table public.appointments
  add column rescheduled_to uuid references public.appointments (id) on delete set null;

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
        when 'pending' then array['confirmed', 'cancelled', 'failed', 'rescheduled']
        when 'confirmed' then array['cancelled', 'rescheduled']
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
    if new.start_at is distinct from old.start_at then
      raise exception 'an appointment time is changed by rescheduling (a new appointment)'
        using errcode = 'insufficient_privilege';
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

alter table app_private.jobs drop constraint jobs_kind_check;
alter table app_private.jobs add constraint jobs_kind_check check (kind in
  ('handover_alert', 'domain_lapsed', 'booking_confirmation', 'booking_alert', 'booking_reconcile',
   'booking_reminder', 'booking_cancelled'));

-- Skip every queued email for an appointment (cancelled, rejected, rescheduled or failed).
create or replace function app_private.skip_appointment_jobs(p_appointment uuid, p_reason text)
returns integer
language sql volatile security definer
set search_path = ''
as $$
  with skipped as (
    update app_private.jobs
       set status = 'skipped', finished_at = now(), last_error = left(p_reason, 300)
     where status = 'queued'
       and kind in ('booking_confirmation', 'booking_alert', 'booking_reminder', 'booking_reconcile')
       and payload->>'appointment_id' = p_appointment::text
    returning 1)
  select count(*)::int from skipped;
$$;
revoke all on function app_private.skip_appointment_jobs(uuid, text) from public, anon, authenticated;

create or replace function app_private.appointment_after_update()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
declare
  v_2h boolean;
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

  -- Reminders once the booking is confirmed (not for pending requests).
  if new.status = 'confirmed' and old.status is distinct from 'confirmed' then
    if new.start_at - interval '24 hours' > now() + interval '15 minutes' then
      perform app_private.enqueue_job('booking_reminder', new.tenant_id,
        jsonb_build_object('appointment_id', new.id, 'start_at', new.start_at, 'lead', '24h'),
        'booking_reminder/' || new.id::text || '/24h', new.start_at - interval '24 hours');
    end if;
    select c.reminder_2h into v_2h from public.scheduling_connections c where c.id = new.connection_id;
    if coalesce(v_2h, false) and new.start_at - interval '2 hours' > now() + interval '5 minutes' then
      perform app_private.enqueue_job('booking_reminder', new.tenant_id,
        jsonb_build_object('appointment_id', new.id, 'start_at', new.start_at, 'lead', '2h'),
        'booking_reminder/' || new.id::text || '/2h', new.start_at - interval '2 hours');
    end if;
  end if;

  -- Leaving an active state: no stale emails may go out.
  if new.status in ('cancelled', 'rescheduled', 'failed') and old.status is distinct from new.status then
    perform app_private.skip_appointment_jobs(new.id, 'appointment ' || new.status);
    if new.status = 'cancelled' then
      perform app_private.enqueue_job('booking_cancelled', new.tenant_id,
        jsonb_build_object('appointment_id', new.id), 'booking_cancelled/' || new.id::text);
    end if;
  end if;
  return null;
end;
$$;

-- ----- provider events (verified webhook deliveries) -------------------------------------------
create table app_private.provider_events (
  id bigint generated always as identity primary key,
  connection_id uuid not null references public.scheduling_connections (id) on delete cascade,
  event_key text not null check (event_key ~ '^[0-9a-f]{64}$'),
  trigger text not null check (char_length(trigger) <= 60),
  result text not null check (char_length(result) <= 60),
  received_at timestamptz not null default now(),
  unique (connection_id, event_key)
);
create index provider_events_received_idx on app_private.provider_events (received_at);
revoke all on app_private.provider_events from public, anon, authenticated, service_role;

-- Where a webhook for this connection is verified (role engage_jobs; no user involved).
create or replace function app_private.webhook_target(p_connection uuid)
returns table (tenant_id uuid, provider text, ciphertext bytea, key_id text)
language sql stable security definer
set search_path = ''
as $$
  select c.tenant_id, c.provider, c.webhook_secret_ciphertext, c.webhook_key_id
    from public.scheduling_connections c
    join public.tenants t on t.id = c.tenant_id
   where c.id = p_connection and c.status <> 'disconnected'
     and c.webhook_secret_ciphertext is not null and t.status in ('pending', 'active');
$$;

-- Apply one verified provider event exactly once. Returns what happened (for logs/tests).
create or replace function app_private.apply_provider_event(
  p_connection uuid, p_event_key text, p_trigger text, p_uid text, p_old_uid text,
  p_start timestamptz, p_end timestamptz, p_engage_ref text
)
returns text
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v public.appointments%rowtype;
  v_new uuid;
  v_result text := 'ignored';
begin
  insert into app_private.provider_events (connection_id, event_key, trigger, result)
  values (p_connection, p_event_key, left(p_trigger, 60), 'pending')
  on conflict (connection_id, event_key) do nothing;
  if not found then
    return 'duplicate';
  end if;

  if p_trigger in ('BOOKING_CREATED', 'BOOKING_REQUESTED') then
    -- Our own booking whose response was lost (reconciliation shortcut).
    update public.appointments
       set status = case when p_trigger = 'BOOKING_REQUESTED' then 'pending' else 'confirmed' end,
           provider_booking_id = p_uid
     where connection_id = p_connection and status = 'unknown' and id::text = p_engage_ref
    returning 'resolved_unknown' into v_result;
    if v_result is null then
      -- The clinic confirmed a requested booking.
      update public.appointments set status = 'confirmed'
       where connection_id = p_connection and provider_booking_id = p_uid and status = 'pending'
         and p_trigger = 'BOOKING_CREATED'
      returning 'confirmed' into v_result;
    end if;
  elsif p_trigger = 'BOOKING_CANCELLED' then
    update public.appointments set status = 'cancelled', failure_reason = 'cancelled_at_provider'
     where connection_id = p_connection and provider_booking_id = p_uid
       and status in ('confirmed', 'pending')
    returning 'cancelled' into v_result;
  elsif p_trigger = 'BOOKING_REJECTED' then
    update public.appointments set status = 'failed', failure_reason = 'rejected_by_clinic'
     where connection_id = p_connection and provider_booking_id = p_uid and status = 'pending'
    returning 'rejected' into v_result;
  elsif p_trigger = 'BOOKING_RESCHEDULED' and p_old_uid is not null and p_uid is not null then
    select * into v from public.appointments
     where connection_id = p_connection and provider_booking_id = p_old_uid
       and status in ('confirmed', 'pending')
     for update;
    if found and p_start is not null then
      v_new := gen_random_uuid();
      update public.appointments set status = 'rescheduled', rescheduled_to = null where id = v.id;
      insert into public.appointments (id, tenant_id, connection_id, appointment_type_id,
          conversation_id, provider, provider_event_type_id, type_name, start_at, end_at,
          attendee_name, attendee_email, attendee_phone, attendee_time_zone, consent_given)
        values (v_new, v.tenant_id, v.connection_id, v.appointment_type_id, null, v.provider,
          v.provider_event_type_id, v.type_name, p_start, p_end, v.attendee_name,
          v.attendee_email, v.attendee_phone, v.attendee_time_zone, true);
      update public.appointments set status = 'confirmed', provider_booking_id = p_uid where id = v_new;
      update public.appointments set rescheduled_to = v_new where id = v.id;
      v_result := 'rescheduled';
    end if;
  end if;

  v_result := coalesce(v_result, 'ignored');
  update app_private.provider_events set result = v_result
   where connection_id = p_connection and event_key = p_event_key;
  return v_result;
end;
$$;

-- Old event records are kept 90 days (enough to absorb provider retries), then purged.
create or replace function app_private.purge_finished_jobs()
returns integer
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_jobs integer;
begin
  delete from app_private.jobs
   where status in ('done', 'skipped', 'dead') and finished_at < now() - interval '30 days';
  get diagnostics v_jobs = row_count;
  delete from app_private.provider_events where received_at < now() - interval '90 days';
  return v_jobs;
end;
$$;

-- Reminder and cancellation email data: same as job_booking plus the connection's id.
revoke all on function app_private.webhook_target(uuid) from public, anon, authenticated;
revoke all on function app_private.apply_provider_event(uuid, text, text, text, text, timestamptz, timestamptz, text)
  from public, anon, authenticated;
grant execute on function app_private.webhook_target(uuid),
  app_private.apply_provider_event(uuid, text, text, text, text, timestamptz, timestamptz, text),
  app_private.rate_limit_hit(text, integer, integer)
  to engage_jobs;

-- Staff may now read the new columns of appointments (already: select on all columns).
