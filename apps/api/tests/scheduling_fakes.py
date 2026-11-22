"""A scripted scheduling provider for API tests (no network)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.services.scheduling.base import (
    AccountInfo,
    Attendee,
    Booking,
    BookingStatus,
    CredentialRejected,
    EventType,
    OutcomeUnknown,
    ProviderRejected,
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


@dataclass
class FakeBooking:
    uid: str
    event_type_id: str
    start: datetime
    attendee: Attendee
    reference: str
    status: BookingStatus


class FakeProvider:
    name = "calcom"

    def __init__(self, world: FakeWorld, credential: str) -> None:
        self.world = world
        self.credential = credential

    def _check(self, operation: str) -> None:
        if self.credential in self.world.revoked or self.credential == REVOKED_KEY:
            raise CredentialRejected("http_401")
        if self.world.fail_next:
            error, self.world.fail_next = self.world.fail_next, None
            raise error
        error = self.world.fail_on.pop(operation, None)
        if error:
            raise error

    def account(self) -> AccountInfo:
        self._check("account")
        return AccountInfo(label="dr-ada", time_zone="Africa/Lagos", username="dr-ada")

    def event_types(self) -> list[EventType]:
        self._check("event_types")
        return list(self.world.event_types)

    def slots(self, event_type_id: str, start: datetime, end: datetime) -> list[Slot]:
        self._check("slots")
        taken = {b.start for b in self.world.bookings if b.status != "cancelled"}
        return [
            Slot(s, s + timedelta(minutes=45))
            for s in self.world.slot_starts
            if start <= s <= end and s not in taken
        ]

    def book(
        self, event_type_id: str, start: datetime, attendee: Attendee, reference: str
    ) -> Booking:
        self._check("book")
        if any(b.start == start and b.status != "cancelled" for b in self.world.bookings):
            raise ProviderRejected("http_409")
        uid = f"uid{len(self.world.bookings) + 1}"
        booking = FakeBooking(
            uid, event_type_id, start, attendee, reference, self.world.book_status
        )
        self.world.bookings.append(booking)
        if self.world.lose_response:  # created at the provider, but the response never arrives
            self.world.lose_response = False
            raise OutcomeUnknown("timeout")
        return Booking(uid, booking.status, start.astimezone(UTC), start + timedelta(minutes=45))

    def find_booking(
        self, reference: str, event_type_id: str, start: datetime, attendee_email: str
    ) -> Booking | None:
        self._check("find_booking")
        for b in self.world.bookings:
            if b.reference == reference:
                return Booking(b.uid, b.status, b.start, b.start + timedelta(minutes=45))
        return None

    def create_webhook(self, url: str, triggers: tuple[str, ...], secret: str) -> str:
        self._check("create_webhook")
        self.world.webhooks.append((url, triggers, secret))
        return f"wh{len(self.world.webhooks)}"

    def delete_webhook(self, webhook_id: str) -> None:
        self._check("delete_webhook")
        self.world.deleted_webhooks.append(webhook_id)

    def cancel(self, provider_booking_id: str, reason: str | None) -> None:
        self._check("cancel")
        self.world.cancelled.append(provider_booking_id)
        for booking in self.world.bookings:
            if booking.uid == provider_booking_id:
                booking.status = "cancelled"

    def reschedule(self, provider_booking_id: str, start: datetime) -> Booking:
        self._check("reschedule")
        return Booking(provider_booking_id + "r", "confirmed", start.astimezone(UTC), None)


class FakeWorld:
    """Shared state for all FakeProvider instances; doubles as the provider factory."""

    def __init__(self) -> None:
        self.event_types = list(EVENT_TYPES)
        self.revoked: set[str] = set()
        self.fail_next: SchedulingError | None = None
        self.fail_on: dict[str, SchedulingError] = {}
        self.book_status: BookingStatus = "confirmed"
        self.lose_response = False
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.slot_starts = [tomorrow + timedelta(hours=h) for h in (8, 9, 10, 11)]
        self.bookings: list[FakeBooking] = []
        self.cancelled: list[str] = []
        self.webhooks: list[tuple[str, tuple[str, ...], str]] = []
        self.deleted_webhooks: list[str] = []
        self.credentials_seen: list[str] = []

    def __call__(self, provider: str, credential: str) -> FakeProvider:
        self.credentials_seen.append(credential)
        return FakeProvider(self, credential)


Factory = Callable[[str, str], FakeProvider]
