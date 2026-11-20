# Product Requirements Document

> Full text converted from the editable Word blueprint. Refer to the source Word copy in `docs/source_word_documents/`.

ZUBEVISION TECHNOLOGIES LTD.

# Product Requirements Document (PRD)

ZUVOORA Engage — AI-powered patient engagement for eye-care businesses

ZE-PRD-001  |  Version 1.0  |  20 November 2026

CONFIDENTIAL – INTERNAL PRODUCT, ENGINEERING AND COMMERCIAL PLANNING

# Document control

| Field | Value |

| --- | --- |

| Product | ZUVOORA Engage |

| Owner | ZubeVision Technologies Ltd. |

| Document purpose | Product scope, requirements, user journeys, acceptance criteria and release priorities |

| Status | Baseline for discovery and MVP planning; not yet a production specification |

| Version | 1.0 |

| Initial market | Nigeria, beginning with Abuja; designed for later regional and international expansion |

| Primary customer | Independent optometry practices, private eye clinics, ophthalmology practices and eye hospitals |

| Product relationship | Independently purchasable module in the wider ZUVOORA ecosystem |



# 1. Executive summary

ZUVOORA Engage is a multi-tenant SaaS patient-engagement platform that allows eye-care businesses to add an intelligent, clinic-specific assistant to an existing website. The initial product helps visitors obtain verified administrative information, submit enquiries and—when enabled—book appointments through connected scheduling providers. It gives clinic staff a dashboard to manage clinic information, review conversations, handle escalations and understand engagement.

Engage must be independently useful to a clinic that does not want the full ZUVOORA operating system. It must also be designed to integrate with ZUVOORA Core and other modules so a customer can expand without replacing its initial implementation.

| Product principle / Build the reusable platform once; configure it for many clinics. Custom enterprise work is separately scoped and priced. Security, privacy, tenant isolation and clinical safety are product requirements—not optional add-ons. |

| --- |



# 2. Vision, positioning and outcomes

## 2.1 Vision

Make existing eye-care websites more useful by turning passive pages into responsive, clinic-specific patient-engagement experiences.

## 2.2 Positioning

ZUVOORA Engage is an AI-powered patient engagement and digital receptionist platform designed specifically for eye-care businesses. It is not positioned as an autonomous diagnostic tool or a replacement for receptionists or clinicians.

## 2.3 Desired outcomes

- Help prospective patients get accurate clinic information without waiting for staff to respond.

- Reduce repetitive administrative enquiries and interruptions for clinic staff.

- Make appointment requests and confirmed bookings easier where scheduling integration is enabled.

- Provide measurable visibility into website conversations, unresolved enquiries and booking activity.

- Give clinics an affordable entry point into the broader ZUVOORA ecosystem.

- Create a repeatable SaaS business in which onboarding a new clinic is primarily configuration, not bespoke software development.

# 3. Problem statement and assumptions

Many clinic websites provide static information and contact details but do not actively answer questions, guide visitors or support a complete booking journey. Clinics may rely on phone calls and messaging channels, creating delays when staff are busy or unavailable. This is a market hypothesis to validate with interviews and pilots; it should not be treated as a universal claim about all Nigerian eye clinics.

# 3.1 Key assumptions to validate

- Target clinics receive enough website or digital enquiries to benefit from automation.

- Repeated administrative questions consume staff time or delay patient responses.

- Clinic owners value after-hours responsiveness and easier booking enough to pay a setup fee and recurring subscription.

- Clinic staff can maintain accurate service, price, opening-hour and policy information.

- Patients are comfortable using a clearly identified AI assistant for administrative questions.

- Scheduling providers and email services can be connected under customer-owned or platform-managed arrangements.

# 4. Target users and personas

| Persona | Goals | Needs / constraints |

| --- | --- | --- |

| Clinic owner / director | Improve patient access, reputation and operational efficiency | Clear ROI, affordable pricing, control over clinic content, reliable support |

| Clinic administrator | Maintain settings and monitor activity | Simple dashboard, role controls, reports, easy configuration |

| Receptionist | Respond to enquiries and manage bookings | Conversation inbox, escalation, booking visibility, minimal extra work |

| Prospective patient | Find accurate information and book a visit | Fast answers, clarity, accessible mobile experience, human contact option |

