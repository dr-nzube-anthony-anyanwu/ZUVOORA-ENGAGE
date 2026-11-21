"""Website domain verification by DNS TXT record (Phase 2b, ADR-022).

Only a DNS TXT lookup is performed: the API never fetches the clinic's website, so a hostname
cannot be used to make the server call internal or arbitrary URLs.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal, Protocol

import dns.exception
import dns.resolver

from app.config import Settings

RECORD_PREFIX = "_zuvoora-engage"
VALUE_PREFIX = "zuvoora-engage-verification"

CheckResult = Literal["verified", "not_found", "mismatch", "dns_error", "timeout"]

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
# Names that can never be a clinic's public website.
_RESERVED_TLDS = frozenset({
    "localhost", "local", "internal", "test", "invalid", "example", "onion", "arpa",
    "home", "lan", "corp", "intranet", "private",
})


class HostnameError(ValueError):
    pass


def normalise_hostname(raw: str) -> str:
    """Return the lower-case ASCII (punycode) hostname or raise HostnameError."""
    value = raw.strip().rstrip(".").lower()
    if not value:
        raise HostnameError("Enter your website's host name, for example www.yourclinic.com.")
    if any(ch in value for ch in "/:@?#[]\\ \t\n"):
        if "://" in value or "/" in value or ":" in value:
            raise HostnameError(
                "Enter only the host name, for example www.yourclinic.com "
                "(no https://, path or port)."
            )
        raise HostnameError("The host name contains characters that are not allowed.")
    try:
        ascii_name = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HostnameError("The host name is not valid.") from exc
    if len(ascii_name) > 253:
        raise HostnameError("The host name is too long.")
    labels = ascii_name.split(".")
    if len(labels) < 2:
        raise HostnameError("Include the full domain, for example yourclinic.com.")
    if not all(_LABEL.match(label) for label in labels):
        raise HostnameError("The host name is not valid.")
    try:
        ipaddress.ip_address(ascii_name)
    except ValueError:
        pass
    else:
        raise HostnameError("IP addresses cannot be registered; use your website's domain name.")
    if labels[-1].isdigit() or not labels[-1][0].isalpha():
        raise HostnameError("The host name is not valid.")
    if labels[-1] in _RESERVED_TLDS:
        raise HostnameError("This is a private or reserved name, not a public website.")
    return ascii_name


def txt_record(hostname: str, token: str) -> tuple[str, str]:
    """The (name, value) the clinic must publish."""
    return f"{RECORD_PREFIX}.{hostname}", f"{VALUE_PREFIX}={token}"


class DomainVerifier(Protocol):
    def check(self, hostname: str, token: str) -> CheckResult: ...


class DnsTxtVerifier:
    def __init__(self, settings: Settings) -> None:
        nameservers = settings.dns_nameservers
        self._resolver = dns.resolver.Resolver(configure=not nameservers)
        if nameservers:
            self._resolver.nameservers = nameservers
        self._resolver.lifetime = settings.dns_timeout_seconds
        self._resolver.timeout = min(2.0, settings.dns_timeout_seconds)

    def check(self, hostname: str, token: str) -> CheckResult:
        name, expected = txt_record(hostname, token)
        try:
            answer = self._resolver.resolve(name, "TXT", raise_on_no_answer=False)
        except dns.resolver.NXDOMAIN:
            return "not_found"
        except dns.resolver.LifetimeTimeout:
            return "timeout"
        except dns.exception.DNSException:
            return "dns_error"
        if answer.rrset is None:
            return "not_found"
        values = {
            b"".join(record.strings).decode("utf-8", "replace").strip()
            for record in answer.rrset
        }
        return "verified" if expected in values else "mismatch"
