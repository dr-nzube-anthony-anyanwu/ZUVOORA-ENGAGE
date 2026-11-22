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
| ADR-021 | Clinic content uses draft/published JSON copies with database-enforced publication invariants | Accepted (Phase 2a, 2026-11-21) |
| ADR-022 | Website ownership proven by DNS TXT record; one verified holder per hostname | Accepted (Phase 2b, 2026-11-21) |
| ADR-023 | Knowledge uploads: content-sniffed, extracted in an isolated worker, originals in a policy-less private bucket, immutable reviewed versions | Accepted (Phase 2c, 2026-11-21) |
| ADR-024 | Dashboard reads and writes only through server-side code (Server Components + Server Actions) calling the API | Accepted (Phase 2d, 2026-11-21) |
| ADR-025 | Public widget traffic runs as a dedicated `engage_widget` role that can read only published content | Accepted (Phase 3a, 2026-11-21) |
| ADR-026 | Cost-first AI: deterministic answers and Postgres text search before any model; cheap tiered OpenRouter models with backups; hard budgets | Accepted (Phase 3 plan, 2026-11-21) |
| ADR-027 | The API serves the widget iframe; verified domains enforced by browser `frame-ancestors` plus signed frame tickets and conversation tokens | Accepted (Phase 3b, 2026-11-21) |
| ADR-028 | Deterministic answering first: emergency and medical-advice rules, structured facts, Postgres full-text retrieval over published content | Accepted (Phase 3c, 2026-11-22) |
| ADR-029 | AI step: OpenRouter gateway with tiered pinned models, privacy/price constraints per request, pre-call budgets, model call outside the DB transaction, code-enforced output guard | Accepted (Phase 3d, 2026-11-22) |
| ADR-030 | Patient conversations and handover contact details are front-desk only (owner/admin/receptionist); viewers and platform admins see metadata; transcript views and status changes audited | Accepted (Phase 3e, 2026-11-22) |

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

### ADR-021 — Draft/publish model for clinic content
- **Context:** Phase 2 requires that public content is unavailable until approved, while clinics must be able to edit live information (hours, FAQs) without taking it offline. The founder approved: owners/admins edit and publish; receptionists/viewers read only.
- **Alternatives:** (a) per-row `status` column (editing a live item would unpublish it or publish unreviewed edits); (b) separate revision tables (more joins and code for little benefit at MVP scale); (c) duplicated typed columns for draft and published (doubles every schema change).
- **Decision:** each content row holds `draft` and `published` JSON objects. Pydantic models define and validate the shape (plain text, structured opening hours); the database enforces type, size and the publication invariants via triggers and column grants (revision increments, publish only the current draft, server-set publisher/time, archive unpublishes, no tenant moves, no DELETE). The API adds optimistic locking on revisions.
- **Consequences:** publication rules hold even if API code is wrong (verified by mutation testing: with the API role check removed, the database still blocked receptionist writes). Content shape changes need a Pydantic change (and a data migration if a field becomes stricter). Phase 3 reads only `published`. The unused Phase 1 `clinic_profiles` columns were dropped (no data existed).

### ADR-022 — Domain verification by DNS TXT
- **Context:** the Phase 3 widget must only run on websites the clinic controls. Phase 1 made `tenant_domains.hostname` globally unique, which would let any clinic squat another clinic's hostname and block it.
- **Alternatives:** HTML meta tag or file upload checks (require the API to fetch arbitrary URLs: SSRF risk, redirects, hosting quirks); CNAME checks (conflict with existing records); manual approval by ZubeVision (does not scale, not proof of control).
- **Decision:** TXT record at `_zuvoora-engage.<hostname>` containing a database-generated token; DNS lookup only, via `dnspython` (system resolvers, or `DNS_RESOLVERS`). Global uniqueness replaced by one active claim per tenant plus one verified holder per hostname.
- **Consequences:** no outbound HTTP from user input; squatting is harmless; ownership changes require removal by the current holder (or support). Verification is not yet re-checked periodically; Phase 3 adds re-verification before the widget trusts a domain.

### ADR-023 — Knowledge document pipeline
- **Context:** clinics upload documents that the Phase 3 assistant will quote. Files are untrusted input (parser exploits, active content, zip bombs, prompt-injection text); nothing may become public without review.
- **Alternatives:** (a) store bytes in Postgres (RLS-protected, but bloats the database and backups; Supabase free tier is 500 MB); (b) parse in the API process (a parser hang or memory blow-up takes the API down, and the parser could see environment secrets); (c) third-party document conversion services (sends clinic documents to another processor).
- **Decision:** content-based type detection with extension agreement; text extraction with `pypdf` 7.1 and `python-docx` 1.2 in a separate `python -I` process with timeout, no environment and POSIX resource limits; reject active/embedded/encrypted content rather than sanitise it; store originals in a private Supabase Storage bucket with no RLS policies (backend secret key only), as octet-stream, at database-derived paths, written in the same transaction as the version row; immutable versions with a one-way review status and database-enforced publication of approved versions only.
- **Consequences:** OCR is not supported (scanned PDFs are refused with a clear message). Malware scanning (e.g. ClamAV) is deferred to Phase 6, mitigated by rejecting active content, never serving originals, and isolating parsing. If a commit fails after the object upload, an orphan object can remain (no data exposure; cleanup job in Phase 6). Chunking/embeddings for retrieval come in Phase 3 from the approved text. A reverse proxy must enforce the same body limit in production. Dev dependency pytest raised to 9.0.3 (PYSEC-2026-1845); `pip-audit` reports no known vulnerabilities.

