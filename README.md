# ZUVOORA Engage

**ZubeVision Technologies Ltd. — AI-powered patient engagement for eye-care businesses**

This is the implementation starter repository for ZUVOORA Engage. It is designed to become a multi-tenant SaaS platform that lets eye clinics add a clinic-specific assistant to an existing website. The assistant will answer administrative questions from clinic-approved information, capture enquiries, hand over to staff and later support appointment scheduling and transactional email.

> This is a starter foundation, not a finished production SaaS. Several routes and integrations are deliberately disabled until their security phase is implemented. Do not use real patient data or expose the application publicly until the relevant phase gates pass.

## Product layers
1. **Engage Essentials:** website assistant, approved clinic knowledge, FAQs, enquiries, handover and basic analytics.
2. **Engage Advanced:** scheduling, confirmation/reminders, advanced analytics and optional WhatsApp/voice.
3. **Full ZUVOORA:** Engage integrated with ZUVOORA Core, Scribe, ZANYRA Insight, ZUVEYA Vision and other modules.

## Stack
- Next.js + TypeScript dashboard.
- FastAPI + Pydantic backend.
- Supabase PostgreSQL/Auth with RLS.
- OpenRouter through a server-side AI gateway.
- Resend initially; provider abstraction for Brevo.
- Cal.com and Calendly behind scheduling adapters.
- Persistent worker/queue for delayed jobs.
- Docker Compose initially; Kubernetes deferred until justified.
- GitHub Actions, Ruff, pytest, ESLint, Gitleaks, Semgrep and Trivy.

## Repository structure
```text
apps/api       FastAPI backend
apps/web       Next.js dashboard
apps/widget    Embeddable widget
apps/worker    Persistent jobs (later phase)
supabase       Migrations, pgTAP RLS tests, local Supabase config and email templates
scripts        Repository tooling (local env generation)
docs           PRD, architecture, security, commercial and operations
prompts        Claude Code master and phase prompts
infra          Deployment configuration
```

## Read these first
1. `docs/operations/START_HERE_WINDOWS.md`
2. `docs/operations/PHASED_IMPLEMENTATION_PLAN.md`
3. `prompts/MASTER_BUILDER_PROMPT.md`
4. `CLAUDE.md`

## Local quick start (Windows PowerShell, Docker Desktop running)
Full details: `docs/operations/LOCAL_DEVELOPMENT.md`.
```powershell
# Repository root: local Supabase (Postgres + Auth) and local-only env files
npm ci
npm run db:start      # first run downloads ~3 GB of images
npm run env:local     # writes apps/api/.env and apps/web/.env.local (never overwrites)
npm run db:test       # pgTAP tenancy/RLS tests

# API
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .
pytest                # unit + integration (integration needs the local stack)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Dashboard (second terminal)
cd apps\web
npm ci
npm run dev
```
API health: `http://127.0.0.1:8000/health/ready` · Dashboard: `http://localhost:3000`.

## Non-negotiable rules
- Keep this repository separate from the existing ZUVOORA project.
- Never trust browser-supplied tenant IDs, roles, plans or permissions.
- Enforce tenant access server-side and in RLS.
- Never expose Supabase service-role, OpenRouter, Resend or OAuth secrets in browser code.
- AI is administrative only, not diagnostic or prescriptive.
- Booking is confirmed only after provider confirmation.
- Reminders must be persistent, idempotent and re-check booking status.
- Add security tests with every feature.
- Complete one phase and its acceptance criteria before starting the next.
