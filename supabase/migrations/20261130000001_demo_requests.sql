-- Demo and pilot requests from the public website (design track D3, ADR-042).
--
-- * Minimal business-contact fields; no health or patient information is asked for.
-- * Visitors cannot read anything back. The public API inserts only through
--   app_private.submit_demo_request() (role engage_widget, no tenant), after rate limiting.
-- * Only MFA platform admins (ZubeVision) can read requests and update their status.
-- * Each new request queues one notification job; the email carries no contact details.
-- * Requests are kept for 12 months (purge_demo_requests, run with the finished-jobs purge).

create table public.demo_requests (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 2 and 120),
  role text check (char_length(role) <= 80),
  clinic_name text not null check (char_length(clinic_name) between 2 and 160),
  city text check (char_length(city) <= 80),
  country text check (char_length(country) <= 80),
  email text not null check (char_length(email) between 6 and 254
                             and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone text check (phone ~ '^[0-9+() .-]{6,30}$'),
  interest text not null default 'demo'
    check (interest in ('demo', 'pilot', 'pricing', 'accessibility', 'other')),
  message text check (char_length(message) <= 1000),
  consent_given boolean not null check (consent_given),
  status text not null default 'new' check (status in ('new', 'contacted', 'closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users (id) on delete set null
);
create index demo_requests_created_idx on public.demo_requests (created_at desc);

alter table public.demo_requests enable row level security;
alter table public.demo_requests force row level security;

create policy demo_requests_admin_select on public.demo_requests for select to engage_app
  using (app_private.is_platform_admin());
create policy demo_requests_admin_update on public.demo_requests for update to engage_app
  using (app_private.is_platform_admin()) with check (app_private.is_platform_admin());

revoke all on public.demo_requests from public, anon, authenticated, service_role;
grant select on public.demo_requests to engage_app;
grant update (status) on public.demo_requests to engage_app;

-- Only the status may change; who and when are set by the server.
create or replace function app_private.demo_request_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (new.id, new.name, new.role, new.clinic_name, new.city, new.country, new.email, new.phone,
      new.interest, new.message, new.consent_given, new.created_at)
     is distinct from
     (old.id, old.name, old.role, old.clinic_name, old.city, old.country, old.email, old.phone,
      old.interest, old.message, old.consent_given, old.created_at) then
    raise exception 'demo requests are immutable' using errcode = 'insufficient_privilege';
  end if;
  new.updated_at := now();
  new.updated_by := app_private.current_user_id();
  return new;
end;
$$;
revoke all on function app_private.demo_request_before_update() from public, anon, authenticated;
create trigger demo_requests_update before update on public.demo_requests
  for each row execute function app_private.demo_request_before_update();

-- ----- public submission (called by the API as engage_widget, after rate limiting) -------------
create or replace function app_private.submit_demo_request(
  p_name text, p_role text, p_clinic_name text, p_city text, p_country text, p_email text,
  p_phone text, p_interest text, p_message text, p_consent boolean
)
returns uuid
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  -- Only the anonymous public path (no signed-in user, no widget clinic) may submit.
  if app_private.current_user_id() is not null or app_private.widget_tenant() is not null then
    raise exception 'not allowed' using errcode = 'insufficient_privilege';
  end if;
  insert into public.demo_requests (name, role, clinic_name, city, country, email, phone,
                                    interest, message, consent_given)
  values (p_name, nullif(p_role, ''), p_clinic_name, nullif(p_city, ''), nullif(p_country, ''),
          lower(p_email), nullif(p_phone, ''), coalesce(nullif(p_interest, ''), 'demo'),
          nullif(p_message, ''), p_consent)
  returning id into v_id;
  perform app_private.enqueue_job('demo_request_alert', null, jsonb_build_object('request_id', v_id),
                                  'demo_request_alert/' || v_id::text);
  return v_id;
end;
$$;
revoke all on function app_private.submit_demo_request(text, text, text, text, text, text, text, text, text, boolean)
  from public, anon, authenticated;
grant execute on function app_private.submit_demo_request(text, text, text, text, text, text, text, text, text, boolean)
  to engage_widget;

-- ----- notification job ------------------------------------------------------------------------
alter table app_private.jobs drop constraint jobs_kind_check;
alter table app_private.jobs add constraint jobs_kind_check check (kind in
  ('handover_alert', 'domain_lapsed', 'booking_confirmation', 'booking_alert', 'booking_reconcile',
   'booking_reminder', 'booking_cancelled', 'quota_alert', 'demo_request_alert'));

-- What the notification may say: clinic, place and interest only (no contact details).
create or replace function app_private.job_demo_request(p_request uuid)
returns table (clinic_name text, city text, country text, interest text, created_at timestamptz,
               status text)
language sql stable security definer
set search_path = ''
as $$
  select d.clinic_name, d.city, d.country, d.interest, d.created_at, d.status
    from public.demo_requests d where d.id = p_request;
$$;
revoke all on function app_private.job_demo_request(uuid) from public, anon, authenticated;
grant execute on function app_private.job_demo_request(uuid) to engage_jobs;

-- ----- retention -------------------------------------------------------------------------------
create or replace function app_private.purge_demo_requests()
returns integer
language sql volatile security definer
set search_path = ''
as $$
  with gone as (
    delete from public.demo_requests where created_at < now() - interval '12 months' returning 1
  )
  select count(*)::integer from gone;
$$;
revoke all on function app_private.purge_demo_requests() from public, anon, authenticated;
grant execute on function app_private.purge_demo_requests() to engage_jobs;
