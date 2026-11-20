# Architecture Review & Development Blueprint

> Full text converted from the editable Word blueprint. Refer to the source Word copy in `docs/source_word_documents/`.

ZUBEVISION TECHNOLOGIES LTD.

# Architecture Review &
Development Blueprint

ZUVOORA Engage — from approved product concept to implementation-ready engineering plan

ZE-DEV-004  |  Version 1.0  |  20 November 2026

CONFIDENTIAL – INTERNAL PRODUCT AND ENGINEERING PLANNING

# Document control and how to use this blueprint

| Field | Value |

| --- | --- |

| Purpose | Review the current architecture baseline and translate it into an ordered, testable implementation plan. |

| Related documents | ZE-PRD-001; ZE-ARCH-002; ZE-GTM-003. |

| Status | Proposed engineering baseline. Decisions marked 'validate' must be checked before implementation or production. |

| Owner | ZubeVision Technologies Ltd. |

| Project root | D:\Technologies\ZUVOORA-ENGAGE (as described by the founder; verify the actual drive letter and folder spelling on the laptop). |

| Versioning | Update this document and decision log when architecture decisions change. |



This document is not a substitute for provider documentation, a legal review, a threat model workshop or a production security assessment. It deliberately separates recommended defaults from items that must be validated against current vendor capabilities and account plans.

# 1. Executive architecture review

The proposed product direction is sound: a standalone, multi-tenant Engage SaaS product, separately deployable from the existing ZUVOORA application, with a planned integration path into the full ZUVOORA ecosystem. The architecture should use reusable modules and provider adapters rather than customer-specific forks.

| Decision area | Review outcome | Action |

| --- | --- | --- |

| Separate project/repository | Keep Engage independent from existing ZUVOORA codebase. | Proceed; protect existing project from accidental changes. |

| Dedicated database boundary | Use a dedicated Engage Supabase project initially. | Proceed; avoid sharing tables/credentials with ZUVOORA Core at MVP. |

| Multi-tenancy | One application serving multiple clinic tenants. | Proceed only with tested tenant isolation across every data path. |

| Frontend/backend | Next.js + TypeScript; FastAPI backend. | Proceed; keep business rules and secrets server-side. |

| AI/RAG | OpenRouter gateway with tenant-scoped retrieval. | Proceed with strict data minimisation, provider review and tool restrictions. |

| Scheduling | Cal.com and Calendly adapters behind a common interface. | Design both; implement one pilot provider first if API access or schedule requires sequencing. |

| Email | Resend first, provider abstraction for future Brevo. | Proceed; validate sender-domain, account and deliverability requirements. |

| Background jobs | Persistent queue and worker for reminders/webhooks. | Required; do not use in-memory timers for scheduled reminders. |

| Deployment | Docker-based deployment on VPS initially. | Start with Docker Compose; defer Kubernetes until justified. |

| Security | Shift-left CI checks and security tests. | Build gates from first repository commit. |



Important refinement: 'support both scheduling providers from the beginning' should mean the architecture and adapter contracts support both. It does not require both production integrations to be completed simultaneously if provider access, plan limitations or pilot demand make a staged release safer.

# 2. Target architecture and request boundaries

Clinic website → Embed widget → Public API gateway → Tenant/domain resolver → Conversation service → Tenant-scoped RAG → AI gateway → Response

↘ Booking service → Scheduling adapter → Cal.com / Calendly

↘ Handover / notification service → Email adapter → Resend

Admin dashboard → Auth/session → RBAC + entitlement checks → Clinic configuration / inbox / analytics

Webhook endpoints → Signature verification → Idempotent event handler → Database state → Persistent queue → Worker

The browser is an untrusted environment. It can hold a public widget identifier and short-lived conversation reference, but never OpenRouter keys, Supabase service-role keys, provider OAuth secrets or privileged tenant credentials.

## 2.1 Recommended logical services

| Service | Owns | Must not do |

| --- | --- | --- |

