"""Container health checks (Phase 6, R11):  python -m app.healthcheck api|worker

* api:    GET http://127.0.0.1:8073/health/live answers 200.
* worker: the heartbeat file was touched within MAX_HEARTBEAT_AGE seconds (the worker loop
          touches it on every pass; an idle pass is at most WORKER_POLL_SECONDS).
Exit code 0 = healthy, 1 = unhealthy. Prints one short word, never configuration values.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request

MAX_HEARTBEAT_AGE = 300  # seconds; a long email batch or domain re-check may hold the loop


def api_healthy(url: str = "http://127.0.0.1:8073/health/live") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310 - fixed local URL
            return response.status == 200
    except OSError:
        return False


def worker_healthy(path: str, max_age: float = MAX_HEARTBEAT_AGE, now: float | None = None) -> bool:
    try:
        age = (now if now is not None else time.time()) - os.path.getmtime(path)
    except OSError:
        return False
    return age <= max_age


def main(argv: list[str]) -> int:
    target = argv[0] if argv else ""
    if target == "api":
        ok = api_healthy()
    elif target == "worker":
        path = os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/engage-worker-heartbeat")  # noqa: S108
        ok = worker_healthy(path)
    else:
        print("usage: python -m app.healthcheck api|worker")
        return 2
    print("healthy" if ok else "unhealthy")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
