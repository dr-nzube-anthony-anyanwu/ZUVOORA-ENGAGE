# Local Development

Everything runs on your machine against a **local** Supabase stack in Docker. No cloud
accounts or real secrets are needed. Use synthetic data only — never real patient data.

Requirements: Python 3.12, Node.js 24 LTS (`.nvmrc`), Docker Desktop running.

## 1. Local Supabase (repository root)
```powershell
npm ci                 # installs the pinned Supabase CLI
npm run db:start       # Postgres + Auth + Mailpit; applies supabase/migrations and supabase/seed.sql
npm run env:local      # writes apps/api/.env and apps/web/.env.local from the local stack
npm run db:test        # pgTAP tenancy / RLS / audit tests
npm run db:lint        # Supabase schema linter
npm run db:reset       # re-create the local DB from migrations (destroys LOCAL data only)
npm run db:stop
```
Local URLs: API gateway `http://127.0.0.1:54321`, Studio `http://127.0.0.1:54323`,
Mailpit (catches all local emails, e.g. invitations) `http://127.0.0.1:54324`.

`env:local` refuses to run against anything but localhost, never overwrites existing files and
never prints keys. The generated files are gitignored.

## 2. API
```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .
pytest                       # unit tests + integration tests (skipped if the local stack is down)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8073
```
Integration tests create synthetic `@example.com` users and clinics on the local stack and
delete them afterwards. They refuse to run against a non-localhost Supabase.

## 3. Dashboard
```powershell
cd apps\web
npm ci
npm run lint
npm run typecheck
npm run build
npm run check:bundle         # fails if a server secret appears in browser files
npm run dev
```

## 4. Create a local platform admin (to try the dashboard)
Self-signup is disabled. Create a user in local Studio (Authentication → Add user, tick
"Auto confirm"), then in Studio's SQL editor:
```sql
insert into public.platform_admins (user_id, note)
select id, 'local dev admin' from auth.users where email = 'you@example.com';
```
Sign in at `http://localhost:3073/login`, then set up two-factor authentication at `/mfa`.
Platform actions (create/suspend clinics) require the MFA-verified session.

## 4b. Dashboard end-to-end tests (Playwright)
Real browser -> dashboard (production build) -> API -> local Supabase. Synthetic users and two
clinics are created before the run and removed afterwards (including stored files). The run
refuses to start unless Supabase is on localhost. Ports 8073 and 3073 must be free.
```powershell
cd apps\web
npx playwright install chromium   # first time only
npm run build
npm run test:e2e
```
CI runs the same tests in the `database-and-api` job.

## 5. Widget
```powershell
cd apps\widget
npm ci
npm run build
```

## 6. Docker Compose (optional)
Requires a root `.env` copied from `.env.example` with real values for the target environment.
```powershell
docker compose config
docker compose build
```
