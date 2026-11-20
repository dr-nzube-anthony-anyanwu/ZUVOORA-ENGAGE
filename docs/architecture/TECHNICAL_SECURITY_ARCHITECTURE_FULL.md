# Technical & Security Architecture

> Full text converted from the editable Word blueprint. Refer to the source Word copy in `docs/source_word_documents/`.

ZUBEVISION TECHNOLOGIES LTD.

# Technical & Security Architecture

ZUVOORA Engage — multi-tenant SaaS, integrations, DevSecOps and operational design

ZE-ARCH-002  |  Version 1.0  |  20 November 2026

CONFIDENTIAL – INTERNAL PRODUCT, ENGINEERING AND COMMERCIAL PLANNING

# 1. Purpose and architecture principles

This document defines the proposed technical and security architecture for ZUVOORA Engage. It is a design baseline for implementation planning. Exact service sizing, provider capabilities, pricing, legal obligations and production security controls must be verified during build and before launch.

- Separate Engage project/repository from the existing ZUVOORA codebase.

- Independent deployment and database boundary initially; integrate with wider ZUVOORA through authenticated APIs.

- One multi-tenant Engage platform, not one application deployment per clinic.

- Tenant context must be established and enforced server-side.

- Secure defaults, least privilege, defence in depth and privacy by design.

- Provider adapters for scheduling, email and AI model routing.

- Persistent background jobs for delayed notifications.

- Observable, testable and recoverable operations.

# 2. Project and repository layout

User's working directory is on the Transcend external SSD. Current arrangement, based on the confirmed description:

| Path | Purpose |

| --- | --- |

| D:\Technologies\ZUVOORA | Existing flagship ZUVOORA project; do not casually modify while building Engage. |

| D:\Technologies\ZUVOORA-ENGAGE | New independent Engage repository/root. |



The external SSD should retain a stable drive letter. Use Git remote repositories and a separate encrypted/off-device backup strategy; the SSD is a working location, not the only backup.

Suggested initial repository layout:

ZUVOORA-ENGAGE/
  apps/
    web/                  # Next.js clinic dashboard and super-admin UI
    widget/               # embeddable browser widget build
    api/                  # FastAPI application
    worker/               # persistent background worker
  packages/
    contracts/            # shared API schemas/types where practical
    email-templates/      # versioned transactional templates
  infrastructure/
    docker/
    nginx/
    github-actions/
    monitoring/
  docs/
    product/
    architecture/
    security/
    operations/
  tests/
    unit/
    integration/
    security/
    e2e/
  scripts/
  .github/workflows/
  .env.example
  .gitignore
  README.md

# 3. High-level architecture

| Component | Responsibility | Security boundary |

| --- | --- | --- |

| Website widget | Loads chat UI and sends visitor messages with public tenant/widget identifier. | No secrets; origin validation; rate limiting; CSP/CORS controls; minimal browser storage. |

| Next.js web app | Clinic dashboard, onboarding, platform administration. | Authenticated users; server-side session handling; role/tenant checks. |

| FastAPI API | Tenant resolution, business rules, chat orchestration, booking and admin endpoints. | Central authorisation point; strict schemas; rate limits; audit events. |

| AI gateway | Model/provider abstraction, prompt policy, usage metering and model selection. | API keys server-side; per-tenant quotas; no direct model access to database. |

| RAG service | Retrieval from tenant-approved knowledge content. | Tenant filter enforced in query path and database policy; document lifecycle controls. |

| PostgreSQL/Supabase | Tenants, users, content, conversations, bookings, integrations, usage and audit records. | RLS, least-privilege roles, private schemas, backup and access monitoring. |

| Worker/queue | Reminders, email, webhook processing, ingestion and retries. | Separate service identity; signed/verified events; idempotency; restricted network access. |

| External providers | Cal.com, Calendly, Resend, optional Brevo and model providers. | OAuth/token protection, webhook verification, vendor review and scoped permissions. |



# 4. Data and tenant isolation model

Every tenant-owned record must carry a tenant identifier or be reachable only through a parent record whose tenant ownership is verified. Tenant identifiers received from browsers are untrusted hints, not proof of permission.

## 4.1 Proposed logical entities

| Entity | Important fields / notes |

| --- | --- |

| tenants | id, legal_name, display_name, status, timezone, plan_id, created_at |