### ADR-024 — Dashboard data access through Server Actions
- **Context:** the clinic dashboard needs forms for every Phase 2 feature. Calling the API from browser JavaScript would expose the API origin, require CORS for writes and put access tokens in client code paths.
- **Alternatives:** browser fetch to the API with the Supabase session token; a separate BFF service.
- **Decision:** pages are Server Components that load data from the API with the user's session on the Next.js server; all writes are Server Actions (`apps/web/lib/actions.ts`). `lib/api.ts` is `server-only`. Every action treats its arguments as untrusted (bound arguments travel through the browser): ids must be UUIDs and kinds/verbs come from fixed lists before an API path is built; the API re-authorises everything. Next.js's built-in Origin check protects actions against CSRF. Server Action body limit raised to 11 MB for document uploads only (the API enforces 10 MB and checks contents). All clinic text is rendered by React as text (no HTML injection); extracted document text is shown in a `<pre>` block.
- **Consequences:** the browser never learns the API URL or holds an API token; `npm run check:bundle` confirms no server code or secrets in client chunks. Hiding forms for read-only roles is a convenience only. Playwright E2E tests (ADR-021..023 features through the UI) run locally and in CI.

### ADR-025 — Dedicated database role for anonymous widget traffic
- **Context:** the public chat widget has no signed-in user, so the Phase 1 `engage_app` + JWT-claims model does not apply. Using the backend's own privileges for public traffic would put tenant isolation entirely in application code.
- **Decision:** a NOLOGIN `engage_widget` role, switched to per transaction with a server-derived tenant and conversation. Column grants expose only published content; RLS confines rows to the tenant and the visitor's own conversation; narrow SECURITY DEFINER functions resolve widget keys against verified domains, count rate limits and report AI spend.
- **Consequences:** a bug in the public API cannot read drafts, other clinics' data or other visitors' conversations (verified by pgTAP and mutation tests). Receptionists can handle conversations and handovers.

### ADR-026 — Cost-first AI architecture
- **Context:** founder budget is small (OpenRouter balance ~$2); frontier models are too expensive for an administrative assistant.
- **Decision:** answer from structured clinic data and fixed emergency rules without a model where possible; retrieve with PostgreSQL full-text search (no embeddings at first); when a model is needed, route by simple rules to a `standard` tier (DeepSeek V4 Flash, backup GLM 5.3 Flash) or a `complex` tier (DeepSeek V4.1 Flash, backup GPT-6 Luna) — model ids in configuration, final choice by evaluation. Every request requires no-training, zero-retention providers. Budgets: $0.20/day per clinic, $0.50/day and $2/month platform-wide (founder-approved); per-answer token caps; automated tests use a fake provider; live evaluations capped at $0.10 per run; a dedicated OpenRouter key with a credit limit is recommended as a hard stop. No patient image uploads in Phase 3.
- **Consequences:** most common questions cost nothing; worst-case spend is bounded independently of code correctness by the key limit. Embeddings are added only if evaluation shows text search is insufficient.

### ADR-027 — Widget delivery and domain enforcement
- **Context:** the widget runs on clinic websites we do not control; the public API has no logged-in user. A widget key is public, so it cannot be the authorisation.
- **Alternatives:** script-injected widget in the host page (no isolation, host CSS/JS can read it); iframe served by the dashboard app (needs a server-to-server proxy and loses the visitor IP for rate limiting); Origin-header checks only (spoofable outside browsers, not enforced by the browser).
- **Decision:** the API serves a tiny loader plus a sandboxed iframe page. The iframe page sends `frame-ancestors` with the clinic's verified domains, so browsers refuse to render it elsewhere; the API also checks the embedding host before issuing a short-lived signed frame ticket, which is exchanged for a 2-hour conversation token. All database work runs as `engage_widget` (ADR-025). The API image is built from the repository root in two stages so it contains the compiled widget.
- **Consequences:** browser embedding on unverified sites fails closed (Playwright test with real cross-site hosts; mutation-checked). Non-browser clients can still call the public API like any public chatbot; rate limits and AI budgets (ADR-026) bound abuse. Messages and the usage ledger stay immutable but can be deleted by the database owner for retention and deletion requests.

