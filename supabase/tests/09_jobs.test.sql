-- Phase 4a job queue: access, enqueue-by-database, leases, retries, dead letters, email data.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(24);

grant engage_app to postgres with inherit false, set true;
grant engage_jobs to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_jobs, engage_widget;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a2', 'a.admin@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a5', 'a.former@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');
insert into public.tenant_memberships (tenant_id, user_id, role, is_active) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner', true),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a2', 'admin', true),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist', true),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer', true);
insert into public.tenant_memberships (tenant_id, user_id, role, is_active, revoked_at) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a5', 'receptionist', false, now());
insert into public.conversations (id, tenant_id) values
  ('40000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a'),
  ('40000000-0000-4000-8000-0000000000c1', '10000000-0000-4000-8000-00000000000c');

-- 1. Enqueued by the database in the same transaction (1-2)
insert into public.handover_requests (id, tenant_id, conversation_id, contact_phone, consent_given) values
  ('60000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a',
   '40000000-0000-4000-8000-0000000000a1', '+234 801 000 0001', true),
  ('60000000-0000-4000-8000-0000000000c1', '10000000-0000-4000-8000-00000000000c',
   '40000000-0000-4000-8000-0000000000c1', '+234 801 000 0002', true);
select results_eq($$select kind, payload->>'handover_id' from app_private.jobs
    where idempotency_key = 'handover_alert/60000000-0000-4000-8000-0000000000a1'$$,
  $$values ('handover_alert'::text, '60000000-0000-4000-8000-0000000000a1'::text)$$,
  'A call-back request enqueues a clinic alert');
select app_private.enqueue_job('handover_alert', '10000000-0000-4000-8000-00000000000a', '{}',
  'handover_alert/60000000-0000-4000-8000-0000000000a1');
select results_eq($$select count(*)::int from app_private.jobs
    where idempotency_key = 'handover_alert/60000000-0000-4000-8000-0000000000a1'$$,
  array[1], 'The same idempotency key is never queued twice');

-- 2. Nobody but the worker functions touches the queue (3-7)
set local role engage_app;
select throws_ok('select * from app_private.jobs', '42501', null, 'Staff role cannot read jobs');
reset role;
set local role engage_widget;
select throws_ok('select * from app_private.jobs', '42501', null, 'Widget role cannot read jobs');
select throws_ok('select * from app_private.claim_jobs(10)', '42501', null, 'Widget role cannot claim jobs');
reset role;
set local role authenticated;
select throws_ok($$select app_private.enqueue_job('handover_alert', null, '{}', 'x')$$, '42501', null,
  'Data API role cannot enqueue jobs');
reset role;
set local role engage_jobs;
select throws_ok('select * from app_private.jobs', '42501', null, 'Worker role has no direct table access');

-- 3. Claiming with leases (8-11)
select results_eq('select count(*)::int from app_private.claim_jobs(10)', array[2], 'Worker claims due jobs');
select is_empty('select 1 from app_private.claim_jobs(10)', 'Leased jobs are not claimed twice');
reset role;
update app_private.jobs set locked_until = now() - interval '1 second'
  where idempotency_key = 'handover_alert/60000000-0000-4000-8000-0000000000c1';
set local role engage_jobs;
select results_eq('select idempotency_key from app_private.claim_jobs(10)',
  array['handover_alert/60000000-0000-4000-8000-0000000000c1'], 'An expired lease is re-claimed (crashed worker)');
select results_eq($$select attempts from app_private.claim_jobs(10)$$, array[]::int[],
  'Nothing else is due');
reset role;

-- 4. Retry, dead letter, completion (12-17)
create function pg_temp.job(p_key text) returns bigint language sql security definer as
  $$ select id from app_private.jobs where idempotency_key = p_key $$;
grant execute on function pg_temp.job(text) to engage_jobs;
set local role engage_jobs;
select is(app_private.fail_job(pg_temp.job('handover_alert/60000000-0000-4000-8000-0000000000a1'), 'resend http_503', false),
  'queued', 'A temporary failure is retried');