| tenant_domains | id, tenant_id, hostname, verification_status, verified_at |

| users | id, auth_subject, email, status, MFA state where available |

| tenant_memberships | tenant_id, user_id, role, status, invited_by |

| branches | id, tenant_id, name, address, timezone, contact details |

| clinic_profiles | tenant_id, opening hours, service descriptions, public contact and policies |

| knowledge_documents | id, tenant_id, source, status, version, checksum, approved_by, reviewed_at |

| knowledge_chunks | id, tenant_id, document_id, content, embedding, metadata |

| conversations | id, tenant_id, visitor/session reference, status, channel, created_at |

| messages | id, tenant_id, conversation_id, role, content, safety metadata, timestamps |

| appointments | id, tenant_id, provider, provider_booking_id, status, time, timezone, minimal booking data |

| integration_connections | id, tenant_id, provider, encrypted credential reference, scopes, status |

| notification_jobs | id, tenant_id, appointment_id, event, scheduled_at, status, idempotency_key |

| usage_events | id, tenant_id, feature, provider, units, estimated_cost, occurred_at |

| subscriptions_entitlements | tenant_id, plan, features, limits, effective dates |

| audit_events | actor, tenant_id, action, resource type/id, outcome, timestamp, correlation id |



## 4.2 RLS and access control requirements

- Enable RLS on every tenant-owned table exposed through Supabase client access.

- Use policies based on authenticated user membership and role, not user-supplied tenant_id alone.

- Keep service-role credentials server-side only; never expose them in Next.js client bundles or widget code.

- Prefer a restricted application database role for backend operations; avoid using a broad service credential for every query.

- Where a privileged backend bypasses RLS, enforce tenant authorization in a central, tested data-access layer and log privileged operations.

- Test direct API calls, guessed IDs, nested relationships, exports, search, vector retrieval, storage objects and background jobs for cross-tenant access.

- Use separate roles for platform administration, tenant administration, workers and read-only analytics where practical.

| Critical design rule / A public widget identifier identifies a clinic configuration; it does not authorise access to private conversations, patient details, appointments or dashboard data. |

| --- |



# 5. Authentication, authorisation and sessions

- Use Supabase Auth initially, with verified email and secure recovery flow.

- Require MFA for ZubeVision super-admin accounts; strongly encourage or require it for clinic owners depending on risk and provider support.

- Implement RBAC roles: platform super-admin, clinic owner, clinic admin, receptionist/operator and read-only viewer.

- Check permissions on the backend for every sensitive action; frontend hiding is not security.

- Use secure, HttpOnly, SameSite cookies where compatible with the selected auth architecture; avoid storing long-lived access tokens in localStorage.

- Set session expiry, refresh, revocation and account deactivation behaviour.

- Protect invitations and password resets against enumeration and abuse.

- Record role changes, integration changes, exports, deletion and privileged access in audit logs.

# 6. Widget and public API security

- Generate a non-secret public widget identifier; never embed API keys or privileged credentials.

- Verify the request Origin/hostname against a registered tenant domain and enforce an explicit allowlist. Treat Origin checks as one control, not the sole defence.

- Use restrictive CORS and Content Security Policy guidance for clinic websites.

- Apply per-IP, per-tenant and per-session rate limits, request size limits and abuse detection.

- Validate all inputs with strict schemas; normalise text safely; render untrusted content with output encoding.

- Use bot mitigation/challenge controls when abuse patterns justify them.

- Keep public endpoints separate from authenticated clinic-admin endpoints.

- Return generic errors to public clients; do not leak stack traces, tenant existence, prompts or internal IDs.

# 7. AI gateway and RAG security

## 7.1 Request flow

1. Widget sends message, public widget identifier and conversation token to the API.

1. API validates tenant status, registered domain, quotas and abuse controls.

1. API creates or validates a conversation scoped to that tenant.

1. RAG layer searches only approved, published knowledge for that tenant and permitted branch/context.

1. AI gateway constructs a constrained prompt with retrieved material clearly marked as untrusted reference content.

1. Model returns response or structured tool proposal.

1. Server validates output and any proposed action; booking tools are invoked only after permission, data validation and user confirmation.

1. Response is stored with minimal required metadata; usage and safety events are recorded.

## 7.2 AI threat controls

