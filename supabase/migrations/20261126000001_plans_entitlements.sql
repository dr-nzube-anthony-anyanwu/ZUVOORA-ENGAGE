-- Phase 5a: plan catalogue, tenant subscriptions and the central entitlement check (ADR-038).
--
-- * Four tiers (founder decision 2026-11-22): Essentials, Professional, Premium (ZUVOORA Engage)
--   and Full ZUVOORA (ecosystem). Live booking in every tier; tiers differ in reminders,
--   analytics, channels and limits. Features not built yet are catalogued with available = false
--   and are never granted as working.
-- * Every clinic always has exactly one subscription (trigger on tenant creation). Only MFA
--   platform admins change catalogue or subscriptions; clinic owners/admins can read their own.
-- * app_private.entitlements_internal() is the single source of truth. The API, the widget role
--   and database triggers all ask it; a frontend flag is never authorisation.
-- * A cancelled subscription keeps all data but grants nothing: the widget stops, exactly like a
--   suspension (widget_tenant_active / resolve_widget now require the chat_widget feature).

create table public.features (
  key text primary key check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
  name text not null check (char_length(name) between 1 and 80),
  description text check (char_length(description) <= 300),
  available boolean not null default true,
  sort_order integer not null default 0
);

create table public.plans (
  key text primary key check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
  name text not null check (char_length(name) between 1 and 80),
  description text check (char_length(description) <= 500),
  tier_order integer not null unique check (tier_order between 1 and 100),
  monthly_price_ngn integer check (monthly_price_ngn >= 0),
  setup_fee_ngn integer check (setup_fee_ngn >= 0),
  is_public boolean not null default true,
  updated_at timestamptz not null default now()
);

create table public.plan_features (
  plan_key text not null references public.plans (key) on delete cascade,
  feature_key text not null references public.features (key) on delete cascade,
  primary key (plan_key, feature_key)
);

-- Limit keys are fixed: each one is enforced somewhere in code or the database.
create table public.plan_limits (
  plan_key text not null references public.plans (key) on delete cascade,
  limit_key text not null check (limit_key in ('messages_month', 'ai_usd_month', 'emails_month',
    'bookings_month', 'documents', 'staff_seats', 'domains', 'branches')),
  value numeric(14, 2) not null check (value >= 0),
  primary key (plan_key, limit_key)
);

create table public.tenant_subscriptions (
  tenant_id uuid primary key references public.tenants (id) on delete cascade,
  plan_key text not null references public.plans (key),
  status text not null default 'trialing'
    check (status in ('trialing', 'active', 'past_due', 'cancelled')),
  started_at timestamptz not null default now(),
  current_period_end timestamptz,
  monthly_price_override_ngn integer check (monthly_price_override_ngn >= 0),
  notes text check (char_length(notes) <= 500),
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users (id) on delete set null
);

create table public.tenant_overrides (
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  kind text not null check (kind in ('feature', 'limit')),
  key text not null check (char_length(key) between 1 and 40),
  feature_enabled boolean,
  limit_value numeric(14, 2) check (limit_value >= 0),
  reason text not null check (char_length(reason) between 3 and 300),
  created_at timestamptz not null default now(),
  created_by uuid references auth.users (id) on delete set null,
  primary key (tenant_id, kind, key),
  check ((kind = 'feature') = (feature_enabled is not null)),
  check ((kind = 'limit') = (limit_value is not null))
);

-- ----- seed: catalogue (editable later by platform admins) -----------------------------------
insert into public.features (key, name, description, available, sort_order) values
  ('chat_widget', 'Website chat widget', 'The chat assistant on the clinic''s verified website.', true, 10),
  ('knowledge_base', 'Knowledge base', 'Clinic profile, branches, services, FAQs and documents.', true, 20),
  ('ai_answers', 'AI answers', 'Answers grounded in the clinic''s published content.', true, 30),
  ('inbox_handover', 'Inbox and call-backs', 'Conversation inbox and call-back requests.', true, 40),
  ('booking', 'Online booking', 'Live booking through Cal.com or Calendly, with confirmations and cancellations.', true, 50),
  ('reminders', 'Appointment reminders', 'Reminders 24 hours (and optionally 2 hours) before.', true, 60),
  ('analytics_basic', 'Basic analytics', 'Conversations, answers, call-backs and bookings.', true, 70),
  ('analytics_full', 'Full analytics', 'Daily trends, rates, AI cost and unanswered topics.', true, 80),
  ('whatsapp', 'WhatsApp', 'WhatsApp conversations (not yet available).', false, 90),
  ('voice_ai', 'Voice AI', 'Voice assistant (not yet available).', false, 100),
  ('ecosystem', 'ZUVOORA ecosystem', 'Integration with the wider ZUVOORA platform (not yet available).', false, 110);