| Web dashboard | Clinic admin UI, owner/admin/receptionist experience, super-admin UI. | Make authorisation decisions only in the browser. |

| Widget | Chat interface, accessible controls, client-side conversation UX. | Store secrets, decide tenant access, directly call model provider. |

| API | Authentication, tenant resolution, policy enforcement, application workflows. | Trust tenant IDs supplied by the client without validation. |

| Knowledge service | Document lifecycle, chunking, retrieval, citations/source metadata. | Search across tenants or use unapproved content. |

| AI gateway | Provider routing, prompt policy, token/cost metering, structured output validation. | Give models unrestricted database, shell or arbitrary network tools. |

| Scheduling service | Common booking contract and provider adapters. | Report booking success before provider confirmation. |

| Notification service | Templates, preferences, delivery state and provider abstraction. | Send reminders based only on stale scheduled data. |

| Worker | Webhook processing, ingestion, reminder execution and retries. | Assume jobs execute exactly once; design idempotently. |

| Platform admin | Tenant lifecycle, support tools, feature entitlements and usage review. | Browse private clinic conversations without authorised support controls. |



# 3. Technology baseline and implementation choices

| Layer | Recommended baseline | Notes / validation |

| --- | --- | --- |

| Frontend dashboard | Next.js + TypeScript + Tailwind | Use a supported stable release; server-side session patterns; strict lint/type checks. |

| Embeddable widget | Small isolated widget bundle; consider iframe isolation for MVP | Iframe offers stronger CSS/DOM isolation; validate UX, accessibility and embedding restrictions. |

| Backend | FastAPI + Pydantic | Versioned REST API; OpenAPI contract; strict request/response schemas. |

| Database | Supabase-managed PostgreSQL | Dedicated Engage project; migrations committed to Git; RLS and private schemas. |

| Vector search | pgvector in same tenant-aware database initially | Confirm extension/plan and query performance; use tenant filters plus RLS/data-access safeguards. |

| Authentication | Supabase Auth | MFA for platform admins; role checks in API and database. |

| AI provider | OpenRouter behind internal AI gateway | Model chosen by quality/cost/privacy tests; provider terms and data controls reviewed. |

| Email | Resend adapter first | Domain authentication, bounce/complaint handling, transactional templates. |

| Scheduling | Cal.com and Calendly adapters | Verify APIs, OAuth, webhooks, rate limits and account-plan eligibility. |

| Queue/worker | Celery + Redis as one candidate | Validate persistence, deployment complexity, retry semantics and monitoring; alternative durable queue acceptable. |

| Containerisation | Docker Compose initially | Separate services and networks; non-root containers; health checks and resource limits. |

| Reverse proxy/TLS | Nginx + HTTPS | Only expose necessary ports; automated certificate renewal and security headers. |

| CI/CD | GitHub Actions | PR gates, protected branches, environment-scoped secrets and deployment approvals. |



# 4. Repository layout

Use one Git repository for the Engage product initially. Keep deployable components and shared contracts organised without creating premature microservices.

ZUVOORA-ENGAGE/
  apps/
    web/                 # Next.js dashboard and admin portal
    widget/              # embeddable chat widget
    api/                 # FastAPI application
    worker/              # background worker and scheduled jobs
  packages/
    api-contracts/       # OpenAPI-generated/shared contracts where appropriate
    email-templates/     # versioned transactional templates
    ui/                  # shared UI components if genuinely shared
  infra/
    docker/              # Dockerfiles and Compose definitions
    nginx/               # reverse proxy configuration
    github/              # CI workflows and security policies
    monitoring/          # dashboards, alerts and probes
  database/
    migrations/          # reviewed SQL migrations
    seeds/               # synthetic development fixtures only
  docs/
    product/ architecture/ security/ operations/ decisions/
  tests/
    unit/ integration/ security/ e2e/ ai-evals/
  scripts/
  .github/workflows/
  .env.example
  .gitignore
  README.md

Do not place real clinic or patient data in seed files, screenshots, fixtures or test recordings. Use synthetic data with obvious test labels.

