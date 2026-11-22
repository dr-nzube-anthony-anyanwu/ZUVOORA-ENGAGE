-- Phase 3e inbox privacy: patient message text and contact details only for the clinic's front
-- desk; viewers and platform admins see conversation metadata only (pgTAP).
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(14);

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
grant execute on function pg_temp.login(text, text) to engage_app, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a2', 'a.admin@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000f1', 'platform.admin@test.invalid');
insert into public.platform_admins (user_id) values ('00000000-0000-4000-8000-0000000000f1');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a2', 'admin'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner');

insert into public.conversations (id, tenant_id, status) values
  ('40000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'handover_requested'),
  ('40000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', 'open');
insert into public.messages (tenant_id, conversation_id, role, content) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'A patient question'),
  ('10000000-0000-4000-8000-00000000000b', '40000000-0000-4000-8000-0000000000b1', 'visitor', 'B patient question');
insert into public.handover_requests (tenant_id, conversation_id, contact_phone, consent_given) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', '+234 801 000 0001', true);

-- 1. Front desk reads content (1-3)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq('select content from public.messages', array['A patient question'],
  'Owner reads own clinic''s messages only');
reset role;
select pg_temp.login('a.admin@test.invalid');
set local role engage_app;
select results_eq('select contact_phone from public.handover_requests', array['+234 801 000 0001'],
  'Admin reads handover contact details');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.messages', array[1], 'Receptionist reads messages');
reset role;

-- 2. Viewer: metadata only (4-7)
select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.conversations', array[1],
  'Viewer sees conversation metadata');
select is_empty('select 1 from public.messages', 'Viewer cannot read message text');
select is_empty('select 1 from public.handover_requests', 'Viewer cannot read patient contact details');
select results_eq($$with u as (update public.handover_requests set status = 'resolved' returning 1)
    select count(*)::int from u$$, array[0], 'Viewer cannot change a handover');
reset role;

-- 3. Platform admin (MFA): metadata only (8-10)
select pg_temp.login('platform.admin@test.invalid', 'aal2');
set local role engage_app;
select results_eq('select count(*)::int from public.conversations', array[2],
  'Platform admin sees conversation metadata across clinics');
select is_empty('select 1 from public.messages', 'Platform admin cannot read message text');
select is_empty('select 1 from public.handover_requests', 'Platform admin cannot read contact details');
reset role;

-- 4. Other clinic and lifecycle (11-14)
select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select results_eq('select content from public.messages', array['B patient question'],
  'Clinic B owner reads only Clinic B messages');
select is_empty('select 1 from public.handover_requests', 'Clinic B owner cannot read Clinic A handovers');
reset role;

select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.handover_requests set status = 'in_progress' returning resolved_at)
    select count(*)::int from u where resolved_at is null$$, array[1],
  'Receptionist moves a handover to in progress');
select throws_ok($$update public.handover_requests set contact_phone = '+1 555 0000'$$, '42501', null,
  'Patient contact details cannot be altered by staff');
reset role;

select * from finish();
rollback;
