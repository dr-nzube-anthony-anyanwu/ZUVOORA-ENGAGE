"""Output guard: model text reaches a visitor only if code can check it is grounded and safe.

Rejected when the answer:
  * is a control token (NO_ANSWER / MEDICAL_ADVICE / EMERGENCY) or empty;
  * contains a number, link or email address that is not in the clinic's sources
    (invented prices, times, phone numbers and URLs are the most harmful hallucinations);
  * looks like medical advice, or leaks the prompt;
  * is too long.
A false rejection costs a polite fallback with a handover offer; a false acceptance could
mislead a patient, so the checks are strict on purpose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.ai.prompting import EMERGENCY, MEDICAL, NO_ANSWER

Verdict = Literal[
    "ok",
    "no_answer",
    "medical",
    "emergency",
    "unsupported_number",
    "unsupported_link",
    "unsupported_email",
    "medical_content",
    "prompt_leak",
    "too_long",
]

MAX_ANSWER_CHARS = 1200

_URL = re.compile(
    r"\b(?:https?://|www\.)[^\s<>()\"']+"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|ng|org|net|health|clinic|info|co|io)\b"
    r"(?:/[^\s<>()\"']*)?",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MEDICAL_OUT = re.compile(
    r"\b(you should (take|use|apply|start|stop)|(take|use|apply|instil+) (\d|one|two|three)\b|"
    r"\d+ ?(mg|ml|drops?)\b|drops? (once|twice|daily|every)|times (a|per) day|"
    r"you (probably |likely |may |might |could )?have (glaucoma|cataracts?|an? infection|"
    r"conjunctivitis|a detached|retinal)|(sounds|looks) like (glaucoma|cataracts?|an? infection|"
    r"conjunctivitis))",
    re.IGNORECASE,
)
_LEAK = re.compile(
    r"<<|>>|\bSOURCES\b|NO_ANSWER|MEDICAL_ADVICE|(?i:system prompt|my instructions|these rules)"
)


@dataclass(frozen=True)
class GuardResult:
    verdict: Verdict
    text: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"


def _numbers(text: str) -> set[str]:
    # "15,000" == "15000"; "09:00" -> {"9", "0"} so "9am" matches; phone groups stay as written.
    text = re.sub(r"(?<=\d)[,](?=\d{3}\b)", "", text)
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text)}


def _digit_blobs(text: str) -> list[str]:
    """Digits of each phone-like run, so "+234 801 555 0101" also matches "08015550101" parts."""
    return [re.sub(r"\D", "", m) for m in re.findall(r"[+\d][\d\s().\-]{5,}\d", text)]


def _norm_link(link: str) -> str:
    link = re.sub(r"^https?://", "", link.lower()).removeprefix("www.")
    return link.rstrip("/.,;:!?")


def check(answer: str, sources: str) -> GuardResult:
    text = answer.strip()
    upper = text.upper()
    if not text or upper.startswith(NO_ANSWER) or upper == NO_ANSWER:
        return GuardResult("no_answer")
    if upper.startswith(MEDICAL):
        return GuardResult("medical")
    if upper.startswith(EMERGENCY):
        return GuardResult("emergency")
    if _LEAK.search(text):
        return GuardResult("prompt_leak")
    if len(text) > MAX_ANSWER_CHARS:
        return GuardResult("too_long")
    if _MEDICAL_OUT.search(text):
        return GuardResult("medical_content")

    # Only the clinic's sources count: echoing a number from the question ("is it ₦500?") could
    # confirm something the clinic never said.
    allowed_text = sources
    allowed_lower = allowed_text.lower()
    for email in _EMAIL.findall(text):
        if email.lower() not in allowed_lower:
            return GuardResult("unsupported_email")
    without_emails = _EMAIL.sub(" ", text)
    allowed_links = {_norm_link(x) for x in _URL.findall(_EMAIL.sub(" ", allowed_text))}
    for link in _URL.findall(without_emails):
        norm = _norm_link(link)
        if norm and not any(norm == a or a.startswith(norm) for a in allowed_links):
            return GuardResult("unsupported_link")

    allowed_numbers = _numbers(allowed_text)
    blobs = _digit_blobs(allowed_text)
    for number in _numbers(without_emails):
        if number in allowed_numbers:
            continue
        # Only long digit runs (a phone number written differently) may match inside a blob;
        # short numbers (prices, times, durations) must appear exactly.
        if len(number) < 7 or not any(number in blob for blob in blobs):
            return GuardResult("unsupported_number")
    return GuardResult("ok", text)
