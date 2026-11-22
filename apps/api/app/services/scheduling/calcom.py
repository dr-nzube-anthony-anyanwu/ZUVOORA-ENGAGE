"""Cal.com API v2 adapter (verified against the official docs on 2026-11-22).

Versions: event types `2026-06-12`, slots `2024-09-04`, bookings `2026-02-25`; `/v2/me` takes
none. Cal.com has no idempotency key for creating bookings, so `book` sends an opaque
`metadata.engage_ref` reference that reconciliation can match, and callers must treat
timeouts/5xx on writes as `OutcomeUnknown` (never retry blindly).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.services.scheduling.base import (
    AccountInfo,
    Attendee,
    Booking,
    BookingStatus,
    CredentialRejected,
    EventType,
    OutcomeUnknown,
    ProviderRejected,
    ProviderUnavailable,
    SchedulingProvider,
    Slot,
)

V_EVENT_TYPES = "2026-06-12"
V_SLOTS = "2024-09-04"
V_BOOKINGS = "2026-02-25"
V_BOOKINGS_LIST = "2026-05-01"
_STATUS: dict[str, BookingStatus] = {
    "accepted": "confirmed",
    "pending": "pending",
    "cancelled": "cancelled",
    "rejected": "rejected",
}


_UID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _uid(value: str) -> str:
    """Booking uids are path segments: allow only a strict character set."""
    if not _UID.match(value):
        raise ProviderRejected("invalid_booking_id")
    return value


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class CalcomProvider:
    name = "calcom"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.cal.com",
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            follow_redirects=False,
        )
        self._username: str | None = None

    # ----- transport -------------------------------------------------------------------------
    def _request(
        self, method: str, path: str, version: str | None, *, write: bool = False, **kwargs: Any
    ) -> Any:
        headers = {"cal-api-version": version} if version else {}
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.ConnectError as exc:  # never reached Cal.com: nothing happened
            raise ProviderUnavailable("connect_error") from exc
        except httpx.TimeoutException as exc:
            if write:
                raise OutcomeUnknown("timeout") from exc
            raise ProviderUnavailable("timeout") from exc
        except httpx.HTTPError as exc:
            if write:
                raise OutcomeUnknown("transport") from exc
            raise ProviderUnavailable("transport") from exc
        if response.status_code in (401, 403):
            raise CredentialRejected(f"http_{response.status_code}")
        if response.status_code == 429:
            raise ProviderUnavailable("rate_limited")  # rejected before processing
        if response.status_code >= 500:
            if write:
                raise OutcomeUnknown(f"http_{response.status_code}")
            raise ProviderUnavailable(f"http_{response.status_code}")
        if response.status_code >= 400:
            raise ProviderRejected(f"http_{response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            if write:
                raise OutcomeUnknown("malformed_response") from exc
            raise ProviderUnavailable("malformed_response") from exc
        if not isinstance(body, dict) or body.get("status") != "success":
            raise ProviderRejected("provider_error")
        return body.get("data")

    # ----- operations ------------------------------------------------------------------------
    def account(self) -> AccountInfo:
        data = self._request("GET", "/v2/me", None)
        try:
            self._username = data.get("username")
            label = self._username or data["email"]
            return AccountInfo(
                label=str(label)[:200], time_zone=data.get("timeZone"), username=self._username
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise ProviderUnavailable("malformed_response") from exc

    def event_types(self) -> list[EventType]:
        if self._username is None:
            self.account()
        params = {"username": self._username} if self._username else {}
        data = self._request("GET", "/v2/event-types", V_EVENT_TYPES, params=params)
        result = []
        for item in data or []:
            try:
                policy = item.get("confirmationPolicy") or {"disabled": True}
                result.append(
                    EventType(
                        id=str(item["id"]),
                        name=str(item["title"])[:120],
                        duration_minutes=int(item["lengthInMinutes"]),
                        requires_confirmation=not policy.get("disabled", False),
                        hidden=bool(item.get("hidden", False)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # skip shapes we do not understand rather than guess
        return result

    def slots(self, event_type_id: str, start: datetime, end: datetime) -> list[Slot]:
        data = self._request(
            "GET",
            "/v2/slots",
            V_SLOTS,
            params={
                "eventTypeId": event_type_id,
                "start": _iso(start),
                "end": _iso(end),
                "timeZone": "UTC",
                "format": "range",
            },
        )
        slots: list[Slot] = []
        for entries in (data or {}).values():
            for entry in entries or []:
                if isinstance(entry, str):
                    slots.append(Slot(_parse(entry), None))
                elif isinstance(entry, dict) and "start" in entry:
                    end_value = entry.get("end")
                    slots.append(
                        Slot(_parse(entry["start"]), _parse(end_value) if end_value else None)
                    )
        return sorted(slots, key=lambda s: s.start)

    def _booking(self, data: Any) -> Booking:
        try:
            return Booking(
                provider_booking_id=str(data["uid"]),
                status=_STATUS.get(str(data.get("status", "")).lower(), "rejected"),
                start=_parse(data["start"]),
                end=_parse(data["end"]) if data.get("end") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OutcomeUnknown("malformed_response") from exc

    def book(
        self, event_type_id: str, start: datetime, attendee: Attendee, reference: str
    ) -> Booking:
        person: dict[str, Any] = {
            "name": attendee.name,
            "email": attendee.email,
            "timeZone": attendee.time_zone,
        }
        if attendee.phone:
            person["phoneNumber"] = attendee.phone
        data = self._request(
            "POST",
            "/v2/bookings",
            V_BOOKINGS,
            write=True,
            json={
                "start": _iso(start),
                "eventTypeId": int(event_type_id),
                "attendee": person,
                "metadata": {"engage_ref": reference},
            },
        )
        return self._booking(data)

    def create_webhook(self, url: str, triggers: tuple[str, ...], secret: str) -> str:
        data = self._request(
            "POST",
            "/v2/webhooks",
            None,
            json={
                "active": True,
                "subscriberUrl": url,
                "triggers": list(triggers),
                "secret": secret,
                "version": "2021-10-20",
            },
        )
        try:
            return _uid(str(data["id"]))
        except (KeyError, TypeError) as exc:
            raise ProviderUnavailable("malformed_response") from exc

    def delete_webhook(self, webhook_id: str) -> None:
        self._request("DELETE", f"/v2/webhooks/{_uid(webhook_id)}", None)

    def find_booking(
        self, reference: str, event_type_id: str, start: datetime, attendee_email: str
    ) -> Booking | None:
        """Find the booking we tried to create (metadata.engage_ref) after an unknown outcome."""
        data = self._request(
            "GET",
            "/v2/bookings",
            V_BOOKINGS_LIST,
            params={
                "attendeeEmail": attendee_email,
                "eventTypeId": event_type_id,
                "afterStart": _iso(start - timedelta(minutes=1)),
                "beforeEnd": _iso(start + timedelta(days=1)),
                "limit": 100,
            },
        )
        for item in data or []:
            if (
                isinstance(item, dict)
                and (item.get("metadata") or {}).get("engage_ref") == reference
            ):
                return self._booking(item)
        return None

    def cancel(self, provider_booking_id: str, reason: str | None) -> None:
        self._request(
            "POST",
            f"/v2/bookings/{_uid(provider_booking_id)}/cancel",
            V_BOOKINGS,
            write=True,
            json={"cancellationReason": reason or "Cancelled via the clinic"},
        )

    def reschedule(self, provider_booking_id: str, start: datetime) -> Booking:
        data = self._request(
            "POST",
            f"/v2/bookings/{_uid(provider_booking_id)}/reschedule",
            V_BOOKINGS,
            write=True,
            json={"start": _iso(start)},
        )
        return self._booking(data)

    def close(self) -> None:
        self._client.close()


class DefaultProviderFactory:
    def __init__(self, calcom_api_url: str) -> None:
        self._calcom_api_url = calcom_api_url

    def __call__(self, provider: str, credential: str) -> SchedulingProvider:
        if provider == "calcom":
            return CalcomProvider(credential, self._calcom_api_url)
        if provider == "calendly":
            from app.services.scheduling.calendly import CalendlyProvider

            return CalendlyProvider(credential)
        raise ProviderUnavailable(f"unsupported_provider:{provider}")
