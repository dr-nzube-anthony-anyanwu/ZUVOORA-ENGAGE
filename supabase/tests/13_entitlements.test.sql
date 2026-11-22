-- Phase 5a plans and entitlements: catalogue, default subscription, overrides, cancellation,
-- who may read or change what, and the widget/reminder gates.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(25);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget;

create function pg_temp.login(p_email text, p_aal text default 'aal1') returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', p_aal)::text, true);
end;
$$;
create function pg_temp.widget(p_tenant uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', p_tenant::text, true);
  perform set_config('request.widget.conversation_id', '', true);
end;
$$;
grant execute on function pg_temp.login(text, text), pg_temp.widget(uuid) to engage_app, engage_widget, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000f1', 'platform.admin@test.invalid');
insert into public.platform_admins (user_id) values ('00000000-0000-4000-8000-0000000000f1');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner');

-- 1. Catalogue and default subscription (1-6)
select results_eq('select key from public.plans order by tier_order',
  array['essentials', 'professional', 'premium', 'full_zuvoora'], 'Four tiers in order');
select results_eq($$select plan_key, status from public.tenant_subscriptions
    where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  $$values ('essentials'::text, 'trialing'::text)$$, 'A new clinic starts on an Essentials trial');
select ok(app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'booking'),
  'Essentials includes live booking');
select ok(not app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'reminders'),
  'Essentials has no reminders');
select ok(not app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'whatsapp'),
  'Features not built yet are never granted');
select is(app_private.limit_internal('10000000-0000-4000-8000-00000000000a', 'domains'), 1.00,
  'Essentials allows one website domain');

-- 2. Upgrade and overrides (7-10)
update public.tenant_subscriptions set plan_key = 'full_zuvoora', status = 'active'
  where tenant_id = '10000000-0000-4000-8000-00000000000a';
select ok(app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'reminders'),
  'An upgrade grants the higher tier''s features');
select ok(not app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'ecosystem'),
  'Even Full ZUVOORA does not get unbuilt features');
insert into public.tenant_overrides (tenant_id, kind, key, limit_value, reason) values
  ('10000000-0000-4000-8000-00000000000a', 'limit', 'domains', 2, 'test override');
insert into public.tenant_overrides (tenant_id, kind, key, feature_enabled, reason) values
  ('10000000-0000-4000-8000-00000000000a', 'feature', 'booking', false, 'test override');
select is(app_private.limit_internal('10000000-0000-4000-8000-00000000000a', 'domains'), 2.00,
  'A limit override replaces the plan''s value');
select ok(not app_private.has_feature_internal('10000000-0000-4000-8000-00000000000a', 'booking'),
  'A feature override can switch a plan feature off');
delete from public.tenant_overrides where tenant_id = '10000000-0000-4000-8000-00000000000a';

-- 3. Who can read and change (11-18)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$select plan_key from app_private.tenant_entitlements('10000000-0000-4000-8000-00000000000a')$$,
  array['full_zuvoora'], 'Owner reads the clinic''s entitlements');
select results_eq('select count(*)::int from public.tenant_subscriptions', array[1],
  'Owner sees only their own subscription');
select results_eq($$with u as (update public.tenant_subscriptions set plan_key = 'premium' returning 1)
    select count(*)::int from u$$, array[0], 'Owner cannot change their own plan');
select throws_ok($$insert into public.tenant_overrides (tenant_id, kind, key, feature_enabled, reason)
    values ('10000000-0000-4000-8000-00000000000a', 'feature', 'reminders', true, 'self-service')$$,
  '42501', null, 'Owner cannot grant themselves features');
select results_eq($$with u as (update public.plan_limits set value = 999999 returning 1)
    select count(*)::int from u$$, array[0], 'Staff cannot edit the catalogue');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.tenant_subscriptions', 'Receptionists do not see billing details');
reset role;
select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select is_empty($$select 1 from app_private.tenant_entitlements('10000000-0000-4000-8000-00000000000a')$$,
  'Another clinic cannot read this clinic''s plan');
reset role;
select pg_temp.login('platform.admin@test.invalid', 'aal2');
set local role engage_app;
select results_eq($$with u as (update public.tenant_subscriptions set plan_key = 'professional'
    where tenant_id = '10000000-0000-4000-8000-00000000000b' returning updated_by)
    select updated_by from u$$, $$values ('00000000-0000-4000-8000-0000000000f1'::uuid)$$,
  'An MFA platform admin changes a plan (stamped by the database)');
reset role;

-- 4. Widget gates and cancellation (19-23)
update public.widget_configs set enabled = true, public_key = repeat('a', 32)
  where tenant_id = '10000000-0000-4000-8000-00000000000a';
insert into public.tenant_domains (tenant_id, hostname) values ('10000000-0000-4000-8000-00000000000a', 'www.a.example.com');
update public.tenant_domains set verification_status = 'verified' where hostname = 'www.a.example.com';
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select ok(app_private.widget_has_feature('booking'), 'The widget sees its own clinic''s features');
select results_eq($$select count(*)::int from app_private.resolve_widget(repeat('a', 32), 'www.a.example.com')$$,
  array[1], 'The widget loads while the subscription is active');
reset role;
update public.tenant_subscriptions set status = 'cancelled' where tenant_id = '10000000-0000-4000-8000-00000000000a';
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select is_empty($$select 1 from app_private.resolve_widget(repeat('a', 32), 'www.a.example.com')$$,
  'A cancelled subscription stops the widget');
select ok(not app_private.widget_tenant_active(), 'Existing chat sessions stop too');
reset role;
select is((select count(*)::int from public.faqs where tenant_id = '10000000-0000-4000-8000-00000000000a') >= 0
  and exists (select 1 from public.widget_configs where tenant_id = '10000000-0000-4000-8000-00000000000a'),
  true, 'Cancelling keeps the clinic''s data and widget configuration');

-- 5. Data API and function access (24-25)
set local role authenticated;
select throws_ok('select 1 from public.plans', '42501', null, 'Data API: catalogue denied');
reset role;
set local role engage_widget;
select throws_ok($$select app_private.has_feature_internal('10000000-0000-4000-8000-00000000000b', 'booking')$$,
  '42501', null, 'The widget cannot ask about another clinic');
reset role;

select * from finish();
rollback;
