-- LOCAL DEVELOPMENT ONLY. Runs on `supabase db reset` / `supabase start`, never on the cloud project.
-- Sets a known password for the backend connection role on the local stack only.
-- For the cloud project, the founder sets a strong unique password directly in the SQL editor.
alter role engage_api with password 'local-dev-only-engage-api';