- Prompt injection: treat user messages and retrieved documents as untrusted; system instructions alone are not a security boundary.

- Tenant leakage: apply tenant filters in retrieval queries and verify tenant ownership at the database layer.

- Tool abuse: expose narrow, typed tools; never provide arbitrary SQL, shell, unrestricted URL fetch or unrestricted database access to the model.

- Action authorisation: model intent is not authorisation. Server-side policy must validate clinic, role, booking state and user confirmation.

- Data exfiltration: do not place secrets or unrelated tenant data in prompts; redact sensitive fields and limit context.

- Hallucinations: answer from approved sources; abstain when evidence is missing; never invent opening hours, fees, availability or services.

- Uploaded documents: scan and parse safely; restrict file types/size; quarantine until approved; do not treat document instructions as system instructions.

- Model output: validate structured outputs and encode before rendering; never execute model-generated code.

- Model/provider logging: review retention and training settings; avoid sending unnecessary personal or health information to providers.

- Testing: maintain adversarial test cases for prompt injection, cross-tenant retrieval, unsafe clinical advice and tool misuse.

# 8. Scheduling integration architecture

Support Cal.com and Calendly through a common internal scheduling interface with provider-specific adapters. The platform should not assume that API access, webhooks or OAuth features are available on every plan; verify current provider documentation, scopes, limits and customer account eligibility during implementation.

class SchedulingProvider:
    async def list_event_types(self, tenant_id): ...
    async def get_availability(self, tenant_id, event_type, date_range): ...
    async def create_booking(self, tenant_id, request, idempotency_key): ...
    async def cancel_booking(self, tenant_id, provider_booking_id): ...
    async def reschedule_booking(self, tenant_id, provider_booking_id, new_slot): ...
    async def verify_webhook(self, headers, body): ...

- Store each tenant's provider connection separately and encrypt refresh/access tokens or store references in a managed secrets store.

- Use least-privilege OAuth scopes and support disconnect/revocation.

- Re-check availability before creating a booking to reduce race conditions.

- Use idempotency keys and unique provider event IDs to prevent duplicate bookings.

- Verify webhook signatures using provider-supported methods; reject invalid or replayed events.

- Handle provider downtime with a clear fallback: provide clinic contact/handover rather than falsely confirming a booking.

- Store provider booking references and minimal local state; define reconciliation for missed webhooks.

- Use clinic timezone explicitly and store timestamps in UTC plus the clinic timezone identifier.

# 9. Email and notification architecture

Use an internal EmailService interface. Resend is the initial transactional email adapter; keep a Brevo adapter feasible without coupling business logic to either provider.

| Message type | Trigger | Controls |

| --- | --- | --- |

| Booking confirmation | Provider confirms booking | Only send after confirmed state; idempotency key. |

| Clinic new-booking alert | Confirmed booking | Limit personal data in email; link to authenticated dashboard. |

| Reminder | Configured lead time before appointment | Recheck current booking status, consent/preferences and timezone before sending. |

| Cancellation | Verified cancellation | Cancel future reminder jobs; send confirmation. |

| Reschedule | Verified reschedule | Replace old reminders and send updated details. |

| Human handover | Visitor requests staff or AI cannot resolve | Send minimal context and secure dashboard link. |



- Authenticate sending domains with SPF, DKIM and DMARC; monitor reputation, bounces and complaints.

- Do not send sensitive clinical details in ordinary email unless the legal, security and provider requirements have been assessed.

- Use persistent notification_jobs records and a durable queue/worker; do not rely on in-memory FastAPI background tasks for jobs due hours or days later.

- Retry transient failures with exponential backoff and jitter; move repeated failures to a dead-letter state for review.

- Use idempotency keys to avoid duplicate email after retries.

- Provide unsubscribe/communication preference handling where required; distinguish transactional notices from marketing messages.

- Keep templates versioned, reviewed and tenant-configurable only through safe fields.

# 10. Background jobs and reliability

Use a persistent queue/scheduler. A practical initial option is Celery with Redis, or a managed durable queue/scheduler if operational simplicity is preferred. The decision should account for the Contabo deployment footprint, persistence, monitoring, recovery and team familiarity.

- Persist job intent in the database before acknowledging critical workflows.

- Use a unique idempotency key for every scheduled action.

- Recheck source-of-truth state before executing a reminder.

- Make workers safe to restart and support graceful shutdown.

