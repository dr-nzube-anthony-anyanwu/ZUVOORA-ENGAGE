"""The common scheduling contract.

Error classes tell callers exactly what they may claim to a patient:
  * `ProviderRejected`   — the provider said no (e.g. the slot was taken). Nothing was booked.
  * `ProviderUnavailable`— the request did not reach the provider or failed before any effect.
  * `OutcomeUnknown`     — a write may or may not have happened (timeout/5xx after sending).
                           Never report success; reconcile before telling anyone anything.
  * `CredentialRejected` — the clinic's key was revoked or lacks permission.
No error carries provider response bodies (they can contain attendee details).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

BookingStatus = Literal["confirmed", "pending", "cancelled", "rejected"]


class SchedulingError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class CredentialRejected(SchedulingError):
    pass


class ProviderUnavailable(SchedulingError):
    pass


class OutcomeUnknown(SchedulingError):
    pass


class ProviderRejected(SchedulingError):
    pass


@dataclass(frozen=True)
class AccountInfo:
    label: str
    time_zone: str | None
    username: str | None = None


@dataclass(frozen=True)
class EventType:
    id: str
    name: str
    duration_minutes: int
    requires_confirmation: bool
    hidden: bool


@dataclass(frozen=True)
class Slot:
    start: datetime  # timezone-aware, UTC
    end: datetime | None


@dataclass(frozen=True)
class Attendee:
    name: str
    email: str
    time_zone: str
    phone: str | None = None


@dataclass(frozen=True)
class Booking:
    provider_booking_id: str
    status: BookingStatus
    start: datetime
    end: datetime | None


class SchedulingProvider(Protocol):
    name: str

    def account(self) -> AccountInfo: ...

    def event_types(self) -> list[EventType]: ...

    def slots(self, event_type_id: str, start: datetime, end: datetime) -> list[Slot]: ...

    def book(
        self, event_type_id: str, start: datetime, attendee: Attendee, reference: str
    ) -> Booking: ...

    def find_booking(
        self, reference: str, event_type_id: str, start: datetime, attendee_email: str
    ) -> Booking | None: ...

    def cancel(self, provider_booking_id: str, reason: str | None) -> None: ...

    def reschedule(self, provider_booking_id: str, start: datetime) -> Booking: ...


class ProviderFactory(Protocol):
    def __call__(self, provider: str, credential: str) -> SchedulingProvider: ...
