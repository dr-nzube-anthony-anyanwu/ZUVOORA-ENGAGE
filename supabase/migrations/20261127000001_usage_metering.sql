-- Phase 5b: usage metering, quotas and quota alerts (ADR-039).
--
-- * Monthly counters (UTC months) per clinic, written ONLY by database triggers on the events
--   themselves, so nothing can be missed or double-counted by application code:
--     messages  <- a visitor message is stored
--     ai_usd / ai_tokens <- an AI usage row is recorded (cost as charged by the provider)
--     bookings  <- an appointment first becomes confirmed or pending
--     emails    <- an email job completes (suppressed/log-only sends are not counted)
-- * Crossing 80% and 100% of a plan limit queues one alert email per clinic, metric, month and
--   threshold (job idempotency key).
-- * Enforcement ("soft for safety, hard for cost"): the API stops AI answers when messages or
--   AI spend reach the limit and pauses new bookings at the bookings limit; emails only warn.

create table app_private.usage_counters (
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  period_month date not null check (extract(day from period_month) = 1),
  metric text not null check (metric in ('messages', 'ai_usd', 'ai_tokens', 'emails', 'bookings')),
  quantity numeric(18, 6) not null default 0 check (quantity >= 0),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, period_month, metric)
);
revoke all on app_private.usage_counters from public, anon, authenticated, service_role;

alter table app_private.jobs drop constraint jobs_kind_check;
alter table app_private.jobs add constraint jobs_kind_check check (kind in
  ('handover_alert', 'domain_lapsed', 'booking_confirmation', 'booking_alert', 'booking_reconcile',
   'booking_reminder', 'booking_cancelled', 'quota_alert'));

create or replace function app_private.current_period() returns date
language sql stable set search_path = ''
as $$ select date_trunc('month', now() at time zone 'UTC')::date $$;

-- Which plan limit governs a metered quantity.
create or replace function app_private.metric_limit_key(p_metric text) returns text
language sql immutable set search_path = ''
as $$
  select case p_metric
    when 'messages' then 'messages_month' when 'ai_usd' then 'ai_usd_month'
    when 'emails' then 'emails_month' when 'bookings' then 'bookings_month' end
$$;

create or replace function app_private.meter(p_tenant uuid, p_metric text, p_qty numeric)
returns void
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v_period date := app_private.current_period();
  v_new numeric;
  v_old numeric;
  v_limit numeric;
  v_threshold integer;
begin
  if p_tenant is null or p_qty is null or p_qty <= 0 then
    return;
  end if;
  insert into app_private.usage_counters (tenant_id, period_month, metric, quantity)
  values (p_tenant, v_period, p_metric, p_qty)
  on conflict (tenant_id, period_month, metric)
  do update set quantity = app_private.usage_counters.quantity + excluded.quantity, updated_at = now()
  returning quantity into v_new;
  v_old := v_new - p_qty;

  v_limit := app_private.limit_internal(p_tenant, app_private.metric_limit_key(p_metric));
  if v_limit is null or v_limit <= 0 then
    return;
  end if;
  foreach v_threshold in array array[80, 100] loop
    if v_old < v_limit * v_threshold / 100.0 and v_new >= v_limit * v_threshold / 100.0 then
      perform app_private.enqueue_job('quota_alert', p_tenant,
        jsonb_build_object('metric', p_metric, 'threshold', v_threshold,
                           'period', to_char(v_period, 'YYYY-MM'), 'limit', v_limit),
        'quota_alert/' || p_tenant::text || '/' || p_metric || '/' || to_char(v_period, 'YYYY-MM')
          || '/' || v_threshold::text);
    end if;
  end loop;
end;
$$;
revoke all on function app_private.meter(uuid, text, numeric) from public, anon, authenticated;
revoke all on function app_private.current_period() from public, anon, authenticated;
revoke all on function app_private.metric_limit_key(text) from public, anon, authenticated;

-- ----- metering triggers ---------------------------------------------------------------------
create or replace function app_private.meter_message() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if new.role = 'visitor' then
    perform app_private.meter(new.tenant_id, 'messages', 1);
  end if;
  return null;
end;
$$;
create trigger messages_meter after insert on public.messages
  for each row execute function app_private.meter_message();

