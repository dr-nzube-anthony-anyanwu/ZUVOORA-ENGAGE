"""Hostname normalisation and the DNS TXT checker (no network: the resolver is faked)."""

from types import SimpleNamespace

import dns.exception
import dns.resolver
import pytest

from app.config import Settings
from app.services.domain_verification import (
    DnsTxtVerifier,
    HostnameError,
    normalise_hostname,
    txt_record,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("www.Clinic.com", "www.clinic.com"),
        ("  clinic.com.  ", "clinic.com"),
        ("eye-care.clinic.co.uk", "eye-care.clinic.co.uk"),
        ("httpclinic.com", "httpclinic.com"),
        ("klinik-münchen.de", "xn--klinik-mnchen-3ob.de"),
    ],
)
def test_valid_hostnames_are_normalised(raw, expected):
    assert normalise_hostname(raw) == expected


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("https://www.clinic.com", "only the host name"),
        ("www.clinic.com/contact", "only the host name"),
        ("www.clinic.com:8080", "only the host name"),
        ("user@clinic.com", "not allowed"),
        ("clinic", "full domain"),
        ("localhost", "full domain"),
        ("api.localhost", "reserved"),
        ("printer.local", "reserved"),
        ("db.internal", "reserved"),
        ("10.0.0.1", "not valid|IP"),
        ("192.168.1.10", "not valid|IP"),
        ("-bad-.com", "not valid"),
        ("under_score.com", "not valid"),
        ("a..com", "not valid"),
        ("", "Enter"),
        ("x" * 64 + ".com", "not valid"),
    ],
)
def test_invalid_hostnames_are_rejected(raw, message):
    with pytest.raises(HostnameError, match=message):
        normalise_hostname(raw)


def test_txt_record_format():
    assert txt_record("www.clinic.com", "ab" * 32) == (
        "_zuvoora-engage.www.clinic.com",
        "zuvoora-engage-verification=" + "ab" * 32,
    )


TOKEN = "0f" * 32


def verifier_with(monkeypatch, behaviour):
    verifier = DnsTxtVerifier(Settings(_env_file=None, dns_resolvers="192.0.2.53"))
    calls = []

    def fake_resolve(name, rdtype, raise_on_no_answer=True):
        calls.append((name, rdtype))
        if isinstance(behaviour, Exception):
            raise behaviour
        records = [SimpleNamespace(strings=parts) for parts in behaviour]
        return SimpleNamespace(rrset=records or None)

    monkeypatch.setattr(verifier._resolver, "resolve", fake_resolve)
    return verifier, calls


def test_matching_record_verifies_and_only_txt_is_queried(monkeypatch):
    value = f"zuvoora-engage-verification={TOKEN}".encode()
    verifier, calls = verifier_with(monkeypatch, [[b"other=1"], [value[:20], value[20:]]])
    assert verifier.check("www.clinic.com", TOKEN) == "verified"
    assert calls == [("_zuvoora-engage.www.clinic.com", "TXT")]


@pytest.mark.parametrize(
    ("behaviour", "expected"),
    [
        ([[b"zuvoora-engage-verification=" + b"00" * 32]], "mismatch"),
        ([], "not_found"),
        (dns.resolver.NXDOMAIN(), "not_found"),
        (dns.resolver.LifetimeTimeout(timeout=4.0, errors={}), "timeout"),
        (dns.resolver.NoNameservers(), "dns_error"),
        (dns.exception.DNSException(), "dns_error"),
    ],
)
def test_check_outcomes(monkeypatch, behaviour, expected):
    verifier, _ = verifier_with(monkeypatch, behaviour)
    assert verifier.check("www.clinic.com", TOKEN) == expected


def test_configured_nameservers_are_used():
    verifier = DnsTxtVerifier(
        Settings(_env_file=None, dns_resolvers="8.8.8.8, 9.9.9.9", dns_timeout_seconds=3)
    )
    assert verifier._resolver.nameservers == ["8.8.8.8", "9.9.9.9"]
    assert verifier._resolver.lifetime == 3