# 5. Environment strategy

| Environment | Purpose | Data and access rules |

| --- | --- | --- |

| Local development | Daily coding and unit/integration tests. | Local or dedicated dev services; synthetic data only; individual developer credentials. |

| Shared staging | End-to-end, provider sandbox and clinic acceptance testing. | Separate Supabase project and provider credentials; synthetic/test bookings; access limited to team and pilot testers. |

| Production | Live clinic tenants. | Separate production database, keys, domains, backups and access policies; no casual developer access. |



- Never copy production patient/conversation data into development or staging unless a documented, lawful, minimised and protected process explicitly permits it.

- Use distinct API keys and OAuth connections per environment.

- Keep .env files out of Git; commit only .env.example with placeholder names.

- Use GitHub environment protection and deployment approvals for production secrets.

- Make database migrations repeatable and reviewed; never rely on manual dashboard edits as the only schema history.

# 6. Proposed database model and migration order

The following is a logical model. Exact columns, indexes, foreign keys, constraints and RLS policies must be designed and reviewed in SQL migrations before application code relies on them.

| Table group | Tables | Key design notes |

| --- | --- | --- |

| Identity / tenancy | tenants, tenant_domains, branches, tenant_memberships | Membership maps authenticated user to tenant and role; verified domain records; tenant status. |

| Clinic content | clinic_profiles, services, faqs, knowledge_documents, knowledge_chunks | Separate structured facts from uploaded documents; content approval/versioning; tenant_id on all tenant-owned rows. |

| Conversations | conversations, messages, conversation_handoffs | Visitor session should be pseudonymous where possible; define retention; restrict staff access. |

| Scheduling | integration_connections, appointment_types, appointments, booking_events | Store provider reference and minimal booking information; unique provider event identifiers. |

| Notifications | notification_preferences, notification_jobs, notification_attempts, email_templates | Persistent scheduling, retry state, idempotency key and provider message ID. |

| Commercial | plans, feature_catalog, plan_entitlements, tenant_subscriptions, usage_events | Server-side entitlement checks; immutable usage events where practical. |

| Governance | audit_events, data_subject_requests, deletion_jobs | Record privileged actions; track request workflow and deletion propagation. |



## 6.1 Suggested migration sequence

1. Create extensions and shared database helper functions only after security review.

1. Create tenants, tenant_domains, users/membership mapping and roles.

1. Create clinic profile, branches, services and FAQ tables.

1. Enable RLS immediately as tenant-owned tables are introduced; add positive and negative policy tests.

1. Create knowledge document/chunk tables and tenant-scoped retrieval indexes.

1. Create conversations, messages and handover tables.

1. Create integration connection, booking and webhook event tables.

1. Create notification preferences, jobs and attempts.

1. Create plan, entitlement and usage metering tables.

1. Add audit events, data lifecycle requests and operational support tables.

Use UUID primary keys, explicit foreign keys, appropriate unique constraints, created_at/updated_at timestamps and indexes based on actual query patterns. Avoid adding patient-specific data fields until a defined booking requirement and privacy assessment justify them.

# 7. API design and route map

Use a versioned API prefix, consistent error envelope, correlation ID, request validation and documented authentication requirements. Route names below are proposed contracts, not yet implemented.

| Area | Example routes | Access |

| --- | --- | --- |

| Public widget | POST /api/v1/public/widget/session; POST /api/v1/public/chat/messages; POST /api/v1/public/handoffs | Public, rate-limited, tenant/domain-resolved. |

| Clinic profile | GET/PATCH /api/v1/clinic/profile; CRUD /api/v1/clinic/services; CRUD /api/v1/clinic/faqs | Authenticated clinic roles; per-action permission checks. |

| Knowledge | POST /api/v1/clinic/knowledge; GET /api/v1/clinic/knowledge; POST /api/v1/clinic/knowledge/{id}/publish | Admin/editor roles; upload scanning and approval. |

