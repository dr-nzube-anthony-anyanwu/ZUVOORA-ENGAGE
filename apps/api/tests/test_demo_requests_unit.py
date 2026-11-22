"""Demo requests (ADR-042): settings and the internal notification email."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services import email_templates


def test_blank_notification_address_means_none_and_bad_addresses_are_refused():
    assert Settings(_env_file=None, demo_request_notify_email="").demo_request_notify_email is None
    assert Settings(_env_file=None, demo_request_notify_email=" ").demo_request_notify_email is None
    assert Settings(_env_file=None, demo_request_notify_email="ops@example.com").demo_request_notify_email == "ops@example.com"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_request_notify_email="not an address")


def test_notification_names_the_clinic_but_carries_no_contact_details():
    email = email_templates.demo_request_alert(
        ("ops@example.com",), "Sample <Optics>", "Abuja, Nigeria", "pilot",
        datetime(2026, 11, 22, 10, 0, tzinfo=UTC), "https://app.example.com/platform/demo-requests",
    )
    assert email.subject == "New ZUVOORA Engage request: Sample <Optics>"
    assert "the pilot programme" in email.text and "Abuja, Nigeria" in email.text
    assert "&lt;Optics&gt;" in email.html and "<Optics>" not in email.html  # escaped
    assert "internal notification" in email.text and "clinic staff" not in email.text
    assert "@" not in email.text.replace("ops@example.com", "")
