"""Fixtures for API integration tests against the LOCAL Supabase stack only.

Requires `npm run db:start` at the repository root. Connection details come from environment
variables (CI) or `supabase status`. Tests are skipped when the stack is unavailable.
All users and clinics are synthetic (`@example.com`) and removed after the session.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import psycopg
import pyotp
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import app
from app.security.jwt import TokenVerifier
from app.services.storage import SupabaseObjectStore
from app.services.supabase_admin import SupabaseAuthAdmin
from app.services.widget_tokens import WidgetTokens

REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_HOSTS = ("http://127.0.0.1:", "http://localhost:")


def _stack_from_cli() -> dict[str, str] | None:
    npx = shutil.which("npx")
    if not npx:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed local developer command
            [npx, "supabase", "status", "-o", "json"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


@pytest.fixture(scope="session")
def stack() -> dict[str, str]:
    env = {
        "API_URL": os.getenv("TEST_SUPABASE_URL"),
        "PUBLISHABLE_KEY": os.getenv("TEST_SUPABASE_PUBLISHABLE_KEY"),
        "SECRET_KEY": os.getenv("TEST_SUPABASE_SECRET_KEY"),
        "DB_URL": os.getenv("TEST_SUPABASE_DB_URL"),
    }
    status = env if all(env.values()) else _stack_from_cli()
    if not status or not all(status.get(k) for k in env):
        pytest.skip("local Supabase stack not running (npm run db:start)")
    if not status["API_URL"].startswith(LOCAL_HOSTS):
        pytest.fail("integration tests must only ever run against a LOCAL Supabase stack")
    try:
        httpx.get(f"{status['API_URL']}/auth/v1/health", timeout=5).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("local Supabase auth service is not reachable")
    db_host = status["DB_URL"].rsplit("@", 1)[1]
    status["ENGAGE_API_DB_URL"] = f"postgresql://engage_api:local-dev-only-engage-api@{db_host}"
    return status


@pytest.fixture(scope="session")
def client(stack):
    settings = Settings(
        _env_file=None,
        app_env="test",
        supabase_url=stack["API_URL"],
        supabase_secret_key=stack["SECRET_KEY"],
        database_url=stack["ENGAGE_API_DB_URL"],
        dashboard_url="http://localhost:3073",
    )
    db = Database(settings)
    db.open()
    app.state.verifier = TokenVerifier(settings)
    app.state.auth_admin = SupabaseAuthAdmin(settings)
    app.state.db = db
    app.state.object_store = SupabaseObjectStore(settings)
    app.state.widget_tokens = WidgetTokens(secrets.token_urlsafe(48))
    try:
        yield TestClient(app)
    finally:
        db.close()
        app.state.verifier = app.state.auth_admin = app.state.db = None
        app.state.object_store = None
        app.state.widget_tokens = None


@dataclass
class User:
    email: str
    password: str = field(repr=False)
    id: uuid.UUID
    token: str = field(default="", repr=False)
    aal2_token: str = field(default="", repr=False)

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def auth_mfa(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.aal2_token}"}


@dataclass
class GoTrue:
    url: str
    publishable_key: str
    secret_key: str
    created: list[uuid.UUID] = field(default_factory=list)

    def _admin_headers(self) -> dict[str, str]:
        return {"apikey": self.secret_key, "Authorization": f"Bearer {self.secret_key}"}

    def _public_headers(self, token: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.publishable_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def create_user(self, label: str) -> User:
        email = f"{label}.{uuid.uuid4().hex[:10]}@example.com"
        password = secrets.token_urlsafe(18) + "aA1"
        response = httpx.post(
            f"{self.url}/auth/v1/admin/users",
            headers=self._admin_headers(),
            json={"email": email, "password": password, "email_confirm": True},
            timeout=10,
        )
        response.raise_for_status()
        user = User(email=email, password=password, id=uuid.UUID(response.json()["id"]))
        self.created.append(user.id)
        user.token = self.sign_in(user)
        return user

    def sign_in(self, user: User) -> str:
        response = httpx.post(
            f"{self.url}/auth/v1/token",
            params={"grant_type": "password"},
            headers=self._public_headers(),
            json={"email": user.email, "password": user.password},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def enable_mfa(self, user: User) -> str:
        """Enrol a TOTP factor and return an aal2 access token."""
        headers = self._public_headers(user.token)
        enrol = httpx.post(
            f"{self.url}/auth/v1/factors", headers=headers,
            json={"factor_type": "totp", "friendly_name": f"test-{uuid.uuid4().hex[:6]}"},
            timeout=10,
        )
        enrol.raise_for_status()
        factor_id, secret = enrol.json()["id"], enrol.json()["totp"]["secret"]
        challenge = httpx.post(
            f"{self.url}/auth/v1/factors/{factor_id}/challenge", headers=headers, timeout=10
        )
        challenge.raise_for_status()
        verify = httpx.post(
            f"{self.url}/auth/v1/factors/{factor_id}/verify", headers=headers,
            json={"challenge_id": challenge.json()["id"], "code": pyotp.TOTP(secret).now()},
            timeout=10,
        )
        verify.raise_for_status()
        user.aal2_token = verify.json()["access_token"]
        return user.aal2_token

    def delete_all(self) -> None:
        for user_id in self.created:
            httpx.delete(
                f"{self.url}/auth/v1/admin/users/{user_id}",
                headers=self._admin_headers(),
                timeout=10,
            )


@pytest.fixture(scope="session")
def gotrue(stack):
    helper = GoTrue(stack["API_URL"], stack["PUBLISHABLE_KEY"], stack["SECRET_KEY"])
    yield helper
    helper.delete_all()


@pytest.fixture(scope="session")
def admin_db(stack):
    """Privileged LOCAL connection used only for fixture setup and audit assertions."""
    with psycopg.connect(stack["DB_URL"], autocommit=True) as conn:
        yield conn


@dataclass
class World:
    platform_admin: User
    a_owner: User
    a_admin: User
    a_receptionist: User
    b_owner: User
    outsider: User
    tenant_a: str
    tenant_b: str
    created_tenants: list[str]


@pytest.fixture(scope="session")
def world(client, gotrue, admin_db) -> World:
    platform_admin = gotrue.create_user("platform")
    admin_db.execute(
        "insert into public.platform_admins (user_id, note) values (%s, 'integration test')",
        (platform_admin.id,),
    )
    gotrue.enable_mfa(platform_admin)

    users = {name: gotrue.create_user(name) for name in
             ("a-owner", "a-admin", "a-receptionist", "b-owner", "outsider")}

    created: list[str] = []

    def create_tenant(name: str, owner: User) -> str:
        response = client.post(
            "/api/v1/platform/tenants",
            headers=platform_admin.auth_mfa,
            json={"legal_name": f"{name} Test Ltd", "display_name": name,
                  "owner_email": owner.email},
        )
        assert response.status_code == 201, response.text
        tenant_id = response.json()["tenant"]["id"]
        created.append(tenant_id)
        return tenant_id

    tenant_a = create_tenant("Clinic A", users["a-owner"])
    tenant_b = create_tenant("Clinic B", users["b-owner"])

    for name, role in (("a-admin", "admin"), ("a-receptionist", "receptionist")):
        response = client.post(
            f"/api/v1/tenants/{tenant_a}/members",
            headers=users["a-owner"].auth,
            json={"email": users[name].email, "role": role},
        )
        assert response.status_code == 201, response.text

    world = World(
        platform_admin=platform_admin,
        a_owner=users["a-owner"],
        a_admin=users["a-admin"],
        a_receptionist=users["a-receptionist"],
        b_owner=users["b-owner"],
        outsider=users["outsider"],
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        created_tenants=created,
    )
    yield world
    # Stored originals are not removed by the tenant cascade; delete them via the Storage API.
    objects = [row[0] for row in admin_db.execute(
        "select storage_path from public.knowledge_document_versions where tenant_id = any(%s)",
        (created,),
    ).fetchall()]
    if objects:
        httpx.request(
            "DELETE", f"{gotrue.url}/storage/v1/object/knowledge-originals",
            headers=gotrue._admin_headers(), json={"prefixes": objects}, timeout=30,
        ).raise_for_status()
    admin_db.execute("delete from public.tenants where id = any(%s)", (created,))
    admin_db.execute("delete from public.platform_admins where user_id = %s", (platform_admin.id,))
