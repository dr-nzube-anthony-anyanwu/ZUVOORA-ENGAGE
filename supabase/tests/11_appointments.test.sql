-- Phase 4c appointments: widget scope, state machine, jobs on confirmation, staff privacy.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(25);

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
create function pg_temp.widget(p_tenant uuid, p_conversation uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', p_tenant::text, true);
  perform set_config('request.widget.conversation_id', coalesce(p_conversation::text, ''), true);
end;
$$;
create function pg_temp.jobs(p_key_prefix text) returns bigint language sql security definer as
  $$ select count(*) from app_private.jobs where idempotency_key like p_key_prefix || '%' $$;
grant execute on function pg_temp.login(text), pg_temp.widget(uuid, uuid), pg_temp.jobs(text)
  to engage_app, engage_widget, engage_jobs, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer');
insert into public.scheduling_connections (id, tenant_id, provider, credential_ciphertext, credential_key_id) values
  ('70000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'calcom', '\x00'::bytea, 'abcdef012345'),
  ('70000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', 'calcom', '\x00'::bytea, 'abcdef012345');
insert into public.appointment_types (id, tenant_id, connection_id, provider_event_type_id, name, duration_minutes) values
  ('71000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', '101', 'Eye exam', 30),
  ('71000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', '70000000-0000-4000-8000-0000000000b1', '201', 'B exam', 30);
insert into public.conversations (id, tenant_id) values
  ('40000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a'),
  ('40000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a');

create function pg_temp.book(p_id uuid, p_conversation uuid, p_type uuid default '71000000-0000-4000-8000-0000000000a1')
returns void language sql as $$
  insert into public.appointments (id, tenant_id, connection_id, appointment_type_id, conversation_id,
    provider, provider_event_type_id, type_name, start_at, attendee_name, attendee_email,
    attendee_time_zone, consent_given)
  values (p_id, '10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', p_type,
          p_conversation, 'calcom', '101', 'Eye exam', now() + interval '2 days', 'Ada Test',
          'ada@example.com', 'Africa/Lagos', true)
$$;
grant execute on function pg_temp.book(uuid, uuid, uuid) to engage_widget;

-- 1. The widget books only in its own conversation (1-5)
select pg_temp.widget('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1');
set local role engage_widget;
select lives_ok($$select pg_temp.book('80000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-0000000000a1')$$,
  'Widget records a booking attempt in its conversation');
select throws_ok($$select pg_temp.book('80000000-0000-4000-8000-000000000002', '40000000-0000-4000-8000-0000000000a1')$$,
  '23505', null, 'Only one booking in flight per conversation');
select throws_ok($$select pg_temp.book('80000000-0000-4000-8000-000000000003', '40000000-0000-4000-8000-0000000000a2')$$,
  '42501', null, 'Cannot book in another visitor''s conversation');
select throws_ok('select attendee_email from public.appointments', '42501', null,
  'Widget cannot read attendee details back');

-- 2. State machine (6-11)
select throws_ok($$update public.appointments set status = 'confirmed' where id = '80000000-0000-4000-8000-000000000001'$$,
  '23514', null, 'Confirmed requires the provider booking id');
select lives_ok($$update public.appointments set status = 'confirmed', provider_booking_id = 'bk_1'
    where id = '80000000-0000-4000-8000-000000000001'$$, 'Provider success confirms the booking');
select throws_ok($$select pg_temp.book('80000000-0000-4000-8000-000000000004', '40000000-0000-4000-8000-0000000000a1',
    '71000000-0000-4000-8000-0000000000b1')$$,
  '23503', null, 'Cannot use another clinic''s appointment type');
reset role;
select is(pg_temp.jobs('booking_confirmation/80000000-0000-4000-8000-000000000001'), 1::bigint,
  'Confirmation email queued with the confirmation');
select is(pg_temp.jobs('booking_alert/80000000-0000-4000-8000-000000000001'), 1::bigint, 'Clinic alert queued');
set local role engage_widget;
select throws_ok($$update public.appointments set status = 'booking' where id = '80000000-0000-4000-8000-000000000001'$$,
  '23514', null, 'A confirmed booking cannot go back');
select throws_ok($$update public.appointments set provider_booking_id = 'bk_other' where id = '80000000-0000-4000-8000-000000000001'$$,
  '42501', null, 'The provider booking id cannot be replaced');
reset role;

-- 3. Unknown outcome -> reconciliation (12-16)
select pg_temp.widget('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1');
set local role engage_widget;
select pg_temp.book('80000000-0000-4000-8000-000000000005', '40000000-0000-4000-8000-0000000000a1');
update public.appointments set status = 'unknown' where id = '80000000-0000-4000-8000-000000000005';
reset role;
select is(pg_temp.jobs('booking_reconcile/80000000-0000-4000-8000-000000000005/1'), 1::bigint,
  'An unknown outcome queues reconciliation');
select is(pg_temp.jobs('booking_confirmation/80000000-0000-4000-8000-000000000005'), 0::bigint,
  'No confirmation while the outcome is unknown');
set local role engage_jobs;
select is(app_private.job_resolve_booking('80000000-0000-4000-8000-000000000005', 'confirmed', 'bk_5'), 'confirmed',
  'Reconciliation confirms a booking found at the provider');
select is(app_private.job_resolve_booking('80000000-0000-4000-8000-000000000005', 'failed', null, 'x'), null,
  'Reconciliation only touches unknown bookings');
reset role;
select is(pg_temp.jobs('booking_confirmation/80000000-0000-4000-8000-000000000005'), 1::bigint,
  'Confirmation queued once reconciled');

-- 4. Staff privacy (17-20)
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.appointments', array[2], 'Front desk sees bookings');
select throws_ok($$update public.appointments set attendee_email = 'x@example.com'$$, '42501', null,
  'Attendee details cannot be changed');
reset role;
select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.appointments', 'Viewers cannot see patient bookings');
reset role;
set local role authenticated;
select throws_ok('select 1 from public.appointments', '42501', null, 'Data API: appointments denied');
reset role;

-- 5. Worker data (21-22)
set local role engage_jobs;
select results_eq($$select type_name, attendee_email, status from app_private.job_booking('80000000-0000-4000-8000-000000000001')$$,
  $$values ('Eye exam'::text, 'ada@example.com'::text, 'confirmed'::text)$$, 'Worker reads booking email data');
select throws_ok('select 1 from public.appointments', '42501', null, 'Worker has no direct table access');
reset role;

-- 6. Reply-To for patient emails comes from the PUBLISHED profile only (Phase 6, D3) (23-25)
set local role engage_jobs;
select is((select clinic_email from app_private.job_booking('80000000-0000-4000-8000-000000000001')),
  null, 'No profile: no clinic email');
reset role;
insert into public.clinic_profiles (tenant_id, draft)
  values ('10000000-0000-4000-8000-00000000000a', '{"public_email": "front-desk@clinic-a.example"}');
set local role engage_jobs;
select is((select clinic_email from app_private.job_booking('80000000-0000-4000-8000-000000000001')),
  null, 'Draft-only email is not used');
reset role;
update public.clinic_profiles set published = draft where tenant_id = '10000000-0000-4000-8000-00000000000a';
set local role engage_jobs;
select is((select clinic_email from app_private.job_booking('80000000-0000-4000-8000-000000000001')),
  'front-desk@clinic-a.example', 'Published email is the Reply-To address');
reset role;

select * from finish();
rollback;
