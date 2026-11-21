-- Phase 2b domain registration/verification: isolation, roles and invariants (pgTAP).
-- Run: npm run db:test   (requires local Supabase: npm run db:start)
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(26);

grant engage_app to postgres with inherit false, set true;
grant usage on schema extensions to engage_app;

create function pg_temp.login(p_email text, p_aal text default 'aal1')
returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', p_aal)::text, true);
end;
$$;
grant execute on function pg_temp.login(text, text) to engage_app, authenticated, anon;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000c1', 's.owner@test.invalid');

insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');

insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner'),
  ('10000000-0000-4000-8000-00000000000c', '00000000-0000-4000-8000-0000000000c1', 'owner');

insert into public.tenant_domains (id, tenant_id, hostname) values
  ('50000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', 'www.clinic-b.example.com'),
  ('50000000-0000-4000-8000-0000000000c1', '10000000-0000-4000-8000-00000000000c', 'clinic-s.example.com');
-- Tenant B has proven DNS control of its hostname.
update public.tenant_domains set verification_status = 'verified'
  where id = '50000000-0000-4000-8000-0000000000b1';

-- 1. Data API roles (1-2)
set local role anon;
select throws_ok('select * from public.tenant_domains', '42501', null, 'anon: domains denied');
reset role;
select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.tenant_domains', '42501', null, 'Data API (authenticated): domains denied');
reset role;

-- 2. Owner A: create, server-owned fields, isolation (3-16)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'www.clinic-a.example.com')$$, 'A owner can claim a hostname');
select results_eq($$select verification_status, verification_token ~ '^[0-9a-f]{64}$', created_by
    from public.tenant_domains where hostname = 'www.clinic-a.example.com'$$,
  $$values ('pending', true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'New claim is pending with a server-generated 256-bit token');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname, verification_token)
    values ('10000000-0000-4000-8000-00000000000a', 'x.clinic-a.example.com', repeat('0', 64))$$,
  '42501', null, 'Client cannot choose the verification token');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname, verification_status)
    values ('10000000-0000-4000-8000-00000000000a', 'y.clinic-a.example.com', 'verified')$$,
  '42501', null, 'Client cannot insert a domain as verified');
select throws_ok($$update public.tenant_domains set verification_token = repeat('1', 64)
    where hostname = 'www.clinic-a.example.com'$$,
  '42501', null, 'Token cannot be changed');
select throws_ok($$update public.tenant_domains set hostname = 'evil.example.com'
    where hostname = 'www.clinic-a.example.com'$$,
  '42501', null, 'Hostname cannot be changed');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'www.clinic-a.example.com')$$,
  '23505', null, 'Duplicate active claim in the same tenant is rejected');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'Not A Host')$$,
  '23514', null, 'Malformed hostnames are rejected by the database');
select lives_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'www.clinic-b.example.com')$$,
  'Another tenant may also CLAIM a hostname (squatting does not block the owner)');
select results_eq('select count(*)::int from public.tenant_domains', array[2],
  'A owner sees only Tenant A domains');
select is_empty($$select 1 from public.tenant_domains where id = '50000000-0000-4000-8000-0000000000b1'$$,
  'A owner cannot read a B domain by guessed UUID');
select results_eq($$with u as (update public.tenant_domains set removed_at = now()
    where id = '50000000-0000-4000-8000-0000000000b1' returning 1) select count(*)::int from u$$,
  array[0], 'A owner cannot remove a B domain');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000b', 'evil.example.com')$$,
  '42501', null, 'A owner cannot add domains to Tenant B');
select throws_ok($$delete from public.tenant_domains$$, '42501', null, 'Domains cannot be deleted');

-- 3. Verification and removal invariants (17-22)
update public.tenant_domains set verification_status = 'verified', last_check_result = 'verified'
  where hostname = 'www.clinic-a.example.com';
select results_eq($$select verified_at = now() from public.tenant_domains where hostname = 'www.clinic-a.example.com'$$,
  array[true], 'verified_at is set by the server');
select throws_ok($$update public.tenant_domains set verification_status = 'verified'
    where tenant_id = '10000000-0000-4000-8000-00000000000a' and hostname = 'www.clinic-b.example.com'$$,
  '23505', null, 'A hostname can be verified by only one tenant at a time (B''s claim is not affected)');
update public.tenant_domains set removed_at = now() - interval '5 years'
  where hostname = 'www.clinic-a.example.com';
select results_eq($$select removed_at = now(), removed_by, verification_status, verified_at is null
    from public.tenant_domains where hostname = 'www.clinic-a.example.com'$$,
  $$values (true, '00000000-0000-4000-8000-0000000000a1'::uuid, 'pending', true)$$,
  'Removal is server-stamped and drops verification');
select throws_ok($$update public.tenant_domains set verification_status = 'verified'
    where hostname = 'www.clinic-a.example.com'$$,
  '23514', null, 'Removed domains are frozen');
select lives_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'www.clinic-a.example.com')$$,
  'A removed hostname can be claimed again');
select results_eq($$select count(distinct verification_token)::int from public.tenant_domains
    where hostname = 'www.clinic-a.example.com'$$,
  array[2], 'A new claim gets a new token');
reset role;

-- 4. Other roles and tenant states (23-26)
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.tenant_domains', array[3],
  'Receptionist can read own clinic domains');
select throws_ok($$insert into public.tenant_domains (tenant_id, hostname)
    values ('10000000-0000-4000-8000-00000000000a', 'r.clinic-a.example.com')$$,
  '42501', null, 'Receptionist cannot add domains');
reset role;

select pg_temp.login('s.owner@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.tenant_domains', 'Suspended tenant owner cannot read domains');
select results_eq($$with u as (update public.tenant_domains set removed_at = now() returning 1)
    select count(*)::int from u$$, array[0], 'Suspended tenant owner cannot change domains');
reset role;

select * from finish();
rollback;
