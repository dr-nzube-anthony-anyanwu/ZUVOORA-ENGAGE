"""Fail if a deployment Compose file breaks the hardening rules (Phase 6, R1 and R10).

Usage (CI and before every change to deploy/):
    docker compose -p engage-ci --env-file deploy/env/ci-policy.env -f deploy/compose.yml \
        config --format json | python deploy/scripts/check_compose_policy.py app
    docker compose -f deploy/proxy/compose.yml config --format json \
        | python deploy/scripts/check_compose_policy.py proxy

Rules for every service: image pinned by digest; no published ports (the proxy may publish
exactly 80 and 443); no host networking or privileged mode; all Linux capabilities dropped (only
an allow-listed few added back); no-new-privileges; memory, CPU and process limits; rotated
json-file logs; a restart policy; a health check; a read-only root filesystem (ClamAV excepted,
its entrypoint writes its own configuration). The app's web service must not receive env_file.
"""

from __future__ import annotations

import json
import sys

CAP_ALLOW = {
    "clamav": {"CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"},
    "caddy": {"NET_BIND_SERVICE"},
}
WRITABLE_ROOT_ALLOWED = {"clamav"}
PROXY_PORTS = {80, 443}


def check_service(name: str, svc: dict, mode: str) -> list[str]:
    problems: list[str] = []

    def bad(message: str) -> None:
        problems.append(f"{name}: {message}")

    image = svc.get("image", "")
    if "@sha256:" not in image:
        bad("image must be pinned by digest (name@sha256:...)")
    ports = svc.get("ports") or []
    if mode == "proxy" and name == "caddy":
        published = {int(p.get("published", 0)) for p in ports}
        if published != PROXY_PORTS or any(p.get("host_ip") not in (None, "") for p in ports):
            bad("the proxy may publish exactly ports 80 and 443")
    elif ports:
        bad("must not publish ports (Docker bypasses the firewall); use the edge network")
    if svc.get("network_mode") == "host" or svc.get("privileged"):
        bad("host networking and privileged mode are not allowed")
    if "ALL" not in (svc.get("cap_drop") or []):
        bad("cap_drop must include ALL")
    extra = set(svc.get("cap_add") or []) - CAP_ALLOW.get(name, set())
    if extra:
        bad(f"capabilities not allowed: {sorted(extra)}")
    if "no-new-privileges:true" not in (svc.get("security_opt") or []):
        bad("security_opt must include no-new-privileges:true")
    if not svc.get("read_only") and name not in WRITABLE_ROOT_ALLOWED:
        bad("read_only root filesystem required")
    if not svc.get("mem_limit") and not svc.get("deploy", {}).get("resources", {}).get("limits"):
        bad("memory limit required")
    if not svc.get("cpus"):
        bad("CPU limit required")
    if not svc.get("pids_limit"):
        bad("pids_limit required")
    logging = svc.get("logging") or {}
    if logging.get("driver") != "json-file" or not (logging.get("options") or {}).get("max-size"):
        bad("json-file logging with max-size required")
    if svc.get("restart") not in ("unless-stopped", "always"):
        bad("restart: unless-stopped required")
    health = svc.get("healthcheck") or {}
    if not health.get("test") or health.get("disable"):
        bad("health check required")
    if mode == "app" and name == "web" and svc.get("env_file"):
        bad("web must not receive env_file (it holds server-only secrets)")
    return problems


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "app"
    config = json.load(sys.stdin)
    services = config.get("services") or {}
    if not services:
        print("no services found")
        return 1
    problems = [p for name, svc in services.items() for p in check_service(name, svc, mode)]
    for problem in problems:
        print(f"POLICY: {problem}")
    if problems:
        return 1
    print(f"compose policy OK ({mode}: {', '.join(sorted(services))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
