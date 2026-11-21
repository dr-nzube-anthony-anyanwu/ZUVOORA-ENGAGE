"""Phase 2b domain registration and verification through the real API and RLS.

DNS is replaced by an in-memory zone controlled by each test, so no real DNS is queried.
"""

from __future__ import annotations

import uuid

import pytest

from app.config import Settings
from app.routes import domains as domains_module
from app.services.domain_verification import txt_record

pytestmark = pytest.mark.integration


class FakeDns:
    """In-memory TXT zone implementing the DomainVerifier protocol."""

    def __init__(self) -> None:
        self.zone: dict[str, set[str]] = {}
        self.queries: list[str] = []
        self.failure: str | None = None

    def publish(self, record: dict) -> None:
        self.zone.setdefault(record["name"], set()).add(record["value"])

    def check(self, hostname: str, token: str):
        name, expected = txt_record(hostname, token)
        self.queries.append(name)
        if self.failure:
            return self.failure
        values = self.zone.get(name)
        if not values:
            return "not_found"
        return "verified" if expected in values else "mismatch"


@pytest.fixture
def dns(client, monkeypatch, app_state):
    fake = FakeDns()
    app_state("domain_verifier", fake)
    monkeypatch.setattr(
        domains_module,
        "get_settings",
        lambda: Settings(_env_file=None, domain_verify_cooldown_seconds=0),
    )
    return fake


def host(label: str = "www") -> str:
    return f"{label}.clinic-{uuid.uuid4().hex[:10]}.example.com"


def url(tenant: str, path: str = "") -> str:
    return f"/api/v1/tenants/{tenant}/domains{path}"


def add(client, user, tenant, hostname):
    response = client.post(url(tenant), headers=user.auth, json={"hostname": hostname})
    assert response.status_code == 201, response.text
    return response.json()


def test_register_then_verify_with_dns_record(client, world, dns, admin_db):
    hostname = host()
    domain = add(client, world.a_owner, world.tenant_a, f"  {hostname.upper()}. ")
    assert domain["hostname"] == hostname
    assert domain["status"] == "pending"
    assert domain["dns_record"]["type"] == "TXT"
    assert domain["dns_record"]["name"] == f"_zuvoora-engage.{hostname}"
    assert domain["dns_record"]["value"].startswith("zuvoora-engage-verification=")

    verify = f"{url(world.tenant_a)}/{domain['id']}/verify"
    missing = client.post(verify, headers=world.a_owner.auth)
    assert missing.status_code == 200
    assert (missing.json()["status"], missing.json()["last_check_result"]) == (
        "pending",
        "not_found",
    )

    dns.publish(
        {"name": domain["dns_record"]["name"], "value": "zuvoora-engage-verification=wrong"}
    )
    wrong = client.post(verify, headers=world.a_admin.auth)
    assert wrong.json()["last_check_result"] == "mismatch"

    dns.publish(domain["dns_record"])
    ok = client.post(verify, headers=world.a_admin.auth)
    assert ok.status_code == 200
    assert ok.json()["status"] == "verified" and ok.json()["verified_at"] is not None
    assert dns.queries == [domain["dns_record"]["name"]] * 3  # TXT lookups only

    actions = [
        r[0]
        for r in admin_db.execute(
            "select action from public.audit_events where target_id = %s order by id",
            (domain["id"],),
        ).fetchall()
    ]
    assert actions == [
        "domain.added",
        "domain.verification_failed",
        "domain.verification_failed",
        "domain.verified",
    ]


@pytest.mark.parametrize(
    "hostname",
    [
        "https://www.clinic.com",
        "www.clinic.com/about",
        "localhost",
        "intranet.local",
        "10.0.0.5",
        "clinic",
        "bad_name.com",
    ],
)
def test_unsafe_or_malformed_hostnames_rejected(client, world, dns, hostname):
    response = client.post(
        url(world.tenant_a), headers=world.a_owner.auth, json={"hostname": hostname}
    )
    assert response.status_code == 422


def test_body_cannot_smuggle_fields(client, world, dns):
    for extra in (
        {"tenant_id": world.tenant_b},
        {"verification_status": "verified"},
        {"verification_token": "0" * 64},
    ):
        response = client.post(
            url(world.tenant_a), headers=world.a_owner.auth, json={"hostname": host(), **extra}
        )
        assert response.status_code == 422, extra


def test_receptionist_can_view_but_not_manage(client, world, dns):
    domain = add(client, world.a_owner, world.tenant_a, host())
    headers = world.a_receptionist.auth
    assert domain["id"] in {
        d["id"] for d in client.get(url(world.tenant_a), headers=headers).json()
    }
    responses = [
        client.post(url(world.tenant_a), headers=headers, json={"hostname": host()}),
        client.post(f"{url(world.tenant_a)}/{domain['id']}/verify", headers=headers),
        client.post(f"{url(world.tenant_a)}/{domain['id']}/remove", headers=headers),
    ]
    assert [r.status_code for r in responses] == [403, 403, 403]
    assert dns.queries == []


