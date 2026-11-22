-- Phase 4a: durable job queue and transactional email (ADR-033).
--
-- * Jobs live in app_private.jobs: no application role can read or write the table directly.
--   Jobs are enqueued by the database itself (triggers / functions) in the same transaction as
--   the event that causes them, so an event can never be committed without its job.
-- * The worker (role engage_jobs) claims jobs with row locks + a lease (FOR UPDATE SKIP LOCKED):
--   concurrent workers never take the same job; a crashed worker's job is re-claimed when its
--   lease expires. Each job has a unique idempotency key (also sent to the email provider).
-- * Job payloads hold ids only. Data for an email is loaded at send time through narrow
--   functions that also re-check that the job still makes sense (clinic active, recipients).
-- * Emails to staff never contain patient details: they link to the dashboard.

create table app_private.jobs (
  id bigint generated always as identity primary key,
  kind text not null check (kind in ('handover_alert', 'domain_lapsed')),
  tenant_id uuid references public.tenants (id) on delete cascade,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  idempotency_key text not null unique check (char_length(idempotency_key) between 1 and 200),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'done', 'skipped', 'dead')),
  run_at timestamptz not null default now(),
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 8 check (max_attempts between 1 and 20),
  locked_until timestamptz,
  last_error text check (char_length(last_error) <= 300),
  result jsonb check (result is null or jsonb_typeof(result) = 'object'),
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create index jobs_due_idx on app_private.jobs (run_at) where status in ('queued', 'running');
create index jobs_finished_idx on app_private.jobs (finished_at) where finished_at is not null;
revoke all on app_private.jobs from public, anon, authenticated, service_role;

-- ----- enqueue (database-internal) -------------------------------------------------------------
create or replace function app_private.enqueue_job(
  p_kind text, p_tenant uuid, p_payload jsonb, p_key text, p_run_at timestamptz default now()
)
returns void
language sql volatile security definer
set search_path = ''
as $$
  insert into app_private.jobs (kind, tenant_id, payload, idempotency_key, run_at)
  values (p_kind, p_tenant, p_payload, p_key, p_run_at)
  on conflict (idempotency_key) do nothing;
$$;
revoke all on function app_private.enqueue_job(text, uuid, jsonb, text, timestamptz)
  from public, anon, authenticated;

-- A new call-back request alerts the clinic's front desk.
create or replace function app_private.handover_after_insert()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  perform app_private.enqueue_job('handover_alert', new.tenant_id,
    jsonb_build_object('handover_id', new.id), 'handover_alert/' || new.id::text);
  return null;
end;
$$;
revoke all on function app_private.handover_after_insert() from public, anon, authenticated;
create trigger handover_requests_alert after insert on public.handover_requests
  for each row execute function app_private.handover_after_insert();

-- A lapsed domain alerts the clinic's owners/admins (re-defines the Phase 3f function).
create or replace function app_private.record_domain_recheck(
  p_domain uuid, p_result text, p_run_id text, p_lapse_after integer default 3
)
returns text
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v public.tenant_domains%rowtype;
  v_failures integer;
begin
  if p_run_id is null or p_run_id !~ '^job:[a-z_]+:[0-9a-f-]{36}$' then
    raise exception 'a job run id is required' using errcode = 'check_violation';
  end if;
  if p_result not in ('verified', 'not_found', 'mismatch', 'dns_error', 'timeout') then
    raise exception 'invalid check result' using errcode = 'check_violation';
  end if;
  select * into v from public.tenant_domains
   where id = p_domain and removed_at is null and verification_status = 'verified'
   for update;
  if not found then
    return null;
  end if;

  v_failures := case
    when p_result = 'verified' then 0
    when p_result in ('not_found', 'mismatch') then v.recheck_failures + 1
    else v.recheck_failures
  end;

  update public.tenant_domains
     set last_checked_at = now(),
         last_check_result = p_result,
         check_count = check_count + 1,
         recheck_failures = v_failures,
         verification_status = case when v_failures >= greatest(p_lapse_after, 1)
                                    then 'pending' else verification_status end
   where id = p_domain;

  if v_failures >= greatest(p_lapse_after, 1) then
    insert into public.audit_events
      (actor_user_id, tenant_id, action, target_type, target_id, request_id, metadata)
    values ('00000000-0000-0000-0000-000000000000', v.tenant_id, 'domain.verification_lapsed',
            'domain', p_domain::text, p_run_id,
            jsonb_build_object('hostname', v.hostname, 'result', p_result, 'failures', v_failures));
    perform app_private.enqueue_job('domain_lapsed', v.tenant_id,
      jsonb_build_object('domain_id', p_domain), 'domain_lapsed/' || p_domain::text || '/' || p_run_id);
    return 'pending';
  end if;
  return 'verified';
end;
$$;

-- ----- worker functions (role engage_jobs) ------------------------------------------------------
create or replace function app_private.claim_jobs(p_limit integer, p_lease_seconds integer default 120)
returns table (id bigint, kind text, tenant_id uuid, payload jsonb, idempotency_key text,
               attempts integer, created_at timestamptz)
