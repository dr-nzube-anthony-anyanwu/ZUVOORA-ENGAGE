-- Phase 3f domain re-verification: who can run it, what counts as failure, lapse and audit (pgTAP).
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(17);

grant engage_app to postgres with inherit false, set true;
grant engage_jobs to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_jobs, engage_widget;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner');
insert into public.tenant_domains (id, tenant_id, hostname) values
  ('50000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'www.a-verified.example.com'),
  ('50000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', 'www.a-pending.example.com'),
  ('50000000-0000-4000-8000-0000000000a3', '10000000-0000-4000-8000-00000000000a', 'www.a-fresh.example.com'),
  ('50000000-0000-4000-8000-0000000000c1', '10000000-0000-4000-8000-00000000000c', 'www.s-verified.example.com');
update public.tenant_domains set verification_status = 'verified'
  where id in ('50000000-0000-4000-8000-0000000000a1', '50000000-0000-4000-8000-0000000000a3',
               '50000000-0000-4000-8000-0000000000c1');
-- a3 was checked an hour ago: not due yet.
update public.tenant_domains set last_checked_at = now() - interval '1 hour'
  where id = '50000000-0000-4000-8000-0000000000a3';

-- 1. Only the jobs role can run it (1-4)
set local role engage_app;
select throws_ok('select * from app_private.domains_due_for_recheck(10)', '42501', null,
  'Staff role cannot list domains for re-checking');
reset role;
set local role engage_widget;
select throws_ok($$select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found', 'job:reverify_domains:00000000-0000-4000-8000-000000000001')$$,
  '42501', null, 'Widget role cannot record re-checks');
reset role;
set local role authenticated;
select throws_ok('select * from app_private.domains_due_for_recheck(10)', '42501', null,
  'Data API role cannot list domains');
reset role;
set local role engage_jobs;
select throws_ok('select * from public.tenant_domains', '42501', null,
  'Jobs role has no direct table access');

-- 2. What is due (5)
select results_eq('select hostname from app_private.domains_due_for_recheck(10)',
  array['www.a-verified.example.com'],
  'Due: verified, unchecked, active clinic only (not pending, recently checked or suspended)');

-- 3. Counting (6-9)
select is(app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found', 'job:reverify_domains:00000000-0000-4000-8000-000000000001'), 'verified',
  'One failure keeps the domain verified');
select is(app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'dns_error', 'job:reverify_domains:00000000-0000-4000-8000-000000000001'), 'verified',
  'Resolver errors are recorded but do not count');
select is(app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'verified', 'job:reverify_domains:00000000-0000-4000-8000-000000000001'), 'verified',
  'A good check clears the failure count');
select throws_ok($$select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'bogus', 'job:reverify_domains:00000000-0000-4000-8000-000000000001')$$,
  '23514', null, 'Unknown results are rejected');
reset role;
select is((select recheck_failures from public.tenant_domains where id = '50000000-0000-4000-8000-0000000000a1'), 0,
  'Failure count reset after a good check (10)');

-- 4. Lapse after 3 consecutive definite failures (11-14)
set local role engage_jobs;
select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found', 'job:reverify_domains:00000000-0000-4000-8000-000000000001');
select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'mismatch', 'job:reverify_domains:00000000-0000-4000-8000-000000000001');
select is(app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found', 'job:reverify_domains:00000000-0000-4000-8000-000000000001'), 'pending',
  'Third consecutive failure lapses the domain');
select is(app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a1', 'not_found', 'job:reverify_domains:00000000-0000-4000-8000-000000000001'), null,
  'A lapsed domain is no longer re-checked');
reset role;
select results_eq($$select verification_status, verified_at is null from public.tenant_domains
    where id = '50000000-0000-4000-8000-0000000000a1'$$,
  $$values ('pending'::text, true)$$, 'Lapsed domain is pending with no verified time');
select results_eq($$select actor_user_id, action, metadata->>'failures', request_id from public.audit_events
    where target_id = '50000000-0000-4000-8000-0000000000a1'$$,
  $$values ('00000000-0000-0000-0000-000000000000'::uuid, 'domain.verification_lapsed', '3', 'job:reverify_domains:00000000-0000-4000-8000-000000000001')$$,
  'Lapse is audited with the system actor and the job run id');
select throws_ok($$select app_private.record_domain_recheck('50000000-0000-4000-8000-0000000000a3', 'verified', null)$$,
  '23514', null, 'A job run id is required (17)');

-- 5. The widget stops on a lapsed host; re-verifying starts clean (15-16)
update public.widget_configs set public_key = repeat('a', 32), enabled = true
  where tenant_id = '10000000-0000-4000-8000-00000000000a';
set local role engage_widget;
select is_empty($$select 1 from app_private.resolve_widget(repeat('a', 32), 'www.a-verified.example.com')$$,
  'The widget is no longer served on a lapsed host');
reset role;

select set_config('request.jwt.claims',
  json_build_object('sub', '00000000-0000-4000-8000-0000000000a1', 'role', 'authenticated', 'aal', 'aal1')::text, true);
set local role engage_app;
update public.tenant_domains set verification_status = 'verified'
  where id = '50000000-0000-4000-8000-0000000000a1';
reset role;
select is((select recheck_failures from public.tenant_domains where id = '50000000-0000-4000-8000-0000000000a1'), 0,
  'Re-verification by the owner resets the failure count');

select * from finish();
rollback;
