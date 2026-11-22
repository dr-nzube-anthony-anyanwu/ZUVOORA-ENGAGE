-- Phase 4d lifecycle: reminders, provider events (cancel/reschedule/reject/created), exactly once.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(24);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant engage_jobs to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget, engage_jobs;

create function pg_temp.login(p_email text) returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', 'aal1')::text, true);
end;
$$;
create function pg_temp.job_status(p_key text) returns text language sql security definer as
  $$ select status from app_private.jobs where idempotency_key = p_key $$;
grant execute on function pg_temp.login(text), pg_temp.job_status(text) to engage_app, engage_jobs;

insert into auth.users (id, email) values ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner');
-- Reminders are a Professional feature (Phase 5); Essentials gets none (13_entitlements).
update public.tenant_subscriptions set plan_key = 'professional', status = 'active'
  where tenant_id = '10000000-0000-4000-8000-00000000000a';
insert into public.scheduling_connections (id, tenant_id, provider, credential_ciphertext, credential_key_id,
    webhook_secret_ciphertext, webhook_key_id) values
  ('70000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'calcom', '\x00'::bytea,
   'abcdef012345', '\x01'::bytea, 'abcdef012345');

-- Appointments are created as 'booking' then confirmed, exactly as the API does.
create function pg_temp.confirmed(p_id uuid, p_uid text, p_start timestamptz) returns void language plpgsql as $$
begin
  insert into public.appointments (id, tenant_id, connection_id, provider, provider_event_type_id, type_name,
      start_at, attendee_name, attendee_email, attendee_time_zone, consent_given)
    values (p_id, '10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', 'calcom', '101',
            'Eye exam', p_start, 'Ada Test', 'ada@example.com', 'Africa/Lagos', true);
  update public.appointments set status = 'confirmed', provider_booking_id = p_uid where id = p_id;
end;
$$;

-- 1. Reminders (1-4)
select pg_temp.confirmed('80000000-0000-4000-8000-000000000001', 'bk1', now() + interval '3 days');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000001/24h'), 'queued',
  'A confirmed booking gets a 24-hour reminder');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000001/2h'), null,
  'The 2-hour reminder is off by default');
update public.scheduling_connections set reminder_2h = true;
select pg_temp.confirmed('80000000-0000-4000-8000-000000000002', 'bk2', now() + interval '3 days');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000002/2h'), 'queued',
  'The 2-hour reminder when the clinic turns it on');
select pg_temp.confirmed('80000000-0000-4000-8000-000000000003', 'bk3', now() + interval '3 hours');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000003/24h'), null,
  'No 24-hour reminder for a booking less than a day away');

-- 2. Cancellation at the provider, exactly once (5-10)
set local role engage_jobs;
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('a', 64),
    'BOOKING_CANCELLED', 'bk1', null, null, null, null), 'cancelled', 'Provider cancellation is applied');
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('a', 64),
    'BOOKING_CANCELLED', 'bk1', null, null, null, null), 'duplicate', 'The same delivery again is a no-op');
reset role;
select is((select status from public.appointments where id = '80000000-0000-4000-8000-000000000001'),
  'cancelled', 'Appointment is cancelled');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000001/24h'), 'skipped',
  'Its reminder is suppressed immediately');
select is(pg_temp.job_status('booking_confirmation/80000000-0000-4000-8000-000000000001'), 'skipped',
  'An unsent confirmation is suppressed too');
select is(pg_temp.job_status('booking_cancelled/80000000-0000-4000-8000-000000000001'), 'queued',
  'The patient is told it was cancelled');

-- 3. Reschedule at the provider (11-16)
set local role engage_jobs;
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('b', 64),
    'BOOKING_RESCHEDULED', 'bk2new', 'bk2', now() + interval '5 days', now() + interval '5 days 30 minutes', null),
  'rescheduled', 'Provider reschedule is applied');
