-- Phase 3a widget path: anonymous visitor isolation, published-only content, conversations,
-- handover, usage ledger, rate limits, and staff access (pgTAP).
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(44);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget;

create function pg_temp.login(p_email text, p_aal text default 'aal1')
returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', p_aal)::text, true);
end;
$$;
-- Server-side widget context, as the API sets it from a verified widget token.
create function pg_temp.widget(p_tenant uuid, p_conversation uuid default null)
returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', coalesce(p_tenant::text, ''), true);
  perform set_config('request.widget.conversation_id', coalesce(p_conversation::text, ''), true);
end;
$$;
grant execute on function pg_temp.login(text, text), pg_temp.widget(uuid, uuid)
  to engage_app, engage_widget, authenticated, anon;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a4', 'a.viewer@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid');

insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a4', 'viewer'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner');

-- Widget configs were created by the tenant trigger; fix keys and enable A and S (B disabled).
update public.widget_configs set public_key = repeat('a', 32), enabled = true
  where tenant_id = '10000000-0000-4000-8000-00000000000a';
update public.widget_configs set public_key = repeat('b', 32), enabled = false
  where tenant_id = '10000000-0000-4000-8000-00000000000b';
update public.widget_configs set public_key = repeat('c', 32), enabled = true
  where tenant_id = '10000000-0000-4000-8000-00000000000c';
insert into public.tenant_domains (tenant_id, hostname) values
  ('10000000-0000-4000-8000-00000000000a', 'www.clinic-a.example.com'),
  ('10000000-0000-4000-8000-00000000000a', 'pending.clinic-a.example.com'),
  ('10000000-0000-4000-8000-00000000000b', 'www.clinic-b.example.com'),
  ('10000000-0000-4000-8000-00000000000c', 'www.clinic-s.example.com');
update public.tenant_domains set verification_status = 'verified'
  where hostname in ('www.clinic-a.example.com', 'www.clinic-b.example.com', 'www.clinic-s.example.com');

insert into public.faqs (id, tenant_id, draft) values
  ('20000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', '{"question": "A published?"}'),
  ('20000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', '{"question": "A draft only?"}'),
  ('20000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', '{"question": "B published?"}');
update public.faqs set published = draft
  where id in ('20000000-0000-4000-8000-0000000000a1', '20000000-0000-4000-8000-0000000000b1');
-- Edit A's published FAQ afterwards: the widget must still see only the published copy.
update public.faqs set draft = '{"question": "SECRET DRAFT EDIT"}' where id = '20000000-0000-4000-8000-0000000000a1';

