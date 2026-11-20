"""Unit tests for access-token verification. No network: JWKS is served by a mock transport."""

import json
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.config import Settings
from app.security.jwt import JWKSCache, TokenError, TokenVerifier

SUPABASE_URL = "http://127.0.0.1:54321"
ISSUER = f"{SUPABASE_URL}/auth/v1"
KID = "test-key-1"


@pytest.fixture(scope="module")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="module")
def other_key():
    return ec.generate_private_key(ec.SECP256R1())


def _jwks_client(private_key) -> httpx.Client:
    public_jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": KID, "alg": "ES256", "use": "sig"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [public_jwk]})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def verifier(signing_key) -> TokenVerifier:
    settings = Settings(_env_file=None, app_env="test", supabase_url=SUPABASE_URL)
    jwks = JWKSCache(settings.jwks_url, 600, client=_jwks_client(signing_key))
    return TokenVerifier(settings, jwks=jwks)


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 600,
        "role": "authenticated",
        "aal": "aal1",
        "email": "user@test.invalid",
        "session_id": str(uuid.uuid4()),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _sign(key, claims, kid=KID, alg="ES256"):
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def test_valid_token_returns_principal(verifier, signing_key):
    claims = _claims(aal="aal2")
    principal = verifier.verify(_sign(signing_key, claims))
    assert str(principal.user_id) == claims["sub"]
    assert principal.mfa_verified is True
    assert principal.email == "user@test.invalid"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 120},  # expired beyond leeway
        {"aud": "anon"},  # wrong audience
        {"iss": "https://evil.example/auth/v1"},  # wrong issuer
        {"role": "anon"},  # anon key style token
        {"role": "service_role"},  # service key must never act as a user
        {"sub": "not-a-uuid"},
        {"sub": None},  # missing subject
        {"aal": None},  # missing assurance level
        {"aal": "aal3"},
        {"iat": None},  # missing issued-at
    ],
    ids=[
        "expired", "wrong-aud", "wrong-iss", "anon-role", "service-role",
        "bad-sub", "missing-sub", "missing-aal", "bad-aal", "missing-iat",
    ],
)
def test_invalid_claims_rejected(verifier, signing_key, overrides):
    with pytest.raises(TokenError):
        verifier.verify(_sign(signing_key, _claims(**overrides)))


def test_signature_from_unknown_key_rejected(verifier, other_key):
    with pytest.raises(TokenError):
        verifier.verify(_sign(other_key, _claims()))


def test_unknown_kid_rejected(verifier, signing_key):
    with pytest.raises(TokenError):
        verifier.verify(_sign(signing_key, _claims(), kid="unknown-kid"))


def test_tampered_payload_rejected(verifier, signing_key):
    header, _payload, signature = _sign(signing_key, _claims()).split(".")
    forged = jwt.utils.base64url_encode(
        json.dumps(_claims(sub=str(uuid.uuid4()))).encode()
    ).decode()
    with pytest.raises(TokenError):
        verifier.verify(f"{header}.{forged}.{signature}")


def test_alg_none_rejected(verifier):
    token = jwt.encode(_claims(), key=None, algorithm="none")
    with pytest.raises(TokenError):
        verifier.verify(token)


def test_hs256_rejected_without_legacy_secret(verifier):
    # Algorithm-confusion style attempt: symmetric token when only asymmetric keys are trusted.
    token = jwt.encode(_claims(), "guessable-secret-value-that-is-long-enough", algorithm="HS256")
    with pytest.raises(TokenError):
        verifier.verify(token)


def test_legacy_hs256_only_in_development_or_test():
    secret = "local-test-secret-at-least-32-characters!!"
    settings = Settings(
        _env_file=None, app_env="test", supabase_url=SUPABASE_URL, supabase_jwt_legacy_secret=secret
    )
    verifier = TokenVerifier(settings, jwks=None)
    token = jwt.encode(_claims(), secret, algorithm="HS256")
    assert verifier.verify(token).aal == "aal1"


def test_garbage_and_oversized_tokens_rejected(verifier):
    for token in ["", "not.a.jwt", "a" * 9000]:
        with pytest.raises(TokenError):
            verifier.verify(token)
