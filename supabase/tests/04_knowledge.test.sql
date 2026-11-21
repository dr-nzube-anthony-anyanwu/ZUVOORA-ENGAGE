-- Phase 2c knowledge documents: isolation, storage privacy, version and review invariants (pgTAP).
-- Run: npm run db:test   (requires local Supabase: npm run db:start)
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(32);

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

-- Helper: one extracted version of a document (values are synthetic).
create function pg_temp.add_version(p_doc uuid, p_tenant uuid, p_text text default 'Policy text')
returns void language sql as $$
  insert into public.knowledge_document_versions
    (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256, extracted_text)
  values (p_tenant, p_doc, 'extracted', 'policy.txt', 'text', 11, repeat('a', 64), p_text);
$$;
grant execute on function pg_temp.add_version(uuid, uuid, text) to engage_app;

create function pg_temp.doc(p_title text) returns uuid language sql as $$
  select id from public.knowledge_documents where title = p_title;
$$;
grant execute on function pg_temp.doc(text) to engage_app;

insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'a.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000a3', 'a.receptionist@test.invalid'),
  ('00000000-0000-4000-8000-0000000000b1', 'b.owner@test.invalid'),
  ('00000000-0000-4000-8000-0000000000c1', 's.owner@test.invalid');

insert into public.tenants (id, legal_name, display_name, status) values
  ('10000000-0000-4000-8000-00000000000a', 'Clinic A Ltd', 'Clinic A', 'active'),
  ('10000000-0000-4000-8000-00000000000b', 'Clinic B Ltd', 'Clinic B', 'active'),
  ('10000000-0000-4000-8000-00000000000c', 'Clinic S Ltd', 'Clinic S', 'suspended');

insert into public.tenant_memberships (tenant_id, user_id, role) values
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a1', 'owner'),
  ('10000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000a3', 'receptionist'),
  ('10000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000b1', 'owner'),
  ('10000000-0000-4000-8000-00000000000c', '00000000-0000-4000-8000-0000000000c1', 'owner');

insert into public.knowledge_documents (tenant_id, title) values
  ('10000000-0000-4000-8000-00000000000b', 'B Policy'),
  ('10000000-0000-4000-8000-00000000000c', 'S Policy');
select pg_temp.add_version(pg_temp.doc('B Policy'), '10000000-0000-4000-8000-00000000000b');
insert into storage.objects (bucket_id, name)
  values ('knowledge-originals', '10000000-0000-4000-8000-00000000000b/x/y');

-- 1. Data API roles cannot reach the tables (1-4)
set local role anon;
select throws_ok('select * from public.knowledge_documents', '42501', null, 'anon: documents denied');
select throws_ok('select * from public.knowledge_document_versions', '42501', null, 'anon: versions denied');
reset role;
select pg_temp.login('b.owner@test.invalid');
set local role authenticated;
select throws_ok('select * from public.knowledge_documents', '42501', null, 'Data API (authenticated): documents denied');
select throws_ok('select * from public.knowledge_document_versions', '42501', null, 'Data API (authenticated): versions denied');
reset role;

-- 2. Original files are private to the backend (5-8)
select results_eq($$select public from storage.buckets where id = 'knowledge-originals'$$,
  array[false], 'knowledge-originals bucket is private');
select results_eq($$select count(*)::int from pg_policies where schemaname = 'storage' and tablename = 'objects'$$,
  array[0], 'No storage.objects policies: browser keys get no object access');
select pg_temp.login('b.owner@test.invalid');
set local role authenticated;
select is_empty($$select 1 from storage.objects where bucket_id = 'knowledge-originals'$$,
  'Signed-in users (even the owning tenant) cannot see original files via Storage');
reset role;
set local role anon;
select is_empty($$select 1 from storage.objects where bucket_id = 'knowledge-originals'$$,
  'anon cannot see original files');
reset role;

-- 3. Owner A: uploads, server-set fields, review and publish rules (9-27)
select pg_temp.login('a.owner@test.invalid');
set local role engage_app;
select lives_ok($$insert into public.knowledge_documents (tenant_id, title)
    values ('10000000-0000-4000-8000-00000000000a', 'A Policy')$$, 'A owner can create a document');
select lives_ok($$select pg_temp.add_version(pg_temp.doc('A Policy'), '10000000-0000-4000-8000-00000000000a', 'v1')$$,
  'A owner can add an extracted version');
