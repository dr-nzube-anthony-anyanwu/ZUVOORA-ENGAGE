-- Phase 3g: AI reading of scanned documents and images uploaded by clinic staff (ADR-041).
--
-- * Clinic owners/admins may upload photos (PNG/JPEG/WebP) and scanned PDFs to the knowledge
--   base. A vision model transcribes them; the text then goes through the existing review and
--   approval flow. Patients cannot upload anything (Phase 3 decision stands).
-- * Every vision call is recorded in public.usage_events (feature 'document', tier 'vision'), so
--   daily AI budgets, plan quotas, meters, alerts and analytics include it. Staff may insert only
--   'document' usage for a clinic they own/administer; the widget may insert only 'chat' usage.
-- * The feature 'document_reading' is in every plan and can be switched off per clinic.

-- ----- usage ledger -----------------------------------------------------------------------------
alter table public.usage_events drop constraint usage_events_feature_check;
alter table public.usage_events add constraint usage_events_feature_check
  check (feature in ('chat', 'document'));
alter table public.usage_events drop constraint usage_events_tier_check;
alter table public.usage_events add constraint usage_events_tier_check
  check (tier in ('standard', 'complex', 'vision'));
alter table public.usage_events add constraint usage_events_feature_shape
  check ((feature = 'document') = (tier = 'vision')
         and (feature = 'chat' or conversation_id is null));

drop policy usage_events_widget_insert on public.usage_events;
create policy usage_events_widget_insert on public.usage_events for insert to engage_widget
  with check (tenant_id = app_private.widget_tenant()
              and feature = 'chat'
              and (conversation_id is null or conversation_id = app_private.widget_conversation()));

create policy usage_events_staff_insert on public.usage_events for insert to engage_app
  with check (feature = 'document'
              and conversation_id is null
              and (app_private.is_platform_admin()
                   or app_private.has_tenant_role(tenant_id,
                        array['owner', 'admin']::public.membership_role[])));

grant insert (tenant_id, feature, provider, model, tier, prompt_tokens, completion_tokens, cost_usd)
  on public.usage_events to engage_app;
grant usage on sequence public.usage_events_id_seq to engage_app;

-- Staff-side spend for budget checks before a vision call (owner/admin of that clinic or MFA
-- platform admin). Same windows as app_private.ai_spend() plus the clinic's month for the quota.
create or replace function app_private.ai_spend_for(p_tenant uuid)
returns table (tenant_today numeric, global_today numeric, global_month numeric, tenant_month numeric)
language plpgsql stable security definer
set search_path = ''
as $$
begin
  if not (app_private.is_platform_admin()
          or app_private.has_tenant_role(p_tenant, array['owner', 'admin']::public.membership_role[])) then
    raise exception 'not authorised' using errcode = 'insufficient_privilege';
  end if;
  return query
  select
    coalesce(sum(u.cost_usd) filter (where u.tenant_id = p_tenant
                                       and u.occurred_at >= date_trunc('day', now())), 0),
    coalesce(sum(u.cost_usd) filter (where u.occurred_at >= date_trunc('day', now())), 0),
    coalesce(sum(u.cost_usd) filter (where u.occurred_at >= date_trunc('month', now())), 0),
    coalesce(sum(u.cost_usd) filter (where u.tenant_id = p_tenant
                                       and u.occurred_at >= date_trunc('month', now())), 0)
  from public.usage_events u
  where u.occurred_at >= date_trunc('month', now()) - interval '1 day';
end;
$$;
revoke all on function app_private.ai_spend_for(uuid) from public, anon, authenticated;
grant execute on function app_private.ai_spend_for(uuid) to engage_app;

-- ----- knowledge versions: images and how the text was obtained ------------------------------------
alter table public.knowledge_document_versions
  drop constraint knowledge_document_versions_detected_type_check;
alter table public.knowledge_document_versions
  add constraint knowledge_document_versions_detected_type_check
  check (detected_type in ('pdf', 'docx', 'text', 'image'));
alter table public.knowledge_document_versions
  add column extraction_method text not null default 'text'
  check (extraction_method in ('text', 'vision'));
alter table public.knowledge_document_versions
  add constraint knowledge_versions_image_needs_vision
  check (detected_type <> 'image' or extraction_method = 'vision');
grant insert (extraction_method) on public.knowledge_document_versions to engage_app;

create or replace function app_private.knowledge_version_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Content and identity are immutable; only the review decision may change, once.
  if (new.tenant_id, new.document_id, new.version_no, new.file_name, new.detected_type,
      new.size_bytes, new.sha256, new.storage_path, new.page_count, new.extraction_error,
      new.extraction_method)
     is distinct from
     (old.tenant_id, old.document_id, old.version_no, old.file_name, old.detected_type,
      old.size_bytes, old.sha256, old.storage_path, old.page_count, old.extraction_error,
      old.extraction_method)
     or new.extracted_text is distinct from old.extracted_text then
    raise exception 'document versions are immutable' using errcode = 'insufficient_privilege';
  end if;
  if new.status is distinct from old.status then
    if not (old.status = 'extracted' and new.status in ('approved', 'rejected')) then
      raise exception 'invalid status transition % -> %', old.status, new.status
        using errcode = 'check_violation';
    end if;
    new.reviewed_by := app_private.current_user_id();
    new.reviewed_at := now();
  else
    new.reviewed_by := old.reviewed_by;
    new.reviewed_at := old.reviewed_at;
    new.review_note := old.review_note;
  end if;
  return new;
end;
$$;
revoke all on function app_private.knowledge_version_before_update() from public, anon, authenticated;

-- ----- plan catalogue ---------------------------------------------------------------------------
insert into public.features (key, name, description, available, sort_order) values
  ('document_reading', 'Reading scanned documents',
   'AI reads photos and scanned PDFs uploaded to the knowledge base; staff review the text.', true, 25)
on conflict (key) do nothing;

insert into public.plan_features (plan_key, feature_key)
select p.key, 'document_reading' from public.plans p
on conflict do nothing;
