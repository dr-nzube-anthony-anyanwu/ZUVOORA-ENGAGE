# Local Development

Everything runs on your machine against a **local** Supabase stack in Docker. No cloud
accounts or real secrets are needed. Use synthetic data only — never real patient data.

Requirements: Python 3.12, Node.js 24 LTS (`.nvmrc`), Docker Desktop running.

## Quick start — every day (after the first-time setup below)

Open **three PowerShell terminals** in VS Code (Terminal → New Terminal) and run one block in each.
Start them in this order and wait for each to be ready.

**Terminal 1 — database (repository root)**
```powershell
cd D:\technologies\ZUVOORA-ENGAGE
npm run db:start
```
Ready when it prints the local URLs (about 30–60 seconds; Docker Desktop must be running).

**Terminal 2 — API (backend)**
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8073
```
Ready when it prints `Application startup complete`. Check: http://127.0.0.1:8073/health/ready

**Terminal 3 — website and dashboard (frontend)**
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\web
npm run dev
```
Ready when it prints `Ready`. Open http://localhost:3073 (public website) and
http://localhost:3073/login (clinic and platform sign-in).

**Optional terminal 4 — background worker** (emails, reminders, alerts; needed only when you
want queued jobs to run — locally emails are only logged)
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\api
.\.venv\Scripts\python.exe -m app.worker
```

**Stopping everything:** press `Ctrl+C` in terminals 2, 3 and 4, then in terminal 1:
```powershell
npm run db:stop
```
`db:stop` keeps your local data; the next `db:start` brings it back.

| What | Address |
|---|---|
| Public website | http://localhost:3073 |
| Sign in | http://localhost:3073/login |
| API health | http://127.0.0.1:8073/health/ready |
| Supabase Studio (local database UI) | http://127.0.0.1:54323 |
| Mailpit (local emails, e.g. invitations) | http://127.0.0.1:54324 |

**Demonstrating the product to others?** Follow the [Demo guide](DEMO_GUIDE.md) — it adds a
sample clinic, demo accounts, a sample clinic website and a practice calendar.

### Troubleshooting
- **"port is already in use" (8073 or 3073):** an earlier API or dashboard is still running. Close
  that terminal, or find it with `Get-NetTCPConnection -LocalPort 3073 -State Listen` and stop that
  process.
- **`db:start` fails or hangs:** start Docker Desktop and wait until it says it is running, then try
  again.
- **The dashboard shows "The Engage service is unavailable":** the API (terminal 2) is not running.
- **`.venv` not found:** do the first-time API setup below.
- **PowerShell refuses to run scripts:** the commands above call the virtual environment's Python
  directly and do not need `Activate.ps1`. If you prefer activating it, run
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal first.
- **Production-like run of the dashboard:** `npm run build` then `npm run start` (instead of
  `npm run dev`).

---

## First-time setup

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
