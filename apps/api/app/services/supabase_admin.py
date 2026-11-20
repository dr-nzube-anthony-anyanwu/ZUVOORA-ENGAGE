"""Server-only adapter for Supabase Auth admin operations (invitations).

Uses the Supabase *secret* key, which must never leave the backend. Failures are explicit:
there is no silent fallback that pretends an invitation was sent.
"""

from __future__ import annotations

import uuid

import httpx

from app.config import Settings


class AuthAdminError(Exception):
    pass


class SupabaseAuthAdmin:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.supabase_url or settings.supabase_secret_key is None:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be configured")
        self._base = f"{settings.supabase_url}/auth/v1"
        secret = settings.supabase_secret_key.get_secret_value()
        self._headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}
        self._client = client or httpx.Client(timeout=10.0)
        self._redirect_to = f"{settings.dashboard_url.rstrip('/')}/auth/confirm"

    def invite_user(self, email: str) -> uuid.UUID:
        """Send a Supabase invitation email and return the new user's id."""
        payload: dict[str, object] = {"email": email}
        try:
            response = self._client.post(
                f"{self._base}/invite",
                json=payload,
                headers=self._headers,
                params={"redirect_to": self._redirect_to},
            )
        except httpx.HTTPError as exc:
            raise AuthAdminError("auth service unreachable") from exc
        if response.status_code >= 400:
            raise AuthAdminError(f"invite failed with status {response.status_code}")
        try:
            return uuid.UUID(response.json()["id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthAdminError("unexpected invite response") from exc
