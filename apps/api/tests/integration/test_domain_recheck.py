"""Phase 3f: the daily domain re-verification job against the real database (scripted DNS)."""

from __future__ import annotations

import uuid

import pytest

from app.jobs import reverify_domains
from tests.integration.test_answering_api import chat  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration


class ScriptedDns:
    """Answers per hostname; any other host (from other tests) stays verified."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def check(self, hostname: str, token: str) -> str:
        self.calls.append(hostname)
        return self.answers.get(hostname, "verified")


@pytest.fixture
def lapsing_host(client, world, chat, admin_db):  # noqa: F811
    host = f"www.lapse-{uuid.uuid4().hex[:8]}.example.com"
    domain_id = admin_db.execute(
        "insert into public.tenant_domains (tenant_id, hostname) values (%s, %s) returning id",
        (world.tenant_a, host),
    ).fetchone()[0]
    admin_db.execute(
        "update public.tenant_domains set verification_status = 'verified' where id = %s",
        (domain_id,),
    )
    yield host, domain_id
    # Keep the shared clinic under its domain limit for later tests.
    admin_db.execute(
        "update public.tenant_domains set removed_at = now() where id = %s", (domain_id,)
    )


def make_due(admin_db, domain_id):
    admin_db.execute(
        "update public.tenant_domains set last_checked_at = now() - interval '2 days' "
        "where id = %s",
        (domain_id,),
    )


def frame_config(client, world, host):
    key = client.get(f"/api/v1/tenants/{world.tenant_a}/widget", headers=world.a_owner.auth).json()[
        "public_key"
    ]
    return client.post("/api/v1/public/widget/frame-config", json={"key": key, "host": host})


def test_record_removed_for_three_checks_lapses_and_stops_the_widget(
    client, world, lapsing_host, admin_db
):
    host, domain_id = lapsing_host
    db = client.app.state.db
    assert frame_config(client, world, host).status_code == 200

    dns = ScriptedDns({host: "not_found"})
    for expected_lapsed in (0, 0, 1):
        make_due(admin_db, domain_id)
        summary = reverify_domains.run(db, dns)
        assert host in dns.calls
        assert summary.lapsed == expected_lapsed

    status = admin_db.execute(
        "select verification_status, recheck_failures from public.tenant_domains where id = %s",
        (domain_id,),
    ).fetchone()
    assert tuple(status) == ("pending", 3)
    assert frame_config(client, world, host).status_code == 403
    audit = admin_db.execute(
        "select count(*) from public.audit_events where action = 'domain.verification_lapsed' "
        "and target_id = %s",
        (str(domain_id),),
    ).fetchone()[0]
    assert audit == 1
    run_id = admin_db.execute(
        "select request_id from public.audit_events where action = 'domain.verification_lapsed' "
        "and target_id = %s",
        (str(domain_id),),
    ).fetchone()[0]
    assert run_id.startswith("job:reverify_domains:")

    # The owner fixes DNS and verifies again from the dashboard flow: back to a clean count.
    admin_db.execute(
        "update public.tenant_domains set verification_status = 'verified' where id = %s",
        (domain_id,),
    )
    assert frame_config(client, world, host).status_code == 200


def test_resolver_trouble_never_lapses_a_domain(client, world, lapsing_host, admin_db):
    host, domain_id = lapsing_host
    db = client.app.state.db
    dns = ScriptedDns({host: "timeout"})
    for _ in range(4):
        make_due(admin_db, domain_id)
        reverify_domains.run(db, dns)
    row = admin_db.execute(
        "select verification_status, recheck_failures, last_check_result "
        "from public.tenant_domains where id = %s",
        (domain_id,),
    ).fetchone()
    assert tuple(row) == ("verified", 0, "timeout")


def test_recently_checked_domains_are_not_checked_again(client, world, lapsing_host, admin_db):
    host, domain_id = lapsing_host
    db = client.app.state.db
    make_due(admin_db, domain_id)
    dns = ScriptedDns({})
    reverify_domains.run(db, dns)
    assert host in dns.calls
    dns.calls.clear()
    reverify_domains.run(db, dns)
    assert host not in dns.calls