insert into public.knowledge_documents (id, tenant_id, title) values
  ('30000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'Published doc'),
  ('30000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', 'Unreviewed doc');
insert into public.knowledge_document_versions
  (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256, extracted_text) values
  ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a1', 'extracted', 'a.txt', 'text', 1, repeat('a', 64), 'approved text'),
  ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a2', 'extracted', 'b.txt', 'text', 1, repeat('b', 64), 'UNREVIEWED TEXT');
update public.knowledge_document_versions set status = 'approved'
  where document_id = '30000000-0000-4000-8000-0000000000a1';
update public.knowledge_documents set published_version_id =
  (select id from public.knowledge_document_versions where document_id = '30000000-0000-4000-8000-0000000000a1')
  where id = '30000000-0000-4000-8000-0000000000a1';

insert into public.conversations (id, tenant_id) values
  ('40000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a'),
  ('40000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a'),
  ('40000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b');
insert into public.messages (tenant_id, conversation_id, role, content) values
  ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a2', 'visitor', 'other visitor message'),
  ('10000000-0000-4000-8000-00000000000b', '40000000-0000-4000-8000-0000000000b1', 'visitor', 'B visitor message');

-- 1. Supabase Data API roles have no access (1-5) ------------------------------------------------
select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.conversations', '42501', null, 'Data API: conversations denied');
select throws_ok('select * from public.messages', '42501', null, 'Data API: messages denied');
select throws_ok('select * from public.handover_requests', '42501', null, 'Data API: handovers denied');
select throws_ok('select * from public.usage_events', '42501', null, 'Data API: usage denied');
select throws_ok('select * from public.widget_configs', '42501', null, 'Data API: widget configs denied');
reset role;

-- 2. Widget key resolution requires an enabled widget, active tenant and VERIFIED host (6-10)
set local role engage_widget;
select results_eq($$select tenant_id from app_private.resolve_widget(repeat('a', 32), 'WWW.Clinic-A.example.com')$$,
  $$values ('10000000-0000-4000-8000-00000000000a'::uuid)$$, 'Enabled widget on a verified host resolves');
select is_empty($$select 1 from app_private.resolve_widget(repeat('a', 32), 'pending.clinic-a.example.com')$$,
  'Unverified host is refused');
select is_empty($$select 1 from app_private.resolve_widget(repeat('a', 32), 'www.clinic-b.example.com')$$,
  'Another clinic''s verified host is refused');
select is_empty($$select 1 from app_private.resolve_widget(repeat('b', 32), 'www.clinic-b.example.com')$$,
  'Disabled widget is refused');
select is_empty($$select 1 from app_private.resolve_widget(repeat('c', 32), 'www.clinic-s.example.com')$$,
  'Suspended clinic''s widget is refused');
reset role;

-- 3. Visitor reads only published content of its own clinic (11-20) -------------------------------
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select results_eq($$select published->>'question' from public.faqs$$, array['A published?'],
  'Widget sees only A''s published FAQ, as published (not the later draft edit)');
select throws_ok('select draft from public.faqs', '42501', null, 'Widget cannot read drafts');
select throws_ok('select draft from public.clinic_profiles', '42501', null, 'Widget cannot read profile drafts');
select results_eq($$select extracted_text from public.knowledge_document_versions$$, array['approved text'],
  'Widget sees only the published document version');
select throws_ok('select storage_path from public.knowledge_document_versions', '42501', null,
  'Widget cannot see storage paths');
select throws_ok('select * from public.tenant_domains', '42501', null, 'Widget cannot read domains');
select throws_ok('select * from public.tenant_memberships', '42501', null, 'Widget cannot read memberships');
select throws_ok('select * from public.audit_events', '42501', null, 'Widget cannot read the audit log');
select lives_ok($$insert into public.conversations (tenant_id, origin_host)
    values ('10000000-0000-4000-8000-00000000000a', 'www.clinic-a.example.com')$$,
  'Widget can start a conversation for its clinic');
select throws_ok($$insert into public.conversations (tenant_id) values ('10000000-0000-4000-8000-00000000000b')$$,
  '42501', null, 'Widget cannot start a conversation for another clinic');
reset role;

-- 4. Visitor is confined to its own conversation (21-31) ---------------------------------------
select pg_temp.widget('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1');
set local role engage_widget;
select lives_ok($$insert into public.messages (tenant_id, conversation_id, role, content)
    values ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'visitor', 'hello')$$,
  'Visitor can post in its own conversation');
select throws_ok($$insert into public.messages (tenant_id, conversation_id, role, content)
    values ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a2', 'visitor', 'x')$$,
  '42501', null, 'Visitor cannot post in another conversation');
select results_eq('select content from public.messages', array['hello'],
  'Visitor sees only its own conversation''s messages');
select results_eq('select count(*)::int from public.conversations', array[1],
  'Visitor sees only its own conversation');
select throws_ok($$update public.messages set content = 'edited'$$, '42501', null, 'Messages cannot be edited');
select throws_ok($$delete from public.messages$$, '42501', null, 'Messages cannot be deleted');
select throws_ok($$insert into public.handover_requests (tenant_id, conversation_id, contact_phone, consent_given)
    values ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', '+2348010000000', false)$$,
  '23514', null, 'Handover requires consent');
