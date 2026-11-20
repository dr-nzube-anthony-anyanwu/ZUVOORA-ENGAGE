# Implementation Tracker

Claude Code may mark an item complete only after actually verifying it.

## Phase 0
- [x] Confirm SSD drive letter and root folder. — `D:\technologies\ZUVOORA-ENGAGE` (exFAT), separate from `D:\technologies\ZUVOORA`.
- [ ] Confirm private GitHub Engage repository and remote. — `git init` done on `main` (2026-11-20); **remote not yet added** (awaiting repository URL).
- [x] Check Python 3.12, Node 24 LTS, Git, Docker and Claude Code. — Python 3.12.10 (venv), Node v24.18.0 / npm 11.5.2, Git 2.46.0, Docker Desktop 29.8.2 / Compose v5.6.0, WSL 2. Node standardised on 24 (ADR-015); Claude Code used via VS Code extension (CLI not on PATH).
- [x] Install API dependencies; pytest and Ruff pass. — `apps/api/.venv` (Python 3.12.10); `ruff check .` → All checks passed (after `ruff check --fix` sorted imports in 3 files); `pytest` → 2 passed.
- [x] Install web dependencies; lint, typecheck and build pass. — Upgraded to Next 16.4.6 / React 19.x (see ADR-011); `npm run lint`, `npm run typecheck`, `npm run build` all exit 0; `npm audit` → 0 vulnerabilities. Widget: `npm run build` exit 0.
- [x] Docker Compose config validates. — `docker compose config --quiet` exit 0 (validated with a placeholder `.env` copied from `.env.example`). Images not built or started.
- [x] No secrets or patient data tracked. — Pattern scan over all files Git would add: no matches; `.env.example` contains placeholders only; no data files present.
- [ ] Baseline committed and pushed to correct remote.

### Phase 0 changes made
- `docker-compose.yml`: web service no longer loads the shared `.env` (it carried server-only secrets); `NEXT_PUBLIC_API_BASE_URL` passed as a build arg.
- `apps/web/Dockerfile`: `npm ci` with lockfile, build arg for public API URL, ensures `public/` exists.
- `.github/workflows/quality.yml`: `npm ci` + cache, web `build` step, new widget job.
- `.github/workflows/security.yml`: Trivy action pinned to commit SHA (v0.36.0) instead of `@master`.
- `.gitignore`: added `*.egg-info/`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, SSH private keys.
- Lockfiles generated: `apps/web/package-lock.json`, `apps/widget/package-lock.json`.
- Node 24 LTS: root `.nvmrc` (`24`) used by CI via `node-version-file`; web Dockerfile on `node:24-alpine`; `engines.node` `>=24 <25` in web and widget; `@types/node` 24.x. Re-verified on Node v24.18.0: web lint/typecheck/build exit 0, widget build exit 0.

### Known items carried forward
- Git on exFAT requires `git config --global --add safe.directory D:/technologies/ZUVOORA-ENGAGE` (applied on this machine).
- pytest emits a Starlette deprecation warning recommending `httpx2` for TestClient; non-blocking.
- ESLint 9.39.5 reports as no longer supported upstream; plan an ESLint 10 upgrade once `eslint-config-next` supports it.

## Phase 1
- [ ] Dedicated Supabase project.
- [ ] Auth and tenant membership.
- [ ] Server-side RBAC.
- [ ] RLS and cross-tenant negative tests.
- [ ] Audit events.

## Phase 2
- [ ] Onboarding, clinic profile, services, hours, FAQs.
- [ ] Domain verification.
- [ ] Knowledge upload quarantine, review and publish.

## Phase 3
- [ ] Widget session and domain validation.
- [ ] Conversation lifecycle and human handover.
- [ ] OpenRouter gateway and tenant-scoped RAG.
- [ ] AI evaluation and prompt-injection tests.

## Phase 4
- [ ] Scheduling adapters and verified webhooks.
- [ ] Resend adapter and persistent jobs.
- [ ] Booking lifecycle and reminder suppression.

## Phase 5–6
- [ ] Entitlements, usage, quotas and analytics.
- [ ] Staging/production, HTTPS, monitoring, backups and restore.
- [ ] Privacy/contract review, security assessment and pilot approval.