| Existing patient | Confirm or manage an appointment | Reliable reminders, clear confirmation, privacy and communication preferences |

| ZubeVision platform administrator | Onboard and support multiple clinics | Tenant administration, usage metering, entitlement controls, auditability |



# 5. Product model and three commercial layers

The ecosystem has three commercial layers. These are packaging and capability tiers, not three unrelated applications.

| Layer | Customer need | Typical capabilities |

| --- | --- | --- |

| Layer 1 — Engage Essentials | A clinic wants an intelligent website assistant without a full practice-management system. | Embeddable chatbot, clinic knowledge base, FAQ answers, enquiry capture, human handover, basic dashboard and analytics. |

| Layer 2 — Engage Advanced | A clinic wants richer patient engagement and workflow automation. | Everything in Essentials plus booking integrations, confirmations, reminders, enhanced analytics, optional WhatsApp and voice integrations, multi-branch options. |

| Layer 3 — Full ZUVOORA | A clinic or hospital wants an integrated eye-care operating system. | Engage as an integrated capability plus applicable Core/EMR, Scribe, ZANYRA Insight, ZUVEYA Vision, longitudinal monitoring and other modules. |



A full ZUVOORA customer should not be forced into a disconnected second product. Engage capabilities should be accessible through the wider ZUVOORA experience, with shared identity and secure API integration where architecturally appropriate. The standalone Engage product remains independently sellable.

# 6. Scope

## 6.1 MVP — must have

- Multi-tenant clinic onboarding and configuration.

- Clinic profile: name, branches (initially optional), website domains, location, contact information, opening hours, services and approved FAQs.

- Knowledge-base ingestion from structured admin forms and approved documents; content review and publication workflow.

- Website-embeddable chat widget with responsive mobile design and clinic-specific branding.

- Backend tenant resolution and server-side tenant isolation.

- AI responses grounded in the selected clinic's approved knowledge; source-aware refusal when information is unavailable.

- Conversation persistence and clinic dashboard inbox.

- Human handover path with clinic contact details or staff notification.

- Usage metering, configurable limits and basic analytics.

- Authentication, roles, audit events and platform super-admin functions.

- Privacy notice, data minimisation, consent/preferences where applicable and retention configuration.

## 6.2 Release 1.1 — booking and transactional email

- Scheduling integration abstraction with separate Cal.com and Calendly adapters.

- Clinic connection and configuration flow for each supported provider.

- Availability retrieval and booking creation using provider-supported APIs.

- Booking confirmation, cancellation and rescheduling event handling.

- Email-provider abstraction; Resend as initial provider, with Brevo-ready adapter design.

- Persistent background job processing for reminders and notifications.

- Configurable reminder rules, initially 24 hours before and optional 2 hours before.

- Idempotency, retries, dead-letter handling and booking-status rechecks before sending reminders.

## 6.3 Later releases — optional modules

- WhatsApp Business Platform integration, subject to business verification, consent and template rules.

- Voice AI receptionist and inbound/outbound workflows.

- SMS provider integrations.

- Advanced multi-branch administration and consolidated reporting.

- Deeper integration with ZUVOORA Core, patient records and clinic workflows.

- Additional languages and localisation.

- Custom enterprise identity, integration and reporting requirements.

## 6.4 Explicitly out of scope for initial releases

- Autonomous diagnosis, triage decisions or treatment recommendations.

- Medication prescribing or clinical decision-making.

- Replacing the clinic's EMR or practice-management system.

- Collecting detailed medical histories through a general website chatbot.

- Guaranteeing appointment conversion, revenue uplift or clinical outcomes.

- Building a separate codebase for every clinic.

- Unreviewed autonomous access to clinical records or unrestricted AI tool execution.

# 7. Functional requirements

| ID | Requirement | Description | Priority |

| --- | --- | --- | --- |

| FR-001 | Tenant onboarding | Platform admin can create a clinic tenant, set its status, configure its domain and assign an owner. | Must |

| FR-002 | Clinic administration | Authorised clinic users can manage approved profile, service, FAQ and opening-hour data. | Must |

| FR-003 | Website widget | Clinic can embed a widget using a tenant-specific public identifier and approved domain. | Must |

| FR-004 | Tenant resolution | Backend validates tenant, domain and widget configuration before processing a public request. | Must |

