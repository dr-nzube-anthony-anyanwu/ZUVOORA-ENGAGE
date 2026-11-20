# Phase 4 — Scheduling and transactional email

Create common scheduling interface; Cal.com and Calendly adapters according to verified API/plan access; per-tenant secure connections; availability and revalidation; create/cancel/reschedule lifecycle; signed webhook verification, replay protection and idempotency. Add Resend email adapter, persistent queue/worker, confirmations, clinic alerts and reminders.

Booking is confirmed only after provider success. Duplicate webhooks cannot duplicate side effects. Cancellation/reschedule suppresses old reminders. Worker rechecks appointment status before sending. Provider outages must never produce false confirmation.
