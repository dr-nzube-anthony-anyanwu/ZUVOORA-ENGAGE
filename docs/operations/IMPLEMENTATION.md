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
  - Custom invite template was first rejected on the free tier with the built-in mailer (`entitlement_required`). Resolved 2026-11-21 (ADR-020): Resend domain `engage.zuvoora.com` (eu-west-1) created via API; DKIM/SPF/return-path/DMARC records added by founder in Cloudflare; all 5 records resolved via 8.8.8.8 and Resend status `verified`. Cloud Supabase Auth now sends via `smtp.resend.com:465` as `ZUVOORA Engage <no-reply@engage.zuvoora.com>` using a dedicated **sending-only, domain-restricted** Resend key (never printed or stored locally); Engage invite template pushed; auth email rate limit 30/h. Local stack still uses Mailpit (SMTP config applied from a temporary config copy, not `config.toml`). End-to-end test invite verified 2026-11-21: Resend `delivered`, landed in inbox (not spam), link → `/auth/confirm` → `/account/set-password` → dashboard; test account deleted afterwards.
  - Founder platform admin created (2026-11-21); verified on cloud: 1 auth user, email confirmed, password set, active `platform_admins` row. TOTP enrolled via dashboard `/mfa` against the cloud project; verified on cloud: 1 verified TOTP factor. Apps returned to local Supabase afterwards (cloud API env kept in gitignored `apps/api/.env.cloud`).
  - **Phase 1 accepted by founder** (2026-11-21). Carried forward: custom invite template needs custom SMTP (Resend); migrate to `sb_publishable_`/`sb_secret_` keys and revoke legacy JWT keys before pilot. Local `config.toml` email settings aligned to the stronger cloud defaults (confirmations on, 1 min resend interval, 8-digit OTP) and unused `storage.vector` disabled; re-verified locally: pgTAP 57/57, pytest 45 passed.
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
- [x] CI green on GitHub with the new `database-and-api` job. — Reported all green by founder from the GitHub Actions page (2026-11-21); not independently queried (no `gh` CLI by choice).

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
Plan approved by founder 2026-11-21 (receptionists read-only; owners/admins edit and publish).
- [x] 2a. Clinic profile, branches with structured opening hours, services, FAQs (draft/publish, ADR-021). — Migration `20261121000001_clinic_content.sql`; `npx supabase db reset` applies cleanly; `npx supabase db lint --level warning` → no schema errors; `npx supabase test db` → 101/101 (57 Phase 1 + 44 new in `02_clinic_content.test.sql`). Mutation check: disabling the "publish only current draft" trigger rule and widening the FAQ insert policy to all roles failed tests 27 and 35 (plus dependent 43); restored → pass. API: 25 endpoints in `app/routes/content.py`; `ruff check .` was run before the new test files were written, so the 2a commit actually FAILED Ruff in CI (E501 in two test files; fixed in the 2b commit — correction recorded 2026-11-21); `pytest` → 78 passed (22 new validation unit tests, 11 new integration tests). API mutation check: letting all roles edit drafts failed the receptionist test (database still blocked the writes: 409 instead of 403).
- [x] 2b. Domain registration and DNS TXT verification (ADR-022). — Migration `20261121000002_domain_verification.sql`; `npx supabase db lint` clean; `npx supabase test db` → 127/127 (26 new in `03_domains.test.sql`). API `app/routes/domains.py` (list/add/verify/remove) + `app/services/domain_verification.py`; `ruff check .` clean; `pytest` → 124 passed (30 new unit, 16 new integration using an in-memory DNS zone). Real-DNS smoke check (system resolver and 8.8.8.8) returned `not_found` for an unpublished record. Mutation check: dropping the verified-hostname unique index and letting all roles verify failed exactly the squatting and receptionist tests; restored → pass.
- [x] 2c. Knowledge upload screening, isolated extraction, review, publish and versioning (ADR-023). — Migration `20261121000003_knowledge_documents.sql` (private bucket + tables); local Storage enabled; `npx supabase db lint` clean; `npx supabase test db` → 159/159 (32 new in `04_knowledge.test.sql`). API `routes/knowledge.py`, `services/extraction.py`, `services/extract_worker.py`, `services/storage.py`, `middleware.py` (body-size limit). `ruff check .` clean; `pytest` → 176 passed, 1 skipped (POSIX memory-limit test runs on Linux CI); 36 extraction unit tests with synthetic malicious samples (PDF JavaScript/launch/attachment/encrypted, Word macros/embeddings, zip bomb), 17 integration tests against real local Storage. Mutation check: a storage read policy for signed-in users failed the browser-download test; letting all roles review failed the receptionist test; restored → pass. `pip-audit` → no known vulnerabilities after raising dev pytest to 9.0.3. Found and fixed: pytest 9 monkeypatch deletes Starlette `app.state` attributes on undo → replaced with an explicit `app_state` fixture.
- [x] 2d. Dashboard pages (ADR-024): clinic workspace with setup checklist, profile, branches with structured hours editor, services, FAQs, documents (upload, review, approve/reject, versions), website domains, team (invite, roles, revoke). Server Components + Server Actions only; ids validated before building API paths; read-only roles see disabled forms. `npm run lint`, `npm run typecheck`, `npm run build` exit 0; `npm run check:bundle` OK; `npm audit` 0 vulnerabilities. Accessibility fix found by E2E: field hints moved out of labels into `aria-describedby`.
- [x] 2e. Playwright E2E acceptance (`@playwright/test` 1.65.0 pinned, Chromium). `npm run test:e2e` → 4 passed: anonymous redirect; owner publishes profile, service, FAQ (markup rendered as text, script never runs), branch with hours + holiday (invalid hours refused), uploads/reviews/publishes a document (disguised executable refused), adds a domain (DNS record shown), checklist 5/6; Clinic B owner gets 404 on 8 Clinic A / tampered URLs; receptionist read-only. Fixtures created and removed per run (0 left, files included). Mutation check: leaving the form editable for receptionists failed the read-only test. Added to CI (`database-and-api` job). Also fixed: API integration teardown now deletes stored files (65 local orphans removed); tenant hard-deletes leaving stored files is tracked for Phase 6 retention work.
- [ ] Domain verification.
- [ ] Knowledge upload quarantine, review and publish.