| FR-005 | Knowledge retrieval | Assistant retrieves only content belonging to the resolved tenant and approved publication state. | Must |

| FR-006 | Grounded answers | Assistant answers from retrieved clinic content; if evidence is insufficient it says so and offers human contact. | Must |

| FR-007 | Conversation inbox | Authorised staff can view and respond to conversations belonging to their clinic. | Must |

| FR-008 | Human escalation | Visitor can request staff contact; clinic receives a configured notification or task. | Must |

| FR-009 | Usage metering | System records tenant-level message, token, provider and feature usage for limits and cost analysis. | Must |

| FR-010 | Scheduling adapters | System supports provider-specific adapters behind a common scheduling interface. | Should |

| FR-011 | Booking lifecycle | System records booking references and handles confirmed, cancelled and rescheduled events safely. | Should |

| FR-012 | Email notifications | System sends transactional messages through a provider abstraction and records delivery status. | Should |

| FR-013 | Reminder scheduler | System schedules persistent reminders and cancels/recomputes them after booking changes. | Should |

| FR-014 | Feature entitlements | System enables features according to a tenant's subscription/package and authorised add-ons. | Must |

| FR-015 | Audit trail | System records security-relevant administrative and integration actions. | Must |

| FR-016 | Data lifecycle | Authorised users can request/export/delete data according to policy and legal obligations. | Must |



# 8. User journeys

## 8.1 Clinic onboarding

1. ZubeVision admin creates a tenant and records the legal/business name, owner contact and selected package.

1. Clinic owner receives an invitation and completes account setup with strong authentication.

1. Clinic administrator enters and verifies website domain, opening hours, services, contact details and approved FAQs.

1. Knowledge content is reviewed and published; the system shows missing or stale information warnings.

1. Widget is generated for the clinic and tested on a staging or approved website.

1. Clinic staff complete acceptance checks; the tenant is activated and usage limits are applied.

## 8.2 Visitor enquiry

1. Visitor opens the clinic website and launches the assistant.

1. Widget sends a public tenant identifier and origin context; backend validates the registered domain and public configuration.

1. Visitor asks an administrative question.

1. Backend retrieves tenant-scoped approved knowledge and calls the configured model through the server-side AI gateway.

1. Assistant provides a concise answer or admits that the information is unavailable and offers human contact.

1. Conversation and usage events are stored with the tenant context and appropriate privacy controls.

## 8.3 Appointment booking

1. Visitor asks to book; assistant explains that booking is available and collects only required details.

1. Backend checks feature entitlement, clinic scheduling connection and provider availability.

1. Visitor selects an available slot; backend revalidates availability immediately before creating the booking.

1. Provider confirms booking; system stores provider reference and status.

1. Confirmation email is queued; clinic notification is sent.

1. Reminder jobs are scheduled using the clinic's configured time zone.

1. On cancellation or rescheduling webhook, the system verifies the event, updates state and cancels/recomputes pending reminders.

# 9. Non-functional requirements

| Area | Requirement / target for MVP |

| --- | --- |

| Availability | Set an initial service objective after deployment baseline; target 99.5% monthly for production MVP, excluding announced maintenance, subject to hosting design. |

| Performance | Aim for fast widget load and responsive first response; measure p50/p95 latency and optimise based on real traffic. Do not promise a fixed AI response time before measurement. |

| Scalability | Tenant-aware architecture; stateless API where practical; background jobs separated from request handling. |

| Accessibility | Keyboard operable, readable contrast, accessible labels, responsive layout and graceful non-chat contact alternatives. |

| Reliability | Persistent jobs, bounded retries, idempotent booking and notification processing. |

| Security | Least privilege, tenant isolation, secrets management, secure headers, rate limits, audit logs and automated security checks. |

| Privacy | Data minimisation, clear privacy notices, retention/deletion controls, restricted access and processor/vendor review. |

| Maintainability | Typed interfaces, documented APIs, migrations, automated tests and provider adapters. |

| Observability | Structured logs, metrics, traces where useful, tenant-safe correlation IDs and alerting. |



# 10. AI behaviour and clinical safety

- Assistant is an administrative information and booking assistant, not a clinician.

- Do not diagnose, prescribe, interpret test results or provide individualised treatment plans.

- Do not imply that a symptom is safe to ignore. For potentially urgent symptoms, advise prompt contact with an appropriate eye-care professional or emergency service using a clinic-approved escalation message.

