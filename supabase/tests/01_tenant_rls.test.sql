-- Phase 1 tenant isolation, RBAC and audit negative/positive tests (pgTAP).
-- Run: npm run db:test   (requires local Supabase: npm run db:start)
-- All data is synthetic and rolled back at the end.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(57);

-- Allow the test session (postgres) to impersonate the backend role; rolled back at the end.
grant engage_app to postgres with inherit false, set true;
-- pgTAP lives in `extensions`; the bare engage_app role needs it only inside this test.
grant usage on schema extensions to engage_app;

-- ---------------------------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------------------------
-- Fixtures (as postgres): tenants A, B (active), S (suspended)
-- ---------------------------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-000000000001', 'platform.admin@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a2', 'a.admin@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a5', 'a.revoked@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000c1', 's.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000d1', 'outsider@test.invalid');

insert into public.platform_admins (user_id) values ('00000000-0000-4000-8000-000000000001');

insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');

insert into public.clinic_profiles (tenant_id, draft) values
  ('10000000-0000-4000-8000-00000000000a', '{"public_phone": "+234-000-000-0001"}'),
  ('10000000-0000-4000-8000-00000000000b', '{"public_phone": "+234-000-000-0002"}'),
  ('10000000-0000-4000-8000-00000000000c', '{"public_phone": "+234-000-000-0003"}');

insert into public.tenant_memberships (tenant_id, user_id, role, is_active, revoked_at) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a2', 'admin', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a5', 'admin', false, now()),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner', true, null),
  ('10000000-0000-4000-8000-00000000000c', '00000000-0000-4000-8000-0000000000c1', 'owner', true, null);