reset role;
select results_eq($$select status, rescheduled_to is not null from public.appointments
    where id = '80000000-0000-4000-8000-000000000002'$$,
  $$values ('rescheduled'::text, true)$$, 'The old appointment is marked rescheduled and linked');
select results_eq($$select n.status, n.provider_booking_id, n.attendee_email, n.start_at > now() + interval '4 days'
    from public.appointments o join public.appointments n on n.id = o.rescheduled_to
    where o.id = '80000000-0000-4000-8000-000000000002'$$,
  $$values ('confirmed'::text, 'bk2new'::text, 'ada@example.com'::text, true)$$,
  'A new confirmed appointment holds the new time and the same patient');
select is(pg_temp.job_status('booking_reminder/80000000-0000-4000-8000-000000000002/24h'), 'skipped',
  'Old-time reminders are suppressed');
select is((select count(*)::int from app_private.jobs j join public.appointments o
    on j.payload->>'appointment_id' = o.rescheduled_to::text
    where o.id = '80000000-0000-4000-8000-000000000002' and j.kind = 'booking_reminder' and j.status = 'queued'),
  2, 'New-time reminders are scheduled (24 h and 2 h)');
select throws_ok($$update public.appointments set start_at = now() + interval '9 days'
    where id = '80000000-0000-4000-8000-000000000003'$$, '42501', null,
  'An appointment time is never edited in place');

-- 4. Created / requested / rejected (17-20)
insert into public.appointments (id, tenant_id, connection_id, provider, provider_event_type_id, type_name,
    start_at, attendee_name, attendee_email, attendee_time_zone, consent_given)
  values ('80000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-00000000000a',
          '70000000-0000-4000-8000-0000000000a1', 'calcom', '101', 'Eye exam', now() + interval '2 days',
          'Ada', 'ada@example.com', 'UTC', true);
update public.appointments set status = 'unknown' where id = '80000000-0000-4000-8000-000000000004';
set local role engage_jobs;
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('c', 64),
    'BOOKING_CREATED', 'bk4', null, null, null, '80000000-0000-4000-8000-000000000004'),
  'resolved_unknown', 'A webhook resolves a booking whose response was lost');
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('d', 64),
    'BOOKING_CANCELLED', 'not-ours', null, null, null, null), 'ignored',
  'Bookings not made through Engage are ignored');
reset role;
select is((select status from public.appointments where id = '80000000-0000-4000-8000-000000000004'),
  'confirmed', 'Resolved booking is confirmed');
insert into public.appointments (id, tenant_id, connection_id, provider, provider_event_type_id, type_name,
    start_at, attendee_name, attendee_email, attendee_time_zone, consent_given)
  values ('80000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-00000000000a',
          '70000000-0000-4000-8000-0000000000a1', 'calcom', '102', 'Fitting', now() + interval '2 days',
          'Ada', 'ada@example.com', 'UTC', true);
update public.appointments set status = 'pending', provider_booking_id = 'bk5' where id = '80000000-0000-4000-8000-000000000005';
set local role engage_jobs;
select is(app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('e', 64),
    'BOOKING_REJECTED', 'bk5', null, null, null, null), 'rejected', 'A clinic rejection fails the request');
reset role;

-- 5. Access (21-24)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select throws_ok($$select app_private.apply_provider_event('70000000-0000-4000-8000-0000000000a1', repeat('f', 64),
    'BOOKING_CANCELLED', 'bk3', null, null, null, null)$$, '42501', null, 'Staff cannot inject provider events');
select throws_ok('select webhook_secret_ciphertext from public.scheduling_connections', '42501', null,
  'Staff cannot read the webhook secret column');
update public.scheduling_connections set status = 'disconnected';
reset role;
set local role engage_jobs;
select is_empty($$select 1 from app_private.webhook_target('70000000-0000-4000-8000-0000000000a1')$$,
  'A disconnected connection accepts no webhooks');
select throws_ok('select 1 from app_private.provider_events', '42501', null, 'Event log is not directly readable');
reset role;

select * from finish();
rollback;
