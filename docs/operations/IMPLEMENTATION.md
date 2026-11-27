# Implementation Tracker

The record of what has been built, how it was verified and what remains. An item is marked
complete only after it has actually been verified; each entry names the commands, test suites
and results it is based on. Architecture decisions are referenced as ADR-nnn
(`docs/decisions/DECISION_LOG.md`).

## Status at a glance (2026-11-22)

| Phase | Scope | Status |
|---|---|---|
| 0 | Environment and repository validation | Accepted 2026-11-20 |
| 1 | Secure foundation: auth, tenancy, RBAC, RLS, audit | Accepted 2026-11-21 |
| 2 | Clinic administration: content, domains, documents, team, dashboard | Accepted 2026-11-21 |
| 3 | Widget, answering, AI, evaluation, inbox; 3g document AI | Accepted 2026-11-22 (3g added and verified the same day) |
| 4 | Scheduling, booking, webhooks, reminders, email | Accepted 2026-11-22 |
| 5 | Plans, entitlements, metering, quotas, analytics | Accepted 2026-11-22 |
| 6 | Hardening, deployment, monitoring, backups, legal review, pilot | **In progress.** Plan approved; 6B (server hardening) accepted 2026-11-25; 6A (repository readiness) accepted 2026-11-25. **Not complete.** |

**Latest full verification** (local, 2026-11-25, stage 6A, commit `5112826`; CI green, including the new `deployment` job):

| Check | Result |
|---|---|
| pgTAP (`npx supabase test db`) | 419 / 419 in 16 files |
| pytest (`apps/api`) | 585 collected: 581 passed, 4 skipped (2 Linux-only resource-limit tests, 2 live-ClamAV tests that run in CI) |
| Playwright (`apps/web`, `npm run test:e2e`) | 20 / 20 |
| Ruff, ESLint, TypeScript, Next.js build, bundle-secret scan | clean / pass |
| Semgrep `p/owasp-top-ten` (pinned container) | 0 findings |
| gitleaks (the 43 changed and new files) | no leaks |
| `npm audit --audit-level=high` (root, web, widget); `pip-audit` | 0 vulnerabilities |
| Docker images (API, dashboard): Trivy, HIGH/CRITICAL with a fix | 0 (after removing npm from the dashboard runtime and applying Debian security updates) |
| Hardened stack run locally (`deploy/compose.yml` against local Supabase) | api, worker, web, clamav healthy; no published ports; real ClamAV detects EICAR; worker auto-restarts |
| Cloud database (staging) | all 19 migrations applied (latest `20261201000001_patient_email_reply_to.sql`, after CI went green on `5112826`); `db lint` no schema errors |

**Conventions**
- "pgTAP" = `supabase/tests`; "API integration" = `apps/api/tests/integration` (real API, real
  local Supabase); "unit" = `apps/api/tests`; "Playwright"/"E2E" = `apps/web/e2e`.
- "Mutation check" = a safeguard was deliberately broken to confirm a test fails, then restored.
- Cloud migrations are applied only after CI is green: `db push --dry-run`, `db push --linked`,
  then `db lint --linked`.
- Only synthetic data is used. No secret values are recorded here.

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
- [x] Founder walkthrough on the cloud project (synthetic "ZUVOORA Demo Eye Clinic", founder as owner), 2026-11-21. Issues reported and fixed: redundant `encType` on Server Action forms (React dev warning); hydration warning caused by browser extensions (Grammarly, ColorZilla) adding `<body>` attributes → `suppressHydrationWarning` on `<body>` only. E2E now also fails on any browser console error or page error; rerun → 4 passed.
- [x] CI green on GitHub for `10de83f` (verified via the public GitHub API): pgTAP, Ruff, pytest, Playwright E2E (first CI run), web lint/typecheck/build/bundle scan, widget, gitleaks v3, Semgrep container (no findings), Trivy. Fixed on the way: pytest `pythonpath` (CI collection error, exit 2, in the 2c/2d runs); all actions on Node 24 and pinned to commit SHAs; archived `semgrep/semgrep-action` replaced by the pinned official container.
- **Phase 2 accepted by founder** (2026-11-21). CI green for `24bff0a`. Carried forward: Grammarly-style extensions and patient text (Phase 3: `data-gramm="false"` on sensitive fields + staff guidance); periodic domain re-verification (Phase 3); malware scanning and stored-file retention on tenant deletion (Phase 6).

## Phase 3
Plan approved by founder 2026-11-21 (ADR-026): caps $0.20/day per clinic, $0.50/day and $2/month platform-wide; no patient image uploads.
- [x] 3a. Data model (ADR-025): `engage_widget` role, widget configs, conversations, messages, handover requests, usage ledger, rate limits. Migration `20261121000004_widget_conversations.sql`; `db lint` clean; pgTAP 201/201 (42 new in `05_widget.test.sql`). Mutation check: granting the widget role draft access and dropping the verified-host condition failed exactly tests 12 and 7; restored → pass. Note: Docker Desktop's D: file sharing broke mid-session (`supabase test db` mount error); tests run via the same `pg_prove` image with a C: copy until Docker Desktop is restarted.
- [x] 3b. Widget and public API (ADR-027): loader + sandboxed iframe served by the API with `frame-ancestors` from verified domains; frame tickets and conversation tokens (dedicated `WIDGET_TOKEN_SECRET`); session/messages/handover endpoints as `engage_widget`; rate limits; honest "not available yet" responder until 3c/3d; dashboard "Chat widget" page (status, snippet, greeting, key rotation). Migration `20261121000005_widget_session_ids.sql` (server-generated conversation ids; owner-only deletes on messages/usage for retention). pgTAP 203/203; `pytest` 199 passed + 1 Linux-only (23 new widget integration tests incl. tampered/foreign/cross-tenant-forged tokens); Playwright 7/7 incl. real cross-site embedding on a verified vs unverified host. Mutation check: `frame-ancestors *` failed the unverified-site test. Found and fixed: asset route shadowing the frame route; Phase 0 placeholder `/public/widget/session` route removed; `insert … returning` vs visitor-only RLS; append-only trigger blocking tenant deletion cascades. API Docker image now multi-stage from the repository root (includes the built widget).
  - CI for `5fd7847` FAILED: Semgrep flagged server-built frame HTML (`raw-html-format`) and a wildcard `postMessage` target; also the "Start local Supabase" step failed (no log detail available without admin rights). Fixed: the frame is now a static file whose script fetches its config from `frame-config` (ticket only for verified hosts), and the close message targets the embedding origin only. Re-verified locally after a Docker/WSL reset: pgTAP 203/203, pytest 196 passed + 1 Linux-only, Playwright 7/7, Semgrep 0 findings (258 rules, 146 files).
