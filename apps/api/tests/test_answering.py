"""Deterministic answering (Phase 3c): safety rules, hours, facts, chunking, query terms."""

from datetime import UTC, datetime

import pytest

from app.services.answering import facts as f
from app.services.answering import hours as h
from app.services.answering.chunking import MAXIMUM, chunk_text
from app.services.answering.retrieval import query_terms
from app.services.answering.safety import (
    DEFAULT_EMERGENCY,
    asks_for_medical_advice,
    emergency_reply,
    is_emergency,
)

HOURS = {
    "weekly": [
        {
            "day": d,
            "closed": False,
            "ranges": [{"open": "08:00", "close": "13:00"}, {"open": "14:00", "close": "17:00"}],
        }
        for d in ("mon", "tue", "wed", "thu", "fri")
    ]
    + [
        {"day": "sat", "closed": False, "ranges": [{"open": "09:00", "close": "13:00"}]},
        {"day": "sun", "closed": True, "ranges": []},
    ],
    "exceptions": [{"date": "2026-12-25", "closed": True, "ranges": [], "note": "Christmas Day"}],
}
FACTS = f.ClinicFacts(
    clinic="Lekki Eye Clinic",
    profile={
        "public_phone": "+234 801 000 0000",
        "public_email": "hello@clinic.example.com",
        "emergency_guidance": "Go to Lagos Island General Hospital emergency unit.",
        "website_url": "https://clinic.example.com",
    },
    branches=[
        {
            "name": "Lekki",
            "address": "1 Admiralty Way",
            "city": "Lagos",
            "timezone": "Africa/Lagos",
            "opening_hours": HOURS,
        }
    ],
    services=[
        {
            "name": "Comprehensive eye examination",
            "description": "Full eye health check",
            "duration_minutes": 45,
            "price_note": "From NGN 15,000",
        },
        {"name": "Contact lens fitting", "price_note": None},
    ],
)


# ----- safety rules -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "I suddenly lost vision in my left eye",
        "my eyesight went dark suddenly",
        "I can't see out of my right eye",
        "bleach splashed in my eye",
        "Chemical got into my eyes at work",
        "my son was hit in the eye with a ball",
        "I see flashes and lots of new floaters",
        "there is a curtain over my vision",
        "severe eye pain and headache",
        "my eye is bleeding",
        "this is an emergency",
    ],
)
def test_emergencies_are_detected(text):
    assert is_emergency(text)


@pytest.mark.parametrize(
    "text",
    [
        "What are your opening hours?",
        "How much is an eye test?",
        "Do you sell contact lenses?",
        "Can I book for Saturday?",
        "Where are you located?",
        "My vision is blurry when reading, do you do eye tests?",
        "Do you open suddenly on public holidays?",
    ],
)
def test_ordinary_questions_are_not_emergencies(text):
    assert not is_emergency(text)


@pytest.mark.parametrize(
    "text",
    [
        "What drops should I use for red eyes?",
        "Should I stop taking my glaucoma medication?",
        "Do I have cataracts?",
        "Is this conjunctivitis?",
        "What dosage of atropine is right?",
        "Can you diagnose my blurry vision?",
    ],
)
def test_medical_advice_requests_are_detected(text):
    assert asks_for_medical_advice(text)


@pytest.mark.parametrize(
    "text",
    [
        "Do you treat glaucoma patients?",
        "How much is a cataract consultation?",
        "What are your opening hours?",
    ],
)
def test_service_questions_are_not_medical_advice(text):
    assert not asks_for_medical_advice(text)


def test_emergency_reply_prefers_clinic_guidance_and_includes_phone():
    reply = emergency_reply("Go to Lagos Island General Hospital.", "+234 801 000 0000")
    assert "Lagos Island General Hospital" in reply and "+234 801 000 0000" in reply
    assert DEFAULT_EMERGENCY in emergency_reply(None, None)


# ----- opening hours ------------------------------------------------------------------------------
def test_weekly_summary_groups_identical_days():
    assert h.weekly_summary(HOURS) == (
        "Mon–Fri 08:00–13:00, 14:00–17:00; Sat 09:00–13:00; Sun closed"
    )


def test_holiday_exception_overrides_weekday():
    is_open, _, note = h.hours_on(HOURS, datetime(2026, 12, 25).date())  # a Friday
    assert (is_open, note) == (False, "Christmas Day")


def test_open_now_respects_branch_timezone_and_lunch_break():
    # 12:30 UTC = 13:30 in Lagos (UTC+1): lunch break on a Monday.
    lagos = h.local_now("Africa/Lagos", datetime(2026, 11, 23, 12, 30, tzinfo=UTC))
    assert h.open_now(HOURS, lagos) is False
    lagos = h.local_now("Africa/Lagos", datetime(2026, 11, 23, 13, 30, tzinfo=UTC))  # 14:30
    assert h.open_now(HOURS, lagos) is True


# ----- facts --------------------------------------------------------------------------------------
MONDAY_NOON_UTC = datetime(2026, 11, 23, 11, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What are your opening hours?", "Mon–Fri 08:00–13:00, 14:00–17:00"),
        ("Are you open on Saturday?", "open 09:00–13:00 on Saturday"),
        ("Are you open tomorrow?", "on Tuesday 24 November"),
        ("Are you open now?", "open now"),
        ("What is your phone number?", "+234 801 000 0000"),
        ("Where are you located?", "1 Admiralty Way, Lagos"),
        ("How much is a comprehensive eye examination?", "From NGN 15,000"),
        ("What services do you offer?", "Contact lens fitting"),
    ],
)
def test_fact_answers_come_from_published_data(question, expected):
    answer, _ = f.answer_from_facts(FACTS, question, MONDAY_NOON_UTC)
    assert answer is not None and expected in answer


def test_unpublished_facts_are_not_invented():
    empty = f.ClinicFacts(clinic="New Clinic")
    answer, found = f.answer_from_facts(
        empty, "What are your opening hours and phone?", MONDAY_NOON_UTC
    )
    assert "hasn't published" in answer
    assert set(found) >= {"hours", "contact"}


def test_missing_price_is_not_invented():
    answer, _ = f.answer_from_facts(FACTS, "How much is contact lens fitting?", MONDAY_NOON_UTC)
    assert "has not published a price" in answer


def test_non_fact_questions_fall_through():
    assert (
        f.answer_from_facts(FACTS, "Do you accept HMO insurance plans?", MONDAY_NOON_UTC)[0] is None
    )


# ----- chunking and query terms ------------------------------------------------------------------
def test_chunks_respect_size_and_keep_all_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(10))
    chunks = chunk_text(text)
    assert len(chunks) > 1 and all(len(c) <= MAXIMUM for c in chunks)
    assert "".join(chunks).count("Paragraph") == 10
    assert chunk_text("x" * 10_000) and all(len(c) <= MAXIMUM for c in chunk_text("x" * 10_000))


@pytest.mark.parametrize(
    ("question", "terms"),
    [
        ("Do you accept HMO plans?", ["accept", "hmo", "plans"]),
        ("x' | !(:* <-> & ;drop table", ["drop", "table"]),
        ("hi", []),
    ],
)
def test_query_terms_are_plain_words_only(question, terms):
    assert query_terms(question) == terms
