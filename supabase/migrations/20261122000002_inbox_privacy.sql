-- Phase 3e: least privilege for patient conversations (ADR-030).
--
-- Message text and handover contact details are patient data. They are now readable only by the
-- clinic's front desk (owner, admin, receptionist), who handle them. Viewers (read-only staff)
-- and platform admins keep conversation metadata (status, counts, times) but not the content.
-- Support access to content, if ever needed, must be an explicit, audited feature.

drop policy messages_staff_select on public.messages;
create policy messages_staff_select on public.messages for select to engage_app
  using (app_private.has_tenant_role(
    tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]));

drop policy handover_staff_select on public.handover_requests;
create policy handover_staff_select on public.handover_requests for select to engage_app
  using (app_private.has_tenant_role(
    tenant_id, array['owner', 'admin', 'receptionist']::public.membership_role[]));

-- Inbox queries: newest first per clinic and status.
create index if not exists conversations_tenant_status_recent_idx
  on public.conversations (tenant_id, status, last_message_at desc);
