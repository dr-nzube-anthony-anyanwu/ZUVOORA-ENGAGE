# Background worker and scheduled jobs

## Worker (always running)

`python -m app.worker` (Compose service `worker`; `--once` processes due jobs and exits) sends
the emails queued in `app_private.jobs` (ADR-033). Several copies may run. It needs the API's
database settings plus the email settings:

| Setting | Meaning |
|---|---|
| `EMAIL_DELIVERY` | `log` (default): nothing is sent. `resend`: send through the Resend API. |
| `RESEND_API_KEY`, `EMAIL_FROM` | Required for `resend`. Use a sending-only key restricted to the verified domain. |
| `EMAIL_ALLOWED_RECIPIENTS` | Outside production, the only addresses/`@domains` that receive real email. Empty = none. |
| `WORKER_POLL_SECONDS` | Idle polling interval (default 5). |

Booking emails (Phase 4c–4d): patient **confirmation**, clinic **new booking** alert (no patient
details), **reminders** 24 hours before (and 2 hours before if the clinic turns it on),
**cancellation** notice; **reconciliation** of bookings whose provider response was lost. A
cancelled, rejected or moved appointment has its queued emails skipped immediately, and the
worker re-checks status and time before any reminder.

Other emails: **call-back request** alert to the clinic's owners, admins and receptionists
(no patient details — a link to the inbox), and **website chat stopped** alert to owners/admins
when a domain lapses. Failed sends retry with backoff for up to 23 hours, then become `dead`
(visible to operators in `app_private.jobs`).

## Scheduled jobs

Jobs run as the `engage_jobs` database role (ADR-031): no user, no tenant, no table access — only
the `app_private` functions granted to that role. They use the API's normal configuration
(`DATABASE_URL` as `engage_api`, which may `set role engage_jobs`).

| Job | Command (from `apps/api`, or in the API container) | Schedule | Purpose |
|---|---|---|---|
| Domain re-verification | `python -m app.jobs.reverify_domains` | Daily | Re-checks verified website domains' DNS TXT records; 3 consecutive definite failures return a domain to *pending*, which stops the chat widget on that site. |

Behaviour of `reverify_domains`:

- Checks domains that are verified, belong to a pending/active clinic and were not checked in the
  last 20 hours (up to 200 per run, oldest first).
- `not_found`/`mismatch` count as failures; `dns_error`/`timeout` are recorded but never count.
- A lapse writes the audit event `domain.verification_lapsed` (actor `00000000-0000-0000-0000-000000000000`,
  `request_id` = `job:reverify_domains:<run id>`).
- Prints counts only (`checked=… lapsed=… verified=…`); exit code 1 on configuration or database
  errors so the scheduler can alert.

Scheduling is configured at deployment (Phase 6). Until then the job can be run manually against
the local stack. Owner notification by email when a domain lapses arrives with the Phase 4 email
jobs.

## Answer evaluation (on request, not scheduled)

The live evaluation calls real models and spends credit, so it never runs automatically:

```powershell
# from apps/api, with the local Supabase stack running; the key is read from your env, never echoed
$env:EVAL_LIVE = "1"
$env:EVAL_OPENROUTER_API_KEY = "<dedicated, credit-limited key>"
$env:EVAL_REPORT = "<path>\eval.json"   # optional JSON report
$env:EVAL_CAP_USD = "0.10"              # optional; default 0.10
python -m pytest tests/integration/test_evaluation.py::test_evaluation_live
```

The hostile-model evaluation (`test_evaluation_with_hostile_model`) runs in CI on every push and
costs nothing.
