"""Background worker (Phase 4a, ADR-033):  python -m app.worker  [--once]

Claims due jobs from the Postgres queue as the `engage_jobs` role, re-checks each job's data at
send time (a handled request or a re-verified domain is skipped), sends email with no database
transaction open, and records the outcome. Safe to run several copies: claims use
FOR UPDATE SKIP LOCKED with a lease, and every send carries the job's idempotency key.
Logs never contain email addresses or message content.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import psycopg

from app.config import Settings, get_settings
from app.db import Database
from app.services import email_templates
from app.services.email import Email, EmailError, EmailSender, build_sender

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


HANDLERS: dict[str, Handler] = {"handover_alert": handover_alert, "domain_lapsed": domain_lapsed}


def process_batch(db: Database, sender: EmailSender, settings: Settings) -> Counter:
    outcome: Counter = Counter()
    with db.jobs_transaction() as conn:
        jobs = conn.execute(
            "select * from app_private.claim_jobs(%s, %s)", (BATCH, LEASE_SECONDS)
        ).fetchall()
    for job in jobs:
        try:
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
    with db.jobs_transaction() as conn:
        return conn.execute("select app_private.purge_finished_jobs() as n").fetchone()["n"]


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
    log.info("worker_started delivery=%s", settings.email_delivery)
    last_purge = 0.0
    try:
        while True:
            counts = process_batch(db, sender, settings)
            if counts:
                log.info("worker_batch %s", " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            if time.monotonic() - last_purge > PURGE_EVERY_SECONDS:
                purge(db)
                last_purge = time.monotonic()
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
