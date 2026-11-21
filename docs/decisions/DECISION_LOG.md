# Architecture Decision Log

| ID | Decision | Status |
|---|---|---|
| ADR-001 | Engage separate repository from existing ZUVOORA | Accepted |
| ADR-002 | Dedicated Supabase project initially | Proposed; approve after setup/RLS review |
| ADR-003 | Widget isolation: prototype iframe first | Proposed |
| ADR-004 | Persistent worker/queue | Required; choose in Phase 4 |
| ADR-005 | Common scheduling interface for Cal.com and Calendly | Accepted; sequence after provider validation |
| ADR-006 | Resend initial email adapter; keep Brevo option | Accepted |
| ADR-007 | OpenRouter server-side model gateway | Accepted; model must pass evaluation |
| ADR-008 | Three commercial layers | Accepted |
| ADR-009 | Reusable modules first; custom enterprise separately priced | Accepted |
| ADR-010 | Docker Compose before Kubernetes | Proposed; reassess on evidence |
| ADR-011 | Web dashboard on Next.js 16 (was 15) | Accepted (Phase 0, 2026-11-20) |
| ADR-012 | Keep `apps/api` (backend) + `apps/web` (frontend) monorepo layout | Accepted (Phase 0, 2026-11-20) |
| ADR-013 | Python 3.12 for API (local venv, Docker, CI) | Accepted (Phase 0, 2026-11-20) |
| ADR-014 | Web container receives only browser-safe config, never the shared `.env` | Accepted (Phase 0, 2026-11-20) |
| ADR-015 | Node.js 24 LTS for web, widget, CI and Docker (was 22) | Accepted (Phase 0, 2026-11-20) |
| ADR-016 | All data access via FastAPI; dedicated `engage_app` DB role; Supabase Data API roles get no table privileges | Accepted (Phase 1, 2026-11-20) |
| ADR-017 | Local-first Supabase (pinned CLI) for development and CI; migrations in `supabase/migrations` | Accepted (Phase 1, 2026-11-20) |
| ADR-018 | Invitation-only accounts; platform admins provision clinics and require TOTP MFA (aal2) | Accepted (Phase 1, 2026-11-20) |
| ADR-019 | Engage ports: API 8073, dashboard 3073 (avoid clashes with other local projects on 8000/3000) | Accepted (2026-11-21) |
| ADR-020 | Email from `engage.zuvoora.com` via Resend (EU); Supabase Auth uses a sending-only, domain-restricted key | Accepted (2026-11-21) |