insert into public.plans (key, name, description, tier_order, monthly_price_ngn, setup_fee_ngn) values
  ('essentials', 'Essentials', 'Website assistant, knowledge base, inbox and live booking.', 1, 20000, 175000),
  ('professional', 'Professional', 'Essentials plus reminders, full analytics and WhatsApp (when available).', 2, 42500, 300000),
  ('premium', 'Premium', 'Professional plus voice AI (when available), multi-branch and higher limits.', 3, 82500, 600000),
  ('full_zuvoora', 'Full ZUVOORA', 'The complete ZUVOORA ecosystem. Pricing on request.', 4, null, null);

insert into public.plan_features (plan_key, feature_key)
select p.key, f.key from public.plans p cross join public.features f
 where f.key in ('chat_widget', 'knowledge_base', 'ai_answers', 'inbox_handover', 'booking', 'analytics_basic')
    or (f.key in ('reminders', 'analytics_full', 'whatsapp') and p.tier_order >= 2)
    or (f.key = 'voice_ai' and p.tier_order >= 3)
    or (f.key = 'ecosystem' and p.tier_order >= 4);

insert into public.plan_limits (plan_key, limit_key, value)
select p.key, l.key, (array[l.t1, l.t2, l.t3, l.t4])[p.tier_order]
  from public.plans p
 cross join (values
   ('messages_month', 2000, 5000, 15000, 50000),
   ('ai_usd_month', 2, 5, 10, 20),
   ('emails_month', 300, 1500, 5000, 15000),
   ('bookings_month', 100, 400, 1500, 5000),
   ('documents', 10, 30, 100, 300),
   ('staff_seats', 3, 10, 25, 100),
   ('domains', 1, 3, 10, 10),
   ('branches', 1, 3, 20, 50)
 ) as l(key, t1, t2, t3, t4);

-- ----- every clinic has a subscription ---------------------------------------------------------
create or replace function app_private.tenant_after_insert_subscription()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  insert into public.tenant_subscriptions (tenant_id, plan_key, status, current_period_end)
  values (new.id, 'essentials', 'trialing', now() + interval '30 days')
  on conflict (tenant_id) do nothing;
  return null;
end;
$$;
revoke all on function app_private.tenant_after_insert_subscription() from public, anon, authenticated;
create trigger tenants_default_subscription after insert on public.tenants
  for each row execute function app_private.tenant_after_insert_subscription();

-- Backfill: the founder's demo clinic gets the full catalogue; any other existing clinic a trial.
insert into public.tenant_subscriptions (tenant_id, plan_key, status, current_period_end)
select t.id,
       case when t.display_name ilike 'ZUVOORA Demo%' then 'full_zuvoora' else 'essentials' end,
       case when t.display_name ilike 'ZUVOORA Demo%' then 'active' else 'trialing' end,
       case when t.display_name ilike 'ZUVOORA Demo%' then null else now() + interval '30 days' end
  from public.tenants t
on conflict (tenant_id) do nothing;

create or replace function app_private.subscription_before_update()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.tenant_id is distinct from old.tenant_id then
    raise exception 'a subscription cannot move between clinics' using errcode = 'insufficient_privilege';
  end if;
  new.updated_at := now();
  new.updated_by := app_private.current_user_id();
  return new;
end;
$$;
create trigger tenant_subscriptions_before_update before update on public.tenant_subscriptions
  for each row execute function app_private.subscription_before_update();

create or replace function app_private.override_before_insert()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.created_at := now();
  new.created_by := app_private.current_user_id();
  return new;
end;
$$;
create trigger tenant_overrides_before_insert before insert on public.tenant_overrides
  for each row execute function app_private.override_before_insert();
revoke all on function app_private.subscription_before_update() from public, anon, authenticated;
revoke all on function app_private.override_before_insert() from public, anon, authenticated;

-- ----- the central entitlement check -----------------------------------------------------------
-- Internal (not granted to any role): used by the wrappers below and by database triggers.
create or replace function app_private.entitlements_internal(p_tenant uuid)
returns table (plan_key text, plan_name text, status text, features text[], limits jsonb)
language sql stable security definer
set search_path = ''
as $$
  select s.plan_key, p.name, s.status,
         case when s.status = 'cancelled' then array[]::text[] else coalesce((
           select array_agg(f.key order by f.sort_order)
             from public.features f
            where f.available
              and coalesce(
                    (select o.feature_enabled from public.tenant_overrides o
                      where o.tenant_id = s.tenant_id and o.kind = 'feature' and o.key = f.key),
                    exists (select 1 from public.plan_features pf
                             where pf.plan_key = s.plan_key and pf.feature_key = f.key))
         ), array[]::text[]) end,
         coalesce((select jsonb_object_agg(l.limit_key, coalesce(o.limit_value, l.value))
                     from public.plan_limits l
                     left join public.tenant_overrides o
                       on o.tenant_id = s.tenant_id and o.kind = 'limit' and o.key = l.limit_key
                    where l.plan_key = s.plan_key), '{}'::jsonb)
    from public.tenant_subscriptions s
    join public.plans p on p.key = s.plan_key
   where s.tenant_id = p_tenant;