insert into public.audit_events (actor_user_id, tenant_id, action)
values ('00000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'test.seeded');

-- ---------------------------------------------------------------------------------------------
-- 1. Anonymous users cannot read private tables (1-6)
-- ---------------------------------------------------------------------------------------------
set local role anon;
select throws_ok('select * from public.tenants', '42501', null, 'anon: tenants denied');
select throws_ok('select * from public.tenant_memberships', '42501', null, 'anon: memberships denied');
select throws_ok('select * from public.clinic_profiles', '42501', null, 'anon: clinic_profiles denied');
select throws_ok('select * from public.tenant_domains', '42501', null, 'anon: tenant_domains denied');
select throws_ok('select * from public.platform_admins', '42501', null, 'anon: platform_admins denied');
select throws_ok('select * from public.audit_events', '42501', null, 'anon: audit_events denied');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 1b. Supabase Data API roles have no access, even with a valid owner session (ADR-016)
--     PostgREST runs requests as `authenticated`; only the backend's engage_app role is granted.
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.tenants', '42501', null, 'Data API (authenticated): tenants denied');
select throws_ok('select * from public.tenant_memberships', '42501', null, 'Data API (authenticated): memberships denied');
select throws_ok('select * from public.clinic_profiles', '42501', null, 'Data API (authenticated): clinic_profiles denied');
select throws_ok($$insert into public.audit_events (actor_user_id, tenant_id, action)
    values ('00000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'bypass.attempt')$$,
  '42501', null, 'Data API (authenticated): cannot write audit events directly');
select throws_ok($$select app_private.tenant_role('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'Data API (authenticated): cannot call security helpers');
reset role;
set local role service_role;
select throws_ok('select * from public.tenants', '42501', null, 'Data API (service_role key): tenants denied');
select throws_ok('select * from public.audit_events', '42501', null, 'Data API (service_role key): audit_events denied');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 2. Tenant A cannot read/update Tenant B (7-13)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq('select id from public.tenants',
  $$values ('10000000-0000-4000-8000-00000000000a'::uuid)$$, 'A owner sees only tenant A');
select is_empty($$select 1 from public.clinic_profiles where tenant_id = '10000000-0000-4000-8000-00000000000b'$$,
  'A owner cannot read B clinic profile (guessed UUID)');
select is_empty($$select 1 from public.tenant_memberships where tenant_id = '10000000-0000-4000-8000-00000000000b'$$,
  'A owner cannot read B memberships');
select results_eq($$with u as (update public.clinic_profiles set draft = '{"public_phone": "pwned"}'
    where tenant_id = '10000000-0000-4000-8000-00000000000b' returning 1) select count(*)::int from u$$,
  array[0], 'A owner cannot update B clinic profile');
select throws_ok($$insert into public.tenant_memberships (tenant_id, user_id, role)
    values ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000d1', 'owner')$$,
  '42501', null, 'A owner cannot add members to B');
-- Browser-supplied tenant_id spoofing: writing an event/row claiming tenant B is rejected.
select throws_ok($$insert into public.audit_events (actor_user_id, tenant_id, action)
    values ('00000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000b', 'spoof.attempt')$$,
  '42501', null, 'Supplied tenant_id B does not grant access to B');
select throws_ok($$update public.tenant_memberships set tenant_id = '10000000-0000-4000-8000-00000000000b'
    where user_id = '00000000-0000-4000-8000-0000000000a3'$$,
  '42501', null, 'Membership tenant_id is immutable (cannot move a member into B)');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 3. Role restrictions (14-24)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq($$select count(*)::int from public.clinic_profiles where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  array[1], 'Receptionist can read own clinic profile');
select results_eq($$with u as (update public.clinic_profiles set draft = '{"public_phone": "x"}'
    where tenant_id = '10000000-0000-4000-8000-00000000000a' returning 1) select count(*)::int from u$$,
  array[0], 'Receptionist cannot update clinic profile');
select throws_ok($$insert into public.tenant_memberships (tenant_id, user_id, role)
    values ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000d1', 'viewer')$$,
  '42501', null, 'Receptionist cannot add members');
select throws_ok($$insert into public.tenants (legal_name, display_name) values ('Rogue Ltd', 'Rogue')$$,
  '42501', null, 'Receptionist cannot create tenants (platform action)');
select is_empty('select 1 from public.audit_events', 'Receptionist cannot read audit log');
reset role;

select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.tenant_memberships set role = 'admin'
    where user_id = '00000000-0000-4000-8000-0000000000a4' returning 1) select count(*)::int from u$$,
  array[0], 'Viewer cannot escalate own role');
reset role;

select pg_temp.login('a.admin@test.invalid');
set local role engage_app;
select throws_ok($$insert into public.tenant_memberships (tenant_id, user_id, role)
    values ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000d1', 'owner')$$,
  '42501', null, 'Admin cannot grant owner role');
select results_eq($$with u as (update public.tenant_memberships set role = 'viewer'
    where user_id = '00000000-0000-4000-8000-0000000000a1' returning 1) select count(*)::int from u$$,
  array[0], 'Admin cannot demote an owner');
select lives_ok($$insert into public.tenant_memberships (tenant_id, user_id, role, invited_by)
    values ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000d1', 'receptionist',
            '00000000-0000-4000-8000-0000000000a2')$$,
  'Admin can add a receptionist (positive control)');
reset role;

select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.clinic_profiles set draft = '{"public_phone": "+234-000-000-0099"}'
    where tenant_id = '10000000-0000-4000-8000-00000000000a' returning 1) select count(*)::int from u$$,
  array[1], 'Owner can update own clinic profile (positive control)');
select results_eq($$with u as (update public.tenants set status = 'active'
    where id = '10000000-0000-4000-8000-00000000000a' returning 1) select count(*)::int from u$$,
  array[0], 'Owner cannot change tenant status (platform action)');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 4. Platform admin requires active row AND MFA (25-29)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('platform.admin@test.invalid', 'aal1');
set local role engage_app;
select throws_ok($$insert into public.tenants (legal_name, display_name) values ('No MFA Ltd', 'No MFA')$$,
  '42501', null, 'Platform admin without MFA (aal1) cannot create tenants');
select is_empty('select 1 from public.tenants', 'Platform admin without MFA sees no tenants');
reset role;

select pg_temp.login('platform.admin@test.invalid', 'aal2');
set local role engage_app;
select lives_ok($$insert into public.tenants (id, legal_name, display_name)
    values ('10000000-0000-4000-8000-0000000000ee', 'New Clinic Ltd', 'New Clinic')$$,
  'Platform admin with MFA can create a tenant');
