"""Deterministic safety rules, checked before anything else (no model involved).

Emergencies get the clinic's published emergency guidance (or a safe default) immediately.
Requests for diagnosis, prescribing or treatment advice get a fixed refusal. Rules are English
and deliberately broad: a false positive costs a cautious reply; a miss could cost sight.
"""

from __future__ import annotations

import re

_EMERGENCY = [
    r"\bemergenc(y|ies)\b",
    r"\bsudden(ly)?\b.{0,40}\b(los[st]|lose|losing|blind|blurr?|dark|black|can'?t see|cannot see|vision|sight)",
    # "sudden(ly)" anywhere in a message about vision, e.g. "my eyesight went dark suddenly"
    r"(?=.*\bsudden(ly)?\b).*\b(vision|sight|eyesight|blind|blurr?\w*)\b",
    r"\b(los[st]|lose|losing)\b.{0,20}\b(vision|sight|eyesight)\b",
    r"\b(can'?t|cannot|can not|unable to)\s+see\b",
    r"\b(went|gone|going)\s+blind\b",
    r"\b(chemicals?|acid|bleach|alkali|lye|caustic|lime|cement|detergent|battery (acid|fluid)|pepper spray)\b.{0,40}\beyes?\b",
    r"\beyes?\b.{0,40}\b(chemicals?|acid|bleach|alkali|caustic|cement|pepper spray)\b",
    r"\b(hit|struck|punched|stabbed|punctured|cut|injur(y|ed|ies)|trauma|wound(ed)?|accident)\b.{0,40}\beyes?\b",
    r"\beyes?\b.{0,40}\b(hit|struck|punched|stabbed|punctured|cut|injur(y|ed)|trauma|bleeding|swollen shut)\b",
    r"\bsomething\b.{0,20}\b(in|into|stuck in|went into)\b.{0,10}\b(my )?eyes?\b",
    r"\bflash(es|ing)?\b.{0,40}\bfloaters?\b|\bfloaters?\b.{0,40}\bflash(es|ing)?\b",
    r"\b(curtain|shadow|veil)\b.{0,30}\b(vision|sight|eye)\b",
    r"\b(severe|extreme|unbearable|terrible|excruciating)\b.{0,30}\b(eye )?pain\b",
    r"\b(bleeding|blood)\b.{0,30}\beyes?\b",
    r"\b(double vision)\b.{0,30}\b(sudden|headache|weak|numb)",
]
_EMERGENCY_RE = re.compile("|".join(f"(?:{p})" for p in _EMERGENCY), re.IGNORECASE)

_MEDICAL = [
    r"\b(what|which)\b.{0,20}\b(drops?|medicines?|medications?|drugs?|tablets?|pills?|antibiotics?|ointments?|treatment)\b.{0,30}\b(use|take|buy|apply|need|should|for)\b",
    r"\bshould i\b.{0,30}\b(take|use|stop|apply|continue|be worried|worry)\b",
    r"\b(dosage|dose|how much (of|should))\b",
    r"\b(prescri(be|ption)|diagnos(e|is))\b",
    r"\bdo i have\b",
    r"\b(is|could) (it|this|that)\b.{0,15}\b(glaucoma|cataract|infection|conjunctivitis|apollo|serious|cancer|tumou?r|normal|dangerous)\b",
    r"\b(cure|treat|heal)\b.{0,20}\b(my|this|it)\b",
    r"\bwhat('?s| is) wrong with my\b",
    r"\b(side effects?)\b",
]
_MEDICAL_RE = re.compile("|".join(f"(?:{p})" for p in _MEDICAL), re.IGNORECASE)

DEFAULT_EMERGENCY = (
    "Please go to the nearest hospital emergency department now, or call emergency services. "
    "Do not wait for an online reply."
)


def is_emergency(text: str) -> bool:
    return bool(_EMERGENCY_RE.search(text))


def asks_for_medical_advice(text: str) -> bool:
    return bool(_MEDICAL_RE.search(text))


def emergency_reply(guidance: str | None, phone: str | None) -> str:
    parts = [
        "This sounds like it could be urgent. I can't assess symptoms.",
        (guidance or DEFAULT_EMERGENCY).strip(),
    ]
    if phone:
        parts.append(f"You can also call the clinic on {phone}.")
    return " ".join(parts)


def medical_advice_reply(clinic: str, phone: str | None) -> str:
    reply = (
        "I'm not able to give medical advice, diagnose conditions or recommend medicines or "
        f"treatment. A clinician at {clinic} can help with that"
    )
    reply += f" — you can call {phone}" if phone else ""
    return reply + ", or I can ask the clinic team to contact you."
