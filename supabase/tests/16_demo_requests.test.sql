-- Design track D3: demo requests — who can submit, read and change them; notification job;
-- retention.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(15);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant engage_jobs to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget, engage_jobs;

create function pg_temp.login(p_email text, p_aal text default 'aal1') returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', p_aal)::text, true);
end;
$$;
create function pg_temp.public_visitor(p_tenant uuid default null) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', coalesce(p_tenant::text, ''), true);
  perform set_config('request.widget.conversation_id', '', true);
end;
$$;
grant execute on function pg_temp.login(text, text), pg_temp.public_visitor(uuid)
  to engage_app, engage_widget, engage_jobs, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000f1', 'platform@test.invalid');
insert into public.platform_admins (user_id, note) values ('00000000-0000-4000-8000-0000000000f1', 'test');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner');

-- 1. Public submission (1-5)
select pg_temp.public_visitor();
set local role engage_widget;
select isnt(app_private.submit_demo_request('Ada Test', 'Manager', 'Sample Clinic', 'Abuja', 'Nigeria',
  'Ada@Example.com', '+234 801 000 0000', 'pilot', 'Hello', true), null, 'The public path can submit a request');
select throws_ok($$select 1 from public.demo_requests$$, '42501', null, 'Visitors cannot read requests');
select throws_ok($$select app_private.submit_demo_request('Ada', null, 'Clinic', null, null,
    'ada@example.com', null, 'demo', null, false)$$, '23514', null, 'Consent is required');
reset role;
select pg_temp.public_visitor('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select throws_ok($$select app_private.submit_demo_request('Ada', null, 'Clinic', null, null,
    'ada@example.com', null, 'demo', null, true)$$, '42501', null, 'A clinic''s chat session cannot submit');
reset role;
select is((select email from public.demo_requests where clinic_name = 'Sample Clinic'), 'ada@example.com',
  'Emails are stored in lower case');

-- 2. Notification job (6)
select is((select count(*) from app_private.jobs j join public.demo_requests d
             on j.payload->>'request_id' = d.id::text
            where j.kind = 'demo_request_alert' and d.clinic_name = 'Sample Clinic'), 1::bigint,
  'Each request queues exactly one notification');

-- 3. Who can read and change (7-12)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select is_empty($$select 1 from public.demo_requests$$, 'Clinic staff cannot see demo requests');
reset role;
select pg_temp.login('platform@test.invalid', 'aal1');
set local role engage_app;
select is_empty($$select 1 from public.demo_requests$$, 'Platform admins without MFA cannot see them');
reset role;
select pg_temp.login('platform@test.invalid', 'aal2');
set local role engage_app;
select is((select count(*) from public.demo_requests), 1::bigint, 'MFA platform admins can see them');
select lives_ok($$update public.demo_requests set status = 'contacted' where clinic_name = 'Sample Clinic'$$,
  'MFA platform admins can change the status');
select throws_ok($$update public.demo_requests set email = 'x@example.com' where clinic_name = 'Sample Clinic'$$,
  '42501', null, 'Request details cannot be changed');
select throws_ok($$delete from public.demo_requests$$, '42501', null, 'Requests cannot be deleted by staff');
reset role;

-- 4. Job data and retention (13-15)
select set_config('test.request_id', (select id::text from public.demo_requests where clinic_name = 'Sample Clinic'), true);
set local role engage_jobs;
select results_eq($$select clinic_name, interest from app_private.job_demo_request(current_setting('test.request_id')::uuid)$$,
  $$values ('Sample Clinic'::text, 'pilot'::text)$$, 'The worker reads only the summary it needs');
select throws_ok($$select email from public.demo_requests$$, '42501', null, 'The jobs role cannot read contact details');
reset role;
-- Test setup only: back-date the request (the trigger rightly forbids this for everyone).
alter table public.demo_requests disable trigger demo_requests_update;
update public.demo_requests set created_at = now() - interval '13 months' where clinic_name = 'Sample Clinic';
alter table public.demo_requests enable trigger demo_requests_update;
set local role engage_jobs;
select is(app_private.purge_demo_requests(), 1, 'Requests older than 12 months are purged');
reset role;

select * from finish();
rollback;