| Inbox | GET /api/v1/clinic/conversations; GET /api/v1/clinic/conversations/{id}; POST .../reply; POST .../assign | Authenticated staff; tenant ownership enforced. |

| Scheduling | GET /api/v1/clinic/scheduling/providers; POST /api/v1/clinic/scheduling/connections; GET .../availability; POST .../bookings | Entitlement + clinic role; provider connection checks. |

| Webhook | POST /api/v1/webhooks/calcom; POST /api/v1/webhooks/calendly; POST /api/v1/webhooks/email-provider | Unauthenticated transport but signature verification, replay protection and idempotency required. |

| Usage / billing | GET /api/v1/clinic/usage; GET /api/v1/clinic/entitlements | Owner/admin access; server-side entitlement source. |

| Platform admin | POST /api/v1/platform/tenants; PATCH /api/v1/platform/tenants/{id}; GET /api/v1/platform/usage | Platform admin only; MFA and audit logging. |



## 7.1 API contract rules

- Use Pydantic models for every input and structured response.

- Reject unknown or invalid fields on sensitive operations where appropriate.

- Use pagination and bounded page sizes for lists.

- Return generic public errors; log internal detail securely with correlation ID.

- Require idempotency keys for booking creation and other non-repeatable actions.

- Do not expose internal database errors, provider credentials or stack traces.

- Document scopes/roles and tenant ownership for every endpoint.

# 8. Widget architecture and installation

The widget must be easy to add to an existing website without asking the clinic to rebuild the site. For the first release, an iframe-based widget is a strong default because it isolates the assistant's styles and DOM from the clinic website. A lightweight script loader can create the iframe and pass only the public widget identifier.

<script src="https://widget.zuvoora.com/loader.js" data-widget-id="PUBLIC_WIDGET_ID" async></script>

The above is illustrative only; the actual domain, attribute names, CSP requirements and loader implementation will be decided during development.

- Use a versioned widget loader and cache static assets safely.

- Validate registered website origin on the backend; allow explicit admin-approved additional domains.

- Do not treat CORS as authentication; protect public endpoints with tenant checks, rate limits and abuse controls.

- Provide a non-JavaScript fallback contact link where practical.

- Support mobile, keyboard navigation, screen readers, reduced motion and visible AI identity.

- Make the clinic's privacy notice accessible before or during data collection.

- Provide a safe maintenance/disabled state if the tenant is suspended or widget service is unavailable.

# 9. AI and knowledge implementation plan

## 9.1 Knowledge ingestion pipeline

1. Clinic administrator enters structured clinic facts and/or uploads an approved document.

1. Validate file type, size and content; quarantine uploads before parsing.

1. Extract text using safe parsers; scan files and reject unsupported or suspicious formats.

1. Split content into chunks with source/document identifiers and tenant metadata.

1. Generate embeddings using an approved provider; review data transfer and retention implications.

1. Store vectors and metadata in tenant-scoped tables.

1. Require a clinic admin to approve/publish content before it is available to the public assistant.

1. On update, create a new document version and retire stale chunks safely.

## 9.2 Answer generation controls

- Retrieve a bounded number of relevant chunks from the active tenant and relevant branch.

- Prefer structured clinic facts for deterministic questions such as opening hours and contact details.

- Include source freshness metadata and do not use expired/unapproved content.

- Ask the model to answer only from evidence; if evidence is missing, respond with a transparent fallback.

- Use a fixed administrative assistant policy; do not accept user/document instructions that override it.

- Do not expose chain-of-thought, system prompts, secrets or internal retrieval metadata.

- Store model/provider, token usage, latency and safety outcome metadata without unnecessarily storing sensitive prompt content.

- Create evaluation sets from synthetic clinic FAQs and clinician-reviewed examples before pilot.

## 9.3 Model selection

Do not hard-code a specific DeepSeek or other model as the permanent product brain. Create a model registry/configuration by task and evaluate candidate models on answer accuracy, refusal behaviour, latency, cost, language quality, provider terms and data handling. A low-cost model is appropriate only if it passes the evaluation set.