select results_eq($$select version_no, storage_path = tenant_id || '/' || document_id || '/' || id, uploaded_by
    from public.knowledge_document_versions where document_id = pg_temp.doc('A Policy')$$,
  $$values (1, true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$,
  'Version number, storage path and uploader are server-set');
select pg_temp.add_version(pg_temp.doc('A Policy'), '10000000-0000-4000-8000-00000000000a', 'v2');
select results_eq($$select max(version_no) from public.knowledge_document_versions where document_id = pg_temp.doc('A Policy')$$,
  array[2], 'Next upload becomes version 2');
select throws_ok($$insert into public.knowledge_document_versions
    (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256, extracted_text)
    values ('10000000-0000-4000-8000-00000000000a', pg_temp.doc('A Policy'), 'approved', 'x.txt', 'text', 1, repeat('a', 64), 'x')$$,
  '23514', null, 'A version cannot be inserted as already approved');
select throws_ok($$insert into public.knowledge_document_versions
    (tenant_id, document_id, status, file_name, detected_type, size_bytes, sha256, extracted_text, storage_path)
    values ('10000000-0000-4000-8000-00000000000a', pg_temp.doc('A Policy'), 'extracted', 'x.txt', 'text', 1, repeat('a', 64), 'x', 'other/path')$$,
  '42501', null, 'Client cannot choose the storage path');
select throws_ok($$select pg_temp.add_version('00000000-0000-0000-0000-000000000000'::uuid, '10000000-0000-4000-8000-00000000000a')$$,
  '23514', null, 'Cannot add a version to a document outside the tenant');
select throws_ok($$insert into public.knowledge_documents (tenant_id, title)
    values ('10000000-0000-4000-8000-00000000000b', 'Rogue')$$,
  '42501', null, 'A owner cannot create documents in Tenant B');
select throws_ok($$update public.knowledge_documents set published_version_id =
      (select id from public.knowledge_document_versions where document_id = pg_temp.doc('A Policy') and version_no = 1)
    where id = pg_temp.doc('A Policy')$$,
  '23514', null, 'An unreviewed version cannot be published');
update public.knowledge_document_versions set status = 'approved', review_note = 'ok'
  where document_id = pg_temp.doc('A Policy') and version_no = 1;
select results_eq($$select reviewed_by, reviewed_at = now() from public.knowledge_document_versions
    where document_id = pg_temp.doc('A Policy') and version_no = 1$$,
  $$values ('00000000-0000-4000-8000-0000000000a1'::uuid, true)$$, 'Approval stamps reviewer and time');
select lives_ok($$update public.knowledge_documents set published_version_id =
      (select id from public.knowledge_document_versions where document_id = pg_temp.doc('A Policy') and version_no = 1)
    where id = pg_temp.doc('A Policy')$$, 'Approved version can be published');
select results_eq($$select v.extracted_text from public.knowledge_documents d
    join public.knowledge_document_versions v on v.id = d.published_version_id where d.title = 'A Policy'$$,
  array['v1'], 'Published version stays v1 while v2 awaits review');
reset role;
-- A version of a different document (as postgres) to test the composite FK.
insert into public.knowledge_documents (tenant_id, title) values ('10000000-0000-4000-8000-00000000000a', 'A Other');
select pg_temp.add_version(pg_temp.doc('A Other'), '10000000-0000-4000-8000-00000000000a');
update public.knowledge_document_versions set status = 'approved' where document_id = pg_temp.doc('A Other');
set local role engage_app;
select throws_ok($$update public.knowledge_documents set published_version_id =
      (select id from public.knowledge_document_versions where document_id = pg_temp.doc('A Other'))
    where id = pg_temp.doc('A Policy')$$,
  '23514', null, 'Cannot publish another document''s version (trigger; composite FK backs it up)');
select throws_ok($$update public.knowledge_document_versions set extracted_text = 'tampered'
    where document_id = pg_temp.doc('A Policy') and version_no = 1$$,
  '42501', null, 'Extracted text cannot be edited');
select throws_ok($$update public.knowledge_document_versions set status = 'rejected'
    where document_id = pg_temp.doc('A Policy') and version_no = 1$$,
  '23514', null, 'An approved version cannot be re-decided');
update public.knowledge_documents set archived_at = now() where id = pg_temp.doc('A Policy');
select results_eq($$select published_version_id is null, archived_by from public.knowledge_documents where title = 'A Policy'$$,
  $$values (true, '00000000-0000-4000-8000-0000000000a1'::uuid)$$, 'Archiving unpublishes');
select throws_ok($$update public.knowledge_documents set published_version_id =
      (select id from public.knowledge_document_versions where document_id = pg_temp.doc('A Policy') and version_no = 1)
    where id = pg_temp.doc('A Policy')$$,
  '23514', null, 'Archived documents cannot be published');
select throws_ok($$delete from public.knowledge_document_versions$$, '42501', null, 'Versions cannot be deleted');
select is_empty($$select 1 from public.knowledge_documents where title = 'B Policy'$$,
  'A owner cannot see Tenant B documents');
select results_eq($$with u as (update public.knowledge_documents set title = 'pwned' where title = 'B Policy' returning 1)
    select count(*)::int from u$$, array[0], 'A owner cannot change Tenant B documents');
reset role;

-- 4. Receptionist and suspended tenant (28-31)
select pg_temp.login('a.receptionist@test.invalid');
set local role engage_app;
select results_eq('select count(*)::int from public.knowledge_document_versions', array[3],
  'Receptionist can read own clinic versions');
select throws_ok($$insert into public.knowledge_documents (tenant_id, title)
    values ('10000000-0000-4000-8000-00000000000a', 'Nope')$$, '42501', null, 'Receptionist cannot upload');
select results_eq($$with u as (update public.knowledge_document_versions set status = 'approved' returning 1)
    select count(*)::int from u$$, array[0], 'Receptionist cannot approve versions');
reset role;

select pg_temp.login('s.owner@test.invalid');
set local role engage_app;
select is_empty('select 1 from public.knowledge_documents', 'Suspended tenant owner cannot read documents');
reset role;

select * from finish();
rollback;
