"""Phase 4a email layer: no network (mock transport), no real email."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services import email_templates
from app.services.email import (
    AllowlistSender,
    Email,
    EmailError,
    LogSender,
    ResendSender,
    build_sender,
)

MESSAGE = Email(("staff@clinic.example.com",), "Subject", "text body", "<p>html</p>")


def resend(handler) -> ResendSender:
    return ResendSender(
        "re_test_not_real",
        "Engage <no-reply@engage.example.com>",
        transport=httpx.MockTransport(handler),
    )


def test_resend_request_carries_key_idempotency_and_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["key"] = request.headers["idempotency-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "msg_123"})

    assert resend(handler).send(MESSAGE, "handover_alert/abc") == "msg_123"
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["auth"] == "Bearer re_test_not_real"
    assert seen["key"] == "handover_alert/abc"
    assert seen["body"]["to"] == ["staff@clinic.example.com"]
    assert seen["body"]["from"] == "Engage <no-reply@engage.example.com>"


@pytest.mark.parametrize(
    ("status", "permanent"),
    [
        (429, False),
        (500, False),
        (503, False),
        (400, True),
        (401, True),
        (403, True),
        (409, True),
        (422, True),
    ],
)
def test_resend_errors_are_classified(status, permanent):
    with pytest.raises(EmailError) as info:
        resend(lambda r: httpx.Response(status, json={"message": "secret detail"})).send(
            MESSAGE, "k"
        )
    assert info.value.kind == f"http_{status}"
    assert info.value.permanent is permanent
    assert "secret detail" not in str(info.value)


def test_timeouts_are_temporary():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EmailError) as info:
        resend(handler).send(MESSAGE, "k")
    assert info.value.kind == "timeout" and info.value.permanent is False


def test_allowlist_limits_recipients_outside_production():
    sent: list[Email] = []

    class Recorder:
        def send(self, email, key):
            sent.append(email)
            return "id"

    guard = AllowlistSender(Recorder(), ["tester@gmail.com", "@zuvoora.com"])
    mixed = Email(("tester@gmail.com", "Staff@Zuvoora.com", "patient@else.com"), "s", "t", "h")
    assert guard.send(mixed, "k") == "id"
    assert sent[0].to == ("tester@gmail.com", "Staff@Zuvoora.com")
    assert guard.send(Email(("x@else.com",), "s", "t", "h"), "k") == "suppressed:allowlist"
    assert len(sent) == 1


def test_log_mode_sends_nothing():
    assert LogSender().send(MESSAGE, "k").startswith("log:")


def test_sender_selection():
    assert isinstance(build_sender(Settings(_env_file=None)), LogSender)
    dev = Settings(
        _env_file=None,
        email_delivery="resend",
        resend_api_key="re_x",
        email_from="a@b.example.com",
        email_allowed_recipients="me@example.com",
    )
    assert isinstance(build_sender(dev), AllowlistSender)
    prod = Settings(
        _env_file=None,
        app_env="production",
        email_delivery="resend",
        resend_api_key="re_x",
        email_from="a@b.example.com",
        supabase_url="https://x.supabase.co",
        supabase_secret_key="s",
        database_url="postgresql://x",
        widget_token_secret="w" * 40,
    )
    assert isinstance(build_sender(prod), ResendSender)


def test_resend_mode_requires_key_and_sender():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, email_delivery="resend")


def test_handover_alert_has_no_patient_details_and_escapes_html():
    email = email_templates.handover_alert(
        ("staff@clinic.example.com",),
        "<b>Clinic</b> & Co",
        datetime(2026, 11, 23, 9, 30, tzinfo=UTC),
        "Africa/Lagos",
        "https://dash.example.com/clinics/t/inbox/c",
    )
    assert "10:30 Africa/Lagos" in email.text  # local clinic time
    assert "<b>Clinic</b>" not in email.html and "&lt;b&gt;Clinic&lt;/b&gt; &amp; Co" in email.html
    assert "https://dash.example.com/clinics/t/inbox/c" in email.html
    assert "not included in this email" in email.text