$$;

create or replace function app_private.has_feature_internal(p_tenant uuid, p_feature text)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce((select p_feature = any (e.features)
                     from app_private.entitlements_internal(p_tenant) e), false);
$$;

create or replace function app_private.limit_internal(p_tenant uuid, p_key text)
returns numeric
language sql stable security definer
set search_path = ''
as $$
  select (e.limits ->> p_key)::numeric from app_private.entitlements_internal(p_tenant) e;
$$;

-- Staff: their own clinic (any member) or an MFA platform admin.
create or replace function app_private.tenant_entitlements(p_tenant uuid)
returns table (plan_key text, plan_name text, status text, features text[], limits jsonb)
language sql stable security definer
set search_path = ''
as $$
  select e.* from app_private.entitlements_internal(p_tenant) e
   where app_private.has_tenant_role(p_tenant) or app_private.is_platform_admin();
$$;

-- The widget: its own clinic only.
create or replace function app_private.widget_has_feature(p_feature text)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select app_private.has_feature_internal(app_private.widget_tenant(), p_feature);
$$;

create or replace function app_private.widget_limit(p_key text)
returns numeric
language sql stable security definer
set search_path = ''
as $$
  select app_private.limit_internal(app_private.widget_tenant(), p_key);
$$;

revoke all on function app_private.entitlements_internal(uuid) from public, anon, authenticated;
revoke all on function app_private.has_feature_internal(uuid, text) from public, anon, authenticated;
revoke all on function app_private.limit_internal(uuid, text) from public, anon, authenticated;
revoke all on function app_private.tenant_entitlements(uuid) from public, anon, authenticated;
revoke all on function app_private.widget_has_feature(text) from public, anon, authenticated;
revoke all on function app_private.widget_limit(text) from public, anon, authenticated;
grant execute on function app_private.tenant_entitlements(uuid) to engage_app;
grant execute on function app_private.widget_has_feature(text), app_private.widget_limit(text)
  to engage_widget;

-- ----- the widget stops for a cancelled subscription (like a suspension) -----------------------
create or replace function app_private.widget_tenant_active()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.tenants t
    where t.id = app_private.widget_tenant() and t.status = 'active'
  ) and app_private.has_feature_internal(app_private.widget_tenant(), 'chat_widget');
$$;

create or replace function app_private.resolve_widget(p_public_key text, p_host text)
returns table (tenant_id uuid, greeting text, display_name text)
language sql stable security definer
set search_path = ''
as $$
  select w.tenant_id, w.greeting, t.display_name
  from public.widget_configs w
  join public.tenants t on t.id = w.tenant_id
  where w.public_key = p_public_key
    and w.enabled
    and t.status = 'active'
    and app_private.has_feature_internal(w.tenant_id, 'chat_widget')
    and exists (
      select 1 from public.tenant_domains d
      where d.tenant_id = w.tenant_id and d.hostname = lower(p_host)
        and d.verification_status = 'verified' and d.removed_at is null
    );
$$;

-- ----- reminders only where the plan includes them --------------------------------------------
create or replace function app_private.appointment_after_update()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
declare
  v_2h boolean;