language sql volatile security definer
set search_path = ''
as $$
  update app_private.jobs j
     set status = 'running',
         attempts = j.attempts + 1,
         locked_until = now() + make_interval(secs => greatest(p_lease_seconds, 10))
   where j.id in (
     select c.id from app_private.jobs c
      where (c.status = 'queued' and c.run_at <= now())
         or (c.status = 'running' and c.locked_until < now())
      order by c.run_at, c.id
      limit least(greatest(p_limit, 1), 100)
      for update skip locked)
  returning j.id, j.kind, j.tenant_id, j.payload, j.idempotency_key, j.attempts, j.created_at;
$$;

create or replace function app_private.complete_job(p_job bigint, p_result jsonb default null)
returns void
language sql volatile security definer
set search_path = ''
as $$
  update app_private.jobs
     set status = 'done', result = p_result, finished_at = now(), locked_until = null,
         last_error = null
   where id = p_job and status = 'running';
$$;

create or replace function app_private.skip_job(p_job bigint, p_reason text)
returns void
language sql volatile security definer
set search_path = ''
as $$
  update app_private.jobs
     set status = 'skipped', last_error = left(p_reason, 300), finished_at = now(),
         locked_until = null
   where id = p_job and status = 'running';
$$;

-- Retry with exponential backoff, unless the error is permanent, attempts are exhausted, or the
-- job is older than 23 hours (the email provider de-duplicates idempotency keys for 24 hours, so
-- a later retry could deliver twice). Returns the job's new status.
create or replace function app_private.fail_job(p_job bigint, p_error text, p_permanent boolean)
returns text
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v app_private.jobs%rowtype;
  v_status text;
begin
  select * into v from app_private.jobs where id = p_job and status = 'running' for update;
  if not found then
    return null;
  end if;
  v_status := case
    when p_permanent or v.attempts >= v.max_attempts or v.created_at < now() - interval '23 hours'
      then 'dead' else 'queued' end;
  update app_private.jobs
     set status = v_status,
         last_error = left(p_error, 300),
         locked_until = null,
         run_at = case when v_status = 'queued'
                       then now() + make_interval(secs => least(30 * power(2, v.attempts - 1), 3600)::int)
                       else run_at end,
         finished_at = case when v_status = 'dead' then now() else null end
   where id = p_job;
  return v_status;
end;
$$;

-- Housekeeping: finished jobs are kept 30 days for troubleshooting, then removed.
create or replace function app_private.purge_finished_jobs()
returns integer
language sql volatile security definer
set search_path = ''
as $$
  with gone as (
    delete from app_private.jobs
     where status in ('done', 'skipped', 'dead') and finished_at < now() - interval '30 days'
    returning 1)
  select count(*)::int from gone;
$$;

-- ----- data for emails, loaded at send time (role engage_jobs) ----------------------------------
-- Recipients: active staff of an active/pending clinic with the given roles.
create or replace function app_private.job_recipients(p_tenant uuid, p_roles public.membership_role[])
returns table (email text)
language sql stable security definer
set search_path = ''
as $$
  select distinct u.email::text
    from public.tenant_memberships m
    join public.tenants t on t.id = m.tenant_id
    join auth.users u on u.id = m.user_id
   where m.tenant_id = p_tenant and m.is_active and m.role = any (p_roles)
     and t.status in ('pending', 'active') and u.email is not null;
$$;

-- Handover alert: clinic name and whether the request is still waiting. No patient details.
create or replace function app_private.job_handover_alert(p_handover uuid)
returns table (tenant_id uuid, clinic text, timezone text, conversation_id uuid, status text,
               created_at timestamptz)
language sql stable security definer
set search_path = ''
as $$
  select h.tenant_id, t.display_name, t.timezone, h.conversation_id, h.status::text, h.created_at
    from public.handover_requests h
    join public.tenants t on t.id = h.tenant_id
   where h.id = p_handover and t.status in ('pending', 'active');
$$;

create or replace function app_private.job_domain_lapsed(p_domain uuid)
returns table (tenant_id uuid, clinic text, hostname text, still_lapsed boolean)
language sql stable security definer
set search_path = ''
as $$
  select d.tenant_id, t.display_name, d.hostname,
         (d.verification_status <> 'verified' and d.removed_at is null)
    from public.tenant_domains d
    join public.tenants t on t.id = d.tenant_id
   where d.id = p_domain and t.status in ('pending', 'active');
$$;

revoke all on function app_private.claim_jobs(integer, integer) from public, anon, authenticated;
revoke all on function app_private.complete_job(bigint, jsonb) from public, anon, authenticated;
revoke all on function app_private.skip_job(bigint, text) from public, anon, authenticated;
revoke all on function app_private.fail_job(bigint, text, boolean) from public, anon, authenticated;
revoke all on function app_private.purge_finished_jobs() from public, anon, authenticated;
revoke all on function app_private.job_recipients(uuid, public.membership_role[]) from public, anon, authenticated;
revoke all on function app_private.job_handover_alert(uuid) from public, anon, authenticated;
revoke all on function app_private.job_domain_lapsed(uuid) from public, anon, authenticated;
grant execute on function
  app_private.claim_jobs(integer, integer), app_private.complete_job(bigint, jsonb),
  app_private.skip_job(bigint, text), app_private.fail_job(bigint, text, boolean),
  app_private.purge_finished_jobs(), app_private.job_recipients(uuid, public.membership_role[]),
  app_private.job_handover_alert(uuid), app_private.job_domain_lapsed(uuid)
  to engage_jobs;
