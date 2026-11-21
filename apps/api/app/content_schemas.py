"""Clinic content models (Phase 2a): profile, branches with opening hours, services and FAQs.

All text is plain text. It is normalised (NFC, trimmed), control characters are rejected and
single-line fields cannot contain line breaks. Nothing is ever treated as HTML or Markdown; the
dashboard and the public assistant render it as text only.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.schemas import _TIMEZONES, StrictModel

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")


def _clean(value: str, *, multiline: bool) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if multiline:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    if _CONTROL.search(value) or (not multiline and ("\n" in value or "\t" in value)):
        raise ValueError("contains control characters or line breaks that are not allowed")
    return value


def _single(value: str) -> str:
    return _clean(value, multiline=False)


def _multi(value: str) -> str:
    return _clean(value, multiline=True)


Line = Annotated[str, AfterValidator(_single)]
Text = Annotated[str, AfterValidator(_multi)]
Phone = Annotated[str, Field(max_length=30, pattern=r"^\+?[0-9][0-9 ()\-]{4,28}$")]
HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAYS: tuple[Day, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


# ----- opening hours ---------------------------------------------------------------------------
class TimeRange(StrictModel):
    open: HHMM
    close: HHMM

    @model_validator(mode="after")
    def _ordered(self) -> TimeRange:
        if self.close <= self.open:
            raise ValueError("close must be after open (overnight ranges are not supported)")
        return self


def _check_ranges(closed: bool, ranges: list[TimeRange]) -> None:
    if closed and ranges:
        raise ValueError("a closed day cannot have opening ranges")
    if not closed and not ranges:
        raise ValueError("an open day needs at least one opening range")
    ordered = sorted(ranges, key=lambda r: r.open)
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if later.open < earlier.close:
            raise ValueError("opening ranges overlap")


class DayHours(StrictModel):
    day: Day
    closed: bool = False
    ranges: list[TimeRange] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _valid(self) -> DayHours:
        _check_ranges(self.closed, self.ranges)
        return self


class HoursException(StrictModel):
    date: date
    closed: bool = True
    ranges: list[TimeRange] = Field(default_factory=list, max_length=3)
    note: Line | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _valid(self) -> HoursException:
        _check_ranges(self.closed, self.ranges)
        return self


class OpeningHours(StrictModel):
    weekly: list[DayHours] = Field(min_length=7, max_length=7)
    exceptions: list[HoursException] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _complete(self) -> OpeningHours:
        if sorted(d.day for d in self.weekly) != sorted(DAYS):
            raise ValueError("weekly hours must list each day exactly once")
        self.weekly.sort(key=lambda d: DAYS.index(d.day))
        dates = [e.date for e in self.exceptions]
        if len(dates) != len(set(dates)):
            raise ValueError("exception dates must be unique")
        self.exceptions.sort(key=lambda e: e.date)
        return self


# ----- content types ---------------------------------------------------------------------------
class ProfileContent(StrictModel):
    about: Text | None = Field(default=None, max_length=2000)
    public_phone: Phone | None = None
    public_email: EmailStr | None = None
    website_url: AnyHttpUrl | None = None
    emergency_guidance: Text | None = Field(
        default=None,
        max_length=500,
        description="What patients should do in an eye emergency (shown instead of advice).",
    )

    @field_validator("website_url")
    @classmethod
    def _url_length(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and len(str(value)) > 300:
            raise ValueError("URL too long")
        return value


class BranchContent(StrictModel):
    name: Line = Field(min_length=2, max_length=120)
    address: Text | None = Field(default=None, max_length=500)
    city: Line | None = Field(default=None, max_length=80)
    phone: Phone | None = None
    email: EmailStr | None = None
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    opening_hours: OpeningHours | None = None
    notes: Text | None = Field(default=None, max_length=1000)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        if value not in _TIMEZONES:
            raise ValueError("unknown IANA timezone")
        return value


class ServiceContent(StrictModel):
    name: Line = Field(min_length=2, max_length=120)
    category: Line | None = Field(default=None, max_length=60)
    description: Text | None = Field(default=None, max_length=1500)
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    price_note: Line | None = Field(default=None, max_length=200)


class FaqContent(StrictModel):
    question: Line = Field(min_length=5, max_length=300)
    answer: Text = Field(min_length=1, max_length=3000)
    category: Line | None = Field(default=None, max_length=60)
    sort_order: int = Field(default=0, ge=0, le=10000)


C = TypeVar("C", ProfileContent, BranchContent, ServiceContent, FaqContent)

ContentState = Literal["draft", "published", "changes_pending", "archived"]


# ----- requests / responses -------------------------------------------------------------------
class CreateContentIn(StrictModel, Generic[C]):  # noqa: UP046 - Pydantic generic model
    content: C


class UpdateDraftIn(StrictModel, Generic[C]):  # noqa: UP046 - Pydantic generic model
    revision: int = Field(ge=1, description="Revision the editor loaded (optimistic locking).")
    content: C


class PublishIn(StrictModel):
    revision: int = Field(ge=1, description="Exact revision the reviewer approved.")


class ContentItemOut(BaseModel, Generic[C]):  # noqa: UP046 - Pydantic generic model
    id: uuid.UUID
    state: ContentState
    revision: int
    draft: C
    published: C | None
    published_revision: int | None
    published_at: datetime | None
    archived_at: datetime | None
    updated_at: datetime