| Task | Initial policy |

| --- | --- |

| Simple FAQ | Use deterministic lookup where possible; otherwise economical model. |

| Multi-document clinic question | RAG with economical model and strict source grounding. |

| Booking intent extraction | Structured schema/tool proposal; backend validates all values. |

| Safety-sensitive or ambiguous query | Safe refusal/handover; do not attempt clinical diagnosis. |

| Provider outage | Graceful fallback and contact details; never pretend the AI completed the task. |



# 10. Scheduling and reminder sequence

Visitor asks to book
  → API checks tenant entitlement and provider connection
  → API retrieves availability
  → visitor selects slot and confirms details
  → API revalidates slot
  → provider booking API called with idempotency control
  → provider success verified
  → appointment row persisted
  → confirmation and clinic alert queued
  → reminder jobs scheduled

Provider webhook: cancellation/reschedule
  → verify signature + timestamp/replay protection
  → persist provider event ID (unique)
  → update appointment state
  → cancel/recompute pending reminder jobs
  → notify relevant parties

- Store timestamps in UTC and the clinic's IANA timezone (for example, Africa/Lagos); render local time to users.

- Use provider event IDs and unique constraints to deduplicate webhooks.

- Before sending a reminder, re-read appointment status and current schedule.

- Define what happens when a booking is made close to reminder time or provider status is unknown.

- Keep notification content minimal; do not include clinical details in ordinary email.

- Make reminder timing configurable by tenant within safe bounds.

# 11. Identity, permissions and entitlement policy

| Role | Example permitted actions | Explicitly disallowed by default |

| --- | --- | --- |

| Platform super-admin | Create/suspend tenant, manage plan, support administration, review platform health. | Unlogged browsing of private conversation content; routine access to clinical records. |

| Clinic owner | Manage clinic, invite users, integrations, package and data requests. | Access to other tenant's data. |

| Clinic admin | Manage clinic content, staff and permitted integrations. | Change platform-level controls or other tenant records. |

| Receptionist | View/assign permitted conversations, respond, manage approved booking workflow. | Change billing, manage owner account, export all data without permission. |

| Viewer | Read approved dashboards and limited records. | Modify content, integrations or access controls. |



Entitlement evaluation must be server-side and should return an explicit allow/deny result with a reason code. A disabled feature must not be reachable by directly calling its API route.

# 12. Development workflow and Definition of Done

1. Create an issue with user value, acceptance criteria, data classification and threat considerations.

1. Create a feature branch from protected main; use small, reviewable pull requests.

1. Run formatting, linting, type checks and unit tests locally.

1. Run secret scanning and dependency checks before push.

1. Open pull request; GitHub Actions runs tests, SAST, secrets scan, dependency and container/config scans.

1. Review code for authorisation, tenant scoping, logging, privacy and failure modes.

1. Merge only after required checks and review pass.

1. Deploy to staging; run integration, E2E, tenant-isolation and AI evaluation tests.

1. Obtain product/security acceptance for sensitive workflows.

1. Deploy to production through a controlled workflow with rollback and monitoring.

## 12.1 Definition of Done

- Acceptance criteria pass and tests are committed.

- API contract and user-facing behaviour are documented.

- Tenant and role checks exist on server-side paths.

- Logs contain no secrets or unnecessary sensitive content.

- Error, retry and provider-outage behaviour is defined.

- Database migrations are reviewed and reversible where feasible.

- Accessibility and responsive behaviour are checked for UI changes.

- Relevant security scans pass policy; exceptions have owner, rationale and expiry.

- Monitoring/alerts are updated for new critical workflows.

- Support documentation and release notes are updated.

# 13. CI/CD security gates

| Gate | Tool / check | Suggested policy |

| --- | --- | --- |

| Code quality | Ruff/pytest for Python; ESLint/TypeScript checks for web | Fail on lint/type/test errors. |

| Secrets | Gitleaks and GitHub secret scanning if available | Block confirmed secrets; rotate any exposed credential immediately. |