begin
  if new.status in ('confirmed', 'pending') and old.status in ('booking', 'unknown') then
    perform app_private.enqueue_job('booking_confirmation', new.tenant_id,
      jsonb_build_object('appointment_id', new.id), 'booking_confirmation/' || new.id::text);
    perform app_private.enqueue_job('booking_alert', new.tenant_id,
      jsonb_build_object('appointment_id', new.id), 'booking_alert/' || new.id::text);
  elsif new.status = 'unknown' and old.status = 'booking' then
    perform app_private.enqueue_job('booking_reconcile', new.tenant_id,
      jsonb_build_object('appointment_id', new.id, 'attempt', 1),
      'booking_reconcile/' || new.id::text || '/1', now() + interval '1 minute');
  end if;

  if new.status = 'confirmed' and old.status is distinct from 'confirmed'
     and app_private.has_feature_internal(new.tenant_id, 'reminders') then
    if new.start_at - interval '24 hours' > now() + interval '15 minutes' then
      perform app_private.enqueue_job('booking_reminder', new.tenant_id,
        jsonb_build_object('appointment_id', new.id, 'start_at', new.start_at, 'lead', '24h'),
        'booking_reminder/' || new.id::text || '/24h', new.start_at - interval '24 hours');
    end if;
    select c.reminder_2h into v_2h from public.scheduling_connections c where c.id = new.connection_id;
    if coalesce(v_2h, false) and new.start_at - interval '2 hours' > now() + interval '5 minutes' then
      perform app_private.enqueue_job('booking_reminder', new.tenant_id,
        jsonb_build_object('appointment_id', new.id, 'start_at', new.start_at, 'lead', '2h'),
        'booking_reminder/' || new.id::text || '/2h', new.start_at - interval '2 hours');
    end if;
  end if;

  if new.status in ('cancelled', 'rescheduled', 'failed') and old.status is distinct from new.status then
    perform app_private.skip_appointment_jobs(new.id, 'appointment ' || new.status);
    if new.status = 'cancelled' then
      perform app_private.enqueue_job('booking_cancelled', new.tenant_id,
        jsonb_build_object('appointment_id', new.id), 'booking_cancelled/' || new.id::text);
    end if;
  end if;
  return null;
end;
$$;

-- ----- RLS -------------------------------------------------------------------------------------
alter table public.features enable row level security;
alter table public.features force row level security;
alter table public.plans enable row level security;
alter table public.plans force row level security;
alter table public.plan_features enable row level security;
alter table public.plan_features force row level security;
alter table public.plan_limits enable row level security;
alter table public.plan_limits force row level security;
alter table public.tenant_subscriptions enable row level security;
alter table public.tenant_subscriptions force row level security;
alter table public.tenant_overrides enable row level security;
alter table public.tenant_overrides force row level security;

-- Catalogue: any signed-in staff member may read it; only MFA platform admins change it.
do $$
declare t text;
begin
  foreach t in array array['features', 'plans', 'plan_features', 'plan_limits'] loop
    execute format('create policy %I on public.%I for select to engage_app using (true)', t || '_read', t);
    execute format('create policy %I on public.%I for insert to engage_app with check (app_private.is_platform_admin())', t || '_admin_insert', t);
    execute format('create policy %I on public.%I for update to engage_app using (app_private.is_platform_admin()) with check (app_private.is_platform_admin())', t || '_admin_update', t);
    execute format('create policy %I on public.%I for delete to engage_app using (app_private.is_platform_admin())', t || '_admin_delete', t);
  end loop;
end;
$$;

create policy tenant_subscriptions_read on public.tenant_subscriptions for select to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[])
         or app_private.is_platform_admin());
create policy tenant_subscriptions_admin_insert on public.tenant_subscriptions for insert to engage_app
  with check (app_private.is_platform_admin());
create policy tenant_subscriptions_admin_update on public.tenant_subscriptions for update to engage_app
  using (app_private.is_platform_admin()) with check (app_private.is_platform_admin());

create policy tenant_overrides_read on public.tenant_overrides for select to engage_app
  using (app_private.has_tenant_role(tenant_id, array['owner', 'admin']::public.membership_role[])
         or app_private.is_platform_admin());
create policy tenant_overrides_admin_insert on public.tenant_overrides for insert to engage_app
  with check (app_private.is_platform_admin());
create policy tenant_overrides_admin_delete on public.tenant_overrides for delete to engage_app
  using (app_private.is_platform_admin());

revoke all on public.features, public.plans, public.plan_features, public.plan_limits,
  public.tenant_subscriptions, public.tenant_overrides from public, anon, authenticated, service_role;
grant select on public.features, public.plans, public.plan_features, public.plan_limits
  to engage_app;
grant update (name, description, available, sort_order) on public.features to engage_app;
grant insert (key, name, description, tier_order, monthly_price_ngn, setup_fee_ngn, is_public),
  update (name, description, monthly_price_ngn, setup_fee_ngn, is_public) on public.plans to engage_app;
grant insert, delete on public.plan_features to engage_app;
grant insert (plan_key, limit_key, value), update (value), delete on public.plan_limits to engage_app;
grant select on public.tenant_subscriptions to engage_app;
grant insert (tenant_id, plan_key, status, current_period_end, monthly_price_override_ngn, notes),
  update (plan_key, status, current_period_end, monthly_price_override_ngn, notes)
  on public.tenant_subscriptions to engage_app;
grant select on public.tenant_overrides to engage_app;
grant insert (tenant_id, kind, key, feature_enabled, limit_value, reason), delete
  on public.tenant_overrides to engage_app;
