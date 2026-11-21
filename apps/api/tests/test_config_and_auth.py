"""Configuration safety and unauthenticated-request behaviour (no database required)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app

client = TestClient(app)

PROD_BASE = {
    "_env_file": None,
    "app_env": "production",
    "supabase_url": "https://example.supabase.co",
    "supabase_secret_key": "placeholder",
    "database_url": "postgresql://engage_api@db.invalid/postgres",
}


def test_production_requires_core_settings():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_production_rejects_legacy_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(**PROD_BASE, supabase_jwt_legacy_secret="x" * 40)


def test_production_requires_https_supabase():
    with pytest.raises(ValidationError):
        Settings(**{**PROD_BASE, "supabase_url": "http://example.supabase.co"})


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(**PROD_BASE, api_cors_origins="*")


def test_secrets_not_exposed_in_repr():
    settings = Settings(**PROD_BASE)
    assert "placeholder" not in repr(settings)


def test_protected_routes_fail_closed_without_auth_config(app_state):
    # No verifier/database configured -> explicit 503, never data.
    app_state("verifier", None)
    app_state("db", None)
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_unavailable"


def test_request_id_is_generated_and_unsafe_ids_replaced():
    response = client.get("/health/live", headers={"X-Request-ID": "bad id with spaces<script>"})
    assert response.status_code == 200
    rid = response.headers["X-Request-ID"]
    assert " " not in rid and "<" not in rid
    assert response.headers["Cache-Control"] == "no-store"