| SAST | Semgrep | Block defined high/critical findings; triage medium findings. |

| Dependencies | pip-audit or equivalent; npm audit with reviewed policy | Block exploitable critical/high vulnerabilities; pin and update dependencies. |

| Container/config | Trivy filesystem, config and image scans | Block critical/high issues according to risk policy. |

| Database/security tests | RLS and tenant-isolation integration tests | Must pass on every relevant PR and staging release. |

| DAST | OWASP ZAP against staging | Run on release cadence; block confirmed exploitable high-risk findings. |

| AI evaluations | Prompt injection, tenant leakage, unsafe clinical answer and tool abuse suite | Block release if safety/tenant isolation thresholds fail. |



Tune scanners to avoid blindly blocking every low-confidence finding. Every exception must have a documented owner, risk acceptance, mitigation and expiry. Automated scanning does not replace code review or professional penetration testing.

# 14. Observability and operations

| Signal | Examples | Alert trigger |

| --- | --- | --- |

| Availability | API/widget health checks, database connectivity | Service unavailable beyond defined threshold. |

| Performance | p50/p95 API latency, model latency, widget load | Sustained degradation beyond SLO. |

| Queue | Backlog, oldest job age, retries, dead-letter count | Reminder jobs at risk of being late. |

| Provider health | AI, email, scheduling error rate and timeouts | Provider outage or abnormal failure increase. |

| Security | Repeated auth failures, rate-limit hits, invalid webhooks, unusual tenant usage | Abuse pattern or suspicious access. |

| Cost | Tokens, model cost, messages and estimated tenant margin | Tenant usage spike or budget threshold. |



- Use structured logs with correlation IDs; avoid logging message text by default.

- Keep separate operational and audit event streams.

- Define retention and access permissions for logs.

- Set up tested database backups and periodic restore drills.

- Maintain incident runbooks for leaked key, tenant data exposure, AI provider outage, email outage and compromised admin account.

# 15. Security threat review — first-pass

| Threat | Potential impact | Primary controls |

| --- | --- | --- |

| Cross-tenant data access | Clinic data disclosure | RLS, backend tenant context, negative tests, vector/storage isolation. |

| Prompt injection | Unsafe output or attempted data/tool misuse | Constrained tools, untrusted content handling, server-side policy, red-team tests. |

| Widget abuse/bot spam | Cost spikes and service degradation | Rate limits, quotas, bot controls, tenant suspension/alerts. |

| Credential leakage | Provider/account compromise | Secret manager, scanning, rotation, least privilege, no frontend secrets. |

| Forged webhook | False booking state or notifications | Signature verification, replay protection, event idempotency. |

| Duplicate booking | Operational confusion and patient impact | Idempotency keys, unique provider references, state reconciliation. |

| Stale reminder | Patient receives incorrect appointment message | Persistent job state recheck; cancel/reschedule propagation. |

| Malicious document upload | Parser exploit or prompt injection | File limits, allowlist, scanning, quarantine, safe parser and approval. |

| Admin account compromise | Tenant configuration/data misuse | MFA, session controls, RBAC, audit, alerts and recovery. |

| Sensitive data sent to AI/email vendor | Privacy and contractual exposure | Minimisation, vendor assessment, redaction, data-processing terms. |



This is an initial threat register, not a complete threat model. Conduct a formal data-flow and abuse-case review before pilot data is processed.

# 16. Implementation phases, milestones and exit criteria

| Phase | Work packages | Exit criteria |

| --- | --- | --- |

| 0 — Project setup | Verify folder, Git repo, environments, secrets policy, docs and decision log. | Clean repo, protected main, CI skeleton and approved baseline. |

| 1 — Secure foundation | Auth, tenant schema, memberships, RLS, audit, roles, migrations and negative tests. | Cross-tenant and role tests pass; no privileged secrets in client. |

| 2 — Clinic admin | Profile, branches, services, FAQs, domain verification and user invitations. | Clinic can configure approved public information safely. |

