"""Encryption of third-party credentials at rest (Phase 4b, ADR-034).

AES-256-GCM with a random 96-bit nonce. The associated data binds each ciphertext to its row
(purpose, tenant, connection id), so a ciphertext copied into another clinic's row cannot be
decrypted. Keys come from the environment (`INTEGRATIONS_ENCRYPTION_KEY`, optional
`..._PREVIOUS` during rotation); each ciphertext records the id of the key that sealed it.
Plaintext credentials never touch the database, logs or API responses.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretsBoxError(Exception):
    pass


def _decode_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise SecretsBoxError("encryption key is not valid base64") from exc
    if len(raw) != 32:
        raise SecretsBoxError("encryption key must be 32 bytes (base64url)")
    return raw


def key_id(raw: bytes) -> str:
    return hashlib.sha256(b"engage-key-id:" + raw).hexdigest()[:12]


def generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes  # nonce (12) || ciphertext+tag
    key_id: str


class SecretsBox:
    def __init__(self, current: str, previous: str | None = None) -> None:
        keys = [_decode_key(current)] + ([_decode_key(previous)] if previous else [])
        self._current_id = key_id(keys[0])
        self._keys = {key_id(k): AESGCM(k) for k in keys}

    @staticmethod
    def _aad(purpose: str, tenant_id: object, record_id: object) -> bytes:
        return f"engage:{purpose}:{tenant_id}:{record_id}".encode()

    def seal(self, plaintext: str, *, purpose: str, tenant_id: object, record_id: object) -> Sealed:
        nonce = os.urandom(12)
        aad = self._aad(purpose, tenant_id, record_id)
        data = self._keys[self._current_id].encrypt(nonce, plaintext.encode(), aad)
        return Sealed(nonce + data, self._current_id)

    def open(self, sealed: Sealed, *, purpose: str, tenant_id: object, record_id: object) -> str:
        cipher = self._keys.get(sealed.key_id)
        if cipher is None or len(sealed.ciphertext) < 28:
            raise SecretsBoxError("credential cannot be decrypted with the configured keys")
        nonce, data = sealed.ciphertext[:12], sealed.ciphertext[12:]
        try:
            return cipher.decrypt(nonce, data, self._aad(purpose, tenant_id, record_id)).decode()
        except InvalidTag as exc:
            raise SecretsBoxError("credential failed authentication") from exc

    @property
    def current_key_id(self) -> str:
        return self._current_id
