-- Phase 3c retrieval passages: who can write them, and the widget sees only published ones (pgTAP).
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(11);

grant engage_app to postgres with inherit false, set true;
grant engage_widget to postgres with inherit false, set true;
grant usage on schema extensions to engage_app, engage_widget;

create function pg_temp.login(p_email text)
returns void language plpgsql as $$
declare v_uid uuid;
begin
  select id into strict v_uid from auth.users where email = p_email;
  perform set_config('request.jwt.claims',
    json_build_object('sub', v_uid, 'role', 'authenticated', 'aal', 'aal1')::text, true);
end;
$$;
create function pg_temp.widget(p_tenant uuid)
returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.widget.tenant_id', p_tenant::text, true);
  perform set_config('request.widget.conversation_id', '', true);
end;
$$;
grant execute on function pg_temp.login(text), pg_temp.widget(uuid) to engage_app, engage_widget, authenticated;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid');
insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');
insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist');

-- Documents: A published (v1 approved), A unreviewed (v1 extracted), B published.
insert into public.knowledge_documents (id, tenant_id, title) values
  ('30000000-0000-4000-8000-0000000000a1', '10000000-0000-4000-8000-00000000000a', 'A published'),
  ('30000000-0000-4000-8000-0000000000a2', '10000000-0000-4000-8000-00000000000a', 'A unreviewed'),
  ('30000000-0000-4000-8000-0000000000b1', '10000000-0000-4000-8000-00000000000b', 'B published');
insert into public.knowledge_document_versions
  (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256, extracted_text) values
  ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a1', 'extracted', 'a.txt', 'text', 1, repeat('a', 64), 'a'),
  ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a2', 'extracted', 'b.txt', 'text', 1, repeat('b', 64), 'b'),
  ('10000000-0000-4000-8000-00000000000b', '30000000-0000-4000-8000-0000000000b1', 'extracted', 'c.txt', 'text', 1, repeat('c', 64), 'c');
update public.knowledge_document_versions set status = 'approved'
  where document_id in ('30000000-0000-4000-8000-0000000000a1', '30000000-0000-4000-8000-0000000000b1');
update public.knowledge_documents d set published_version_id = v.id
  from public.knowledge_document_versions v
  where v.document_id = d.id and d.id in ('30000000-0000-4000-8000-0000000000a1', '30000000-0000-4000-8000-0000000000b1');
create function pg_temp.version_of(p_doc uuid) returns uuid language sql as $$
  select id from public.knowledge_document_versions where document_id = p_doc;
$$;
grant execute on function pg_temp.version_of(uuid) to engage_app, engage_widget;
insert into public.knowledge_chunks (tenant_id, document_id, version_id, ordinal, content) values
  ('10000000-0000-4000-8000-00000000000b', '30000000-0000-4000-8000-0000000000b1',
   pg_temp.version_of('30000000-0000-4000-8000-0000000000b1'), 0, 'B secret parking passage');

-- 1. Data API (1)
select pg_temp.login('a.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.knowledge_chunks', '42501', null, 'Data API: chunks denied');
reset role;

-- 2. Writing passages (2-5)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.knowledge_chunks (tenant_id, document_id, version_id, ordinal, content)
    values ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a1',
            pg_temp.version_of('30000000-0000-4000-8000-0000000000a1'), 0, 'A parking passage')$$,
  'Owner can index an approved version');
select throws_ok($$insert into public.knowledge_chunks (tenant_id, document_id, version_id, ordinal, content)
    values ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a2',
            pg_temp.version_of('30000000-0000-4000-8000-0000000000a2'), 0, 'unreviewed passage')$$,
  '42501', null, 'Unreviewed versions cannot be indexed');
select throws_ok($$update public.knowledge_chunks set content = 'tampered'$$, '42501', null,
  'Passages cannot be edited');
select throws_ok($$delete from public.knowledge_chunks$$, '42501', null, 'Passages cannot be deleted by the app');
reset role;

select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select throws_ok($$insert into public.knowledge_chunks (tenant_id, document_id, version_id, ordinal, content)
    values ('10000000-0000-4000-8000-00000000000a', '30000000-0000-4000-8000-0000000000a1',
            pg_temp.version_of('30000000-0000-4000-8000-0000000000a1'), 1, 'x')$$,
  '42501', null, 'Receptionist cannot index documents (6)');
reset role;

-- 3. Widget reads only its clinic's published passages (7-11)
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select results_eq('select content from public.knowledge_chunks', array['A parking passage'],
  'Widget sees only its clinic''s published passages');
select results_eq($$select count(*)::int from public.knowledge_chunks where search @@ to_tsquery('english', 'parking')$$,
  array[1], 'Full-text search never crosses tenants');
select results_eq('select app_private.widget_clinic_name()', array['Clinic A'], 'Widget can read its clinic name');
reset role;

update public.knowledge_documents set published_version_id = null where id = '30000000-0000-4000-8000-0000000000a1';
select pg_temp.widget('10000000-0000-4000-8000-00000000000a');
set local role engage_widget;
select is_empty('select 1 from public.knowledge_chunks', 'Unpublishing removes passages from the widget');
reset role;

select pg_temp.widget('10000000-0000-4000-8000-00000000000c');
set local role engage_widget;
select results_eq('select app_private.widget_clinic_name()', array[null::text],
  'Suspended clinic: no name, nothing served');
reset role;

select * from finish();
rollback;
