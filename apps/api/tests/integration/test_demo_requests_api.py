"""Design track D3: demo and pilot requests from the public website, through the real API and RLS."""

from __future__ import annotations

import uuid

import pytest

from app.config import get_settings
from app.routes import demo_requests
from tests.integration.test_booking_api import drain
from tests.integration.test_worker import FakeSender

pytestmark = pytest.mark.integration

URL = "/api/v1/public/demo-requests"
CONSOLE = "/api/v1/platform/demo-requests"


def request_body(**extra) -> dict:
    return {
        "name": "Ada Test", "role": "Practice manager", "clinic_name": f"Sample Eye Clinic {uuid.uuid4().hex[:6]}",
        "city": "Abuja", "country": "Nigeria", "email": f"ada.{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+234 801 000 0000", "interest": "demo", "message": "We would like to see a demo.",
        "consent": True, **extra,
    }


def stored(admin_db, clinic_name: str) -> list[tuple]:
    return admin_db.execute(
        "select id, email, interest, status from public.demo_requests where clinic_name = %s",
        (clinic_name,)).fetchall()


@pytest.fixture(autouse=True)
def cleanup(admin_db):
    yield
    admin_db.execute("delete from public.demo_requests where email like '%%@example.com'")
    admin_db.execute("delete from app_private.jobs where kind = 'demo_request_alert'")


def test_a_visitor_submits_and_only_platform_admins_can_read_it(client, world, admin_db):
    body = request_body(interest="pilot")
    response = client.post(URL, json=body)
    assert response.status_code == 202 and response.json() == {"status": "received"}
    assert body["email"] not in response.text  # nothing is echoed back
    rows = stored(admin_db, body["clinic_name"])
    assert len(rows) == 1 and rows[0][1:] == (body["email"], "pilot", "new")
    job = admin_db.execute("select count(*) from app_private.jobs where kind = 'demo_request_alert' "
                           "and payload->>'request_id' = %s", (str(rows[0][0]),)).fetchone()[0]
    assert job == 1

    listed = client.get(CONSOLE, headers=world.platform_admin.auth_mfa)
    assert listed.status_code == 200
    assert any(r["clinic_name"] == body["clinic_name"] for r in listed.json())
    for headers in ({}, world.platform_admin.auth, world.a_owner.auth):  # anonymous, no MFA, clinic owner
        assert client.get(CONSOLE, headers=headers).status_code in (401, 403)


def test_status_changes_are_platform_admin_only_and_audited(client, world, admin_db):
    body = request_body()
    client.post(URL, json=body)
    request_id = stored(admin_db, body["clinic_name"])[0][0]
    assert client.patch(f"{CONSOLE}/{request_id}", headers=world.a_owner.auth,
                        json={"status": "contacted"}).status_code == 403
    changed = client.patch(f"{CONSOLE}/{request_id}", headers=world.platform_admin.auth_mfa,
                           json={"status": "contacted"})
    assert changed.status_code == 200 and changed.json()["status"] == "contacted"
    audit = admin_db.execute("select metadata->>'status' from public.audit_events "
                             "where action = 'demo_request.status_changed' and target_id = %s",
                             (str(request_id),)).fetchone()[0]
    assert audit == "contacted"
    assert client.patch(f"{CONSOLE}/{uuid.uuid4()}", headers=world.platform_admin.auth_mfa,
                        json={"status": "closed"}).status_code == 404


def test_honeypot_submissions_are_accepted_but_not_stored(client, admin_db):
    body = request_body(website="https://spam.example.com")
    assert client.post(URL, json=body).status_code == 202
    assert stored(admin_db, body["clinic_name"]) == []


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"consent": False}, "consent_required"),
        ({"email": "not-an-email"}, "validation_error"),
        ({"clinic_name": "x"}, "validation_error"),
        ({"interest": "diagnosis"}, "validation_error"),
        ({"phone": "call me maybe"}, "validation_error"),
        ({"message": "x" * 1001}, "validation_error"),
        ({"diagnosis": "glaucoma"}, "validation_error"),  # unknown fields are refused
    ],
)
def test_invalid_requests_are_refused_and_nothing_is_stored(client, admin_db, change, code):
    body = request_body(**change)
    response = client.post(URL, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert stored(admin_db, body["clinic_name"]) == []


def test_rate_limits(client, admin_db, monkeypatch):
    monkeypatch.setitem(demo_requests.LIMITS, "demo_email", (86400, 2))
    body = request_body()
    for _ in range(2):
        assert client.post(URL, json={**body, "clinic_name": f"Clinic {uuid.uuid4().hex[:6]}"}).status_code == 202
    limited = client.post(URL, json={**body, "clinic_name": "Clinic limited"})
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limited"
    assert stored(admin_db, "Clinic limited") == []


def test_notification_has_no_contact_details(client, admin_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_request_notify_email", "ops@example.com")
    body = request_body()
    client.post(URL, json=body)
    sender = FakeSender()
    drain(client, sender, None)
    sent = [e for key, e in sender.sent if key.startswith("demo_request_alert/")]
    assert len(sent) == 1
    email = sent[0]
    assert email.to == ("ops@example.com",) and body["clinic_name"] in email.subject
    for private in (body["email"], body["phone"], body["name"], body["message"]):
        assert private not in email.text and private not in email.html


def test_without_a_notification_address_the_job_is_skipped(client, admin_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_request_notify_email", None)
    body = request_body()
    client.post(URL, json=body)
    sender = FakeSender()
    drain(client, sender, None)
    assert [k for k, _ in sender.sent if k.startswith("demo_request_alert/")] == []
    status = admin_db.execute("select status from app_private.jobs where kind = 'demo_request_alert' "
                              "and payload->>'request_id' = %s",
                              (str(stored(admin_db, body["clinic_name"])[0][0]),)).fetchone()[0]
    assert status == "skipped"
