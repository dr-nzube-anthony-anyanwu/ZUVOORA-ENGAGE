-- Phase 6 (founder decision D3): patient booking emails carry the clinic's name as sender and,
-- when the clinic has PUBLISHED an email address on its profile, a Reply-To with that address,
-- so a patient's reply reaches the clinic instead of an unattended platform mailbox.
--
-- job_booking() gains one column, clinic_email, taken from the PUBLISHED profile only (like
-- clinic_phone). A function's result columns cannot be changed in place, so it is recreated with
-- the same argument list, security settings and grants.

drop function app_private.job_booking(uuid);

create function app_private.job_booking(p_appointment uuid)
returns table (tenant_id uuid, clinic text, clinic_time_zone text, clinic_phone text,
               clinic_email text,
               type_name text, start_at timestamptz, end_at timestamptz, status text,
               attendee_name text, attendee_email text, attendee_time_zone text,
               conversation_id uuid)
language sql stable security definer
set search_path = ''
as $$
  select a.tenant_id, t.display_name, t.timezone, p.published->>'public_phone',
         p.published->>'public_email',
         a.type_name, a.start_at, a.end_at, a.status, a.attendee_name, a.attendee_email,
         a.attendee_time_zone, a.conversation_id
    from public.appointments a
    join public.tenants t on t.id = a.tenant_id
    left join public.clinic_profiles p on p.tenant_id = a.tenant_id
   where a.id = p_appointment and t.status in ('pending', 'active');
$$;

revoke all on function app_private.job_booking(uuid) from public, anon, authenticated;
grant execute on function app_private.job_booking(uuid) to engage_jobs;