reset role;
select ok((select run_at > now() + interval '20 seconds' from app_private.jobs
    where idempotency_key = 'handover_alert/60000000-0000-4000-8000-0000000000a1'),
  'Retries back off');
set local role engage_jobs;
select is(app_private.fail_job(pg_temp.job('handover_alert/60000000-0000-4000-8000-0000000000c1'), 'resend http_422', true),
  'dead', 'A permanent failure goes straight to the dead letters');
reset role;
select app_private.enqueue_job('domain_lapsed', '10000000-0000-4000-8000-00000000000a', '{}', 'old-job');
update app_private.jobs set created_at = now() - interval '24 hours', status = 'running',
  locked_until = now() + interval '1 minute' where idempotency_key = 'old-job';
set local role engage_jobs;
select is(app_private.fail_job(pg_temp.job('old-job'), 'timeout', false), 'dead',
  'No retry after 23 hours (outside the email idempotency window)');
reset role;
select app_private.enqueue_job('domain_lapsed', '10000000-0000-4000-8000-00000000000a', '{}', 'done-job');
update app_private.jobs set status = 'running' where idempotency_key = 'done-job';
set local role engage_jobs;
select app_private.complete_job(pg_temp.job('done-job'), '{"message_id": "m1"}');
reset role;
select results_eq($$select status, result->>'message_id' from app_private.jobs where idempotency_key = 'done-job'$$,
  $$values ('done'::text, 'm1'::text)$$, 'Completion stores the provider message id');
update app_private.jobs set finished_at = now() - interval '31 days' where idempotency_key = 'done-job';
set local role engage_jobs;
select is(app_private.purge_finished_jobs(), 1, 'Finished jobs are purged after 30 days');

-- 5. Email data is re-checked at send time and never includes patient details (18-22)
select results_eq($$select clinic, status from app_private.job_handover_alert('60000000-0000-4000-8000-0000000000a1')$$,
  $$values ('Clinic A'::text, 'new'::text)$$, 'Handover alert data: clinic and status only');
select is_empty($$select 1 from app_private.job_handover_alert('60000000-0000-4000-8000-0000000000c1')$$,
  'No alert for a suspended clinic');
select results_eq($$select email from app_private.job_recipients('10000000-0000-4000-8000-00000000000a',
    array['owner', 'admin', 'receptionist']::public.membership_role[]) order by email$$,
  array['a.admin@test.invalid', 'a.owner@test.invalid', 'a.receptionist@test.invalid'],
  'Front-desk recipients: active members only, no viewers');
select results_eq($$select email from app_private.job_recipients('10000000-0000-4000-8000-00000000000a',
    array['owner', 'admin']::public.membership_role[]) order by email$$,
  array['a.admin@test.invalid', 'a.owner@test.invalid'], 'Owner/admin recipients');
select is_empty($$select 1 from app_private.job_recipients('10000000-0000-4000-8000-00000000000c',
    array['owner']::public.membership_role[])$$, 'No recipients for a suspended clinic');
reset role;

-- 6. Domain lapse enqueues an owner alert (23-24)
insert into public.tenant_domains (id, tenant_id, hostname) values
  ('50000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'www.a.example.com');
update public.tenant_domains set verification_status = 'verified' where id = '50000000-0000-4000-8000-0000000000a1';
set local role engage_jobs;
select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found',
  'job:reverify_domains:00000000-0000-4000-8000-000000000001', 1);
reset role;
select results_eq($$select kind from app_private.jobs where payload->>'domain_id' = '50000000-0000-4000-8000-0000000000a1'$$,
  array['domain_lapsed'], 'A lapsed domain enqueues an owner alert');
set local role engage_jobs;
select results_eq($$select hostname, still_lapsed from app_private.job_domain_lapsed('50000000-0000-4000-8000-0000000000a1')$$,
  $$values ('www.a.example.com'::text, true)$$, 'Domain alert data re-checked at send time');
reset role;

select * from finish();
rollback;