create or replace function app_private.meter_ai() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  perform app_private.meter(new.tenant_id, 'ai_usd', new.cost_usd);
  perform app_private.meter(new.tenant_id, 'ai_tokens', new.prompt_tokens + new.completion_tokens);
  return null;
end;
$$;
create trigger usage_events_meter after insert on public.usage_events
  for each row execute function app_private.meter_ai();

create or replace function app_private.meter_booking() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if new.status in ('confirmed', 'pending') and old.status in ('booking', 'unknown') then
    perform app_private.meter(new.tenant_id, 'bookings', 1);
  end if;
  return null;
end;
$$;
create trigger appointments_meter after update on public.appointments
  for each row execute function app_private.meter_booking();

-- complete_job (Phase 4a) now also meters sent emails.
create or replace function app_private.complete_job(p_job bigint, p_result jsonb default null)
returns void
language plpgsql volatile security definer
set search_path = ''
as $$
declare
  v app_private.jobs%rowtype;
  v_message text;
begin
  update app_private.jobs
     set status = 'done', result = p_result, finished_at = now(), locked_until = null,
         last_error = null
   where id = p_job and status = 'running'
  returning * into v;
  if not found then
    return;
  end if;
  v_message := coalesce(p_result ->> 'message_id', '');
  if v.kind <> 'booking_reconcile' and v_message <> ''
     and v_message not like 'log:%' and v_message not like 'suppressed:%' then
    perform app_private.meter(v.tenant_id, 'emails', 1);
  end if;
end;
$$;

revoke all on function app_private.meter_message() from public, anon, authenticated;
revoke all on function app_private.meter_ai() from public, anon, authenticated;
revoke all on function app_private.meter_booking() from public, anon, authenticated;

-- ----- reading usage ---------------------------------------------------------------------------
create or replace function app_private.usage_internal(p_tenant uuid, p_period date)
returns table (metric text, quantity numeric)
language sql stable security definer set search_path = ''
as $$
  select c.metric, c.quantity from app_private.usage_counters c
   where c.tenant_id = p_tenant and c.period_month = p_period;
$$;

-- Owners/admins of the clinic, or MFA platform admins.
create or replace function app_private.tenant_usage(p_tenant uuid, p_period date default null)
returns table (metric text, quantity numeric)
language sql stable security definer set search_path = ''
as $$
  select u.* from app_private.usage_internal(p_tenant, coalesce(p_period, app_private.current_period())) u
   where app_private.has_tenant_role(p_tenant, array['owner', 'admin']::public.membership_role[])
      or app_private.is_platform_admin();
$$;

-- The widget: is its own clinic at or over a monthly limit?
create or replace function app_private.widget_quota_reached(p_metric text)
returns boolean
language sql stable security definer set search_path = ''
as $$
  select coalesce((
    select u.quantity >= l.cap
      from (select app_private.limit_internal(app_private.widget_tenant(),
                                              app_private.metric_limit_key(p_metric)) as cap) l
      join app_private.usage_internal(app_private.widget_tenant(), app_private.current_period()) u
        on u.metric = p_metric
     where l.cap is not null), false);
$$;

-- Quota alert email data (worker): clinic name and whether the clinic is still served.
create or replace function app_private.job_quota_alert(p_tenant uuid)
returns table (clinic text, plan_name text)
language sql stable security definer set search_path = ''
as $$
  select t.display_name, p.name
    from public.tenants t
    join public.tenant_subscriptions s on s.tenant_id = t.id
    join public.plans p on p.key = s.plan_key
   where t.id = p_tenant and t.status in ('pending', 'active') and s.status <> 'cancelled';
$$;

revoke all on function app_private.usage_internal(uuid, date) from public, anon, authenticated;
revoke all on function app_private.tenant_usage(uuid, date) from public, anon, authenticated;
revoke all on function app_private.widget_quota_reached(text) from public, anon, authenticated;
revoke all on function app_private.job_quota_alert(uuid) from public, anon, authenticated;
grant execute on function app_private.tenant_usage(uuid, date) to engage_app;
grant execute on function app_private.widget_quota_reached(text) to engage_widget;
grant execute on function app_private.job_quota_alert(uuid) to engage_jobs;
