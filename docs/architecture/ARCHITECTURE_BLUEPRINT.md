# Architecture Blueprint

## Objective
Standalone multi-tenant Engage SaaS with a future API-based integration path into the full ZUVOORA ecosystem.

## Request flow
```text
Clinic website → isolated widget → public API → tenant/domain validation
  → conversation service → tenant-scoped approved knowledge retrieval
  → server-side AI gateway → response / human handover

Clinic dashboard → Auth/session → RBAC + tenant membership + entitlements
  → clinic content / inbox / booking settings / analytics

Scheduling webhook → signature verification + replay protection
  → idempotent event handler → booking state → persistent worker
  → email provider adapter
```

## Boundaries
- Next.js: dashboard.
- Widget: embed UI; never trusted for authorisation.
- FastAPI: business logic and policy enforcement.
- Supabase: PostgreSQL, Auth, storage and RLS.
- OpenRouter: model routing behind internal gateway.
- Resend: initial email adapter.
- Cal.com/Calendly: scheduling adapters.
- Worker: durable notifications and webhook processing.
- Docker Compose: initial packaging.

## Multi-tenancy
Browser tenant IDs are untrusted. Resolve membership from verified auth and apply tenant scoping in backend and RLS. Public widget ID identifies public config only.

## ZUVOORA Core integration
Keep a separate Engage database initially. Integrate via authenticated, versioned APIs and explicit workflow/consent rules. No direct shared database credentials.

## Operations
Start with Docker Compose. Expose only reverse proxy ports; use HTTPS, non-root containers, secrets outside images, firewall/SSH hardening, monitoring and tested backups. Defer Kubernetes until justified.