### ADR-028 — Deterministic answering and full-text retrieval
- **Context:** most patient questions are administrative (hours, contacts, location, services, prices, common FAQs). Sending them to a model costs money and risks invented facts; emergencies must never wait for or depend on a model.
- **Decision:** a fixed pipeline: (1) English emergency rules → the clinic's published emergency guidance (or a safe default) plus its phone; (2) medical-advice rules → a fixed refusal with a handover offer; (3) intent rules → answers built only from published profile/branch/service data (hours computed in the branch time zone with holiday exceptions; unpublished facts are reported as not published, never guessed); (4) PostgreSQL full-text search (`to_tsquery` built only from plain words) over published FAQs, services and passages of approved, published document versions; a strong FAQ match is answered verbatim; (5) otherwise an honest fallback with handover (Phase 3d inserts the AI step here, grounded in the retrieved passages). Document passages are created in the approval transaction and are immutable for application roles; the widget can read only passages of the currently published version of its active clinic.
- **Consequences:** zero model cost for the common cases; no cross-tenant or unpublished content can reach a patient (pgTAP + API tests, mutation-checked). Rules are English-only and keyword-based: broad on emergencies by design (false positives cost a cautious reply). Embeddings remain deferred until the evaluation (3f) shows text search is insufficient.

### ADR-029 — AI gateway, budgets and output guard
- **Context:** ADR-026 fixed the cost-first approach; ADR-028 left a slot for an AI answer grounded in retrieved passages. A model can invent prices, times or phone numbers, can be steered by text inside documents or visitor messages, and every call costs money from a small balance.
- **Alternatives:** call the model inside the widget transaction (simple, but holds the clinic-wide rate-limit row locks for seconds, serialising all of a clinic's visitors); trust the prompt alone for grounding (no enforcement); OpenRouter `~...-latest` model aliases (behaviour changes without our knowledge); GLM 5.3 Flash as the standard backup (verified 2026-11-22: it rejects requests with reasoning disabled, and reasoning tokens would add cost and latency).
- **Decision:** the AI step runs only when no deterministic step answered and retrieval found published passages. Tier by simple rules (long, multi-part or comparative questions → `complex`). Models are pinned ids in configuration: standard `deepseek/deepseek-v4-flash` → `openai/gpt-6-luna`; complex `deepseek/deepseek-v4.1-flash` → `openai/gpt-6-luna`; OpenRouter's `models` list provides the failover. Every request sets `provider.zdr=true`, `data_collection=deny`, `max_price` (USD 0.50/1.00 per million tokens), `max_tokens=300` and disables reasoning. Before each call the worst-case cost of that call is checked against the usage ledger (`ai_spend()`): $0.20/day per clinic, $0.50/day and $2/month platform-wide. The route commits the visitor message, calls the model with no transaction open, then stores the answer and the usage row in a second transaction; usage is recorded even when the answer is rejected, and timeouts are recorded at worst-case cost. The prompt delimits the clinic's sources and treats sources and visitor text as data; the model replies with fixed tokens for no-answer, medical advice and emergencies. A code guard rejects any answer containing a number, link or email address not present in the clinic's sources (numbers from the visitor's question do not count), medical-advice phrasing, prompt leakage or excessive length; rejected answers become the honest fallback with a handover offer. AI is off unless `AI_ENABLED=true`; the test suite forces it off and uses a fake gateway.
- **Consequences:** no invented numbers or links reach patients (unit + API tests, mutation-checked); a strict guard sometimes falls back where a looser one would answer, which the 3f evaluation measures. Budget checks can be passed by concurrent calls at the same moment, so overshoot is bounded by concurrent calls × one call's worst case (≈$0.002); the dedicated OpenRouter key's credit limit is the independent hard stop. Live smoke test (2026-11-22): all three configured models answered a grounded synthetic question through the gateway for ≈$0.0001 in total.

### ADR-030 — Front-desk-only access to patient conversations
- **Context:** handover requests contain patient names, phone numbers and emails given with consent for one purpose (a call back), and transcripts may contain health information. Phase 3a let every clinic member, including read-only viewers, and MFA platform admins read them.
- **Alternatives:** keep broad read access and rely on the dashboard hiding it (the API and database would still serve it); give platform admins support access by default (convenient, but every operator could read every clinic's patients).
- **Decision:** message text and handover details are readable only by the clinic's owner, admin and receptionist roles (RLS, migration `20261122000002_inbox_privacy.sql`); viewers and platform admins keep conversation metadata. The staff inbox API (`/tenants/{id}/inbox/summary`, `/handovers`, `/conversations`, `/conversations/{id}`, `PATCH /handovers/{id}`, `POST /conversations/{id}/close`) requires those roles, audits every transcript view (`conversation.viewed`), every handover status change (with from/to) and every closure. Contact details stay immutable; status timestamps and resolvers are set by the database. Dashboard transcript links do not prefetch, so audit entries reflect real views. Any future support access to content must be a separate, explicit, time-limited and audited feature.
- **Consequences:** least privilege for patient data at the database layer (pgTAP + API tests, both mutation-checked); viewers can no longer read conversations; the founder sees the demo clinic's inbox as its owner, not as platform admin.
