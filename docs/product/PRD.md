# Product Requirements Document — ZUVOORA Engage

## Vision
Make existing eye-care websites more useful through responsive, clinic-specific patient engagement.

## Definition
An independently purchasable multi-tenant SaaS platform that embeds an AI administrative assistant on an eye-care website. It answers from clinic-approved information, captures enquiries and hands off to staff; later it supports scheduling and reminders.

## Customers
Independent optometry practices, private eye clinics, ophthalmology practices, eye hospitals and optical retail businesses. Buyers are clinic owners/directors; operators are administrators/receptionists; end users are prospective/existing patients.

## Commercial layers
1. Essentials: widget, clinic knowledge, FAQs, enquiries, handover, basic analytics.
2. Advanced: scheduling, reminders, advanced reporting, optional WhatsApp/voice.
3. Full ZUVOORA: Engage integrated with Core, Scribe, ZANYRA Insight and ZUVEYA Vision.

## MVP
Multi-tenant onboarding; clinic profile/domains/services/hours/FAQs; approved knowledge; website widget; tenant-scoped AI; inbox/handover; usage metering; authentication, RBAC, RLS, audit and privacy controls.

## Later releases
Cal.com/Calendly adapters; booking lifecycle; Resend email/reminders; entitlements and analytics; optional channels and Core integration.

## Exclusions
No autonomous diagnosis, treatment recommendations, prescribing or EMR replacement. No per-clinic code forks. No false booking confirmations.

## Acceptance
Tenant isolation across all data paths; safe fallback for unknown facts; domain validation/rate limits; provider-confirmed booking; idempotent webhooks; obsolete reminders suppressed; server-side entitlements; no secrets in frontend/source.
