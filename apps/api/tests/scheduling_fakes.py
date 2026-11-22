"""A scripted scheduling provider for API tests (no network)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.services.scheduling.base import (
    AccountInfo,
    Attendee,
    Booking,
    CredentialRejected,
    EventType,
    SchedulingError,
    Slot,
)

# Obviously fake, low-entropy test keys (never real credentials; not secret-scanner noise).
VALID_KEY = "cal_" + "a" * 24
REVOKED_KEY = "cal_" + "b" * 24

EVENT_TYPES = [
    EventType("101", "Comprehensive eye exam", 45, False, False),
    EventType("102", "Contact lens fitting", 30, True, False),
    EventType("103", "Internal staff meeting", 60, False, True),
]


class FakeProvider:
    name = "calcom"

    def __init__(self, world: FakeWorld, credential: str) -> None:
        self.world = world
        self.credential = credential

    def _check(self) -> None:
        if self.credential in self.world.revoked or self.credential == REVOKED_KEY:
            raise CredentialRejected("http_401")
        if self.world.fail_next:
            error, self.world.fail_next = self.world.fail_next, None
            raise error

    def account(self) -> AccountInfo:
        self._check()
        return AccountInfo(label="dr-ada", time_zone="Africa/Lagos", username="dr-ada")

    def event_types(self) -> list[EventType]:
        self._check()
        return list(self.world.event_types)

    def slots(self, event_type_id: str, start: datetime, end: datetime) -> list[Slot]:
        self._check()
        first = start.replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
        return [
            Slot(first + timedelta(hours=h), first + timedelta(hours=h, minutes=45))
            for h in (9, 10, 11)
        ]

    def book(
        self, event_type_id: str, start: datetime, attendee: Attendee, reference: str
    ) -> Booking:
        self._check()
        self.world.bookings.append((event_type_id, start, attendee, reference))
        return Booking(f"uid{len(self.world.bookings)}", "confirmed", start.astimezone(UTC), None)

    def cancel(self, provider_booking_id: str, reason: str | None) -> None:
        self._check()
        self.world.cancelled.append(provider_booking_id)

    def reschedule(self, provider_booking_id: str, start: datetime) -> Booking:
        self._check()
        return Booking(provider_booking_id + "r", "confirmed", start.astimezone(UTC), None)


class FakeWorld:
    """Shared state for all FakeProvider instances; doubles as the provider factory."""

    def __init__(self) -> None:
        self.event_types = list(EVENT_TYPES)
        self.revoked: set[str] = set()
        self.fail_next: SchedulingError | None = None
        self.bookings: list = []
        self.cancelled: list[str] = []
        self.credentials_seen: list[str] = []

    def __call__(self, provider: str, credential: str) -> FakeProvider:
        self.credentials_seen.append(credential)
        return FakeProvider(self, credential)


Factory = Callable[[str, str], FakeProvider]
