"""Phase 6 (D3): patient emails show the clinic's name and send replies to the clinic's
published address; staff alerts stay unchanged. Mock transport only, no real email."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.services import email_templates
from app.services.email import AllowlistSender, Email, ResendSender, display_name

START = datetime(2026, 12, 3, 9, 30, tzinfo=UTC)


def sent_body(email: Email) -> dict:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "msg_1"})

    sender = ResendSender(
        "re_test_not_real",
        "ZUVOORA Engage <no-reply@engage.example.com>",
        transport=httpx.MockTransport(handler),
    )
    sender.send(email, "key/1")
    return seen


@pytest.mark.parametrize(
    "build",
    [
        lambda e: email_templates.booking_confirmation(
            "ada@example.com", "Ada", "Lumen Eye Clinic", "Eye exam", START, "UTC", False, None,
            clinic_email=e,
        ),
        lambda e: email_templates.booking_reminder(
            "ada@example.com", "Ada", "Lumen Eye Clinic", "Eye exam", START, "UTC", None,
            clinic_email=e,
        ),
        lambda e: email_templates.booking_cancelled(
            "ada@example.com", "Ada", "Lumen Eye Clinic", "Eye exam", START, "UTC", None,
            clinic_email=e,
        ),
    ],
)
def test_patient_emails_come_from_the_clinic_and_replies_reach_it(build):
    body = sent_body(build("front-desk@lumen.example"))
    assert body["from"] == "Lumen Eye Clinic via ZUVOORA Engage <no-reply@engage.example.com>"
    assert body["reply_to"] == ["front-desk@lumen.example"]
    assert "Replies to this email go to Lumen Eye Clinic." in body["text"]
    assert "do not reply" not in body["text"]


def test_without_a_published_clinic_address_there_is_no_reply_to():
    email = email_templates.booking_confirmation(
        "ada@example.com", "Ada", "Lumen Eye Clinic", "Eye exam", START, "UTC", False, None
    )
    body = sent_body(email)
    assert "reply_to" not in body
    assert body["from"].startswith("Lumen Eye Clinic via ZUVOORA Engage")
    assert "Please do not reply to this email." in body["text"]


def test_staff_alerts_keep_the_platform_sender():
    email = email_templates.handover_alert(
        ("staff@clinic.example",), "Lumen Eye Clinic", START, "UTC", "https://x.example/inbox"
    )
    body = sent_body(email)
    assert body["from"] == "ZUVOORA Engage <no-reply@engage.example.com>"
    assert "reply_to" not in body


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Lumen Eye Clinic", "Lumen Eye Clinic"),
        ('Evil "Clinic" <admin@bank.example>', "Evil Clinic admin bank.example"),
        ("Line\r\nBcc: victim@example.com", "Line Bcc victim example.com"),
        ("   ", "Your clinic"),
        ("A" * 80, "A" * 60),
    ],
)
def test_clinic_names_cannot_break_or_spoof_the_sender(name, expected):
    assert display_name(name) == expected


def test_allowlist_keeps_sender_name_and_reply_to():
    captured: list[Email] = []

    class Capture:
        def send(self, email: Email, idempotency_key: str) -> str:
            captured.append(email)
            return "id"

    email = Email(
        ("ada@example.com", "other@elsewhere.example"), "s", "t", "<p>h</p>",
        sender_name="Lumen", reply_to="front-desk@lumen.example",
    )
    AllowlistSender(Capture(), ["ada@example.com"]).send(email, "k")
    assert captured[0].to == ("ada@example.com",)
    assert (captured[0].sender_name, captured[0].reply_to) == ("Lumen", "front-desk@lumen.example")