| 3 — Widget and chat | Widget loader, public API, sessions, rate limiting, conversation storage and handover. | Widget works on test website; domain and tenant checks pass. |

| 4 — Knowledge and AI | Ingestion, approval, RAG, model gateway, evaluation suite and usage metering. | Grounded answer tests pass; safe fallback and injection tests pass. |

| 5 — Booking and email | Scheduling adapters, provider connections, webhook processing, Resend and worker jobs. | Test booking lifecycle, duplicate webhook and reminder cancellation pass. |

| 6 — SaaS packaging | Entitlements, plans, quotas, usage dashboard and admin controls. | Package gates enforced server-side; usage measurable. |

| 7 — Production readiness | Monitoring, backups, restore, incident runbooks, privacy review and staging security scans. | Release checklist complete and pilot approval recorded. |

| 8 — Pilot and iteration | Three clinic pilots, measured outcomes, feedback and pricing validation. | Renewal evidence, product changes and go/no-go decision. |



Do not start all phases at once. Complete and review each phase's exit criteria before introducing more sensitive workflows.

# 17. First two weeks — detailed starter plan

| Day / block | Task | Deliverable |

| --- | --- | --- |

| 1 | Verify external SSD drive letter, exact folder name, Git status and existing ZUVOORA separation. | Confirmed project path and no accidental coupling. |

| 2 | Create GitHub repository, README, branch protection and .gitignore. | Remote repository and clean initial commit. |

| 3 | Create docs/decision log, .env.example, secret handling guidance. | Project documentation baseline. |

| 4 | Select supported runtime versions and pin dependencies; scaffold Next.js, FastAPI and worker. | Buildable skeleton. |

| 5 | Create local Docker Compose for app, database/queue only as selected; add health checks. | Repeatable local environment. |

| 6–7 | Add CI: lint, type checks, unit tests, Gitleaks, Semgrep and dependency scans. | First security-gated pull request. |

| 8–9 | Design tenant schema and threat/data-flow diagram; review RLS policies. | Reviewed database design before migration. |

| 10 | Implement initial tenant/auth migration and automated RLS negative tests. | First secure foundation milestone. |

| 11–12 | Implement membership/role checks and audit event foundation. | Role and permission tests. |

| 13–14 | Architecture review checkpoint; resolve issues before clinic profile and widget work. | Phase 1 readiness decision. |



The plan is intentionally foundation-heavy. It is better to spend the first two weeks establishing a secure, repeatable project than to rush into a visually impressive chatbot with unsafe data boundaries.

# 18. Claude Code / Codex working instructions

Use the following as a reusable project-level instruction file or initial coding-agent prompt. It is deliberately conservative: the coding agent must inspect the repository and propose changes before making broad architectural assumptions.

PROJECT: ZUVOORA Engage
OWNER: ZubeVision Technologies Ltd.
SOURCE OF TRUTH: docs/product/PRD.md, docs/architecture/architecture.md,
docs/security/security-baseline.md and docs/decisions/ADR-*.md.

NON-NEGOTIABLE RULES:
1. Keep this repository independent from the existing ZUVOORA project.
2. Build a multi-tenant SaaS product; never create customer-specific code forks.
3. Never trust tenant_id, role, plan or permissions supplied by the browser.
4. Enforce tenant isolation and authorisation on the server and database.
5. Never expose provider keys, service-role keys or secrets in frontend code.
6. Do not implement diagnosis, prescribing or autonomous clinical advice.
7. AI output is untrusted. Never execute model-generated SQL, shell or arbitrary code.
8. Booking success must be confirmed by the scheduling provider before being shown as confirmed.
9. Reminder jobs must be persistent, idempotent and re-check appointment status before sending.
10. Add tests for security boundaries and failure modes with every feature.
11. Run lint, type checks, tests, secret scans and security scans before declaring work complete.
12. Do not silently change architecture. Propose an ADR for material changes.

