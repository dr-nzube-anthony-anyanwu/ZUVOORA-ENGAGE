"""Re-verify verified website domains (Phase 3f, ADR-031). Run once a day by a scheduler:

    python -m app.jobs.reverify_domains

Each domain's DNS lookup happens with no database transaction open. Three consecutive definite
failures (record missing or wrong) lapse the domain to 'pending' in the database, which stops the
widget on that host and writes an audit event. Exit code 0 on success, 1 on a configuration or
database error. Output contains counts only (no hostnames or tokens).
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.db import Database
from app.services.domain_verification import CheckResult, DnsTxtVerifier, DomainVerifier

log = logging.getLogger("engage.jobs.reverify_domains")
LAPSE_AFTER = 3


@dataclass
class Summary:
    checked: int = 0
    lapsed: int = 0
    results: Counter = field(default_factory=Counter)


def run(db: Database, verifier: DomainVerifier, batch: int = 200) -> Summary:
    summary = Summary()
    run_id = f"job:reverify_domains:{uuid.uuid4()}"  # stored as request_id on audit events
    with db.jobs_transaction() as conn:
        due = conn.execute(
            "select id, hostname, verification_token from app_private.domains_due_for_recheck(%s)",
            (batch,),
        ).fetchall()
    for domain in due:
        result: CheckResult = verifier.check(domain["hostname"], domain["verification_token"])
        with db.jobs_transaction() as conn:
            status = conn.execute(
                "select app_private.record_domain_recheck(%s, %s, %s, %s) as status",
                (domain["id"], result, run_id, LAPSE_AFTER),
            ).fetchone()["status"]
        summary.checked += 1
        summary.results[result] += 1
        if status == "pending":
            summary.lapsed += 1
            log.warning("domain_verification_lapsed domain=%s", domain["id"])
    return summary


def main(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    if settings.database_url is None:
        log.error("DATABASE_URL is not configured")
        return 1
    db = Database(settings)
    db.open()
    try:
        summary = run(db, DnsTxtVerifier(settings))
    except Exception:  # noqa: BLE001 - report and fail the scheduled run
        log.exception("domain re-verification failed")
        return 1
    finally:
        db.close()
    print(  # noqa: T201 - scheduler output
        f"checked={summary.checked} lapsed={summary.lapsed} "
        + " ".join(f"{k}={v}" for k, v in sorted(summary.results.items()))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
