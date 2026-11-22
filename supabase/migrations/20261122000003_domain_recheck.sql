-- Phase 3f: periodic re-verification of verified website domains (ADR-031).
--
-- A domain stays verified only while its DNS TXT record stays in place. A scheduled job (role
-- engage_jobs, no user, no tenant) re-checks verified domains once a day. After 3 consecutive
-- definite failures (record missing or wrong) the domain lapses to 'pending', so the widget
-- stops on that host. Resolver errors/timeouts are recorded but never count as failures.
-- Every lapse is written to the audit log with the system actor (the nil UUID).

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'engage_jobs') then
    create role engage_jobs nologin noinherit nobypassrls;
  end if;
end;
$$;
grant engage_jobs to engage_api;
grant usage on schema app_private to engage_jobs;

alter table public.tenant_domains
  add column recheck_failures integer not null default 0
    constraint tenant_domains_recheck_failures check (recheck_failures >= 0);

-- A fresh verification starts a clean failure count.
create or replace function app_private.domain_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.tenant_id is distinct from old.tenant_id
     or new.hostname is distinct from old.hostname
     or new.verification_token is distinct from old.verification_token then
    raise exception 'domain identity is immutable' using errcode = 'insufficient_privilege';
  end if;
  if old.removed_at is not null then
    raise exception 'removed domains cannot be changed' using errcode = 'check_violation';
  end if;

  if new.removed_at is not null then  -- removal: server-set time/actor; loses verification
    new.removed_at := now();
    new.removed_by := app_private.current_user_id();
    new.verification_status := 'pending';
  end if;

  if new.verification_status = 'verified' and old.verification_status <> 'verified' then
    new.verified_at := now();
    new.recheck_failures := 0;
  elsif new.verification_status <> 'verified' then
    new.verified_at := null;
  else
    new.verified_at := old.verified_at;
  end if;

  new.updated_at := now();
  return new;
end;
$$;

create index if not exists tenant_domains_recheck_idx
  on public.tenant_domains (last_checked_at nulls first)
  where verification_status = 'verified' and removed_at is null;

-- Verified domains not checked within the interval, oldest first. Only active/pending clinics.
create or replace function app_private.domains_due_for_recheck(
  p_limit integer, p_interval interval default interval '20 hours'
)
returns table (id uuid, hostname text, verification_token text)
language sql stable security definer
set search_path = ''
as $$
  select d.id, d.hostname, d.verification_token
    from public.tenant_domains d
    join public.tenants t on t.id = d.tenant_id
   where d.verification_status = 'verified'
     and d.removed_at is null
     and t.status in ('pending', 'active')
     and (d.last_checked_at is null or d.last_checked_at < now() - p_interval)
   order by d.last_checked_at nulls first, d.id
   limit least(greatest(p_limit, 1), 500);
$$;

-- Record one re-check. Returns the domain's status afterwards ('verified' or 'pending').
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
    return null;  -- removed or no longer verified meanwhile: nothing to do
  end if;

  v_failures := case
    when p_result = 'verified' then 0
    when p_result in ('not_found', 'mismatch') then v.recheck_failures + 1
    else v.recheck_failures  -- resolver trouble is not evidence against the clinic
  end;

  update public.tenant_domains
     set last_checked_at = now(),
         last_check_result = p_result,
         check_count = check_count + 1,
         recheck_failures = v_failures,
         verification_status = case when v_failures >= greatest(p_lapse_after, 1)
                                    then 'pending'
                                    else verification_status end
   where id = p_domain;

  if v_failures >= greatest(p_lapse_after, 1) then
    insert into public.audit_events
      (actor_user_id, tenant_id, action, target_type, target_id, request_id, metadata)
    values ('00000000-0000-0000-0000-000000000000', v.tenant_id, 'domain.verification_lapsed',
            'domain', p_domain::text, p_run_id,
            jsonb_build_object('hostname', v.hostname, 'result', p_result, 'failures', v_failures));
    return 'pending';
  end if;
  return 'verified';
end;
$$;

revoke all on function app_private.domains_due_for_recheck(integer, interval) from public, anon, authenticated;
revoke all on function app_private.record_domain_recheck(uuid, text, text, integer) from public, anon, authenticated;
grant execute on function app_private.domains_due_for_recheck(integer, interval) to engage_jobs;
grant execute on function app_private.record_domain_recheck(uuid, text, text, integer) to engage_jobs;
