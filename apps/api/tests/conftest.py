"""Shared fixtures for all API tests."""

from __future__ import annotations

import base64
import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest

# Tests never call a real model or spend credit: AI is forced off and the key removed before the
# app (and its settings) load. AI tests inject a FakeGateway explicitly.
os.environ["AI_ENABLED"] = "false"
os.environ["AI_VISION_ENABLED"] = "false"
os.environ["OPENROUTER_API_KEY"] = ""
# A random per-run key for third-party credential encryption; never a real deployment key.
os.environ["INTEGRATIONS_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["EMAIL_DELIVERY"] = "log"

from app.main import app  # noqa: E402

_MISSING = object()


@pytest.fixture
def app_state() -> Iterator[Callable[[str, Any], None]]:
    """Temporarily replace attributes on `app.state`, restoring the exact previous values.

    pytest's monkeypatch cannot be used here: Starlette's State keeps attributes outside
    `__dict__`, so monkeypatch (pytest >= 9) deletes them on undo instead of restoring them.
    """
    saved: dict[str, Any] = {}

    def swap(name: str, value: Any) -> None:
        if name not in saved:
            saved[name] = getattr(app.state, name, _MISSING)
        setattr(app.state, name, value)

    yield swap
    for name, value in saved.items():
        if value is _MISSING:
            delattr(app.state, name)
        else:
            setattr(app.state, name, value)
