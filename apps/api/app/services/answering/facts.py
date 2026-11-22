"""Answers built only from a clinic's PUBLISHED structured data (no model, no invention).

If the clinic has not published the information asked for, the answer says so and offers a
handover — it never guesses hours, prices or contact details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import psycopg

from app.services.answering import hours as h

_INTENTS = {
    "hours": r"\b(open|opening|opens|close|closing|closes|closed|hours?|timings?|working (days|hours)|"
    r"what time|today|tonight|tomorrow|weekend|holidays?|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
    # "contact lens(es)" is a product, not a request for contact details.
    "contact": r"\b(phone|call|number|telephone|tel|whats ?app|e-?mail|contact(?!\s*lens)|reach (you|the clinic))\b",
    # Location questions only ("where can I park?" is not an address question).
    "address": r"\b(where (are|is) (you|the clinic|your (clinic|office|branch(es)?))|address|location|located|directions?|find you|how (do|can) i (get|find) (to )?(you|the clinic)|your branch(es)?|map)\b",
    "services": r"\b(services?|offer|provide|price|prices|pricing|cost|costs|how much|fees?|charges?|"
    r"do you (do|treat|perform|have|check|test))\b",
    "website": r"\b(website|web site|site|url)\b",
}
_INTENT_RE = {name: re.compile(p, re.IGNORECASE) for name, p in _INTENTS.items()}
_DAY_WORDS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass
class ClinicFacts:
    clinic: str
    profile: dict = field(default_factory=dict)
    branches: list[dict] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)

    @property
    def phone(self) -> str | None:
        return self.profile.get("public_phone") or next(
            (b.get("phone") for b in self.branches if b.get("phone")), None
        )


def load_facts(conn: psycopg.Connection, clinic: str) -> ClinicFacts:
    """Published facts for the widget's tenant (RLS + column grants: published copies only)."""
    profile = conn.execute("select published from public.clinic_profiles").fetchone()
    branches = conn.execute("select published from public.branches order by id").fetchall()
    services = conn.execute("select published from public.services order by id").fetchall()
    return ClinicFacts(
        clinic=clinic,
        profile=profile["published"] if profile else {},
        branches=[r["published"] for r in branches],
        services=[r["published"] for r in services],
    )


def intents(question: str) -> list[str]:
    return [name for name, pattern in _INTENT_RE.items() if pattern.search(question)]


def _hours_answer(facts: ClinicFacts, question: str, now: datetime) -> str | None:
    with_hours = [b for b in facts.branches if b.get("opening_hours")]
    if not with_hours:
        return None
    q = question.lower()
    lines = []
    for branch in with_hours:
        hours, name = branch["opening_hours"], branch["name"]
        local = h.local_now(branch.get("timezone", "Africa/Lagos"), now)
        target = None
        if re.search(r"\b(now|right now|currently|at the moment)\b", q):
            state = "open now" if h.open_now(hours, local) else "closed right now"
            is_open, text, _ = h.hours_on(hours, local.date())
            lines.append(f"{name}: {state}" + (f" (today {text})." if is_open else "."))
            continue
        if "tomorrow" in q:
            target = local.date() + timedelta(days=1)
        elif re.search(r"\b(today|tonight)\b", q):
            target = local.date()
        else:
            for word, index in _DAY_WORDS.items():
                if word in q:
                    target = local.date() + timedelta(days=(index - local.weekday()) % 7)
                    break
        if target is not None:
            is_open, text, note = h.hours_on(hours, target)
            label = target.strftime("%A %d %B")
            extra = f" ({note})" if note else ""
            lines.append(f"{name}: {'open ' + text if is_open else 'closed'} on {label}{extra}.")
        else:
            line = f"{name}: {h.weekly_summary(hours)}."
            upcoming = h.upcoming_exceptions(hours, local.date())
            if upcoming:
                line += " Coming up: " + "; ".join(upcoming) + "."
            lines.append(line)
    return "Opening hours — " + " ".join(lines) if len(lines) > 1 else lines[0]


def _contact_answer(facts: ClinicFacts) -> str | None:
    parts = []
    if facts.profile.get("public_phone"):
        parts.append(f"phone {facts.profile['public_phone']}")
    if facts.profile.get("public_email"):
        parts.append(f"email {facts.profile['public_email']}")
    for branch in facts.branches:
        branch_bits = [x for x in (branch.get("phone"), branch.get("email")) if x]
        if branch_bits:
            parts.append(f"{branch['name']}: " + ", ".join(branch_bits))
    return f"You can contact {facts.clinic}: " + "; ".join(parts) + "." if parts else None


def _address_answer(facts: ClinicFacts) -> str | None:
    lines = []
    for branch in facts.branches:
        place = ", ".join(x for x in (branch.get("address"), branch.get("city")) if x)
        if place:
            lines.append(
                f"{branch['name']}: {place}"
                + (f" ({branch['notes']})" if branch.get("notes") else "")
            )
    return "We're located at — " + "; ".join(lines) + "." if lines else None


def _services_answer(facts: ClinicFacts, question: str) -> str | None:
    if not facts.services:
        return None
    q = question.lower()
    named = [
        s
        for s in facts.services
        if all(word in q for word in re.findall(r"[a-z]{4,}", s["name"].lower())[:2])
    ]
    if named:
        lines = []
        for s in named[:3]:
            bits = [s["name"]]
            if s.get("description"):
                bits.append(s["description"])
            if s.get("duration_minutes"):
                bits.append(f"about {s['duration_minutes']} minutes")
            if s.get("price_note"):
                bits.append(f"price: {s['price_note']}")
            elif re.search(r"\b(price|cost|how much|fee)", q):
                bits.append("the clinic has not published a price for this")
            lines.append(" — ".join(bits))
        return " ".join(f"{line}." for line in lines)
    wants_price = bool(re.search(r"\b(price|prices|cost|how much|fees?|charges?)\b", q))
    items = []
    for s in facts.services[:15]:
        items.append(
            f"{s['name']} ({s['price_note']})" if wants_price and s.get("price_note") else s["name"]
        )
    return f"{facts.clinic} offers: " + "; ".join(items) + "."


def answer_from_facts(
    facts: ClinicFacts, question: str, now: datetime
) -> tuple[str | None, list[str]]:
    """(answer or None, intents found). None means: no fact intent, or nothing published."""
    found = intents(question)
    if not found:
        return None, []
    builders = {
        "hours": lambda: _hours_answer(facts, question, now),
        "contact": lambda: _contact_answer(facts),
        "address": lambda: _address_answer(facts),
        "services": lambda: _services_answer(facts, question),
        "website": lambda: (
            f"Our website is {facts.profile['website_url']}."
            if facts.profile.get("website_url")
            else None
        ),
    }
    answers = [a for a in (builders[i]() for i in found) if a]
    if not answers:
        missing = ", ".join(
            {
                "hours": "opening hours",
                "contact": "contact details",
                "address": "address",
                "services": "services",
                "website": "website",
            }[i]
            for i in found
        )
        return (
            f"I'm sorry, {facts.clinic} hasn't published its {missing} here yet. "
            "I can ask the clinic team to contact you."
        ), found
    return " ".join(answers), found