WORK METHOD:
- First inspect the repository and report what exists.
- Read the source-of-truth documents.
- State assumptions and identify missing decisions.
- Propose a small implementation plan and files to change.
- Implement one milestone at a time.
- Add/update tests and docs.
- Report commands run, results, limitations and remaining risks.
- Never claim tests or security checks passed unless they were actually executed.

# 19. Architecture decision records to create

| ADR | Decision to record | Status |

| --- | --- | --- |

| ADR-001 | Standalone repository and deployment boundary from ZUVOORA Core | Proposed; accept before scaffold. |

| ADR-002 | Dedicated Supabase project and tenant isolation strategy | Proposed; detailed RLS review required. |

| ADR-003 | Widget isolation approach: iframe vs web component | Open; prototype and assess CSP/accessibility. |

| ADR-004 | Queue/worker technology | Open; choose after operational comparison. |

| ADR-005 | Scheduling adapter contract and provider sequencing | Proposed; validate provider API/plan access. |

| ADR-006 | Email provider abstraction with Resend initial adapter | Proposed; validate account and deliverability. |

| ADR-007 | AI gateway/model evaluation and provider data policy | Open; evaluate candidate models and terms. |

| ADR-008 | Data retention, logging and deletion policy | Open; privacy/legal review required. |

| ADR-009 | Deployment topology on Contabo and capacity thresholds | Open; load test and threat review. |

| ADR-010 | Three-layer entitlement and upgrade model | Proposed; align PRD and pricing. |



# 20. Go/no-go checklist before real clinic pilot

- PRD and architecture baseline approved and versioned.

- Pilot clinic contract, data-processing terms and privacy notice reviewed.

- Clinic has approved the exact public knowledge and escalation wording.

- Widget domain is verified and installation tested.

- RLS, tenant isolation, role and public endpoint negative tests pass.

- AI evaluation set passes; no known cross-tenant or unsafe clinical response issue.

- Scheduling provider connection and webhook verification pass in test environment.

- Booking idempotency, cancellation, rescheduling and reminder suppression pass.

- Email sender domain authenticated; delivery, bounce and retry behaviour tested.

- Backups and restoration tested; incident contact and rollback plan documented.

- Usage limits, alerts and customer support expectations are configured.

- Clinic staff have been trained and have accepted the workflow.

# 21. Final recommendations

- Keep the first release focused: administrative chatbot, approved knowledge, human handover, then booking and reminders.

- Architect for Cal.com and Calendly from day one, but sequence production integrations according to validated provider access and pilot needs.

- Use an iframe widget unless a prototype demonstrates a clear reason to choose another embed method.

- Use a persistent worker/queue for reminders; do not rely on process memory or cron-only assumptions.

- Use a dedicated Engage Supabase project and prove RLS with automated negative tests before real clinic data.

- Do not use Kubernetes just because it was part of the DevOps learning journey; Docker Compose is a sensible initial operating model on one VPS.

- Keep the full ZUVOORA ecosystem integration API-based and versioned; avoid direct shared database coupling.

- Make privacy, clinical boundaries, provider data handling and customer contracts release requirements.

# Appendix A — Founder checklist for the first coding session

- Connect the Transcend SSD and confirm its stable drive letter.

- Open the exact ZUVOORA-ENGAGE folder, not the existing ZUVOORA folder.

- Confirm Git repository root in VS Code terminal before running scaffold commands.

- Create or confirm a private GitHub repository.

- Ensure no .env file, credentials, clinic exports or patient data are tracked.

- Commit the blueprint documents into docs/ as versioned project references.

- Create a development-only environment and synthetic sample tenant.

- Run the initial CI workflow and verify it fails when a test or secret scan is intentionally triggered in a safe test fixture.

# Appendix B — Source documents

- 01_ZUVOORA_Engage_PRD.docx — Product requirements baseline.

- 02_ZUVOORA_Engage_Technical_Security_Architecture.docx — Technical and security architecture baseline.

- 03_ZUVOORA_Engage_Commercial_GTM_Strategy.docx — Commercial and go-to-market baseline.