def test_other_tenant_cannot_see_verify_or_remove(client, world, dns):
    domain = add(client, world.a_owner, world.tenant_a, host())
    attacker = world.b_owner.auth
    for response in (
        client.get(url(world.tenant_a), headers=attacker),
        client.post(f"{url(world.tenant_a)}/{domain['id']}/verify", headers=attacker),
        client.post(f"{url(world.tenant_a)}/{domain['id']}/remove", headers=attacker),
        client.post(f"{url(world.tenant_b)}/{domain['id']}/verify", headers=attacker),
        client.post(f"{url(world.tenant_b)}/{domain['id']}/remove", headers=attacker),
        client.get(url(world.tenant_a), headers=world.outsider.auth),
    ):
        assert response.status_code == 404
    assert dns.queries == []
    still = client.get(url(world.tenant_a), headers=world.a_owner.auth).json()
    assert domain["id"] in {d["id"] for d in still}


def test_squatting_cannot_block_or_steal_a_verified_domain(client, world, dns, admin_db):
    hostname = host()
    # Tenant B claims first (squatting) but cannot verify without DNS control.
    squat = add(client, world.b_owner, world.tenant_b, hostname)
    real = add(client, world.a_owner, world.tenant_a, hostname)
    dns.publish(real["dns_record"])
    assert (
        client.post(
            f"{url(world.tenant_b)}/{squat['id']}/verify", headers=world.b_owner.auth
        ).json()["last_check_result"]
        == "mismatch"
    )
    assert (
        client.post(
            f"{url(world.tenant_a)}/{real['id']}/verify", headers=world.a_owner.auth
        ).json()["status"]
        == "verified"
    )
    # Even if B's token were also published, the hostname stays with the first verifier.
    dns.publish(squat["dns_record"])
    taken = client.post(f"{url(world.tenant_b)}/{squat['id']}/verify", headers=world.b_owner.auth)
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "domain_taken"
    kept = admin_db.execute(
        "select count(*) from public.audit_events where target_id = %s "
        "and action = 'domain.verification_failed'",
        (squat["id"],),
    ).fetchone()[0]
    assert kept == 2  # attempts are recorded even when refused


def test_cooldown_between_checks(client, world, monkeypatch, dns):
    monkeypatch.setattr(
        domains_module,
        "get_settings",
        lambda: Settings(_env_file=None, domain_verify_cooldown_seconds=60),
    )
    domain = add(client, world.a_owner, world.tenant_a, host())
    verify = f"{url(world.tenant_a)}/{domain['id']}/verify"
    assert client.post(verify, headers=world.a_owner.auth).status_code == 200
    again = client.post(verify, headers=world.a_owner.auth)
    assert again.status_code == 429
    assert again.json()["error"]["code"] == "too_many_checks"
    assert len(dns.queries) == 1


def test_dns_failures_are_reported_not_fatal(client, world, dns):
    domain = add(client, world.a_owner, world.tenant_a, host())
    dns.failure = "timeout"
    response = client.post(
        f"{url(world.tenant_a)}/{domain['id']}/verify", headers=world.a_owner.auth
    )
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["last_check_result"]) == (
        "pending",
        "timeout",
    )


def test_remove_releases_hostname_and_reclaim_gets_new_token(client, world, dns):
    hostname = host()
    domain = add(client, world.a_owner, world.tenant_a, hostname)
    dns.publish(domain["dns_record"])
    client.post(f"{url(world.tenant_a)}/{domain['id']}/verify", headers=world.a_owner.auth)
    duplicate = client.post(
        url(world.tenant_a), headers=world.a_owner.auth, json={"hostname": hostname}
    )
    assert duplicate.status_code == 409

    removed = client.post(
        f"{url(world.tenant_a)}/{domain['id']}/remove", headers=world.a_owner.auth
    )
    assert removed.status_code == 204
    listed = client.get(url(world.tenant_a), headers=world.a_owner.auth).json()
    assert domain["id"] not in {d["id"] for d in listed}
    gone = client.post(f"{url(world.tenant_a)}/{domain['id']}/verify", headers=world.a_owner.auth)
    assert gone.status_code == 404

    # Another clinic can now verify it (after proving DNS control with its own token).
    other = add(client, world.b_owner, world.tenant_b, hostname)
    assert other["dns_record"]["value"] != domain["dns_record"]["value"]
    dns.publish(other["dns_record"])
    verified = client.post(
        f"{url(world.tenant_b)}/{other['id']}/verify", headers=world.b_owner.auth
    )
    assert verified.json()["status"] == "verified"


def test_domain_limit(client, world, dns, admin_db):
    existing = admin_db.execute(
        "select count(*) from public.tenant_domains where tenant_id = %s and removed_at is null",
        (world.tenant_b,),
    ).fetchone()[0]
    for _ in range(10 - existing):
        add(client, world.b_owner, world.tenant_b, host())
    over = client.post(url(world.tenant_b), headers=world.b_owner.auth, json={"hostname": host()})
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "limit_reached"