- [x] 3c. Deterministic answering (ADR-028): emergency and medical-advice rules, structured facts (hours with time zones/holidays, contacts, address, services, prices), Postgres full-text retrieval over published FAQs/services/approved document passages, verbatim strong-FAQ answers, honest fallback. Migration `20261122000001_retrieval.sql` (`knowledge_chunks`, FTS indexes, `widget_clinic_name()`); passages created on approval. pgTAP 214/214 (11 new); 46 new unit tests (incl. false-positive guards); 8 new API integration tests (published-only, cross-tenant FAQ/document isolation, unpublish removes passages). Mutation check: widget passage policy without the published-version condition failed the unpublish test. Rule gaps found by tests and fixed: "…went dark suddenly" missed; "where can I park?" mis-routed to the address. Test infra: integration tests take Supabase settings from env when `supabase status` is slow; widget rate limits raised in tests (one shared client IP) except the dedicated limit test. Widget: a "Contact the clinic team" button keeps a person one click away even after a good answer (previously the handover form appeared only on fallback/safety replies). Final verification after a Docker reset: pgTAP 214/214; `pytest` 250 passed + 1 Linux-only; Playwright 7/7 (the widget test now checks the real published Saturday hours); Ruff and ESLint clean; Semgrep `p/owasp-top-ten` 0 findings (258 rules, 144 files); gitleaks directory scan: only the reviewed docs false positive in `.gitleaksignore`.
- [x] 3d. AI step (ADR-029): OpenRouter gateway with pinned tiered models (standard DeepSeek V4 Flash → GPT-6 Luna; complex DeepSeek V4.1 Flash → GPT-6 Luna), `zdr` + `data_collection: deny` + `max_price` on every request, reasoning disabled, 300-token cap; pre-call budget check against the usage ledger ($0.20/day per clinic, $0.50/day and $2/month platform); model call outside the DB transaction, answer and usage stored afterwards (usage recorded for rejected answers; timeouts at worst case); grounded prompt with delimited sources; code guard rejects numbers/links/emails not in the clinic's sources, medical-advice phrasing, prompt leaks. `AI_ENABLED=false` by default; tests force it off and use `FakeGateway`. Tests: 63 unit (gateway via mock transport, guard, routing, budgets, settings) + 9 API integration (published-only prompt, cross-tenant/draft exclusion, budget exhaustion never calls the model, hallucination replaced but billed, safety before model). Mutation checks: guard without the number check and answerer without the budget check each failed a test. Live smoke test with the dedicated $1-limited key: 3 models answered a synthetic grounded question, ≈$0.0001 total; GLM 5.3 Flash (planned backup) rejected disabled reasoning (HTTP 400) and was replaced. Not enabled in any deployed environment yet.
- [x] 3e. Conversation lifecycle and human handover (ADR-030): dashboard **Inbox** for owners/admins/receptionists (nav count of new requests; tabs "Needs follow-up", "Resolved", "All conversations"); conversation page with call-back card (tel:/mailto: links), transcript rendered as text with how each answer was produced, actions new → in progress → resolved → reopen, and close conversation (visitor then gets `conversation_closed`). Staff API under `/tenants/{id}/…` (summary, handovers, conversations, detail, status, close), front desk only; transcript views, status changes and closures audited. Migration `20261122000002_inbox_privacy.sql`: message text and contact details no longer readable by viewers or platform admins. pgTAP 228/228 (14 new); 13 new API integration tests (lifecycle and audit, viewer 403, other clinic/outsider/platform admin 404, closed conversation blocks the visitor); Playwright 8/8 (receptionist works the request end to end; visitor's HTML shown as text). Mutation checks: viewer re-allowed in the messages policy → 2 pgTAP failures; viewer added to the API role set → 5 API failures.
- [x] 3f. AI evaluation and prompt-injection tests (ADR-032) + domain re-verification (ADR-031). Evaluation: 46 synthetic cases (emergency 8, medical-advice safety 8, injection 8, isolation 6, quality 16) through the real widget API and RLS; hostile-model mode in CI (every AI call attacks; 100% required in all categories; no foreign/draft/unapproved text in any prompt) and a capped live mode. **Live run 2026-11-22: emergency/safety/injection/isolation 100%, quality 93.8% (15/16), $0.0006 for 15 calls** — report `docs/evaluations/PHASE3_LIVE_EVALUATION_2026-11-22.md`. Found and fixed: "contact lens" questions routed to the clinic's contact details. Domain re-verification: migration `20261122000003_domain_recheck.sql` (role `engage_jobs`, `domains_due_for_recheck`, `record_domain_recheck`, `recheck_failures`), job `python -m app.jobs.reverify_domains` (daily; see `SCHEDULED_JOBS.md`); 3 consecutive definite failures lapse a domain to pending (widget stops), resolver errors never count, lapses audited with the system actor and run id. pgTAP 245/245 (17 new); pytest 341 + 2 skipped (Linux-only; live evaluation on request). Mutation checks: guard disabled → hostile evaluation falls to 62–67% in safety/injection/isolation. Found by the full run and fixed: test domains left on the shared clinic hit the 10-domain limit; lapse audit events now carry a request id like every other event.
- [x] 3g. AI reading of photos and scanned documents (ADR-041; added 2026-11-22 at the founder's request: clinic uploads only, no patient uploads). Migration `20261129000001_document_vision.sql` (`usage_events` feature `document` / tier `vision`, staff may insert only document usage for their own clinic, widget only chat; `ai_spend_for()`; `extraction_method` on versions, immutable; `document_reading` in every plan). Worker: PNG/JPEG/WebP decoded with an allow-list and 40 MP cap, scanned PDFs (< 20 chars of text per page) rendered with PDFium, every page re-encoded as a fresh JPEG ≤ 1600 px (EXIF/GPS dropped), ≤ 10 pages. `VisionReader` (one call per page, 4 parallel, temperature 0, transcription-only prompt, output cleaned and capped); plan, monthly allowance and daily/platform budgets checked with the worst case before any call; every call (also failures) in the usage ledger. Separate switch `AI_VISION_ENABLED` (off by default); models `google/gemma-4-26b-a4b-it` → `mistralai/mistral-small-3.2-24b-instruct` → `openai/gpt-6-luna`. Web: photos accepted, "never upload patient information" hint, "Read by AI" badge and review warning. Dependencies: `pillow` 13.0, `pypdfium2` 5.14 (releases older than two weeks). Found and fixed: a blank `OPENROUTER_API_KEY` counted as a key. Tests: 30 unit (`test_vision.py`), 11 API integration (`test_document_vision_api.py`), pgTAP 17 new (`15_document_vision`), Playwright 2 new (`documents-vision.spec.ts`, fake OpenRouter that refuses requests without ZDR/no-collection/price cap). Mutation checks: budget check removed → budget test failed; metadata stripping removed → EXIF test failed. **Live smoke test 2026-11-22** (synthetic price list, $1-limited key): Gemma 4, Mistral Small 3.2 and GPT-6 Luna each transcribed it exactly; $0.000354 in total ($0.000043 with Gemma).
- [x] **Phase 3 acceptance evidence:** widget only on verified domains (Playwright, real cross-site hosts); RAG isolation and prompt-injection tests pass (pgTAP, API, hostile-model and live evaluations); safe fallback and human handover work end to end (API + Playwright); quality 93.8% ≥ the agreed 90%.
- **Phase 3 accepted by founder** (2026-11-22). 3g (document AI) was added afterwards at the founder's request and verified as recorded above; it is off by default (`AI_VISION_ENABLED=false`) and enabled per environment.
  - 3g CI note: the first CI run for `0b19ede` failed at "Start local Supabase"; the same migrations then started, linted and passed pgTAP 401/401 on a fresh throwaway local stack, and an empty commit (`6e8ed2a`) re-ran CI green. Treated as a transient CI failure.

## Phase 4
Founder decisions (2026-11-22): Cal.com is the pilot provider (Calendly adapter in 4e); clinics connect with an API key/token now (OAuth later, after provider approval); background jobs in a Postgres queue, not Redis.

- [x] 4a. Resend adapter and persistent jobs (ADR-033): migration `20261123000001_jobs_and_email.sql` (`app_private.jobs`; enqueue by the database on call-back requests and domain lapses; `claim_jobs` with SKIP LOCKED + lease, `complete_job`, `skip_job`, `fail_job` with backoff/dead letters/23-hour cut-off, `purge_finished_jobs`; send-time data functions that re-check status and clinic state). Worker `python -m app.worker` (Compose `worker` service; Redis removed). `ResendSender` with `Idempotency-Key`, `LogSender` (default), `AllowlistSender` outside production. Emails: call-back alert to the front desk and "website chat stopped" to owners/admins, with no patient details. pgTAP 269/269 (24 new); 21 new unit + integration tests (alert once, never twice; handled request skipped; retry with the same key; permanent failure dead; crash retried; suspended clinic skipped). Mutation check: removing the send-time status re-check failed a test. Live check: one real alert to the founder's test address; repeating the same idempotency key returned the same Resend message id (no second email).
- [x] 4b. Scheduling core and Cal.com adapter (ADR-034): migration `20261123000002_scheduling_connections.sql` (`scheduling_connections` with encrypted credential columns no role can select, `appointment_types`, `scheduling_credential()`, triggers for server-set actors, disconnect wipes the ciphertext, one live connection per clinic, widget sees only enabled types of an active connection). `SecretsBox` (AES-256-GCM, row-bound associated data, key rotation). Provider contract with explicit error classes; `CalcomProvider` (me, event types, slots, book, cancel, reschedule). Staff API `/tenants/{id}/scheduling` (connect after verifying the key, provider event types, choose appointment types, disconnect; audited without the key). Dashboard **Scheduling** page (password field with `autocomplete=off`, `data-gramm=false`). Browser tests use a local fake Cal.com server. pgTAP 295/295 (26 new); pytest 391 + 2 skipped (31 new: encryption, adapter request/response/error mapping, API roles, revoked key → failing, disconnect erases, copied-ciphertext attack); Playwright 9/9 (owner connects with a wrong then a right key, chooses types, receptionist read-only, disconnect; the key never appears on a page). Mutation check: removing the row binding failed 3 tests.
- [x] 4c. Booking from the widget, confirmations and clinic alerts (ADR-035): migration `20261124000001_appointments.sql` (`appointments` with database-enforced state machine, one in-flight booking per conversation, appointment type bound to the same clinic, attendee details immutable and front-desk-only; confirmation/alert jobs only from confirmed/pending; `unknown` queues reconciliation; worker functions `job_booking`, `job_booking_reconcile`, `job_resolve_booking`, `job_retry_reconcile`; `answer_source` and job kinds extended). Widget API `/api/v1/public/widget/booking/{options,slots}` and `POST /booking` (record → re-check slot → book → record outcome; rate limits); `frame-config` reports whether booking is offered. Worker: patient confirmation email, clinic alert without patient details, reconciliation by `engage_ref` (1, 3 and 10 minutes, then failed). Widget: "Book an appointment" panel (type → time in the visitor's time zone → details + consent). Tests: pgTAP 317/317 (22 new; a mis-ordered cross-clinic test was moved after the first booking, with the founder's approval for the deletion of its original position); 11 new API integration tests (confirmed, pending, taken slot caught before any provider write, refusal/outage book nothing and queue nothing, lost response → unconfirmed + call-back + reconciled to confirmed + email, unknown that never happened → failed, revoked key, isolation and validation, per-conversation limit); unit tests for the lookup and emails; Playwright 10/10 (a patient books from the clinic website through a fake Cal.com; the booked time disappears for the next visitor). Mutation check: skipping the slot re-check failed a test. Live: booked, found by reference and cancelled an "Eye exam" on the founder's Cal.com account.
- [x] 4d. Verified webhooks, lifecycle and reminders (ADR-036): migration `20261125000001_booking_lifecycle.sql` (encrypted per-connection webhook secret, `reminder_2h`, `rescheduled` state, times never edited in place, `provider_events` exactly-once log, `apply_provider_event`, reminders on confirmation, `skip_appointment_jobs` on leaving an active state, cancellation notice, 90-day event purge). Webhook receiver `/api/v1/webhooks/calcom/{connection}` (HMAC on the raw body, uniform 401, 72-hour freshness, rate limit, size cap). Webhook setup (automatic via `POST /v2/webhooks` with a public https API URL, otherwise URL + secret shown once), 2-hour reminder setting, staff Appointments API and page (cancel through Cal.com first). Worker: reminder (re-checks status, time, not started) and cancellation emails. Tests: pgTAP 341/341 (24 new); pytest 429 + 2 skipped (16 webhook unit tests; 9 lifecycle integration tests: rotation, automatic registration, refused deliveries, cancel applied once + patient emailed, reschedule, reminder sent, staff cancel never claims success on outage/unknown, front-desk-only list); Playwright 10/10 (manual webhook set-up shows the secret once; the clinic cancels the patient's booking). Mutation checks: signature check removed → 2 API failures; reminder suppression removed → 3 pgTAP failures. Pending: confirm the signature encoding against a real Cal.com delivery (needs a public URL).
- [x] 4e. Calendly adapter, failure modes, acceptance (ADR-037): `CalendlyProvider` from the documented API (no live account), Calendly webhook verification (`t=,v1=`, 3-minute tolerance) mapped to the canonical events, provider-generic webhook route, provider choice on the dashboard's Connect form. `docs/operations/FAILURE_MODES.md` (18 failure modes with behaviour and the test that proves each). Tests: 12 Calendly unit tests (documented request bodies, 7-day windows, pagination, location handling, errors, reconciliation matching, unsupported reschedule, webhook signature/tolerance/mapping) + 2 API integration tests (token format; booking + signed Calendly cancellation applied once; wrong-provider address refused). pytest 443 + 2 skipped; Playwright 10/10.
- [x] **Phase 4 acceptance evidence:** booking confirmed only after provider success (API tests incl. lost-response and outage cases; live Cal.com book/find/cancel); duplicate webhooks cannot duplicate effects (DB + API tests); cancellation/reschedule suppresses old reminders (DB tests, mutation-checked); worker re-checks status before sending (API tests, mutation-checked); provider outages never produce a false confirmation (API tests); signed webhook verification and replay protection (unit + API tests, mutation-checked). Open items for Phase 6: confirm the Cal.com webhook signature encoding against a real delivery; live Calendly test when an account exists.
- **Phase 4 accepted by founder** (2026-11-22). No Calendly account exists yet; live webhook testing deferred to Phase 6 (needs a public HTTPS address).

## Phase 5
Founder decisions (2026-11-22): four plans — Essentials, Professional, Premium (ZUVOORA Engage) and Full ZUVOORA (ecosystem); live booking in every plan; plans differ in reminders, analytics, channels (WhatsApp, voice — not built yet), multi-branch and limits; over a limit: soft for safety, hard for cost; no online payments yet (platform admin assigns plans).

- [x] 5a. Catalogue, subscriptions and the central entitlement check (ADR-038): migration `20261126000001_plans_entitlements.sql` (features, plans, plan_features, plan_limits seeded; `tenant_subscriptions` created per clinic by trigger, demo clinic backfilled to Full ZUVOORA; `tenant_overrides`; `entitlements_internal()` + role wrappers; widget stops for cancelled subscriptions; reminders only where the plan includes them). `app/services/entitlements.py`; gates on booking (staff + widget), reminders, AI answers; plan limits on domains, documents, staff seats (before any invitation), branches. Platform API (`/platform/plans`, `/platform/subscriptions`, `/platform/tenants/{id}/subscription|overrides`) and `POST /platform/tenants` with `plan_key`; clinic `GET /tenants/{id}/plan`. Web: clinic "Plan & usage" page, `/platform` (clinics & plans, plan catalogue), reminder toggle hidden when not in the plan. Tests: pgTAP 366/366 (25 new); 9 new API integration tests (owner-only plan view, MFA-only plan management, plan change keeps identity/data/widget, reminders and booking refused by direct API calls, cancelled subscription stops the widget but keeps data, domain and staff-seat limits from the plan, new clinics on a requested plan); Playwright 11/11 (an MFA platform admin changes a clinic's plan; owners see included / not-in-plan / not-yet-available; receptionists see no billing). Mutation check: a gate that allows everything failed 2 tests. pytest 452 + 2 skipped.
- [x] 5b. Usage metering, quotas and alerts (ADR-039): migration `20261127000001_usage_metering.sql` (`app_private.usage_counters`, `meter()` with 80%/100% alert jobs, triggers on visitor messages, AI usage rows, first booking confirmation and real email sends via `complete_job`; `tenant_usage()`, `widget_quota_reached()`, `job_quota_alert()`). AI step skipped at the message/AI limits; booking paused at the bookings limit (options, slots, book, widget button); `GET /tenants/{id}/usage`; quota alert email (worker); usage bars on Plan & usage. Tests: pgTAP 384/384 (18 new); 6 new API integration tests (counters reconcile with real messages and bookings, AI spend metered, AI pauses at both limits while facts/emergency continue, bookings pause while call-backs continue, one 100% alert to owners). Mutation check: removing the AI quota check failed 2 tests.
- [x] 5c. Analytics (ADR-040): migration `20261128000001_analytics.sql` (`platform_overview()` for MFA platform admins; time indexes). `GET /tenants/{id}/analytics` (owner/admin; basic for all plans, full from Professional: daily series, cancellation/reschedule rates, AI cost and share, unanswered topics as keyword counts ≥ 2); `GET /platform/analytics` (estimated monthly revenue, AI cost, per-clinic usage vs limits). Web: clinic Analytics page (7/30/90 days) and a "This month" overview on `/platform`. Tests: 7 new API integration tests (numbers reconcile with independent SQL, full analytics follow the plan, topics are keywords only and single mentions hidden, receptionist/other clinic/plan gate, day-range validation, platform overview MFA-only with no content). Mutation check: allowing single-mention topics failed a test.
- [x] 5d. Acceptance: `tests/integration/test_plan_acceptance.py` (7 tests) — AI answers switched off → no model call, fallback + call-back offer, facts continue; booking switched off → frame-config hides booking, `POST /booking` 403 with the provider never called, scheduling `/connect` refused before any other check; document limit refuses before storing; branch limit from the plan; a round trip Full ZUVOORA → Essentials → Premium → Professional (cancelled) → Professional → Full ZUVOORA leaves the tenant id/status, widget key, FAQs, branches, documents, domains, members, conversations, messages, appointments, scheduling connections and usage counters unchanged and the same embed code still loads; every meter (messages, AI cost, AI tokens, bookings, emails) moves exactly as much as its source table over a real chat + AI answer + booking + worker run; the 80% alert fires once and the 100% alert does not. `TENANCY_AND_RLS.md` Phase 5 section. pytest 471 + 2 skipped (473), pgTAP 384/384, Ruff clean, Semgrep 0 findings (258 rules, 210 files), gitleaks only the reviewed false positive in `DEVELOPMENT_BLUEPRINT_FULL.md:130`. Mutation checks: AI-answers gate removed → its test failed; `/connect` booking gate removed → its test failed.
- [x] **Phase 5 acceptance evidence:** plans are enforced server-side — every gate is refused on a direct API call (`test_plans_api.py`, `test_plan_acceptance.py`, `test_analytics_api.py`, pgTAP `13_entitlements`), mutation-checked; upgrades/downgrades/cancellation keep identity, data and the widget (`test_any_plan_change_keeps_identity_data_and_widget`); usage is metered by the database and reconciles with source tables (`test_meters_reconcile_with_source_tables`, pgTAP `14_usage`); quotas are soft for safety and hard for cost (AI and new bookings pause; facts, emergency guidance, call-backs and existing-booking emails continue); alerts fire once per threshold; analytics are counts only (no transcripts). Not built and shown "not yet available": WhatsApp, voice AI, ecosystem. No online payments (platform admin assigns plans).

- **Phase 5 accepted by founder** (2026-11-22).

## Design track — brand, public website and demo requests (2026-11-22)
Separate from Phase 6. Brief tailored from the founder's research: `prompts/DESIGN_UI_UX_BRIEF.md`. Founder decisions: no public prices; secure demo-request feature approved; no founder section yet; official logo supplied the same day.

- [x] D1. Design system and public homepage (ADR-042): tokens and typography in `app/globals.css` (Plus Jakarta Sans + Inter self-hosted with `next/font`; CSP unchanged), official logo (`docs/brand/` → cropped `public/brand/*`, browser icons from the eye symbol), palette sampled from the logo and contrast-checked (`docs/design/DESIGN_SYSTEM.md`). `(marketing)` route group: homepage (story, challenge, solution, audience, six alternating feature rows with labelled illustrative previews, value, accessible FAQ accordion, three steps, scripted demo with no AI call, four-plan comparison without prices, roadmap with "Coming soon", responsibility, pilot invitation, final call to action, footer with existing pages only) and `/accessibility` statement. Every claim mapped to a live capability (`docs/design/HOMEPAGE_CONTENT.md`). Fixed during review: plan-table hidden labels widened the page by 285 px on phones; logo link name mismatch found by axe.
- [x] D2. Sign-in, two-factor and set-password pages restyled with a shared `AuthShell` (logic, labels and redirects unchanged); dashboard and platform sidebars show the logo.
- [x] D3. Demo requests (ADR-042): migration `20261130000001_demo_requests.sql` (`demo_requests` with forced RLS — MFA platform admins only, details immutable, 12-month purge; `submit_demo_request()` for the public role, refused inside a clinic chat session or for signed-in users; `demo_request_alert` job; `job_demo_request()` returns no contact details). API `POST /api/v1/public/demo-requests` (minimal fields, honeypot, rate limits per forwarded IP/email/global) and `GET/PATCH /api/v1/platform/demo-requests` (audited). Web `/request-demo` (Server Action; consent; no health information) and platform console "Demo requests". Setting `DEMO_REQUEST_NOTIFY_EMAIL` (blank = unset). Tests: pgTAP 15 new (`16_demo_requests`); 13 API integration + 2 unit tests; Playwright 5 new in `marketing.spec.ts` (axe WCAG 2.2 AA on home, demo request, accessibility, sign-in; keyboard accordion; scripted demo; 375 px with no sideways scroll; request travels to the MFA console, invisible to a clinic owner).
- Verification before the logo change: pytest 527 passed + 2 skipped (529); pgTAP 416/416 (16 files); Playwright 18/18; Ruff, ESLint, TypeScript, build, bundle-secret scan clean; Semgrep 0 findings (258 rules, 234 files); gitleaks only the reviewed false positive. New dev dependency: `@axe-core/playwright` 4.14.0 (MPL-2.0, test-only).
- After the official logo and colours: ESLint, TypeScript, build and bundle-secret scan clean; Playwright 18/18 including all axe checks; header logo 212×51 px desktop / 176×43 px mobile; no sideways scrolling at 375 px.
- [x] D4. Dashboard and chat widget in the brand: shared dashboard classes restyled (panels, buttons, inputs, tables, tabs, badges, links), current section marked with `aria-current` (`components/NavLink.tsx`), sticky sidebar on desktop and a scrolling section row on phones, onboarding line and progress bar on the clinic overview; widget `frame.css` and launcher restyled (pill quick actions, capped call-back/booking panels so the conversation stays visible). No markup labels or behaviour changed. New `e2e/dashboard-a11y.spec.ts` (axe on the dashboard list, overview, inbox, services, plan; current-section marking; 375 px; axe inside the widget frame) — passed first run. Found during visual review and fixed: the call-back form squeezed the conversation; dashboard links used the browser's default blue; the full sidebar pushed phone content below the fold.
- [x] Demo kit and console gaps (2026-11-22): platform console "Create a clinic" form (owner invited by email; existing API) and per-clinic **Activate / Suspend** buttons with a "Clinic active" badge — previously only possible through the API, and new clinics stayed "pending" (widget off). Local demo helpers (refuse anything but the local database): `npm run demo:setup` (three demo accounts with fresh passwords; "Lumen Eye Clinic (sample)" on Professional with published profile, branch hours, 4 services, 6 FAQs created through the API; widget on and allowed on `lumen-eye-clinic.localhost`; safe to rerun), `npm run demo:site` (sample clinic website embedding the real widget; key read per request), `npm run demo:calendar` (practice Cal.com). Step-by-step `docs/operations/DEMO_GUIDE.md`. Verified with a throwaway automated walkthrough (homepage → owner connects calendar → patient asks hours/prices/FAQ/emergency/medical/unknown, books and requests a call-back → receptionist sees both → admin enrols TOTP, creates and activates a clinic, invitation in Mailpit), then all demo data removed. Found and fixed during the walkthrough: the demo website cached a stale widget key; the activation message vanished with its button. E2E `plans.spec.ts` now also creates and activates a clinic; Playwright 20/20.
- Not done yet (D5): genuine product screenshots; Lighthouse/Core Web Vitals measurement; founder section; privacy notice and terms (Phase 6 legal review).

## Phase 6 — planning (not complete)
Brief: `prompts/phases/PHASE_6_HARDENING_DEPLOYMENT_PILOT.md`. The phase was deferred on
2026-11-22 and resumed on 2026-11-24 for planning only.

**Founder direction (2026-11-24):**
- **Hosting:** the existing Contabo Cloud VPS, which may be shared with the main ZUVOORA application.
- **Domain:** `zuvoora.com` with DNS at Cloudflare.
- **Host names:** `engage`, `api-engage`, `staging-engage` and `staging-api-engage`.
- **Runtime:** Docker Compose.
- **Database:** Supabase Cloud. The existing project becomes staging; a new production project will be created.
- **Providers:** OpenRouter, Resend, Cal.com and Calendly.
- **Customers:** three pilot clinics.

**Readiness audit.** The audit covered the repository only. Nothing was run on any server, and no
DNS, provider or credential was changed. The full report is in
`docs/operations/PHASE6_DEPLOYMENT_PLAN.md`. Its findings:

*Blockers:*
- **R1:** the Compose file publishes 8073 and 3073 on all interfaces. Docker bypasses UFW, so the API and dashboard would be reachable on the server IP over http.
- **R2:** uvicorn runs without proxy headers, so every visitor shares the proxy's IP for rate limits. Separately, the dashboard trusts the first `X-Forwarded-For` value, which can be forged.
- **R3:** there are no production backups or restore drill, and stored files are not in database backups.
- **R4:** the production project needs Auth custom SMTP and URLs.
- **R5:** the legal documents do not exist yet.
- **R6:** the shared host needs a founder decision.
- **R7:** there are no deployment assets.

*High:*
- **R8:** production accepts `EMAIL_DELIVERY=log`, http URLs and a missing `PUBLIC_API_URL`.
- **R9:** a 10-page document read can take about 120 seconds, longer than Cloudflare's 100-second limit.
- **R10:** containers have no limits or hardening, and their logs are unbounded.
- **R11:** the worker has no health check, and `reverify_domains` is not scheduled.
- **R12:** there is no monitoring.
- **R13:** CI neither builds nor scans images, base images are not digest-pinned, and `pip-audit` and `npm audit` do not run.
- **R14:** the API docs would be public on staging.

*Medium and low:* R15–R21. R21 is the host-name example in `.env.example`, fixed on 2026-11-24.

**Plan.** Stages 6A–6J: repository readiness and read-only VPS inspection, hardening, accounts and
secrets, DNS and TLS, staging, live integrations, monitoring with backups and a restore drill,
security testing, production, then the pilot.

**New documents:**
- `CONTABO_VPS_SETUP.md`
- `PRODUCTION_DEPLOYMENT.md`
- `ROLLBACK_AND_RECOVERY.md`
- `docs/security/PRODUCTION_SECURITY_CHECKLIST.md`
- `PHASE6_FOUNDER_GUIDE.md`, the founder's step-by-step tasks

ADR-043 records the architecture and is **proposed, not accepted**. The 13 founder questions are
in plan §8.

**Founder decisions (2026-11-24)** (details in plan §1a):
- **VPS:** Cloud VPS 6 in the EU, with 6 cores, 12 GB RAM and 200 GB disk.
- **D1:** staging shares the VPS.
- **D2:** Supabase stays on the Free plan for now, so our own encrypted backup is the only backup and a restore drill is mandatory.
- **D3:** Engage sends from `engage.zuvoora.com`. Clinic emails carry the clinic's name and Reply-To. The founder's mailbox receives alerts; its address is held only in the server env. Custom clinic sending domains are in the backlog.
- **D4:** AI is on at launch.
- **D5:** ClamAV virus scanning, failing closed, is added in 6A.
- **D6:** there is no lawyer yet, so real patient data waits for reviewed legal documents. Claude may prepare drafts.

**VPS inspection (2026-11-25, read-only, run by the founder):**
- **System:** Ubuntu 24.04.5 LTS; 6 cores; 11 GiB RAM; no swap; 193 GB disk with 2.7 GB used.
- **Software:** the server is empty. No Docker, no web server and no ZUVOORA application; only SSH listens.
- **Security:** UFW is inactive. Root and password SSH login are on. fail2ban is not installed. 21 updates are waiting. An unused `ubuntu` sudo account exists.
- **Access:** the founder logs in with an SSH key added through Contabo "Reset credentials".
- **Decision:** the proxy is Caddy. Hardening steps were tailored in `CONTABO_VPS_SETUP.md` §3.

**6B progress (2026-11-25), founder at the console, guided step by step:**
- Contabo snapshot taken.
- All pending updates installed (kernel 6.8.0-151; reboot pending).
- Admin user `engageadmin` created, in the sudo group, with the founder's SSH key; `sudo` verified.
- The unused `ubuntu` account is locked, with no login shell.
- Rebooted into kernel 6.8.0-151.
- SSH hardened (`/etc/ssh/sshd_config.d/00-engage-hardening.conf`). Verified with `sshd -T`: root login no, password and keyboard-interactive no, X11 no, MaxAuthTries 3, AllowUsers engageadmin. A root login and a password-only login were both refused from the founder's laptop, and the key login as engageadmin works.
- UFW is active: deny incoming, allow outgoing; 22/tcp LIMIT, 80/tcp and 443/tcp ALLOW (IPv4 and IPv6).
- fail2ban is active with the sshd jail (5 tries / 10 minutes, 1-hour ban). It banned 2 attacking addresses within seconds of starting.
- Unattended security upgrades are confirmed on. The old 6.8.0-147 kernel was removed.
- A 2 GB swap file was added (swappiness 10).
- Docker 29.10.1 and Compose v5.8.0 were installed from Docker's official apt repository. `/etc/docker/daemon.json` sets json-file logs (10 MB × 3), live-restore and no-new-privileges. The `hello-world` test passed. `engageadmin` is deliberately not in the `docker` group.
- `/opt/zuvoora-engage/{production,staging}` were created (root only, 700).
- External TCP check from the founder's network: only 22 is open. 80 and 443 are allowed by UFW but nothing listens yet; 2375, 3073 and 8073 are closed.
- **6B result: all checks passed; accepted by the founder 2026-11-25.**
- Ubuntu 26.04 LTS is offered but deliberately **not** applied: 24.04 is supported to 2029, and a release upgrade will be planned separately.

**Remaining questions (2026-11-25):** the founder said "use your recommendation", recorded as D7–D12 in plan §8:
- **D7:** the production region is the same as staging's.
- **D8:** public GHCR images.
- **D9:** Cloudflare Access for the staging dashboard.
- **D10:** UptimeRobot.
- **D11:** Backblaze B2.
- **D12:** provisional retention periods (to be reviewed by a lawyer).

ADR-043 is accepted.

**6A — repository readiness (built and verified locally; accepted by the founder 2026-11-25).**

Code changes:
- **Settings** (`app/config.py`). Staging and production refuse to start without:
  - https `DASHBOARD_URL`, CORS origins and `PUBLIC_API_URL`;
  - a `FORWARDED_ALLOW_IPS` list (not `*` and not 0.0.0.0/0; every entry must be an IP address or network);
  - `MALWARE_SCAN_REQUIRED=true` with `CLAMAV_HOST`;
  - `EMAIL_DELIVERY=resend` (production only).

  Interactive API docs now exist only in development and test. The document-reading time bound is enforced through `AI_VISION_PARALLEL` (5) and `AI_VISION_DEADLINE_SECONDS` (85): ceil(pages ÷ parallel) × timeout must fit within the deadline, at most 80 seconds by default (R2, R8, R9, R14).
- **Visitor address** (`app/middleware.py:install_proxy_headers`). uvicorn's ProxyHeadersMiddleware trusts only the configured networks and takes the right-most untrusted address, and the container runs uvicorn with `--no-proxy-headers`. The dashboard's demo-request action uses the last `X-Forwarded-For` entry (the one set by our proxy) and only if it looks like an IP address (R2).
- **Virus scanning** (`app/services/malware_scan.py`). A clamd INSTREAM client that fails closed: infected files get 422 `upload_malware` and are audited with `reason=malware` and `signature`. If the scanner is down or required but missing, uploads get 503 `scan_unavailable`. Scanning runs after type detection and before parsing, storage or AI reading (D5).
- **Worker.**
  - A heartbeat file plus `python -m app.healthcheck api|worker`.
  - Hourly scheduled domain re-verification (`WORKER_RUN_SCHEDULES`; idempotent through the 20-hour due rule; failures never stop email).
- **Email identity** (D3).
  - Patient booking emails (confirmation, reminder, cancellation) are sent as "<Clinic> via ZUVOORA Engage <platform address>", with a sanitised display name.
  - When the clinic has **published** an email address, Reply-To is set to it.
  - Migration `20261201000001_patient_email_reply_to.sql` adds `clinic_email` to `app_private.job_booking()` from the published profile only. Staff alerts are unchanged.
- **Dashboard.** `/healthz`; standalone output when `NEXT_OUTPUT=standalone` (images only).

Images:
- **API image:** digest-pinned bases (node 24.22.3-alpine, python 3.12.16-slim), Debian security updates at build time, UID 10001, `HEALTHCHECK`, no Server header.
- **Dashboard image:** a standalone server only, npm/yarn/corepack removed, UID 10001, `HEALTHCHECK`.

Deployment (`deploy/`):
- `compose.yml`: api, worker, web and clamav. No published ports; read-only root filesystems with tmpfs; `cap_drop ALL`; no-new-privileges; memory, CPU and process limits; rotated logs; health checks. Fixed private subnets per environment, and the web container receives no env file.
- `proxy/Caddyfile` and `proxy/compose.yml`: Caddy 2.11, Origin CA TLS, Authenticated Origin Pulls required, X-Forwarded-For replaced with CF-Connecting-IP, 12 MB body limit, 95-second upstream limit, proxy logs without query strings, headers or bodies, unknown hosts aborted.
- `env/*.env.example`.
- `scripts/preflight.sh`: names only, never values; checks owner and mode, placeholders, https, production email, and that no secret is shared between staging and production (by hash).
- `scripts/deploy.sh`: digest-only release in `release.env`, wait for health, smoke checks, automatic rollback, `releases.log`.
- `scripts/rollback.sh`.
- `scripts/check_compose_policy.py` and `scripts/test_preflight.sh`.

CI:
- **`quality.yml`:**
  - `pip-audit` and `npm audit --audit-level=high` (web, widget);
  - a new `deployment` job: Compose policy check for both files, shellcheck, preflight tests as root, a **real ClamAV EICAR test** against the pinned scanner image, image builds, Trivy image scans (vulnerabilities and secrets) and a non-root check.
- **`images.yml` (new):** on a `v*` tag, builds the API image and the staging and production dashboard images, scans them, pushes them to GHCR and prints the exact `deploy.sh` commands with digests. It never deploys.

Evidence (local):
- Each Compose file passes the policy check, and a mutation check (a published port, `env_file` on web, a writable root filesystem, an extra capability) is caught.
- The Caddyfile passes `caddy validate` with throwaway certificates.
- `test_preflight.sh`: 9/9 in an Ubuntu 24.04 container.
- shellcheck: warnings clean (one style note).
- Both images build; Trivy initially found 1 HIGH (Debian libzstd, fixed by the security updates) and 6 HIGH in the npm bundled with the Node image (fixed by removing npm from the runtime), and 0 afterwards.
- The full hardened stack ran locally against the local database:
  - every container healthy, none publishing a port;
  - `/health/ready`, the widget loader and the dashboard homepage answered;
  - the real ClamAV detected EICAR (`Eicar-Test-Signature`) and passed a clean file;
  - writes to `/app` were refused (read-only), and processes run as uid 10001;
  - the worker came back after SIGTERM (RestartCount 1), and the scheduled re-check ran.
- The test stack was then removed.

Not in 6A (planned later):
- `backup.sh` and the restore check (6G, needing the 6C accounts);
- retention implementation (R17, from the provisional D12);
- nonce CSP (R18).

CI on `5112826`: both workflows green. Every job passed, including `deployment` (policy, shellcheck, preflight tests, the real ClamAV EICAR test, image builds, Trivy image scans and the non-root check). Staging database migrated: dry run, push, lint clean.

**6C progress (2026-11-26):**

Done:
- **Production Supabase project** `zuvoora-engage-production` created: ref `zitwanfosyhtjmfqjlsm`, region eu-west-1 (the same as staging, D7), Free plan (D2), status ACTIVE_HEALTHY, checked with `supabase projects list`. The organisation now holds two projects, the free maximum.
- **OpenRouter** staging and production keys.
- **Backblaze B2** bucket and write-only key.
- **Resend domain** `engage.zuvoora.com`: already verified on 2026-11-21, so only the keys remain.
- **2026-11-27:** GitHub repository variables set by the founder (staging and production Supabase URL and publishable key). They will be verified by the first `images` run.
- **6C complete (2026-11-27).** Open from 6C: the optional email forwarding (6.2b), and making the GHCR packages public after the first release (6.8b).
- **2026-11-27:** Cal.com and Calendly test accounts created by the founder (no API keys yet).
- **2026-11-27:** UptimeRobot account created (founder; first monitor `zuvoora.com`; the Engage monitors come after deployment).
- **2026-11-27:** backup encryption public key (age) received; bech32 checksum verified; stored in `deploy/backup/age-recipients.txt`. The private key is held only by the founder.
- **2026-11-27:** quick checks confirmed by the founder: 2FA on all provider accounts, SSH key backed up (USB stick and Bitwarden), B2 Object Lock enabled, B2 key write-only.
- **2026-11-27:** Resend app keys (staging and production) and the production SMTP key created; OpenRouter credit limits confirmed by the founder.
- **2026-11-27:** SSH shortcut `engage-vps` added to the founder's laptop (appended to the existing config, with a backup).
- **2026-11-27, Cloudflare read-only check:** the four Engage names are unused; the Resend DNS records exist; the zone SSL mode is Full (automatic) on the Free plan. 6D will add a per-host Configuration Rule for Full (strict) instead of changing the zone-wide mode.

Remaining founder tasks (`PHASE6_FOUNDER_GUIDE.md`, "Where you are now"):
- quick checks (2FA, key backup, B2 Object Lock and write-only key, OpenRouter limits);
- 3 Resend keys;
- the age backup key;
- UptimeRobot;
- Cal.com and Calendly test accounts;
- the Cloudflare read-only look;
- 4 GitHub variables;
- after Claude migrates production: 6.1b (engage_api password, API keys, Auth SMTP, Data API).

**Production database migrated (2026-11-26, founder-approved):**
- **Setup:** a separate CLI work directory `D:\technologies\engage-prod-ops` (outside the repository) holds a copy of `supabase/migrations` and `config.toml`. It is the only place linked to production (`zitwanfosyhtjmfqjlsm`), while the repository stays linked to staging (`fjgthmmntjqdcrkajfaf`). The founder entered the production database password in their own terminal (Job 0).
- **Dry run:** the first attempt from the repository failed safely ("password authentication failed"). The CLI had read the repository's gitignored root `.env`, which contains the **staging** `SUPABASE_DB_PASSWORD`. Commands now run from inside the work directory; this is documented in `PRODUCTION_DEPLOYMENT.md`, step 5.
- **Results:** the dry run listed exactly the 19 migrations and no seed. The push applied all 19. `db lint --linked` found no schema errors, and `migration list` shows local = remote for all 19. The local demo seed was not applied.
- **Bitwarden:** account created by the founder.

**Production Auth configured (2026-11-27):**
- **Founder (Step 6.1b):**
  - Job A: `engage_api` password.
  - Job B: publishable and secret keys plus the pooler host, saved in Bitwarden.
  - Job C: Auth custom SMTP through Resend with a production-only sending key, rate limit 30 per hour.
  - Job D: `public` removed from the Data API.
- **Claude, via `config push`:**
  - Run from `engage-prod-ops`, whose `config.toml` copy differs from the repository's only in `site_url` and `additional_redirect_urls` (`https://engage.zuvoora.com`, `/auth/confirm`) and `email_sent` (30).
  - The diff was reviewed first. It showed the new-project defaults still in place: **sign-ups enabled**, minimum password length 6, `site_url` localhost, the default invitation template.
  - Pushed: sign-ups off, minimum password length 12 with lower, upper and digits, secure password change, the site URL and redirect, the invitation subject and template, a 10 MiB storage file limit.
- **Verified afterwards (`config diff`):**
  - every declared Auth setting matches;
  - SMTP remains enabled and unchanged (host `smtp.resend.com`, port 465, user `resend`, sender `no-reply@engage.zuvoora.com`), held only remotely because its password is never in files;
  - TOTP MFA is on (no difference);
  - remaining differences are only the pooler sizes, which are dashboard-only and the defaults are fine.
- **Not verifiable by tool:** Job A (the role password), Job B (the keys) and Job D (Data API schemas: the CLI does not manage `api.schemas`). These rest on the founder's confirmation; Job D will be checked from outside in 6E.

**Next step:** 6D (DNS, proxy and TLS).

Environments and deployment
- [ ] Separate staging and production (the existing cloud Supabase project becomes staging; a new production project).
- [ ] Hardened server (Ubuntu LTS): SSH keys only, firewall, automatic security updates, non-root containers, read-only filesystems where possible.
- [ ] Reverse proxy with HTTPS and security headers; dashboard and API on their own subdomains.
- [ ] Deployment and rollback procedure; secrets in a protected store (never in images or the repository).
- [ ] Worker and the daily domain re-verification job running as services; job-queue health visible.
- [ ] Real visitor IP for rate limits: run uvicorn with `--proxy-headers` and `--forwarded-allow-ips` limited to the reverse proxy and the dashboard server (the dashboard forwards the visitor address for demo requests).
- [ ] Set `DEMO_REQUEST_NOTIFY_EMAIL`; publish a reviewed privacy notice and terms and link them from the public footer and the demo form.
- [ ] Migrate to Supabase `sb_publishable_` / `sb_secret_` keys and revoke legacy JWT keys.

Monitoring, backups and recovery
- [ ] Uptime checks on `/health/live` and `/health/ready` with alerts.
- [ ] Structured logs without patient content; alerting on errors, dead jobs and AI budget exhaustion.
- [ ] Scheduled, encrypted, off-site database backups and a documented **restore drill** with timings.

Security and data protection
- [ ] Malware scanning of uploaded files; stored-file retention when a clinic is deleted.
- [ ] Data retention policy implemented (conversations, call-backs, provider events, audit).
- [ ] Nonce-based Content Security Policy for the dashboard (inline scripts currently allowed for Next.js hydration).
- [ ] Container image scanning before deployment; independent security assessment.
- [ ] Privacy notice, terms, data processing agreement, retention schedule and incident runbooks reviewed by qualified professionals. No certification or legal-compliance claims without independent evidence.

Integrations to confirm on a public address
- [ ] Cal.com webhook signature encoding against a real delivery.
- [ ] Calendly live test (needs an account).
- [ ] Enable AI answers and document reading in staging with the dedicated, credit-limited key; run the live evaluation there.

Pilot
- [ ] Pilot acceptance checklist complete; pilot clinics onboarded only after it is signed off.

## Known issues and notes
- `14_usage.test.sql` failed once locally (email meter showed 3 instead of 1, tests 10–11) during the 3g work and passed in every later run, including a fresh stack; the cause was not found. Watch for recurrence.
- pytest emits a Starlette deprecation warning recommending `httpx2` for `TestClient` (non-blocking).
- ESLint 9 is reported as no longer supported upstream; upgrade when `eslint-config-next` supports ESLint 10.
- `apps/worker/` is a placeholder from Phase 0; the worker runs from the API package (`python -m app.worker`).
- Repository visibility is public; CI status is checked through the public GitHub API (`gh` is not used).
