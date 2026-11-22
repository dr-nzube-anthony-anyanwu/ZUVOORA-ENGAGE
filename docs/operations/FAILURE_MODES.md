# Failure modes — booking, webhooks, jobs and email (Phase 4)

What happens when things go wrong, what the patient and the clinic see, and where each behaviour
is tested. "API test" = `apps/api/tests/integration`, "DB test" = `supabase/tests` (pgTAP),
"unit" = `apps/api/tests`. Decisions: ADR-033 to ADR-036.

| # | Failure | What the system does | Patient sees | Clinic sees | Proven by |
|---|---|---|---|---|---|
| 1 | Provider unreachable before a booking is sent (connect error, 429) | Attempt marked `failed`; nothing booked | "Online booking is not available right now" + option to contact the clinic | Nothing to do | API test `test_provider_refusal_or_outage_books_nothing` |
| 2 | Provider timeout / 5xx **after** the booking was sent | Attempt marked `unknown`; call-back request created with the patient's details; reconciliation job checks the provider after 1, 3 and 10 minutes (Cal.com by `engage_ref`; Calendly by type + time + email); then `confirmed` (emails follow) or `failed`. Never retried blindly | "Nothing is confirmed yet — the clinic team will contact you" | Call-back request in the Inbox; booking shows "Being checked" | API tests `test_lost_response_is_never_reported_as_booked_and_is_reconciled`, `test_unknown_outcome_that_never_happened_ends_failed` |
| 3 | Chosen time taken by someone else meanwhile | Slot re-checked just before booking; attempt `failed` without calling the provider's booking API | "That time is no longer available" + fresh times | Nothing | API test `test_a_taken_slot_is_caught_before_booking`; Playwright `widget-booking.spec.ts` |
| 4 | Provider refuses the booking (slot gone, payment required, location mismatch) | Attempt `failed` | Same as 3 | Nothing | API test (refusal case) |
| 5 | Duplicate webhook delivery (provider retry or replay) | Body hash recorded once per connection; repeat returns `duplicate` with no effect | — | — | DB test `12_booking_lifecycle` (2); API tests `test_cancellation_in_calcom_is_applied_once…`, `test_booking_and_calendly_cancellation_webhook` |
| 6 | Forged / tampered / stale webhook | HMAC check on the raw body (Cal.com hex/base64; Calendly `t=,v1=` with 3-minute tolerance), signed `createdAt` within 72 h; unknown connection, bad secret and bad signature all answer the same 401 | — | Security log event | Unit `test_webhooks.py`, `test_calendly.py`; API test `test_unverifiable_deliveries_are_refused`; mutation-checked |
| 7 | Webhook never arrives (misconfigured, provider outage) | Bookings made in the widget are still recorded; staff cancellations update locally after provider success; changes made only in the provider are missed until the webhook works | — | "Booking updates: Not set up" on the Scheduling page | Documented limitation; webhook set-up tests |
| 8 | Appointment cancelled / moved / rejected | All queued confirmations, alerts and reminders for it are skipped in the same transaction; a cancellation notice is queued; a move creates a new appointment with its own reminders | Cancellation email; new confirmation for a move | Status in Appointments | DB test `12_booking_lifecycle` (mutation-checked) ; API tests (cancel, reschedule) |
| 9 | Worker crashes or restarts mid-job | Claimed jobs have a 120 s lease; an expired lease is re-claimed. Email sends carry the job's idempotency key, so a re-run within 24 h does not deliver twice | At most one email | — | DB test `09_jobs` (expired lease); API test `test_a_crashing_job_is_retried_not_lost` |
| 10 | Email provider down (429/5xx/timeout) | Retries with exponential backoff, at most 8 attempts and only within 23 hours (inside Resend's 24-hour idempotency window); then `dead` | Email may be late, never doubled | — | DB test `09_jobs`; API test `test_temporary_failure_is_retried_with_the_same_key` |
| 11 | Email permanently refused (bad address, unverified domain) | Job `dead` immediately | — | — | API test `test_permanent_failure_goes_to_dead_letters` |
| 12 | Clinic's provider key revoked | Provider answers 401/403 → connection marked `failing`; widget booking unavailable (nothing booked); reconciliation stops (dead letter) | "Online booking is not available right now" | "Needs attention" on the Scheduling page | API tests `test_revoked_key_marks_the_connection_failing`, `test_revoked_key_stops_booking_and_flags_the_connection` |
| 13 | Stored key cannot be decrypted (key lost or ciphertext copied from another clinic) | Refused; never used for another clinic | "Not available" | "Connect again" message | API test `test_a_credential_copied_to_another_clinic_cannot_be_used` |
| 14 | Clinic suspended | Widget refuses to load; no booking; worker skips every email (data functions return nothing for suspended clinics); webhooks for it are not accepted | Chat unavailable | — | DB tests `09_jobs`, `05_widget`; API test `test_suspended_clinic_gets_no_alert` |
| 15 | Clinic disconnects the provider | Credential and webhook secret erased; booking types hidden from the widget; webhooks refused | Booking button gone | — | DB tests `10_scheduling`, `12_booking_lifecycle` |
| 16 | Staff cancels but the provider does not confirm | Local status unchanged (no false "cancelled"); the provider's webhook brings the truth | — | "The scheduling provider did not confirm the cancellation" | API test `test_staff_cancel_goes_through_calcom_first` |
| 17 | Two bookings submitted at once in one chat | One in-flight booking per conversation (unique index); at most 3 per conversation; rate limits per IP and conversation | Second gets "already in progress" | — | DB test `11_appointments`; API test `test_booking_limit_per_conversation` |
| 18 | Domain lost / DNS record removed | Daily re-check; 3 definite failures lapse the domain (widget stops there) and email owners/admins | Chat no longer on that site | "Website chat stopped" email | DB tests `08_domain_recheck`, `09_jobs`; API test `test_record_removed_for_three_checks…` |

## Known limits (tracked)

- Cal.com's webhook signature encoding is undocumented; both hex and base64 forms of the HMAC are
  accepted. Confirm against a real delivery when the API has a public URL (Phase 6 staging).
- Calendly is implemented from its documentation only (no live account yet). Its free plan allows
  5 API bookings per day; Calendly has no booking metadata, so reconciliation matches type, time
  and email; rescheduling happens through Calendly's own link.
- Changes made directly in the provider for bookings not made through Engage are ignored.