- Use retry policies by error class; do not retry permanent validation/authentication errors indefinitely.

- Expose queue depth, oldest-job age, failures and retry counts in monitoring.

- Define manual replay and dead-letter review procedures.

# 11. Feature entitlements and three-layer product model

| Commercial layer | Entitlement examples | Architecture behaviour |

| --- | --- | --- |

| Layer 1 — Engage Essentials | Chatbot, knowledge base, widget, inbox, basic analytics, enquiry email | Enabled by tenant plan; no booking entitlement unless separately purchased. |

| Layer 2 — Engage Advanced | Scheduling, reminder engine, advanced analytics, WhatsApp, voice, multi-branch options | Feature flags/entitlements enable modules; integrations still require customer setup and provider authorisation. |

| Layer 3 — Full ZUVOORA | Core/EMR, Scribe, ZANYRA Insight, ZUVEYA Vision, longitudinal monitoring, integrated Engage | Engage communicates with ZUVOORA modules through authenticated, versioned APIs; shared identity only after security design. |



Do not implement package checks as scattered frontend conditionals. Use a central entitlement service/policy with server-side checks on every feature endpoint. A plan upgrade should enable existing capabilities and preserve tenant data; it should not require a new codebase.

# 12. Integration with the existing ZUVOORA platform

- Keep Engage in its own repository and dedicated Supabase project initially.

- Integrate through documented, versioned APIs with service-to-service authentication and scoped credentials.

- Do not directly share database tables or credentials between Engage and the existing ZUVOORA application.

- Define canonical identifiers and mapping for clinic, branch, patient and appointment only when required.

- Use explicit consent and workflow rules before moving patient information between systems.

- Provide an upgrade path: an Engage-only clinic can later connect to ZUVOORA Core without losing its Engage tenant, widget or conversation history.

- Use event/API contracts and contract tests to prevent changes in one product from silently breaking the other.

# 13. Shift-left security and DevSecOps

| Stage | Controls / tools | Gate |

| --- | --- | --- |

| Plan/design | Threat modelling, data-flow diagrams, security requirements, privacy review, OWASP ASVS mapping | High-risk threats have mitigations and owners. |

| Local development | Pre-commit checks, secret scanning, linting, unit tests, secure coding guidance | No committed secrets; critical tests pass. |

| Pull request | GitHub Actions, Semgrep SAST, Gitleaks, dependency audit, Trivy filesystem/config scan | Block merge for defined critical/high findings and failed tests. |

| Build | Pinned dependencies where practical, SBOM generation, container image scan, signed/reproducible build practices as feasible | Only approved images/artifacts proceed. |

| Staging | Integration tests, tenant isolation tests, OWASP ZAP baseline/active scan in controlled environment | No unresolved release-blocking vulnerabilities. |

| Production | TLS, hardened host, least privilege, monitoring, alerting, backups, audit logs | Deployment checklist and rollback plan approved. |

| Ongoing | Patch management, vulnerability triage, access review, restore tests, incident exercises | Findings tracked to closure. |



## 13.1 Initial toolchain

| Purpose | Suggested tool |

| --- | --- |

| Source control / CI | GitHub and GitHub Actions |

| SAST | Semgrep |

| Secret scanning | Gitleaks plus GitHub secret scanning where available |

| Dependency/container/config scanning | Trivy; ecosystem-native dependency audit tools |

| Dynamic web testing | OWASP ZAP against staging |

| API testing | Pytest, HTTPX, schema and authorisation tests |

| Web testing | Playwright or equivalent end-to-end tests |

| Infrastructure | Docker, Nginx, UFW, SSH hardening; Terraform for repeatable infrastructure where useful |

| Monitoring | Uptime Kuma plus application metrics/logging and alerting |

| Security references | OWASP ASVS, OWASP Top 10, NIST SSDF |



# 14. Infrastructure and deployment

Initial deployment target is the existing Contabo VPS environment, but Engage should have its own deployment configuration and service boundaries. Do not assume that the same VPS is automatically sufficient for production; load-test and monitor resource use before adding customer traffic.

- Use separate development, staging and production environments, even if staging initially shares modest infrastructure.

- Run services as non-root users; minimise installed packages and exposed ports.

- Expose only required public ports (typically 80/443); restrict SSH to trusted sources where practical and use key-based authentication.

