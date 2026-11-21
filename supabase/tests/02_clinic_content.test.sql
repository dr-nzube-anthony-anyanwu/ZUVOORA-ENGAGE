-- Phase 2a clinic content: tenant isolation, roles and the draft/publish invariants (pgTAP).
-- Run: npm run db:test   (requires local Supabase: npm run db:start)
-- All data is synthetic and rolled back at the end.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(44);

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

-- ---------------------------------------------------------------------------------------------
-- Fixtures (as postgres)
-- ---------------------------------------------------------------------------------------------
insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-000000000001', 'platform.admin@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a5', 'a.revoked@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000c1', 's.owner@test.invalid');

insert into public.platform_admins (user_id) values ('00000000-0000-4000-8000-000000000001');

insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');

insert into public.tenant_memberships (tenant_id, user_id, role, is_active, revoked_at) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer', true, null),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a5', 'admin', false, now()),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner', true, null),
  ('10000000-0000-4000-8000-00000000000c', '00000000-0000-4000-8000-0000000000c1', 'owner', true, null);

insert into public.clinic_profiles (tenant_id, draft) values
  ('10000000-0000-4000-8000-00000000000a', '{"description": "Clinic A"}'),
  ('10000000-0000-4000-8000-00000000000b', '{"description": "Clinic B"}');

insert into public.faqs (id, tenant_id, draft) values
  ('20000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', '{"question": "A1?", "answer": "a"}'),
  ('20000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', '{"question": "A2?", "answer": "a"}'),
  ('20000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', '{"question": "B1?", "answer": "b"}'),
  ('20000000-0000-4000-8000-0000000000c1', '10000000-0000-4000-8000-00000000000c', '{"question": "S1?", "answer": "s"}');
insert into public.services (id, tenant_id, draft) values
  ('30000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', '{"name": "B service"}');
insert into public.branches (id, tenant_id, draft) values
  ('40000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', '{"name": "B branch"}');

-- ---------------------------------------------------------------------------------------------
-- 1. Anonymous and Supabase Data API roles have no access (1-7)
-- ---------------------------------------------------------------------------------------------
set local role anon;
select throws_ok('select * from public.faqs', '42501', null, 'anon: faqs denied');
select throws_ok('select * from public.services', '42501', null, 'anon: services denied');
select throws_ok('select * from public.branches', '42501', null, 'anon: branches denied');
reset role;

select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.faqs', '42501', null, 'Data API (authenticated): faqs denied');
select throws_ok('select * from public.services', '42501', null, 'Data API (authenticated): services denied');
select throws_ok('select * from public.branches', '42501', null, 'Data API (authenticated): branches denied');
reset role;
set local role service_role;
select throws_ok('select * from public.faqs', '42501', null, 'Data API (service_role): faqs denied');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 2. Cross-tenant isolation for the Tenant A owner (8-14)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.faqs', array[2], 'A owner sees only the 2 Tenant A FAQs');
select is_empty($$select 1 from public.faqs where id = '20000000-0000-4000-8000-0000000000b1'$$,
  'A owner cannot read a B FAQ by guessed UUID');
select is_empty('select 1 from public.services', 'A owner cannot see B services');
select is_empty('select 1 from public.branches', 'A owner cannot see B branches');
select results_eq($$with u as (update public.faqs set draft = '{"question": "pwned"}'
    where id = '20000000-0000-4000-8000-0000000000b1' returning 1) select count(*)::int from u$$,
  array[0], 'A owner cannot edit a B FAQ');
select throws_ok($$insert into public.faqs (tenant_id, draft)
    values ('10000000-0000-4000-8000-00000000000b', '{"question": "x"}')$$,
  '42501', null, 'A owner cannot create content in Tenant B');
select is_empty($$select 1 from public.clinic_profiles where tenant_id = '10000000-0000-4000-8000-00000000000b'$$,
  'A owner cannot read the B profile');

-- ---------------------------------------------------------------------------------------------
-- 3. Column privileges: bookkeeping is server-controlled (15-21)
-- ---------------------------------------------------------------------------------------------
select throws_ok($$insert into public.faqs (tenant_id, draft, published)
    values ('10000000-0000-4000-8000-00000000000a', '{"q": 1}', '{"q": 1}')$$,
  '42501', null, 'Cannot insert content as already published');
select throws_ok($$update public.faqs set tenant_id = '10000000-0000-4000-8000-00000000000b'
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '42501', null, 'Cannot move content to another tenant');
select throws_ok($$update public.faqs set revision = 99 where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '42501', null, 'Cannot set revision directly');
select throws_ok($$update public.faqs set published_by = '00000000-0000-4000-8000-0000000000b1'
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '42501', null, 'Cannot spoof published_by');
select throws_ok($$delete from public.faqs where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '42501', null, 'Content cannot be deleted (archive instead)');
select throws_ok($$update public.clinic_profiles set published_at = now()
    where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  '42501', null, 'Cannot set profile published_at directly');
select throws_ok($$insert into public.services (id, tenant_id, draft)
    values ('30000000-0000-4000-8000-0000000000a9', '10000000-0000-4000-8000-00000000000a', '{}')$$,
  '42501', null, 'Cannot choose content ids');

