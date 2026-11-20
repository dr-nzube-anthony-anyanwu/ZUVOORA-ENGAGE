# Phased Implementation Plan

| Phase | Focus | Exit gate |
|---|---|---|
| 0 | Environment, repository, starter validation | API/web checks pass, no secrets, correct Git remote |
| 1 | Auth, tenancy, RBAC, RLS, audit | Cross-tenant and role negative tests pass |
| 2 | Clinic onboarding, services, FAQs, domains, knowledge approval | Tenant-safe admin workflows pass |
| 3 | Widget, sessions, chat, RAG, human handover | Domain, RAG isolation and AI safety tests pass |
| 4 | Cal.com/Calendly, Resend, jobs/reminders | Booking lifecycle, idempotency and reminder tests pass |
| 5 | Packages, entitlements, quotas, usage, analytics | Server-side feature gating and cost visibility |
| 6 | Security hardening, deployment, monitoring, backup, pilot | Release checklist and pilot approval |
| 7 | WhatsApp, voice, multi-branch, ZUVOORA Core integration | Separate business case and threat review for each |

## Phase 0
Verify SSD path; keep existing ZUVOORA separate; check Python 3.12, Node 24 LTS, Git, Docker, Claude Code; create private repo; run tests/lint/typecheck/build and Compose validation.

## Phase 1
Dedicated Supabase project, migrations, Auth, membership, roles, RLS, audit and negative security tests.

## Phase 2
Clinic onboarding, profile, hours, services, FAQs, domain verification, document quarantine/approval/versioning.

## Phase 3
Widget, public domain validation, conversations, OpenRouter gateway, tenant-scoped RAG, handover and AI evaluations.

## Phase 4
Scheduling adapters, booking lifecycle, signed webhooks, Resend, persistent worker and reminders.

## Phase 5
Feature catalogue, entitlements, plans, quotas, usage metering, analytics and upgrade path.

## Phase 6
Production controls, HTTPS, monitoring, backup/restore, incident response, privacy review and pilot.

## Phase 7
Optional channels and deeper ecosystem integrations only after pilot evidence.