- Use Nginx as reverse proxy and obtain TLS certificates; enforce HTTPS and secure headers.

- Use Docker Compose initially if it meets operational needs; do not add Kubernetes complexity until scale/operational requirements justify it.

- Keep secrets outside images and source control; use protected deployment secrets and rotate credentials.

- Use health checks, resource limits, restart policies and log rotation.

- Back up database and critical configuration; encrypt backups and test restoration.

- Separate worker and API processes; avoid mounting unnecessary host paths or Docker socket access into application containers.

- Document DNS, certificates, firewall rules, deployment, rollback and disaster recovery.

# 15. Logging, monitoring and incident response

- Use structured logs with correlation IDs and tenant IDs where appropriate, but avoid logging message bodies, access tokens, secrets or unnecessary health information.

- Record security audit events for login anomalies, role changes, integration changes, exports, deletion, admin access and suspicious requests.

- Monitor API latency/error rates, database health, queue backlog, AI cost, provider failures, email bounces and widget abuse.

- Alert on unusual tenant usage spikes, repeated authentication failures, webhook verification failures and abnormal data access patterns.

- Define incident severity, owner, containment steps, evidence preservation, notification decision process and recovery steps.

- Review applicable statutory breach notification timelines with qualified privacy/legal advice; do not improvise legal deadlines.

# 16. Privacy, data protection and clinical safety

- Map data flows and identify controller/processor roles for each customer arrangement.

- Collect only data needed for the stated service; avoid asking website visitors to enter detailed medical histories.

- Provide transparent privacy information and appropriate consent/preference controls.

- Define retention schedules for anonymous chats, booking records, audit records and backups.

- Support data subject requests through a documented workflow, subject to lawful retention obligations.

- Review data processing terms, subprocessors, cross-border transfers and model-provider retention/training terms.

- Assess obligations under Nigeria's Data Protection Act 2023 and NDPC guidance; obtain legal advice for contracts and operational compliance.

- Before international launch, assess local requirements such as UK GDPR, HIPAA where applicable in the US, and relevant Canadian privacy laws.

- Keep the chatbot administrative; urgent symptoms require safe escalation language and no false reassurance.

# 17. Testing strategy

| Test category | Examples |

| --- | --- |

| Unit | Tenant resolver, entitlement checks, prompt assembly, notification scheduling, provider adapter mapping. |

| Integration | Supabase RLS, OAuth token refresh, provider API errors, webhook signatures, email sending. |

| Security negative tests | Tenant A attempts to read Tenant B; receptionist attempts owner action; anonymous user attempts private endpoint. |

| AI red-team tests | Prompt injection, cross-tenant retrieval, secret extraction, malicious uploaded document, unauthorised tool invocation. |

| Reliability | Duplicate webhooks, worker restart, queue outage, provider timeout, email retry, reminder cancellation. |

| End-to-end | Clinic onboarding, widget conversation, handover, booking, confirmation and reminder lifecycle. |

| Accessibility | Keyboard navigation, screen reader labels, contrast, mobile layout. |

| Performance | Widget load, concurrent chat, API p95 latency, queue throughput and database load. |



# 18. Release readiness checklist

- All MVP requirements and acceptance criteria pass.

- Tenant isolation negative tests pass across API, database, storage, RAG, exports and workers.

- No unresolved critical/high release-blocking security findings.

- Secrets scanning and dependency/container scans pass policy.

- Provider credentials and webhook verification configured in production.

- Backup restoration has been tested.

- Privacy notice, customer terms, data processing agreement and retention policy reviewed.

- Clinic knowledge content approved and reviewed.

- Operational dashboards and alerting are active.

- Support and incident escalation contacts are defined.

- Rollback and provider-outage fallback are documented.

- Customer acceptance testing completed.

# 19. Decisions still requiring technical validation

- Cal.com and Calendly API/OAuth/webhook capabilities and plan restrictions for target customers.

- Whether Celery/Redis or a managed queue/scheduler is the best first production choice.

- Supabase project configuration, RLS patterns, vector extension availability and backup plan.

- Resend sending limits, domain authentication and account eligibility; Brevo adapter requirements.

- Contabo capacity under measured concurrent traffic and worker load.

- Model-provider data retention, regional processing, cost and acceptable use terms.

- Exact tenant data retention and privacy contract terms.
