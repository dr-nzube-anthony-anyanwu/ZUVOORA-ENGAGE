"""Phase 6 (D5): the real ClamAV daemon detects the standard EICAR anti-virus test file.

Runs only when CLAMAV_LIVE_HOST is set (the `deployment` CI job starts the same pinned ClamAV
image that production uses). EICAR is a harmless, industry-standard test string; it is assembled
at run time so that this source file itself does not trigger desktop anti-virus scanners.
"""

from __future__ import annotations

import os

import pytest

from app.services.malware_scan import ClamdScanner

HOST = os.environ.get("CLAMAV_LIVE_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="set CLAMAV_LIVE_HOST to test a real clamd")

_PARTS = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$", "EICAR-STANDARD-", "ANTIVIRUS-TEST-FILE!$H+H*")


def scanner() -> ClamdScanner:
    return ClamdScanner(HOST or "", int(os.environ.get("CLAMAV_LIVE_PORT", "3310")), 60)


def test_real_clamav_detects_the_eicar_test_file():
    result = scanner().scan("".join(_PARTS).encode())
    assert not result.clean
    assert result.signature and "Eicar" in result.signature


def test_real_clamav_passes_a_clean_document():
    assert scanner().scan(b"Opening hours: Monday to Friday, 8am to 5pm.").clean
