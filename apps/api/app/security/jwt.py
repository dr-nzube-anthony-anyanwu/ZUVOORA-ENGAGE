"""Supabase access-token verification.

Every check fails closed:
  * signature verified against the project's published JWKS (asymmetric: ES256/RS256/EdDSA);
    the legacy HS256 shared secret is accepted only in development/test when configured;
  * the algorithm comes from our allow-list, never from the token header alone;
  * issuer, audience, expiry, issued-at and subject are required and validated;
  * only end-user sessions (role == "authenticated") are accepted — anon/service tokens are not.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from app.config import Settings

ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256", "EdDSA"})
REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud"]
CLOCK_SKEW_SECONDS = 30


class TokenError(Exception):
    """Raised for any invalid token. The message is safe to log but not shown to clients."""


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str | None
    aal: str
    session_id: str | None
    claims: dict[str, Any] = field(repr=False)

    @property
    def mfa_verified(self) -> bool:
        return self.aal == "aal2"


class JWKSCache:
    """Fetches and caches the Supabase JWKS. Refreshes on unknown `kid` (rate-limited)."""

    def __init__(self, url: str, ttl_seconds: int, client: httpx.Client | None = None) -> None:
        self._url = url
        self._ttl = ttl_seconds
        self._client = client or httpx.Client(timeout=5.0)
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()
        self._min_refresh_interval = 30.0

    def get(self, kid: str) -> PyJWK:
        now = time.monotonic()
        if kid in self._keys and now - self._fetched_at < self._ttl:
            return self._keys[kid]
        with self._lock:
            stale = now - self._fetched_at >= self._ttl
            can_refresh = now - self._fetched_at >= self._min_refresh_interval
            if kid not in self._keys or stale:
                if can_refresh or not self._keys:
                    self._refresh()
            if kid not in self._keys:
                raise TokenError("unknown signing key id")
            return self._keys[kid]

    def _refresh(self) -> None:
        try:
            response = self._client.get(self._url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TokenError("unable to fetch signing keys") from exc
        keys: dict[str, PyJWK] = {}
        for raw in payload.get("keys", []):
            kid = raw.get("kid")
            if not kid:
                continue
            try:
                key = PyJWK.from_dict(raw)
            except jwt.PyJWTError:
                continue
            if key.algorithm_name in ASYMMETRIC_ALGORITHMS:
                keys[kid] = key
        self._keys = keys
        self._fetched_at = time.monotonic()


class TokenVerifier:
    def __init__(self, settings: Settings, jwks: JWKSCache | None = None) -> None:
        if not settings.jwt_issuer:
            raise ValueError("SUPABASE_URL (or SUPABASE_JWT_ISSUER) must be configured")
        self._issuer = settings.jwt_issuer
        self._audience = settings.supabase_jwt_audience
        self._jwks = jwks
        if self._jwks is None and settings.jwks_url:
            self._jwks = JWKSCache(settings.jwks_url, settings.jwks_cache_seconds)
        legacy = settings.supabase_jwt_legacy_secret
        self._legacy_secret = (
            legacy.get_secret_value()
            if legacy is not None and settings.app_env in {"development", "test"}
            else None
        )

    def verify(self, token: str) -> Principal:
        if not token or len(token) > 8192:
            raise TokenError("missing or oversized token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("malformed token header") from exc

        alg = header.get("alg")
        if alg in ASYMMETRIC_ALGORITHMS:
            kid = header.get("kid")
            if not kid or self._jwks is None:
                raise TokenError("asymmetric token without resolvable key id")
            jwk = self._jwks.get(kid)
            if jwk.algorithm_name != alg:
                raise TokenError("algorithm does not match signing key")
            key: Any = jwk.key
            algorithms = [alg]
        elif alg == "HS256" and self._legacy_secret:
            key = self._legacy_secret
            algorithms = ["HS256"]
        else:
            raise TokenError("algorithm not allowed")

        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(f"token rejected: {type(exc).__name__}") from exc

        if claims.get("role") != "authenticated":
            raise TokenError("only authenticated user sessions are accepted")
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise TokenError("subject is not a user id") from exc

        aal = claims.get("aal")
        if aal not in {"aal1", "aal2"}:
            raise TokenError("missing or invalid authenticator assurance level")

        email = claims.get("email")
        return Principal(
            user_id=user_id,
            email=email if isinstance(email, str) else None,
            aal=aal,
            session_id=claims.get("session_id"),
            claims=claims,
        )
