# Architecture Review & Development Blueprint

## Architecture review
The proposed direction is appropriate: independent Engage repository/deployment, dedicated database boundary initially, one multi-tenant SaaS, provider adapters, and API-based future integration with ZUVOORA Core.

## Repository layout
`apps/web`, `apps/widget`, `apps/api`, `apps/worker`, `database/migrations`, `docs`, `prompts`, `infra`, `tests`.

## Core request flow
Widget → public API → tenant/domain validation → conversation → tenant-scoped RAG → server AI gateway → answer/handover. Booking and webhooks flow through separate services and a persistent worker.

## Database domains
Tenants/domains/memberships; clinic content; knowledge documents/chunks; conversations/messages/handoffs; integrations/appointments/webhook events; notification jobs/attempts; plans/entitlements/usage; audit/data requests.

## API areas
Public widget sessions/messages/handoffs; clinic profile/services/FAQs/knowledge; inbox; scheduling; webhooks; usage/entitlements; platform administration. Every private endpoint must check membership, role and tenant ownership.

## Widget
Prototype an iframe for style/DOM isolation. Loader contains only a public widget identifier. Validate registered origin on the server; CORS is not authentication. Rate-limit public endpoints.

## AI/RAG
Use structured clinic facts for hours/services; approved and fresh documents for retrieval; model answers only from evidence. Unknown facts get a safe fallback. No arbitrary SQL/shell/network tools.

## Booking/email
Common scheduling interface. Revalidate availability. Confirm only after provider success. Verify webhooks, deduplicate events, persist jobs, re-check status before reminders. Resend first, Brevo-ready abstraction.

## Security gates
Ruff/pytest, ESLint/typecheck, Gitleaks, Semgrep, dependency audit, Trivy, tenant negative tests, OWASP ZAP on staging, AI adversarial evaluations.

## Phases
0 environment; 1 secure foundation; 2 clinic admin; 3 widget/chat/RAG; 4 scheduling/email; 5 SaaS entitlements; 6 hardening/pilot; 7 expansion.
