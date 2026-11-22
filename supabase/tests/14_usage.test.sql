-- Phase 5b usage metering: what is counted, thresholds alert once, who can read, widget quotas.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(18);

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
create function pg_temp.widget(p_tenant uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', p_tenant::text, true);
  perform set_config('request.widget.conversation_id', '', true);
end;
$$;
create function pg_temp.used(p_tenant uuid, p_metric text) returns numeric language sql security definer as $$
  select coalesce((select quantity from app_private.usage_counters
                    where tenant_id = p_tenant and metric = p_metric
                      and period_month = app_private.current_period()), 0)
$$;
create function pg_temp.alerts(p_tenant uuid) returns bigint language sql security definer as $$
  select count(*) from app_private.jobs where kind = 'quota_alert' and tenant_id = p_tenant
$$;
grant execute on function pg_temp.login(text), pg_temp.widget(uuid), pg_temp.used(uuid, text),
  pg_temp.alerts(uuid) to engage_app, engage_widget, engage_jobs, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist');
-- A small message limit so thresholds are reachable.
insert into public.tenant_overrides (tenant_id, kind, key, limit_value, reason) values
  ('10000000-0000-4000-8000-00000000000a', 'limit', 'messages_month', 5, 'test');
insert into public.conversations (id, tenant_id) values
  ('40000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a');

-- 1. Messages: visitor messages count, other roles do not (1-2)
insert into public.messages (tenant_id, conversation_id, role, content) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'one'),
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'two'),
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'three');
insert into public.messages (tenant_id, conversation_id, role, content, answer_source) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'assistant', 'reply', 'facts');
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'messages'), 3.000000::numeric,
  'Visitor messages are counted; assistant replies are not');
select is(pg_temp.used('10000000-0000-4000-8000-00000000000b', 'messages'), 0::numeric,
  'Counters are per clinic');

-- 2. Thresholds: one alert per threshold per month (3-6)
select is(pg_temp.alerts('10000000-0000-4000-8000-00000000000a'), 0::bigint, 'No alert below 80%');
insert into public.messages (tenant_id, conversation_id, role, content) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'four');
select is(pg_temp.alerts('10000000-0000-4000-8000-00000000000a'), 1::bigint, '80% crossed: one alert');
insert into public.messages (tenant_id, conversation_id, role, content) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'five'),
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'six'),
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'seven');
select is(pg_temp.alerts('10000000-0000-4000-8000-00000000000a'), 2::bigint,
  '100% crossed: a second alert, and no more after that');
select results_eq($$select payload->>'threshold' from app_private.jobs
    where kind = 'quota_alert' and tenant_id = '10000000-0000-4000-8000-00000000000a' order by id$$,
  array['80', '100'], 'Alerts name their threshold');

-- 3. AI usage, bookings, emails (7-11)
insert into public.usage_events (tenant_id, feature, provider, model, tier, prompt_tokens, completion_tokens, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'chat', 'fake', 'm', 'standard', 900, 100, 0.0012);
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'ai_usd'), 0.001200::numeric, 'AI cost is metered');
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'ai_tokens'), 1000::numeric, 'AI tokens are metered');
insert into public.scheduling_connections (id, tenant_id, provider, credential_ciphertext, credential_key_id) values
  ('70000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'calcom', '\x00'::bytea, 'abcdef012345');
insert into public.appointments (id, tenant_id, connection_id, provider, provider_event_type_id, type_name,
    start_at, attendee_name, attendee_email, attendee_time_zone, consent_given)
  values ('80000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-00000000000a',
          '70000000-0000-4000-8000-0000000000a1', 'calcom', '1', 'Exam', now() + interval '3 days',
          'Ada', 'ada@example.com', 'UTC', true);
update public.appointments set status = 'confirmed', provider_booking_id = 'bk1'
  where id = '80000000-0000-4000-8000-000000000001';
update public.appointments set status = 'cancelled' where id = '80000000-0000-4000-8000-000000000001';
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'bookings'), 1::numeric,
  'A booking counts once (cancelling does not count again)');
set local role engage_jobs;
select app_private.complete_job(id, '{"message_id": "re_1"}') from app_private.claim_jobs(1);
reset role;
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'emails'), 1::numeric, 'A sent email is counted');
set local role engage_jobs;
select app_private.complete_job(id, '{"message_id": "suppressed:allowlist"}') from app_private.claim_jobs(1);
reset role;
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'emails'), 1::numeric,
  'A suppressed (not sent) email is not counted');

-- 4. Widget quota check (12-13)
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select ok(app_private.widget_quota_reached('messages'), 'The widget sees its messages quota is reached');
select ok(not app_private.widget_quota_reached('bookings'), 'Bookings are under the limit');
reset role;

-- 5. Who can read usage (14-18)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$select quantity from app_private.tenant_usage('10000000-0000-4000-8000-00000000000a')
    where metric = 'messages'$$, array[7.000000::numeric], 'Owner reads this month''s usage');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select is_empty($$select 1 from app_private.tenant_usage('10000000-0000-4000-8000-00000000000a')$$,
  'Receptionists do not see usage');
select throws_ok('select 1 from app_private.usage_counters', '42501', null, 'Counters are not directly readable');
select throws_ok($$select app_private.meter('10000000-0000-4000-8000-00000000000a', 'messages', -100)$$,
  '42501', null, 'Staff cannot write counters');
reset role;
set local role engage_widget;
select throws_ok($$select * from app_private.tenant_usage('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'The widget cannot read usage');
reset role;

select * from finish();
rollback;