- Use clinic-approved content for opening hours, services, fees and policies; show uncertainty when information is missing or stale.

- Never fabricate prices, appointment slots, credentials, locations or clinical services.

- Do not expose prompts, secrets, internal configuration, other tenants' content or private conversations.

- Tool calls such as booking, cancellation or rescheduling require backend authorisation, validated arguments and confirmation of provider success.

- Treat uploaded documents and retrieved text as untrusted data, not instructions that override system policy.

# 11. Analytics and success metrics

| Metric | Definition / reason |

| --- | --- |

| Widget engagement | Unique sessions that start a conversation; measure adoption. |

| Resolved conversation rate | Conversations resolved without human escalation, reviewed for quality. |

| Human handover rate | Share requiring staff attention; reveals knowledge gaps and complex needs. |

| After-hours conversation share | Demand outside clinic opening hours. |

| Booking intent rate | Conversations that request booking. |

| Confirmed booking rate | Provider-confirmed bookings attributable to Engage; not merely booking clicks. |

| Reminder delivery rate | Successful reminder deliveries and failures. |

| Knowledge answer quality | Sampled answer accuracy and unsupported-answer rate. |

| Cost per conversation | AI, hosting and relevant provider cost divided by eligible conversations. |

| Customer retention | Renewal/churn by cohort and package. |

| Staff time impact | Clinic-reported change in repetitive enquiry workload; validate with baseline. |



# 12. Acceptance criteria and release gates

- Tenant A cannot access Tenant B's records through UI, API, direct object identifiers, search, vector retrieval or background jobs.

- Widget only serves approved public configuration for an active tenant and permitted domain.

- Assistant does not answer a clinic-specific question from another clinic's knowledge base.

- Unknown clinic information produces a safe fallback rather than a fabricated answer.

- Booking is only described as confirmed after the scheduling provider confirms it.

- Duplicate webhook delivery does not create duplicate bookings, notifications or reminders.

- Rescheduling/cancellation invalidates obsolete reminder jobs.

- Clinic roles cannot perform actions outside their permissions.

- Secrets are not present in frontend bundles, logs, source control or public widget configuration.

- CI pipeline blocks defined high-severity security failures and failing critical tests.

# 13. Risks and mitigations

| Risk | Mitigation |

| --- | --- |

| Low website traffic means limited value | Qualify customers; measure baseline traffic and enquiry volume; do not promise lead generation. |

| Clinic information becomes outdated | Owner review workflow, last-reviewed timestamp, expiry reminders and easy update controls. |

| AI hallucination or unsafe advice | Tenant-scoped RAG, refusal behaviour, clinical boundaries, test sets and human escalation. |

| Cross-tenant exposure | RLS, backend tenant context, negative security tests, isolated vector filters and least privilege. |

| Provider API changes or plan limits | Adapter architecture, provider capability checks, contract tests and fallback/manual workflow. |

| Email deliverability problems | Domain authentication, suppression handling, bounce monitoring and provider abstraction. |

| Cost overrun | Per-tenant usage metering, quotas, alerts, model routing and abuse controls. |

| Support burden grows with custom work | Standard packages, documented onboarding, separately priced enterprise scope and change control. |



# 14. Open questions to resolve during discovery

- Which three pilot clinics will participate, and what websites do they use?

- Do pilot clinics already use Cal.com, Calendly or another scheduling tool?

- Who owns and pays for scheduling and email provider accounts?

- What information may the chatbot display publicly, and who approves it?

- What patient data is strictly necessary for booking?

- What are each clinic's preferred retention and communication rules?

- What support hours and service levels can ZubeVision realistically provide?

- What package limits and overage rules are commercially acceptable?

# 15. Glossary

| Term | Meaning |

| --- | --- |

| Tenant | A clinic/customer workspace with logically isolated data and configuration. |

| RAG | Retrieval-augmented generation: retrieving approved information before asking a model to answer. |

| RBAC | Role-based access control. |

| RLS | PostgreSQL row-level security. |

| Entitlement | A permission to use a paid feature under a package or add-on. |

| Webhook | A provider-to-platform event notification, such as a booking being cancelled. |

| Idempotency | A design property ensuring repeated requests/events do not cause duplicate effects. |

| DAST/SAST | Dynamic/static application security testing. |


