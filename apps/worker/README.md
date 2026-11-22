# Background worker

The background worker is **not** a separate application. It is part of the API package and runs
from `apps/api`:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

In Docker Compose it is the `worker` service (same image as the API, no exposed ports).

## What it does (Phase 4–5, ADR-033 to ADR-039)
- Claims jobs from the durable PostgreSQL queue (`app_private.jobs`) with `SKIP LOCKED` leases;
  several workers can run safely at the same time.
- Retries failures with backoff; jobs that keep failing become dead letters after a 23-hour cut-off.
- Sends transactional email through Resend with idempotency keys (log-only by default; outside
  production only allowlisted recipients receive email).
- Job types: booking confirmation, clinic booking alert, 24-hour and optional 2-hour reminders,
  cancellation notice, call-back alert, "website chat stopped" alert, quota alert, booking
  reconciliation.
- Every job re-checks the current state before acting (a cancelled booking never gets a reminder;
  a suspended clinic gets nothing).
- Runs as the restricted `engage_jobs` database role, which has no table access and works only
  through dedicated functions.

Scheduled jobs (such as the daily domain re-verification, `python -m app.jobs.reverify_domains`)
are described in [`docs/operations/SCHEDULED_JOBS.md`](../../docs/operations/SCHEDULED_JOBS.md).

This folder is kept only as a pointer; there is no code here.
