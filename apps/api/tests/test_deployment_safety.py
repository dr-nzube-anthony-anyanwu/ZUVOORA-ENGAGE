"""Phase 6 (stage 6A): settings that protect a real server, the visitor address behind the reverse
proxy, worker health and the scheduled domain re-check. No database or network."""

from __future__ import annotations

import os
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import healthcheck, worker
from app.config import Settings
from app.middleware import install_proxy_headers
from tests.test_config_and_auth import PROD_BASE


def settings(**changes) -> Settings:
    return Settings(**{**PROD_BASE, **changes})


# ----- staging / production settings (R2, R8, R14, D5) ------------------------------------------
def test_complete_production_settings_are_accepted():
    s = settings()
    assert s.trusted_proxies == ["172.30.0.0/24"]
    assert s.api_docs_enabled is False


@pytest.mark.parametrize(
    "changes",
    [
        {"dashboard_url": "http://engage.example.com"},
        {"api_cors_origins": "http://engage.example.com"},
        {"api_cors_origins": "https://engage.example.com,http://other.example.com"},
        {"public_api_url": None},
        {"public_api_url": "http://api-engage.example.com"},
        {"forwarded_allow_ips": ""},
        {"forwarded_allow_ips": "*"},
        {"forwarded_allow_ips": "0.0.0.0/0"},
        {"malware_scan_required": False},
        {"clamav_host": None},
        {"clamav_host": "  "},
        {"email_delivery": "log"},
    ],
)
def test_unsafe_production_settings_are_refused(changes):
    with pytest.raises(ValidationError):
        settings(**changes)


def test_staging_may_hold_back_email_but_not_the_other_safeguards():
    staging = settings(app_env="staging", email_delivery="log")
    assert staging.email_delivery == "log" and staging.api_docs_enabled is False
    with pytest.raises(ValidationError):
        settings(app_env="staging", forwarded_allow_ips="")
    with pytest.raises(ValidationError):
        settings(app_env="staging", malware_scan_required=False)


def test_proxy_addresses_must_be_addresses_or_networks():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, forwarded_allow_ips="proxy.example.com")
    trusted = Settings(_env_file=None, forwarded_allow_ips=" 10.0.0.1 , fd00::/8 ").trusted_proxies
    assert trusted == ["10.0.0.1", "fd00::/8"]


def test_api_docs_only_on_developer_machines():
    assert Settings(_env_file=None).api_docs_enabled is True
    assert Settings(_env_file=None, app_env="test").api_docs_enabled is True


def test_document_reading_must_finish_before_the_proxy_gives_up():
    # Defaults: 10 pages, 5 at a time, 40 s each -> 2 rounds x 40 s = 80 s <= 85 s.
    assert Settings(_env_file=None).ai_vision_parallel == 5
    with pytest.raises(ValidationError):  # 3 rounds x 40 s = 120 s
        Settings(_env_file=None, ai_vision_parallel=4)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_vision_timeout_seconds=60)
    with pytest.raises(ValidationError):  # the deadline itself is capped below Cloudflare's 100 s
        Settings(_env_file=None, ai_vision_deadline_seconds=120)
    Settings(
        _env_file=None, ai_vision_max_pages=4, ai_vision_parallel=2, ai_vision_timeout_seconds=40
    )


# ----- visitor address behind the reverse proxy (R2) --------------------------------------------
def _echo_app(trusted: str) -> FastAPI:
    app = FastAPI()

    @app.get("/ip")
    def ip(request: Request) -> dict[str, str]:
        return {"ip": request.client.host if request.client else "?"}

    install_proxy_headers(app, Settings(_env_file=None, forwarded_allow_ips=trusted))
    return app


def _seen(app: FastAPI, peer: str, forwarded: str | None) -> str:
    headers = {"X-Forwarded-For": forwarded} if forwarded is not None else {}
    with TestClient(app, client=(peer, 40000)) as client:
        return client.get("/ip", headers=headers).json()["ip"]


def test_forwarded_address_is_used_only_from_the_trusted_proxy():
    app = _echo_app("172.30.0.0/24")
    assert _seen(app, "172.30.0.10", "203.0.113.7") == "203.0.113.7"
    # Anyone else sending the header is ignored: the real peer address is used.
    assert _seen(app, "198.51.100.20", "203.0.113.7") == "198.51.100.20"


def test_a_visitor_cannot_inject_an_address_through_the_proxy():
    # The visitor sends "X-Forwarded-For: 1.2.3.4"; a proxy that appends would forward
    # "1.2.3.4, <visitor>". The right-most untrusted address (the real visitor) is used.
    app = _echo_app("172.30.0.0/24")
    assert _seen(app, "172.30.0.10", "1.2.3.4, 203.0.113.7") == "203.0.113.7"


def test_dashboard_hop_is_trusted_too():
    # Visitor -> proxy -> dashboard server (Server Action) -> API: both hops are trusted.
    app = _echo_app("172.30.0.0/24")
    assert _seen(app, "172.30.0.11", "203.0.113.7, 172.30.0.10") == "203.0.113.7"


def test_without_trusted_proxies_the_header_is_ignored():
    app = _echo_app("")
    assert _seen(app, "198.51.100.20", "203.0.113.7") == "198.51.100.20"


# ----- worker health and schedule (R11) ---------------------------------------------------------
def test_worker_heartbeat_fresh_stale_and_missing(tmp_path):
    beat = tmp_path / "beat"
    assert healthcheck.worker_healthy(str(beat)) is False  # never started
    worker.touch_heartbeat(str(beat))
    assert healthcheck.worker_healthy(str(beat)) is True
    old = time.time() - healthcheck.MAX_HEARTBEAT_AGE - 5
    os.utime(beat, (old, old))
    assert healthcheck.worker_healthy(str(beat)) is False  # the loop stopped


def test_heartbeat_problems_never_stop_the_worker(tmp_path):
    worker.touch_heartbeat(str(tmp_path / "missing-dir" / "beat"))  # no exception


def test_healthcheck_cli(tmp_path, monkeypatch):
    beat = tmp_path / "beat"
    beat.touch()
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(beat))
    assert healthcheck.main(["worker"]) == 0
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(tmp_path / "none"))
    assert healthcheck.main(["worker"]) == 1
    assert healthcheck.main([]) == 2


def test_scheduled_recheck_failure_does_not_stop_email_delivery(monkeypatch):
    from app.jobs import reverify_domains

    def boom(*_args, **_kwargs):
        raise RuntimeError("dns down")

    monkeypatch.setattr(reverify_domains, "run", boom)
    worker.run_scheduled(db=None, settings=Settings(_env_file=None))  # logged, not raised
