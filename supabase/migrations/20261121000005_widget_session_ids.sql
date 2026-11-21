-- ZUVOORA Engage — Phase 3b: the API chooses a new conversation's id (uuid4) and sets it as the
-- widget context before inserting, so `insert ... returning` satisfies the visitor-only SELECT
-- policy. The id is generated server-side; it never comes from the visitor.
grant insert (id) on public.conversations to engage_widget;

-- Messages and the usage ledger stay immutable (no UPDATE for anyone) and undeletable by the
-- application roles, but the database owner may delete them, so tenant deletion and lawful
-- data-deletion/retention jobs work (cascades from conversations/tenants). The audit log keeps
-- its stricter rule (no deletion by anyone).
create or replace function app_private.reject_app_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE'
     or current_user in ('engage_app', 'engage_widget', 'engage_api', 'authenticated', 'anon',
                         'service_role') then
    raise exception '% is append-only', tg_table_name using errcode = 'insufficient_privilege';
  end if;
  return old;
end;
$$;
revoke all on function app_private.reject_app_mutation() from public, anon, authenticated;

drop trigger messages_append_only on public.messages;
drop trigger usage_events_append_only on public.usage_events;
create trigger messages_append_only before update or delete on public.messages
  for each row execute function app_private.reject_app_mutation();
create trigger usage_events_append_only before update or delete on public.usage_events
  for each row execute function app_private.reject_app_mutation();
drop function app_private.reject_mutation();
