"""Background worker (Phase 4a, ADR-033):  python -m app.worker  [--once]

Claims due jobs from the Postgres queue as the `engage_jobs` role, re-checks each job's data at
send time (a handled request or a re-verified domain is skipped), sends email with no database
transaction open, and records the outcome. Safe to run several copies: claims use
FOR UPDATE SKIP LOCKED with a lease, and every send carries the job's idempotency key.
Logs never contain email addresses or message content.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import signal
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from app.config import Settings, get_settings
from app.db import Database
from app.services import email_templates
from app.services.email import Email, EmailError, EmailSender, build_sender
from app.services.scheduling.base import CredentialRejected, ProviderFactory, SchedulingError
from app.services.scheduling.calcom import DefaultProviderFactory
from app.services.secrets_box import Sealed, SecretsBox, SecretsBoxError

log = logging.getLogger("engage.worker")
BATCH = 10
LEASE_SECONDS = 120
PURGE_EVERY_SECONDS = 3600


@dataclass(frozen=True)
class Skip:
    reason: str


Handler = Callable[[psycopg.Connection, dict, Settings], Email | Skip]


def _recipients(
    conn: psycopg.Connection, tenant_id: uuid.UUID, roles: list[str]
) -> tuple[str, ...]:
    rows = conn.execute(
        "select email from app_private.job_recipients(%s, %s::public.membership_role[])",
        (tenant_id, roles),
    ).fetchall()
    return tuple(sorted(r["email"] for r in rows))


def handover_alert(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = conn.execute(
        "select * from app_private.job_handover_alert(%s)", (job["payload"].get("handover_id"),)
    ).fetchone()
    if row is None:
        return Skip("clinic inactive or request removed")
    if row["status"] != "new":
        return Skip("already being handled")
    to = _recipients(conn, row["tenant_id"], ["owner", "admin", "receptionist"])
    if not to:
        return Skip("no recipients")
    url = f"{settings.dashboard_url}/clinics/{row['tenant_id']}/inbox/{row['conversation_id']}"
    return email_templates.handover_alert(
        to, row["clinic"], row["created_at"], row["timezone"], url
    )


def domain_lapsed(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = conn.execute(
        "select * from app_private.job_domain_lapsed(%s)", (job["payload"].get("domain_id"),)
    ).fetchone()
    if row is None:
        return Skip("clinic inactive or domain removed")
    if not row["still_lapsed"]:
        return Skip("domain verified again")
    to = _recipients(conn, row["tenant_id"], ["owner", "admin"])
    if not to:
        return Skip("no recipients")
    url = f"{settings.dashboard_url}/clinics/{row['tenant_id']}/domains"
    return email_templates.domain_lapsed(to, row["clinic"], row["hostname"], url)


def _booking(conn: psycopg.Connection, job: dict) -> dict | None:
    return conn.execute(
        "select * from app_private.job_booking(%s)", (job["payload"].get("appointment_id"),)
    ).fetchone()


def booking_confirmation(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = _booking(conn, job)
    if row is None:
        return Skip("clinic inactive or booking removed")
    if row["status"] not in ("confirmed", "pending"):  # cancelled/failed since it was queued
        return Skip(f"booking is {row['status']}")
    return email_templates.booking_confirmation(
        row["attendee_email"],
        row["attendee_name"],
        row["clinic"],
        row["type_name"],
        row["start_at"],
        row["attendee_time_zone"],
        row["status"] == "pending",
        row["clinic_phone"],
        clinic_email=row.get("clinic_email"),
    )


def booking_alert(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = _booking(conn, job)
    if row is None:
        return Skip("clinic inactive or booking removed")
    if row["status"] not in ("confirmed", "pending"):
        return Skip(f"booking is {row['status']}")
    to = _recipients(conn, row["tenant_id"], ["owner", "admin", "receptionist"])
    if not to:
        return Skip("no recipients")
    url = f"{settings.dashboard_url}/clinics/{row['tenant_id']}/inbox/{row['conversation_id']}"
    return email_templates.booking_alert(
        to,
        row["clinic"],
        row["type_name"],
        row["start_at"],
        row["clinic_time_zone"],
        row["status"] == "pending",
        url,
    )


def booking_reminder(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = _booking(conn, job)
    if row is None:
        return Skip("clinic inactive or booking removed")
    if row["status"] != "confirmed":
        return Skip(f"booking is {row['status']}")
    # The reminder is for the time it was scheduled for; a moved booking has its own reminders.
    if (
        row["start_at"].isoformat()
        != datetime.fromisoformat(job["payload"]["start_at"]).isoformat()
    ):
        return Skip("appointment time changed")
    if row["start_at"] <= datetime.now(UTC):
        return Skip("appointment already started")
    return email_templates.booking_reminder(
        row["attendee_email"],
        row["attendee_name"],
        row["clinic"],
        row["type_name"],
        row["start_at"],
        row["attendee_time_zone"],
        row["clinic_phone"],
        clinic_email=row.get("clinic_email"),
    )


def booking_cancelled(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = _booking(conn, job)
    if row is None:
        return Skip("clinic inactive or booking removed")
    if row["status"] != "cancelled":
        return Skip(f"booking is {row['status']}")
    return email_templates.booking_cancelled(
        row["attendee_email"],
        row["attendee_name"],
        row["clinic"],
        row["type_name"],
        row["start_at"],
        row["attendee_time_zone"],
        row["clinic_phone"],
        clinic_email=row.get("clinic_email"),
    )


def quota_alert(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    row = conn.execute(
        "select clinic, plan_name from app_private.job_quota_alert(%s)", (job["tenant_id"],)
    ).fetchone()
    if row is None:
        return Skip("clinic inactive or subscription cancelled")
    to = _recipients(conn, job["tenant_id"], ["owner", "admin"])
    if not to:
        return Skip("no recipients")
    payload = job["payload"]
    return email_templates.quota_alert(
        to, row["clinic"], row["plan_name"], str(payload.get("metric")),
        int(payload.get("threshold", 0)), str(payload.get("period")),
        f"{settings.dashboard_url}/clinics/{job['tenant_id']}/plan",
    )


def demo_request_alert(conn: psycopg.Connection, job: dict, settings: Settings) -> Email | Skip:
    """Tell ZubeVision about a new demo request (no contact details in the email)."""
    recipient = settings.demo_request_notify_email
    if not recipient:
        return Skip("no notification address configured")
    row = conn.execute(
        "select clinic_name, city, country, interest, created_at, status "
        "from app_private.job_demo_request(%s)",
        (job["payload"].get("request_id"),),
    ).fetchone()
    if row is None:
        return Skip("request removed")
    place = ", ".join(p for p in (row["city"], row["country"]) if p)
    return email_templates.demo_request_alert(
        (recipient,), row["clinic_name"], place, row["interest"], row["created_at"],
        f"{settings.dashboard_url}/platform/demo-requests",
    )


HANDLERS: dict[str, Handler] = {
    "demo_request_alert": demo_request_alert,
    "quota_alert": quota_alert,
    "handover_alert": handover_alert,
    "domain_lapsed": domain_lapsed,
    "booking_confirmation": booking_confirmation,
    "booking_alert": booking_alert,
    "booking_reminder": booking_reminder,
    "booking_cancelled": booking_cancelled,
}

# Reconciliation attempts after an unknown booking outcome: 1 min, +2 min, +7 min.
RECONCILE_DELAYS = {1: 120, 2: 420}


def reconcile_booking(
    db: Database, job: dict, box: SecretsBox | None, providers: ProviderFactory | None
) -> str:
    """Find the booking we tried to create; confirm it, retry later, or record the failure."""
    if box is None or providers is None:
        raise EmailError("integrations_not_configured", permanent=False)
    appointment_id = job["payload"].get("appointment_id")
    attempt = int(job["payload"].get("attempt", 1))
    with db.jobs_transaction() as conn:
        row = conn.execute(
            "select * from app_private.job_booking_reconcile(%s)", (appointment_id,)
        ).fetchone()
    if row is None:
        return "skipped:gone"
    if row["status"] != "unknown":
        return "skipped:resolved"
    try:
        key = box.open(
            Sealed(bytes(row["ciphertext"]), row["key_id"]),
            purpose="scheduling",
            tenant_id=row["tenant_id"],
            record_id=row["connection_id"],
        )
    except SecretsBoxError as exc:
        raise EmailError("credential_unreadable", permanent=True) from exc
    provider = providers(row["provider"], key)
    try:  # no transaction open during the provider call
        found = provider.find_booking(
            appointment_id, row["provider_event_type_id"], row["start_at"], row["attendee_email"]
        )
    except CredentialRejected as exc:
        raise EmailError("credential_rejected", permanent=True) from exc
    except SchedulingError as exc:
        raise EmailError(f"provider:{exc.kind}", permanent=False) from exc
    with db.jobs_transaction() as conn:
        if found and found.status in ("confirmed", "pending"):
            conn.execute(
                "select app_private.job_resolve_booking(%s, %s, %s)",
                (appointment_id, found.status, found.provider_booking_id),
            )
            return f"resolved:{found.status}"
        if found or attempt not in RECONCILE_DELAYS:
            reason = f"provider_status:{found.status}" if found else "not_found_after_reconcile"
            conn.execute(
                "select app_private.job_resolve_booking(%s, 'failed', null, %s)",
                (appointment_id, reason),
            )
            return "resolved:failed"
        conn.execute(
            "select app_private.job_retry_reconcile(%s, %s, %s)",
            (appointment_id, attempt + 1, RECONCILE_DELAYS[attempt]),
        )
        return "retry_scheduled"


def process_batch(
    db: Database,
    sender: EmailSender,
    settings: Settings,
    box: SecretsBox | None = None,
    providers: ProviderFactory | None = None,
) -> Counter:
    outcome: Counter = Counter()
    with db.jobs_transaction() as conn:
        jobs = conn.execute(
            "select * from app_private.claim_jobs(%s, %s)", (BATCH, LEASE_SECONDS)
        ).fetchall()
    for job in jobs:
        try:
            if job["kind"] == "booking_reconcile":
                result = reconcile_booking(db, job, box, providers)
                with db.jobs_transaction() as conn:
                    if result.startswith("skipped:"):
                        conn.execute("select app_private.skip_job(%s, %s)", (job["id"], result))
                    else:
                        conn.execute(
                            "select app_private.complete_job(%s, %s::jsonb)",
                            (job["id"], json.dumps({"result": result})),
                        )
                outcome["reconciled"] += 1
                continue
            handler = HANDLERS.get(job["kind"])
            if handler is None:
                raise EmailError(f"unknown_kind:{job['kind']}", permanent=True)
            with db.jobs_transaction() as conn:
                prepared = handler(conn, job, settings)
            if isinstance(prepared, Skip):
                with db.jobs_transaction() as conn:
                    conn.execute(
                        "select app_private.skip_job(%s, %s)", (job["id"], prepared.reason)
                    )
                outcome["skipped"] += 1
                continue
            message_id = sender.send(prepared, job["idempotency_key"])  # no transaction open
            with db.jobs_transaction() as conn:
                conn.execute(
                    "select app_private.complete_job(%s, %s::jsonb)",
                    (job["id"], json.dumps({"message_id": message_id})),
                )
            outcome["sent"] += 1
        except EmailError as exc:
            status = _fail(db, job["id"], exc.kind, exc.permanent)
            log.warning(
                "job_failed id=%s kind=%s error=%s now=%s", job["id"], job["kind"], exc.kind, status
            )
            outcome[f"failed_{status}"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad job must not stop the worker
            log.exception("job_crashed id=%s kind=%s", job["id"], job["kind"])
            status = _fail(db, job["id"], type(exc).__name__, False)
            outcome[f"failed_{status}"] += 1
    return outcome


def _fail(db: Database, job_id: int, error: str, permanent: bool) -> str:
    with db.jobs_transaction() as conn:
        return conn.execute(
            "select app_private.fail_job(%s, %s, %s) as status", (job_id, error, permanent)
        ).fetchone()["status"]


def purge(db: Database) -> int:
    """Remove finished jobs past their retention, and demo requests older than 12 months."""
    with db.jobs_transaction() as conn:
        jobs = conn.execute("select app_private.purge_finished_jobs() as n").fetchone()["n"]
        conn.execute("select app_private.purge_demo_requests()")
        return jobs


def touch_heartbeat(path: str) -> None:
    """Tell the container health check this loop is alive (Phase 6, R11). Never fatal."""
    with contextlib.suppress(OSError):
        Path(path).touch()


def run_scheduled(db: Database, settings: Settings) -> None:
    """Daily domain re-verification (Phase 3f) from the worker loop. Safe to call hourly: only
    domains not checked in the last 20 hours are due. Failures are logged, never fatal."""
    from app.jobs import reverify_domains
    from app.services.domain_verification import DnsTxtVerifier

    try:
        summary = reverify_domains.run(db, DnsTxtVerifier(settings))
        log.info("scheduled_reverify checked=%d lapsed=%d", summary.checked, summary.lapsed)
    except Exception:  # noqa: BLE001 - a scheduling failure must not stop email delivery
        log.exception("scheduled_reverify_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.worker")
    parser.add_argument("--once", action="store_true", help="process due jobs once and exit")
    args = parser.parse_args(argv)
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    if settings.database_url is None:
        log.error("DATABASE_URL is not configured")
        return 1
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    db = Database(settings)
    db.open()
    sender = build_sender(settings)
    box = (
        SecretsBox(
            settings.integrations_encryption_key.get_secret_value(),
            settings.integrations_encryption_key_previous.get_secret_value()
            if settings.integrations_encryption_key_previous
            else None,
        )
        if settings.integrations_encryption_key is not None
        else None
    )
    providers = DefaultProviderFactory(settings.calcom_api_url)
    log.info("worker_started delivery=%s", settings.email_delivery)
    last_purge = 0.0
    last_schedule = 0.0
    try:
        while True:
            touch_heartbeat(settings.worker_heartbeat_file)
            counts = process_batch(db, sender, settings, box, providers)
            if counts:
                log.info("worker_batch %s", " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            if time.monotonic() - last_purge > PURGE_EVERY_SECONDS:
                purge(db)
                last_purge = time.monotonic()
            if (
                settings.worker_run_schedules
                and not args.once
                and time.monotonic() - last_schedule > settings.domain_recheck_every_seconds
            ):
                run_scheduled(db, settings)
                last_schedule = time.monotonic()
            if args.once or stop:
                break
            if not counts:  # idle: wait before polling again
                for _ in range(int(settings.worker_poll_seconds * 10)):
                    if stop:
                        break
                    time.sleep(0.1)
    finally:
        db.close()
        log.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
