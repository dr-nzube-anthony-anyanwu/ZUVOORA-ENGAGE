# Implementation Tracker

Claude Code may mark an item complete only after actually verifying it.

## Phase 0
- [x] Confirm SSD drive letter and root folder. — `D:\technologies\ZUVOORA-ENGAGE` (exFAT), separate from `D:\technologies\ZUVOORA`.
- [x] Confirm private GitHub Engage repository and remote. — `origin` = https://github.com/dr-nzube-anthony-anyanwu/ZUVOORA-ENGAGE.git; branch `main` (2026-11-20).
- [x] Check Python 3.12, Node 24 LTS, Git, Docker and Claude Code. — Python 3.12.10 (venv), Node v24.18.0 / npm 11.5.2, Git 2.46.0, Docker Desktop 29.8.2 / Compose v5.6.0, WSL 2. Node standardised on 24 (ADR-015); Claude Code used via VS Code extension (CLI not on PATH).
- [x] Install API dependencies; pytest and Ruff pass. — `apps/api/.venv` (Python 3.12.10); `ruff check .` → All checks passed (after `ruff check --fix` sorted imports in 3 files); `pytest` → 2 passed.
- [x] Install web dependencies; lint, typecheck and build pass. — Upgraded to Next 16.4.6 / React 19.x (see ADR-011); `npm run lint`, `npm run typecheck`, `npm run build` all exit 0; `npm audit` → 0 vulnerabilities. Widget: `npm run build` exit 0.
- [x] Docker Compose config validates. — `docker compose config --quiet` exit 0 (validated with a placeholder `.env` copied from `.env.example`). Images not built or started.
- [x] No secrets or patient data tracked. — Pattern scan over all files Git would add: no matches; `.env.example` contains placeholders only; no data files present.
- [x] Baseline committed and pushed to correct remote. — commit `89725b1` pushed to `origin/main`; `git ls-remote` confirms. `.gitattributes` added to normalise LF line endings.

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
- Phase 0 accepted by founder 2026-11-20. Gitleaks finding in run #1 was a reviewed false positive (prose in `DEVELOPMENT_BLUEPRINT_FULL.md:130`); allowlisted by exact fingerprint in `.gitleaksignore`; `gitleaks git` 8.24.3 full-history scan → no leaks.

## Phase 1
- [x] Dedicated Supabase **cloud** project. — "ZUVOORA ENGAGE", eu-west-1, Postgres 17, Auth signs ES256 (2026-11-21). `npx supabase link`; `db push --dry-run` then `db push --linked` applied `20261120000001_tenant_foundation.sql` (seed not pushed); `migration list --linked` shows local = remote. `config push` (auth only) applied: sign-up disabled, min password 12 + `lower_upper_letters_digits`, secure password change; `/auth/v1/settings` confirms `disable_signup: true`. `engage_api` password set from a random value via SCRAM verifier only; stored in gitignored `apps/api/.env.cloud`. Cloud checks: RLS enabled+forced on all 6 tables; `anon`/`authenticated`/`service_role` have no table privileges; Data API returns 401 (anon key) / 403 (service-role key) `42501` for tenants, memberships, audit, platform_admins; `audit_events` not updatable/deletable by `engage_app`; `engage_api` has no direct table access and works via `SET LOCAL ROLE engage_app`.
  - Open: custom **invite email template** rejected by Supabase on the free tier with the built-in mailer (`entitlement_required`); cloud invites therefore use the default template, which does not link to `/auth/confirm`. Resolve by configuring custom SMTP (Resend, ADR-006) — the built-in mailer also only delivers to the org's own team addresses. Until then, cloud users are created by the founder (step 6 of the guide).
  - Open: founder inserts own `platform_admins` row and enrols TOTP. Local `config.toml` email settings aligned to the stronger cloud defaults (confirmations on, 1 min resend interval, 8-digit OTP) and unused `storage.vector` disabled; re-verified locally: pgTAP 57/57, pytest 45 passed.
  Everything below was first verified on the LOCAL stack (Supabase CLI 2.122.1, Postgres 17, Auth with ES256 JWKS).
- [x] Migrations apply cleanly. — `npx supabase db reset` applies `20261120000001_tenant_foundation.sql` + local seed; `npx supabase db lint --level warning` → no schema errors.
- [x] Auth and tenant membership. — Invitation-only (self-signup returns `signup_disabled`, tested); password ≥12 mixed case + digit; TOTP MFA enabled; dashboard login/MFA/invite-acceptance/sign-out pages.
- [x] Server-side session verification. — FastAPI verifies ES256 JWTs via JWKS (iss, aud, exp, iat, sub, role=authenticated, aal); 18 unit tests incl. alg=none, HS256 confusion, tampering, unknown kid, anon/service-role tokens.
- [x] Server-side RBAC. — Tenant from URL path only; bodies forbid unknown fields; 404 for inaccessible tenants; 403 for insufficient role.
- [x] RLS and cross-tenant negative tests. — `npx supabase test db` → 57/57 pass. Mutation check: removing the suspended-tenant condition made exactly the 3 suspended-tenant tests fail (now numbered 42–44); restored → pass.
- [x] Audit events. — Append-only (grants + triggers, even for table owner); written in the same transaction as the action; tested.
- [x] Service-role secrets never appear in browser bundles. — `npm run check:bundle` scans `.next/static` for secret formats, server env names and the actual local secret values → OK (16 files). Planted fake `sb_secret_` value is detected (exit 1).
- [x] API test suite. — `pytest` → 45 passed (27 unit + 18 integration against local Supabase); `ruff check .` → all checks passed.
- [x] Dashboard checks. — `npm run lint`, `npm run typecheck`, `npm run build` exit 0; smoke test: `/dashboard` anonymous → 307 `/login`; forged `/auth/confirm` → `/login`; CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy present.
- [x] Ports moved to API 8073 / dashboard 3073 (ADR-019), 2026-11-21. — Ports confirmed free; app smoke test on new ports OK (health ready, CORS from :3073, /dashboard → /login); pgTAP 57/57, pytest 45 passed, web lint/typecheck, compose config all pass.
- [ ] CI green on GitHub with the new `database-and-api` job. — Pending first push of Phase 1.

### Phase 1 exit-gate test mapping
| Gate | pgTAP (DB) | API integration |
|---|---|---|
| Tenant A cannot read/update Tenant B | tests 14–18, 57 | `test_cross_tenant_*` |
| Browser-supplied tenant_id does not change tenant | 19–20 | `test_browser_supplied_tenant_id_cannot_change_tenant` |
| Anonymous users cannot read private tables | 1–6 (+ Data API 7–13) | `test_unauthenticated_*`, `test_supabase_data_api_*` |
| Receptionist cannot perform owner/platform actions | 21–31, 55–56 | `test_receptionist_*`, `test_admin_cannot_*` |
| Revoked membership loses access | 37–41 | `test_revoked_member_loses_access_immediately` |
| Suspended tenant is blocked | 42–44 | `test_suspended_tenant_is_blocked_then_restored` |
| Service-role secrets never in browser bundles | — | `npm run check:bundle` (web) |

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
