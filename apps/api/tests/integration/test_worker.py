"""Phase 4a: the worker against the real queue (fake email sender; nothing is sent)."""

from __future__ import annotations

import pytest

from app import worker
from app.config import get_settings
from app.services.email import Email, EmailError
from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)
from tests.integration.test_inbox_api import visitor_session

pytestmark = pytest.mark.integration


class FakeSender:
    """Records deliveries; `fail` maps idempotency keys to errors to raise (once each)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Email]] = []
        self.fail: dict[str, EmailError | Exception] = {}

    def send(self, email: Email, idempotency_key: str) -> str:
        error = self.fail.pop(idempotency_key, None)
        if error:
            raise error
        self.sent.append((idempotency_key, email))
        return f"fake-{len(self.sent)}"


@pytest.fixture
def handover(client, world, chat):  # noqa: F811
    token = visitor_session(client, world, chat)
    client.post("/api/v1/public/widget/messages", json={"token": token, "text": "Call me please"})
    response = client.post(
        "/api/v1/public/widget/handover",
        json={"token": token, "name": "Bola Test", "phone": "+234 801 000 7777", "consent": True},
    )
    assert response.status_code == 200, response.text
    handovers = client.get(
        f"/api/v1/tenants/{world.tenant_a}/handovers", headers=world.a_owner.auth
    ).json()
    item = next(
        h for h in handovers if h["contact_phone"] == "+234 801 000 7777" and h["status"] == "new"
    )
    return item


def job(admin_db, key):
    row = admin_db.execute(
        "select status, attempts, result, last_error from app_private.jobs "
        "where idempotency_key = %s",
        (key,),
    ).fetchone()
    return row


def run(client, sender):
    """Drain everything due, as the worker loop does (other tests leave jobs in the queue)."""
    for _ in range(50):
        if not worker.process_batch(client.app.state.db, sender, get_settings()):
            return
    raise AssertionError("queue did not drain")


def test_call_back_request_alerts_the_front_desk_once(client, world, handover, admin_db):
    key = f"handover_alert/{handover['id']}"
    sender = FakeSender()
    run(client, sender)
    mine = [e for k, e in sender.sent if k == key]
    assert len(mine) == 1
    email = mine[0]
    assert set(email.to) == {world.a_owner.email, world.a_admin.email, world.a_receptionist.email}
    assert f"/inbox/{handover['conversation_id']}" in email.text
    for private in ("Bola Test", "+234 801 000 7777", "Call me please"):
        assert private not in email.text and private not in email.html
    status, attempts, result, _ = job(admin_db, key)
    assert (status, attempts) == ("done", 1)
    assert result["message_id"].startswith("fake-")

    run(client, sender)  # nothing is sent twice
    assert len([k for k, _ in sender.sent if k == key]) == 1


def test_handled_requests_are_not_alerted(client, world, handover, admin_db):
    client.patch(
        f"/api/v1/tenants/{world.tenant_a}/handovers/{handover['id']}",
        headers=world.a_receptionist.auth,
        json={"status": "in_progress"},
    )
    sender = FakeSender()
    run(client, sender)
    key = f"handover_alert/{handover['id']}"
    assert not [k for k, _ in sender.sent if k == key]
    assert job(admin_db, key)[0] == "skipped"


def test_temporary_failure_is_retried_with_the_same_key(client, handover, admin_db):
    key = f"handover_alert/{handover['id']}"
    sender = FakeSender()
    sender.fail[key] = EmailError("http_503", permanent=False)
    run(client, sender)
    status, attempts, _, error = job(admin_db, key)
    assert (status, attempts, error) == ("queued", 1, "http_503")

    admin_db.execute(
        "update app_private.jobs set run_at = now() where idempotency_key = %s", (key,)
    )
    run(client, sender)
    assert [k for k, _ in sender.sent].count(key) == 1
    assert job(admin_db, key)[:2] == ("done", 2)


def test_permanent_failure_goes_to_dead_letters(client, handover, admin_db):
    key = f"handover_alert/{handover['id']}"
    sender = FakeSender()
    sender.fail[key] = EmailError("http_422", permanent=True)
    run(client, sender)
    assert job(admin_db, key)[0] == "dead"


def test_a_crashing_job_is_retried_not_lost(client, handover, admin_db):
    key = f"handover_alert/{handover['id']}"
    sender = FakeSender()
    sender.fail[key] = RuntimeError("bug")
    run(client, sender)
    assert job(admin_db, key)[0] == "queued"


def test_suspended_clinic_gets_no_alert(client, world, handover, admin_db):
    key = f"handover_alert/{handover['id']}"
    admin_db.execute(
        "update public.tenants set status = 'suspended' where id = %s", (world.tenant_a,)
    )
    try:
        sender = FakeSender()
        run(client, sender)
    finally:
        admin_db.execute(
            "update public.tenants set status = 'active' where id = %s", (world.tenant_a,)
        )
    assert not [k for k, _ in sender.sent if k == key]
    assert job(admin_db, key)[0] == "skipped"