### ADR-011 — Next.js 16
- **Context:** `eslint.config.mjs` used the Next 16 flat-config entry points, so lint failed on Next 15; Next 15 also pulled a high-severity `postcss` advisory (npm's only fix was Next 16.4.6); the webpack build failed on the exFAT SSD (`EISDIR readlink`).
- **Alternatives:** stay on 15 with FlatCompat + `postcss` override + webpack `symlinks: false` workaround.
- **Decision:** upgrade to `next@^16.4.6`, `eslint-config-next@^16.4.6`, React 19.2+, while the dashboard is still a shell.
- **Consequences:** lint/typecheck/build pass; audit clean; Turbopack is the default builder. Next added `.next/dev/types` to `tsconfig.json` and set `jsx: react-jsx` automatically.

### ADR-012 — Repository layout
- **Context:** founder asked whether to use `backend/` and `frontend/` folders.
- **Decision:** keep `apps/api` (backend), `apps/web` (frontend), `apps/widget`, `apps/worker` — already a backend/frontend split, matching the blueprint docs, CI and prompts.

### ADR-013 — Python 3.12
- **Context:** founder initially preferred 3.11; tests pass on 3.11 but `pyproject.toml`, Dockerfile and CI target 3.12.
- **Decision:** use 3.12 everywhere so local, CI and production match.

### ADR-014 — No shared secrets in the web container
- **Context:** Compose loaded the full `.env` (service-role, OpenRouter, Resend, OAuth secrets) into the web service.
- **Decision:** web gets only explicit `NEXT_PUBLIC_*` build args and non-secret runtime values; the API alone loads `.env`.

### ADR-015 — Node.js 24 LTS
- **Context:** starter targeted Node 22 (older LTS); founder's machine runs Node 24.18.0. Node 24 is a supported LTS line with a longer support window than 22.
- **Decision:** standardise on Node 24. Root `.nvmrc` is the single source for local version managers and CI (`node-version-file`); Docker uses `node:24-alpine`; `engines.node` is `>=24 <25`.
- **Consequences:** local, CI and container runtimes match. Revisit when the next LTS line is adopted; bump `.nvmrc`, Dockerfile tag and `engines` together.

Record context, alternatives, decision and consequences for every major architecture change.

### ADR-016 — Single data path through the API (`engage_app` role)
- **Context:** Supabase's Data API (PostgREST/GraphQL) runs as `anon`/`authenticated`. If Engage tables were granted to `authenticated`, any signed-in user could write directly with their token, bypassing API authorisation and audit logging. Setting `api.schemas = []` locally did not stop PostgREST serving `public` (verified).
- **Alternatives:** rely on RLS alone with Data API access (writes unaudited); rely on dashboard "exposed schemas" config (easy to misconfigure, not testable in CI).
- **Decision:** grant table privileges only to a NOLOGIN `engage_app` role that RLS policies target. The backend logs in as NOINHERIT `engage_api` and per transaction runs `SET LOCAL ROLE engage_app` with verified JWT claims. `anon`, `authenticated` and `service_role` get nothing.
- **Consequences:** Data API isolation holds regardless of project configuration and is covered by pgTAP and integration tests. A missed role switch fails closed (tested). Cloud setup needs one manual step: set the `engage_api` password.

### ADR-017 — Local-first Supabase
- **Context:** Phase 1 tests need real Postgres + Auth; cloud projects should not be test targets.
- **Decision:** Supabase CLI pinned in the root `package.json` (2.122.1, avoiding the 18-day-old 3.x major); `supabase/config.toml` mirrors production auth policy; CI starts an ephemeral local stack. Migration moved from `database/migrations/` to `supabase/migrations/` (never applied anywhere before).
- **Consequences:** every test runs offline and identically in CI; the cloud project only receives reviewed migrations via `supabase db push`.

### ADR-018 — Invitation-only accounts and MFA-gated platform admins
- **Context:** clinic accounts carry patient-adjacent data; self-signup adds abuse surface before billing/onboarding exist.
- **Decision:** public sign-up disabled. Platform admins (active `platform_admins` row **and** `aal2` session) create clinics and invite the owner; owners/admins invite staff. Passwords ≥ 12 chars with mixed case and digits. TOTP optional for clinic staff in Phase 1.
- **Consequences:** self-serve onboarding is deferred to Phase 5 with billing. Requiring MFA for clinic owners should be revisited before pilot (Phase 6).

### ADR-020 — Email sending domain and Supabase SMTP
- **Context:** Supabase's built-in mailer blocks custom templates on the free tier and only delivers to the org's team addresses, so clinic invites could not work. Engage has no domain of its own; the founder owns `zuvoora.com` (DNS on Cloudflare).
- **Alternatives:** `mail.zuvoora.com` (reputation shared with ZUVOORA core); buying a separate domain (cost, delay).
- **Decision:** dedicated subdomain `engage.zuvoora.com` in Resend region eu-west-1 (matches Supabase region), with DKIM, SPF, return-path and DMARC (`p=none`, tighten to `quarantine` once delivery is clean). Supabase Auth SMTP uses its own Resend key with `sending_access` limited to that domain; the founder's full-access key is used only for setup. SMTP is applied to the cloud project from a temporary config copy so the local stack keeps using Mailpit.
- **Consequences:** Engage's sender reputation is isolated from `zuvoora.com`. The full-access Resend key should be replaced in `.env` by a sending-only key before the backend sends email (Phase 4). To rotate the Supabase SMTP key, create a new restricted key and re-run the SMTP push (see `SUPABASE_CLOUD_SETUP.md`).