select results_eq($$with u as (update public.tenants set status = 'suspended'
    where id = '10000000-0000-4000-8000-0000000000ee' returning 1) select count(*)::int from u$$,
  array[1], 'Platform admin with MFA can suspend a tenant');
reset role;

select pg_temp.login('outsider@test.invalid', 'aal2');
set local role engage_app;
select throws_ok($$insert into public.tenants (legal_name, display_name) values ('Fake Admin Ltd', 'Fake')$$,
  '42501', null, 'MFA alone (without platform_admins row) grants no platform powers');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 5. Revoked membership loses access (30-34)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.revoked@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.tenants', 'Revoked member sees no tenants');
select is_empty('select 1 from public.clinic_profiles', 'Revoked member cannot read clinic profile');
reset role;

-- Live revocation by the owner takes effect immediately.
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.tenant_memberships set is_active = false, revoked_at = now(),
    revoked_by = '00000000-0000-4000-8000-0000000000a1'
    where user_id = '00000000-0000-4000-8000-0000000000a4' returning 1) select count(*)::int from u$$,
  array[1], 'Owner can revoke a viewer');
reset role;

select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.tenants', 'Just-revoked viewer immediately sees no tenants');
select results_eq('select count(*)::int from public.tenant_memberships', array[1],
  'Revoked user still sees only their own (inactive) membership row');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 6. Suspended tenant is blocked (35-37)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('s.owner@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.tenants', 'Suspended tenant owner sees no tenants');
select is_empty('select 1 from public.clinic_profiles', 'Suspended tenant owner cannot read profile');
select results_eq($$with u as (update public.clinic_profiles set draft = '{"public_phone": "x"}'
    where tenant_id = '10000000-0000-4000-8000-00000000000c' returning 1) select count(*)::int from u$$,
  array[0], 'Suspended tenant owner cannot update profile');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 7. Audit log integrity (38-44)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.audit_events (actor_user_id, tenant_id, action)
    values ('00000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'membership.revoked')$$,
  'Owner can record an audit event as themselves');
select throws_ok($$insert into public.audit_events (actor_user_id, tenant_id, action)
    values ('00000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', 'forged.event')$$,
  '42501', null, 'Cannot write audit events as another user');
select throws_ok($$update public.audit_events set action = 'tampered.event'$$,
  '42501', null, 'Authenticated users cannot update audit events');
select throws_ok($$delete from public.audit_events$$,
  '42501', null, 'Authenticated users cannot delete audit events');
select results_eq('select count(*)::int from public.audit_events', array[2],
  'Owner reads only tenant A audit events');
reset role;

select throws_ok($$update public.audit_events set action = 'tampered.event'$$,
  '42501', null, 'Even the table owner cannot update audit events (trigger)');
select throws_ok($$delete from public.audit_events$$,
  '42501', null, 'Even the table owner cannot delete audit events (trigger)');

-- ---------------------------------------------------------------------------------------------
-- 8. Ownership and platform-admin visibility (45-46)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select throws_ok($$update public.tenant_memberships set role = 'admin'
    where user_id = '00000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'Last active owner cannot demote themselves');
select is_empty('select 1 from public.platform_admins', 'Non-admin cannot list platform admins');
select is(app_private.find_user_id_for_invite('10000000-0000-4000-8000-00000000000a', 'B.OWNER@test.invalid'),
  '00000000-0000-4000-8000-0000000000b1'::uuid, 'Owner can resolve an invitee by email (case-insensitive)');
reset role;

select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select throws_ok($$select app_private.find_user_id_for_invite('10000000-0000-4000-8000-00000000000a', 'b.owner@test.invalid')$$,
  '42501', null, 'Receptionist cannot use the invite lookup (no email enumeration)');
select throws_ok($$select * from app_private.tenant_member_directory('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'Receptionist cannot list member emails');
reset role;

select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select throws_ok($$select * from app_private.tenant_member_directory('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'Tenant B owner cannot list Tenant A member emails');
reset role;

select * from finish();
rollback;