select lives_ok($$insert into public.handover_requests (tenant_id, conversation_id, contact_phone, consent_given)
    values ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', '+2348010000000', true)$$,
  'Visitor can request a handover with consent');
select results_eq($$with u as (update public.conversations set status = 'handover_requested' returning 1)
    select count(*)::int from u$$, array[1], 'Visitor can mark its conversation for handover');
select throws_ok($$update public.conversations set status = 'closed'$$, '42501', null,
  'Visitor cannot close conversations (staff action)');
select throws_ok($$insert into public.usage_events (tenant_id, feature, provider, model, tier, cost_usd)
    values ('10000000-0000-4000-8000-00000000000b', 'chat', 'fake', 'm', 'standard', 1)$$,
  '42501', null, 'Usage cannot be charged to another clinic');
reset role;

-- 5. Usage ledger, spend and rate limits (32-35) ------------------------------------------------
select pg_temp.widget('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1');
set local role engage_widget;
insert into public.usage_events (tenant_id, conversation_id, feature, provider, model, tier, cost_usd)
  values ('10000000-0000-4000-8000-00000000000a', '40000000-0000-4000-8000-0000000000a1', 'chat', 'fake', 'm', 'standard', 0.0025);
select results_eq('select tenant_today, global_today from app_private.ai_spend()',
  $$values (0.0025::numeric, 0.0025::numeric)$$, 'Spend is summed per clinic and globally');
select results_eq($$select array[app_private.rate_limit_hit('t:k', 60, 2), app_private.rate_limit_hit('t:k', 60, 2),
    app_private.rate_limit_hit('t:k', 60, 2)]$$, $$values (array[true, true, false])$$,
  'Rate limit allows 2 hits then refuses');
select throws_ok($$delete from public.usage_events$$, '42501', null, 'Usage ledger is append-only');
select throws_ok('select * from app_private.rate_limits', '42501', null, 'Rate-limit table is not directly readable');
reset role;

-- 6. Staff access (36-42) ---------------------------------------------------------------------
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.conversations', array[3],
  'Receptionist sees all of A''s conversations');
select results_eq($$with u as (update public.handover_requests set status = 'resolved' returning resolved_by)
    select resolved_by from u$$, $$values ('00000000-0000-4000-8000-0000000000a3'::uuid)$$,
  'Receptionist can resolve a handover (resolver stamped by the server)');
select throws_ok($$select app_private.rotate_widget_key('10000000-0000-4000-8000-00000000000a')$$,
  '42501', null, 'Receptionist cannot rotate the widget key');
select is_empty('select 1 from public.usage_events', 'Receptionist cannot see AI costs');
reset role;

select pg_temp.login('a.viewer@test.invalid');
set local role engage_app;
select results_eq($$with u as (update public.conversations set status = 'closed' returning 1)
    select count(*)::int from u$$, array[0], 'Viewer cannot close conversations');
reset role;

select pg_temp.login('b.owner@test.invalid');
set local role engage_app;
select results_eq($$select count(*)::int from public.messages where tenant_id = '10000000-0000-4000-8000-00000000000a'$$,
  array[0], 'Clinic B owner cannot read Clinic A messages');
reset role;

-- 7. Retention path: the database owner can delete; nobody can edit (43-44)
select lives_ok($$delete from public.conversations where id = '40000000-0000-4000-8000-0000000000b1'$$,
  'Database owner can delete a conversation with its messages (retention / deletion requests)');
select throws_ok($$update public.messages set content = 'rewritten'$$, '42501', null,
  'Messages cannot be edited, even by the database owner');

select results_eq($$select count(*)::int from public.widget_configs w join public.tenants t on t.id = w.tenant_id$$,
  $$select count(*)::int from public.tenants$$, 'Every tenant has a widget configuration');

select * from finish();
rollback;
