"""Validation rules for clinic content (no database needed)."""

import pytest
from pydantic import ValidationError

from app.content_schemas import (
    BranchContent,
    CreateContentIn,
    FaqContent,
    OpeningHours,
    ProfileContent,
    ServiceContent,
    UpdateDraftIn,
)

WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def week(**overrides):
    days = {d: {"day": d, "ranges": [{"open": "08:00", "close": "17:00"}]} for d in WEEK}
    days["sun"] = {"day": "sun", "closed": True}
    days.update(overrides)
    return {"weekly": list(days.values())}


def test_valid_opening_hours_are_normalised_into_day_order():
    hours = OpeningHours.model_validate({"weekly": list(reversed(week()["weekly"]))})
    assert [d.day for d in hours.weekly] == WEEK
    assert hours.weekly[6].closed is True


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"mon": {"day": "mon", "ranges": [{"open": "17:00", "close": "08:00"}]}},
         "close must be after"),
        ({"mon": {"day": "mon", "ranges": [{"open": "08:00", "close": "08:00"}]}},
         "close must be after"),
        ({"mon": {"day": "mon", "ranges": [{"open": "8:00", "close": "17:00"}]}}, "pattern"),
        ({"mon": {"day": "mon", "ranges": [{"open": "08:00", "close": "24:00"}]}}, "pattern"),
        ({"mon": {"day": "mon", "closed": True, "ranges": [{"open": "08:00", "close": "12:00"}]}},
         "closed day"),
        ({"mon": {"day": "mon", "ranges": []}}, "at least one"),
        ({"mon": {"day": "mon", "ranges": [{"open": "08:00", "close": "12:00"},
                                           {"open": "11:00", "close": "15:00"}]}}, "overlap"),
        ({"mon": {"day": "tue", "ranges": [{"open": "08:00", "close": "12:00"}]}}, "exactly once"),
    ],
)
def test_invalid_opening_hours_are_rejected(override, reason):
    with pytest.raises(ValidationError, match=reason):
        OpeningHours.model_validate(week(**override))


def test_opening_hours_require_all_seven_days():
    data = week()
    data["weekly"] = data["weekly"][:6]
    with pytest.raises(ValidationError):
        OpeningHours.model_validate(data)


def test_split_day_and_holiday_exceptions():
    data = week(sat={"day": "sat", "ranges": [{"open": "13:00", "close": "16:00"},
                                             {"open": "09:00", "close": "12:00"}]})
    data["exceptions"] = [
        {"date": "2026-12-26", "closed": True, "note": "Boxing Day"},
        {"date": "2026-12-24", "closed": False, "ranges": [{"open": "09:00", "close": "13:00"}]},
    ]
    hours = OpeningHours.model_validate(data)
    assert [str(e.date) for e in hours.exceptions] == ["2026-12-24", "2026-12-26"]
    data["exceptions"].append({"date": "2026-12-26", "closed": True})
    with pytest.raises(ValidationError, match="unique"):
        OpeningHours.model_validate(data)


@pytest.mark.parametrize("bad", ["Line\nbreak", "Tab\there", "Null\x00byte", "Bidi‮override"])
def test_single_line_fields_reject_control_characters(bad):
    with pytest.raises(ValidationError):
        FaqContent(question=bad, answer="Fine")


def test_multiline_fields_allow_line_breaks_but_not_control_characters():
    faq = FaqContent(question="  Do you accept walk-ins?  ", answer="Yes.\r\nCall first.")
    assert faq.question == "Do you accept walk-ins?"
    assert faq.answer == "Yes.\nCall first."
    with pytest.raises(ValidationError):
        FaqContent(question="Valid question?", answer="Bell\x07")


def test_html_is_kept_as_inert_text_not_interpreted():
    faq = FaqContent(question="<script>alert(1)</script>?", answer="<b>bold</b>")
    assert faq.question == "<script>alert(1)</script>?"  # rendered as text by the dashboard


def test_unknown_fields_are_rejected_everywhere():
    with pytest.raises(ValidationError):
        FaqContent(question="Valid question?", answer="a", tenant_id="x")
    with pytest.raises(ValidationError):
        CreateContentIn[FaqContent].model_validate(
            {"content": {"question": "Valid question?", "answer": "a"}, "tenant_id": "x"}
        )
    with pytest.raises(ValidationError):
        UpdateDraftIn[ServiceContent].model_validate(
            {"revision": 1, "content": {"name": "Eye test"}, "published": True}
        )


def test_branch_timezone_and_contacts():
    BranchContent(name="Lekki", timezone="Africa/Lagos", phone="+234 801 234 5678",
                  email="lekki@example.com", opening_hours=week())
    with pytest.raises(ValidationError, match="timezone"):
        BranchContent(name="Lekki", timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        BranchContent(name="Lekki", phone="call us!")


def test_service_bounds():
    ServiceContent(name="Comprehensive eye exam", duration_minutes=45, price_note="From NGN 15,000")
    with pytest.raises(ValidationError):
        ServiceContent(name="Exam", duration_minutes=2)
    with pytest.raises(ValidationError):
        ServiceContent(name="X")


def test_profile_website_must_be_http_url():
    ProfileContent(website_url="https://clinic.example.com")
    for bad in ("javascript:alert(1)", "ftp://example.com", "not a url"):
        with pytest.raises(ValidationError):
            ProfileContent(website_url=bad)


def test_revision_must_be_positive():
    with pytest.raises(ValidationError):
        UpdateDraftIn[FaqContent].model_validate(
            {"revision": 0, "content": {"question": "Valid question?", "answer": "a"}}
        )