- [x] Founder walkthrough on the cloud project (synthetic "ZUVOORA Demo Eye Clinic", founder as owner), 2026-11-21. Issues reported and fixed: redundant `encType` on Server Action forms (React dev warning); hydration warning caused by browser extensions (Grammarly, ColorZilla) adding `<body>` attributes → `suppressHydrationWarning` on `<body>` only. E2E now also fails on any browser console error or page error; rerun → 4 passed.
- [x] CI green on GitHub for `10de83f` (verified via the public GitHub API): pgTAP, Ruff, pytest, Playwright E2E (first CI run), web lint/typecheck/build/bundle scan, widget, gitleaks v3, Semgrep container (no findings), Trivy. Fixed on the way: pytest `pythonpath` (CI collection error, exit 2, in the 2c/2d runs); all actions on Node 24 and pinned to commit SHAs; archived `semgrep/semgrep-action` replaced by the pinned official container.
- **Phase 2 accepted by founder** (2026-11-21). CI green for `24bff0a`. Carried forward: Grammarly-style extensions and patient text (Phase 3: `data-gramm="false"` on sensitive fields + staff guidance); periodic domain re-verification (Phase 3); malware scanning and stored-file retention on tenant deletion (Phase 6).

## Phase 3
Plan approved by founder 2026-11-21 (ADR-026): caps $0.20/day per clinic, $0.50/day and $2/month platform-wide; no patient image uploads.
- [x] 3a. Data model (ADR-025): `engage_widget` role, widget configs, conversations, messages, handover requests, usage ledger, rate limits. Migration `20261121000004_widget_conversations.sql`; `db lint` clean; pgTAP 201/201 (42 new in `05_widget.test.sql`). Mutation check: granting the widget role draft access and dropping the verified-host condition failed exactly tests 12 and 7; restored → pass. Note: Docker Desktop's D: file sharing broke mid-session (`supabase test db` mount error); tests run via the same `pg_prove` image with a C: copy until Docker Desktop is restarted.
- [x] 3b. Widget and public API (ADR-027): loader + sandboxed iframe served by the API with `frame-ancestors` from verified domains; frame tickets and conversation tokens (dedicated `WIDGET_TOKEN_SECRET`); session/messages/handover endpoints as `engage_widget`; rate limits; honest "not available yet" responder until 3c/3d; dashboard "Chat widget" page (status, snippet, greeting, key rotation). Migration `20261121000005_widget_session_ids.sql` (server-generated conversation ids; owner-only deletes on messages/usage for retention). pgTAP 203/203; `pytest` 199 passed + 1 Linux-only (23 new widget integration tests incl. tampered/foreign/cross-tenant-forged tokens); Playwright 7/7 incl. real cross-site embedding on a verified vs unverified host. Mutation check: `frame-ancestors *` failed the unverified-site test. Found and fixed: asset route shadowing the frame route; Phase 0 placeholder `/public/widget/session` route removed; `insert … returning` vs visitor-only RLS; append-only trigger blocking tenant deletion cascades. API Docker image now multi-stage from the repository root (includes the built widget).
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
