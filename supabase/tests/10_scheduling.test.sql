-- Phase 4b scheduling connections and appointment types: credential secrecy, roles, widget view.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(26);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget;

create function pg_temp.login(p_email text) returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', 'aal1')::text, true);
end;
$$;
create function pg_temp.widget(p_tenant uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', p_tenant::text, true);
  perform set_config('request.widget.conversation_id', '', true);
end;
$$;
grant execute on function pg_temp.login(text), pg_temp.widget(uuid) to engage_app, engage_widget, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner');

-- 1. Data API has no access (1)
select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select id from public.scheduling_connections', '42501', null, 'Data API: connections denied');
reset role;

-- 2. Connecting (2-6)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.scheduling_connections
    (id, tenant_id, provider, account_label, credential_ciphertext, credential_key_id, credential_hint)
    values ('70000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'calcom',
            'dr-ada', '\x0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c'::bytea, 'abcdef012345', '9f3c')$$,
  'Owner connects a scheduling account');
select results_eq($$select connected_by from public.scheduling_connections$$,
  $$values ('00000000-0000-4000-8000-0000000000a1'::uuid)$$, 'Connecting user is stamped by the database');
select throws_ok('select credential_ciphertext from public.scheduling_connections', '42501', null,
  'Even the owner cannot read the encrypted credential column');
select throws_ok($$insert into public.scheduling_connections (tenant_id, provider, credential_ciphertext, credential_key_id)
    values ('10000000-0000-4000-8000-00000000000a', 'calcom', '\x00'::bytea, 'abcdef012345')$$,
  '23505', null, 'Only one live connection per clinic');
select throws_ok($$update public.scheduling_connections set tenant_id = '10000000-0000-4000-8000-00000000000b'$$,
  '42501', null, 'A connection cannot move to another clinic');
reset role;

-- 3. Roles (7-9)
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.scheduling_connections set account_label = 'x' returning 1)
    select count(*)::int from u$$, array[0], 'Receptionist cannot change the connection');
reset role;
select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select results_eq('select account_label from public.scheduling_connections', array['dr-ada'],
  'Viewer sees connection metadata');
reset role;
select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.scheduling_connections', 'Other clinic sees nothing');
reset role;

-- 4. Credential function (10-15)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$select key_id from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  array['abcdef012345'], 'Owner can obtain the ciphertext for the API to decrypt');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq($$select count(*)::int from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  array[1], 'Receptionist can use the connection (booking management)');
reset role;
select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select is_empty($$select 1 from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  'Viewer cannot obtain the credential');
reset role;
select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select is_empty($$select 1 from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  'Other clinic cannot obtain the credential');
reset role;
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select results_eq($$select count(*)::int from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  array[1], 'The clinic''s own widget can use its connection');
reset role;
select pg_temp.widget('10000000-0000-4000-8000-00000000000b');
set local role engage_widget;
select is_empty($$select 1 from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  'Another clinic''s widget cannot');
reset role;

-- 5. Appointment types (16-21)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.appointment_types (tenant_id, connection_id, provider_event_type_id, name, duration_minutes, enabled)
    values ('10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', '101', 'Eye exam', 30, true),
           ('10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', '102', 'Hidden type', 15, false)$$,
  'Owner chooses appointment types to offer');
select throws_ok($$update public.appointment_types set provider_event_type_id = '999'$$, '42501', null,
  'The provider event type of an appointment type cannot be changed');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select throws_ok($$insert into public.appointment_types (tenant_id, connection_id, provider_event_type_id, name, duration_minutes)
    values ('10000000-0000-4000-8000-00000000000a', '70000000-0000-4000-8000-0000000000a1', '103', 'x', 30)$$,
  '42501', null, 'Receptionist cannot add appointment types');
reset role;
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select results_eq('select name from public.appointment_types', array['Eye exam'],
  'Widget sees only enabled types of its clinic');
select throws_ok('select credential_ciphertext from public.scheduling_connections', '42501', null,
  'Widget cannot read the credential column');
reset role;
select pg_temp.widget('10000000-0000-4000-8000-00000000000b');
set local role engage_widget;
select is_empty('select 1 from public.appointment_types', 'Other clinic''s widget sees no types');
reset role;

-- 6. Disconnecting (22-26)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
update public.scheduling_connections set status = 'disconnected';
select results_eq($$select status, credential_hint is null, disconnected_by from public.scheduling_connections$$,
  $$values ('disconnected'::text, true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'Disconnecting wipes the credential and stamps who did it');
select is_empty($$select 1 from app_private.scheduling_credential('70000000-0000-4000-8000-0000000000a1')$$,
  'A disconnected credential is gone');
select throws_ok($$update public.scheduling_connections set status = 'active'$$, '23514', null,
  'A disconnected connection cannot be revived (connect again instead)');
reset role;
select is((select credential_ciphertext is null from public.scheduling_connections), true,
  'The ciphertext is erased in the database');
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select is_empty('select 1 from public.appointment_types', 'No bookable types after disconnecting');
reset role;

select * from finish();
rollback;