-- ---------------------------------------------------------------------------------------------
-- 4. Draft/publish lifecycle (22-33)
-- ---------------------------------------------------------------------------------------------
select lives_ok($$insert into public.faqs (tenant_id, draft)
    values ('10000000-0000-4000-8000-00000000000a', '{"question": "New?", "answer": "n"}')$$,
  'A owner can create a FAQ');
select results_eq($$select revision, published is null, created_by from public.faqs where draft->>'question' = 'New?'$$,
  $$values (1, true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'New content starts at revision 1, unpublished, created_by = caller');
update public.faqs set draft = '{"question": "A1 edited?", "answer": "a"}'
  where id = '20000000-0000-4000-8000-0000000000a1';
select results_eq($$select revision from public.faqs where id = '20000000-0000-4000-8000-0000000000a1'$$,
  array[2], 'Editing the draft increments revision');
update public.faqs set published = draft where id = '20000000-0000-4000-8000-0000000000a1';
select results_eq($$select published_revision, published_by, published->>'question' from public.faqs
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  $$values (2, '00000000-0000-4000-8000-0000000000a1'::uuid, 'A1 edited?')$$,
  'Publishing stamps revision and publisher');
update public.faqs set draft = '{"question": "A1 draft v3?", "answer": "a"}'
  where id = '20000000-0000-4000-8000-0000000000a1';
select results_eq($$select revision, published_revision, published->>'question' from public.faqs
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  $$values (3, 2, 'A1 edited?')$$,
  'Editing after publish keeps the published copy live and unchanged');
select throws_ok($$update public.faqs set published = '{"question": "never reviewed"}'
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'Only the current draft can be published');
update public.faqs set archived_at = now() where id = '20000000-0000-4000-8000-0000000000a1';
select results_eq($$select published is null, archived_by from public.faqs where id = '20000000-0000-4000-8000-0000000000a1'$$,
  $$values (true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'Archiving unpublishes and records who archived');
select throws_ok($$update public.faqs set published = draft where id = '20000000-0000-4000-8000-0000000000a1'$$,
  '23514', null, 'Archived content cannot be published');
update public.faqs set archived_at = null where id = '20000000-0000-4000-8000-0000000000a1';
select results_eq($$select archived_at is null, archived_by is null, published is null from public.faqs
    where id = '20000000-0000-4000-8000-0000000000a1'$$,
  $$values (true, true, true)$$, 'Restoring un-archives but does not republish');
update public.clinic_profiles set published = draft where tenant_id = '10000000-0000-4000-8000-00000000000a';
select results_eq($$select published->>'description', published_revision from public.clinic_profiles
    where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  $$values ('Clinic A', 1)$$, 'Owner can publish the clinic profile');
update public.faqs set published = draft where id = '20000000-0000-4000-8000-0000000000a2';
update public.faqs set published = null where id = '20000000-0000-4000-8000-0000000000a2';
select results_eq($$select published_at is null and published_by is null and published_revision is null
    from public.faqs where id = '20000000-0000-4000-8000-0000000000a2'$$,
  array[true], 'Unpublishing clears publication metadata');
update public.faqs set archived_at = now() - interval '1 year'
  where id = '20000000-0000-4000-8000-0000000000a2';
select results_eq($$select archived_at = now() from public.faqs where id = '20000000-0000-4000-8000-0000000000a2'$$,
  array[true], 'Archive time is set by the server (client value ignored)');
reset role;

-- ---------------------------------------------------------------------------------------------
-- 5. Read-only roles, revoked members, suspended tenants, platform admins (34-44)
-- ---------------------------------------------------------------------------------------------
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.faqs', array[3], 'Receptionist can read own clinic FAQs');
select throws_ok($$insert into public.faqs (tenant_id, draft) values ('10000000-0000-4000-8000-00000000000a', '{"q": 1}')$$,
  '42501', null, 'Receptionist cannot create FAQs');
select results_eq($$with u as (update public.faqs set draft = '{"q": "x"}' returning 1) select count(*)::int from u$$,
  array[0], 'Receptionist cannot edit FAQs');
select results_eq($$with u as (update public.faqs set published = draft returning 1) select count(*)::int from u$$,
  array[0], 'Receptionist cannot publish FAQs');
reset role;

select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.clinic_profiles set draft = '{"x": 1}' returning 1) select count(*)::int from u$$,
  array[0], 'Viewer cannot edit the clinic profile');
reset role;

select pg_temp.login('a.revoked@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.faqs', 'Revoked member cannot read FAQs');
reset role;

select pg_temp.login('s.owner@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.faqs', 'Suspended tenant owner cannot read FAQs');
select throws_ok($$insert into public.faqs (tenant_id, draft) values ('10000000-0000-4000-8000-00000000000c', '{"q": 1}')$$,
  '42501', null, 'Suspended tenant owner cannot create FAQs');
reset role;

select pg_temp.login('platform.admin@test.invalid', 'aal1');
set local role engage_app;
select is_empty('select 1 from public.faqs', 'Platform admin without MFA sees no FAQs');
reset role;

select pg_temp.login('platform.admin@test.invalid', 'aal2');
set local role engage_app;
select results_eq('select count(*)::int from public.faqs', array[5], 'MFA platform admin sees all tenants (support)');
reset role;

select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select results_eq($$select count(*)::int from public.faqs where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  array[0], 'Tenant B owner cannot see any Tenant A FAQs');
reset role;

select * from finish();
rollback;
