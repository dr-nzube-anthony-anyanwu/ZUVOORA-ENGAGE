-- Phase 3g: AI reading of photos/scanned PDFs — who may record document usage, staff-side spend,
-- metering, version records and the catalogue feature.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(17);

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
create function pg_temp.used(p_tenant uuid, p_metric text) returns numeric language sql security definer as $$
  select coalesce((select quantity from app_private.usage_counters
                    where tenant_id = p_tenant and metric = p_metric
                      and period_month = app_private.current_period()), 0)
$$;
grant execute on function pg_temp.login(text), pg_temp.widget(uuid), pg_temp.used(uuid, text)
  to engage_app, engage_widget, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist');

-- 1. Owners record document usage for their own clinic only (1-5)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier,
    prompt_tokens, completion_tokens, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'document', 'fake', 'fake/vision', 'vision', 1200, 40, 0.0004)$$,
  'An owner records document-reading usage for their clinic');
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'chat', 'fake', 'm', 'standard', 0)$$,
  '42501', null, 'Staff cannot write chat usage');
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000b', 'document', 'fake', 'm', 'vision', 0)$$,
  '42501', null, 'Staff cannot write usage for another clinic');
select throws_ok($$insert into public.usage_events (tenant_id, conversation_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', gen_random_uuid(), 'document', 'fake', 'm', 'vision', 0)$$,
  '42501', null, 'Staff cannot attach usage to a conversation');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'document', 'fake', 'm', 'vision', 0)$$,
  '42501', null, 'Receptionists cannot record document usage');
reset role;

-- 2. Shape and the widget (6-8)
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'document', 'fake', 'm', 'standard', 0)$$,
  '23514', null, 'Document usage is always the vision tier');
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'document', 'fake', 'm', 'vision', 0)$$,
  '42501', null, 'The widget cannot record document usage');
select lives_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', 'chat', 'fake', 'm', 'standard', 0.0001)$$,
  'The widget still records chat usage');
reset role;

-- 3. Metering and staff-side spend (9-12)
select is(pg_temp.used('10000000-0000-4000-8000-00000000000a', 'ai_usd'), 0.000500::numeric,
  'Document reading counts toward the clinic''s AI meter');
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select results_eq($$select tenant_today, tenant_month from app_private.ai_spend_for('10000000-0000-4000-8000-00000000000a')$$,
  $$values (0.000500::numeric, 0.000500::numeric)$$, 'Owners read their clinic''s AI spend before a call');
reset role;
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select throws_ok($$select * from app_private.ai_spend_for('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'Receptionists cannot read AI spend');
reset role;
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select throws_ok($$select * from app_private.ai_spend_for('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'The widget cannot call the staff spend function');
reset role;

-- 4. Versions record how the text was obtained (13-15)
insert into public.knowledge_documents (id, tenant_id, title) values
  ('50000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'Price list');
select throws_ok($$insert into public.knowledge_document_versions (tenant_id, document_id, status, file_name,
    detected_type, size_bytes, sha256, extracted_text)
  values ('10000000-0000-4000-8000-00000000000a', '50000000-0000-4000-8000-0000000000a1', 'extracted',
          'prices.jpg', 'image', 100, repeat('a', 64), 'Exam 25,000')$$,
  '23514', null, 'A photo can only be read by AI (extraction_method vision)');
insert into public.knowledge_document_versions (tenant_id, document_id, status, file_name, detected_type,
    extraction_method, size_bytes, sha256, extracted_text)
  values ('10000000-0000-4000-8000-00000000000a', '50000000-0000-4000-8000-0000000000a1', 'extracted',
          'prices.jpg', 'image', 'vision', 100, repeat('a', 64), 'Exam 25,000');
select is((select extraction_method from public.knowledge_document_versions
            where document_id = '50000000-0000-4000-8000-0000000000a1'), 'vision', 'The method is stored');
select throws_ok($$update public.knowledge_document_versions set extraction_method = 'text'
    where document_id = '50000000-0000-4000-8000-0000000000a1'$$,
  '42501', null, 'The extraction method is immutable');

-- 5. Catalogue (16-17)
select is((select count(*) from public.plan_features where feature_key = 'document_reading'),
  (select count(*) from public.plans), 'Reading scanned documents is in every plan');
select ok((select 'document_reading' = any(features) from app_private.entitlements_internal('10000000-0000-4000-8000-00000000000a')),
  'A clinic''s entitlements include it');

select * from finish();
rollback;
