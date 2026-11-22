"""Calendly API v2 adapter (Phase 4e) — built from the official docs (2026-11-22); not yet tested
against a live account (the founder has none). Personal access token per clinic.

Differences from Cal.com handled here:
  * Event types are identified by their URI; bookings by the scheduled event's UUID.
  * Create Event Invitee (POST /invitees) returns the invitee, not the event's times.
  * No booking metadata: reconciliation matches event type + exact start + invitee email.
  * No reschedule API: patients reschedule through Calendly's own link (webhooks report it).
  * Free plans allow 5 API bookings per day; paid plans 10 per minute / 100 per day.
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
    CredentialRejected,
    EventType,
    OutcomeUnknown,
    ProviderRejected,
    ProviderUnavailable,
    Slot,
)

API = "https://api.calendly.com"
MAX_WINDOW = timedelta(days=7)  # stay well inside the documented 31-day limit per request
_UUID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_EVENT_TYPE_URI = re.compile(r"^https://api\.calendly\.com/event_types/[A-Za-z0-9_-]{1,100}$")
# Location kinds that need no value from the patient (otherwise we send none and let Calendly
# decide; a rejection is reported as "not available").
_SIMPLE_LOCATIONS = {
    "physical",
    "custom",
    "google_conference",
    "zoom_conference",
    "microsoft_teams_conference",
    "gotomeeting_conference",
    "webex_conference",
    "inbound_call",
}


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def uuid_from_uri(uri: str, collection: str) -> str:
    """'.../scheduled_events/ABC/invitees/DEF' -> 'ABC' for collection 'scheduled_events'."""
    parts = uri.rstrip("/").split("/")
    try:
        value = parts[parts.index(collection) + 1]
    except (ValueError, IndexError) as exc:
        raise ProviderRejected("bad_uri") from exc
    if not _UUID.match(value):
        raise ProviderRejected("bad_uri")
    return value


class CalendlyProvider:
    name = "calendly"

    def __init__(
        self,
        token: str,
        base_url: str = API,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            follow_redirects=False,
        )
        self._me: dict | None = None

    def _request(self, method: str, path: str, *, write: bool = False, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ProviderUnavailable("connect_error") from exc
        except httpx.TimeoutException as exc:
            raise (OutcomeUnknown if write else ProviderUnavailable)("timeout") from exc
        except httpx.HTTPError as exc:
            raise (OutcomeUnknown if write else ProviderUnavailable)("transport") from exc
        if response.status_code in (401, 403):
            raise CredentialRejected(f"http_{response.status_code}")
        if response.status_code == 429:
            raise ProviderUnavailable("rate_limited")
        if response.status_code >= 500:
            raise (OutcomeUnknown if write else ProviderUnavailable)(f"http_{response.status_code}")
        if response.status_code >= 400:
            raise ProviderRejected(f"http_{response.status_code}")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise (OutcomeUnknown if write else ProviderUnavailable)("malformed_response") from exc

    def _user(self) -> dict:
        if self._me is None:
            body = self._request("GET", "/users/me")
            try:
                self._me = dict(body["resource"])
            except (KeyError, TypeError) as exc:
                raise ProviderUnavailable("malformed_response") from exc
        return self._me

    # ----- operations ------------------------------------------------------------------------
    def account(self) -> AccountInfo:
        me = self._user()
        label = me.get("slug") or me.get("email") or me.get("name") or "Calendly account"
        return AccountInfo(
            label=str(label)[:200], time_zone=me.get("timezone"), username=me.get("slug")
        )

    def event_types(self) -> list[EventType]:
        me = self._user()
        result: list[EventType] = []
        params: dict[str, Any] = {"user": me["uri"], "active": "true", "count": 100}
        for _ in range(10):  # at most 1,000 event types
            body = self._request("GET", "/event_types", params=params)
            for item in body.get("collection") or []:
                try:
                    if not _EVENT_TYPE_URI.match(item["uri"]):
                        continue
                    result.append(
                        EventType(
                            id=item["uri"],
                            name=str(item.get("name") or "Appointment")[:120],
                            duration_minutes=int(item["duration"]),
                            requires_confirmation=False,
                            hidden=bool(item.get("secret", False)),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            token = (body.get("pagination") or {}).get("next_page_token")
            if not token:
                break
            params = {**params, "page_token": token}
        return result

    def slots(self, event_type_id: str, start: datetime, end: datetime) -> list[Slot]:
        if not _EVENT_TYPE_URI.match(event_type_id):
            raise ProviderRejected("bad_event_type")
        start = max(start, datetime.now(UTC) + timedelta(minutes=1))  # must be in the future
        slots: list[Slot] = []
        window = start
        while window < end:
            upper = min(window + MAX_WINDOW, end)
            body = self._request(
                "GET",
                "/event_type_available_times",
                params={
                    "event_type": event_type_id,
                    "start_time": _iso(window),
                    "end_time": _iso(upper),
                },
            )
            for item in body.get("collection") or []:
                if item.get("status") == "available" and item.get("start_time"):
                    slots.append(Slot(_parse(item["start_time"]), None))
            window = upper
        return sorted({s.start: s for s in slots}.values(), key=lambda s: s.start)

    def _location(self, event_type_id: str, attendee: Attendee) -> dict | None:
        uuid = uuid_from_uri(event_type_id, "event_types")
        body = self._request("GET", f"/event_types/{uuid}")
        resource = body.get("resource") or {}
        if resource.get("pooling_type") == "round_robin":
            return None
        locations = resource.get("locations") or []
        if len(locations) != 1:
            return None
        kind = locations[0].get("kind")
        if kind in _SIMPLE_LOCATIONS:
            return {"kind": kind}
        if kind == "outbound_call" and attendee.phone:
            return {"kind": kind, "location": attendee.phone}
        return None

    def book(
        self, event_type_id: str, start: datetime, attendee: Attendee, reference: str
    ) -> Booking:
        location = self._location(event_type_id, attendee)
        body: dict[str, Any] = {
            "event_type": event_type_id,
            "start_time": _iso(start),
            "invitee": {
                "name": attendee.name,
                "email": attendee.email,
                "timezone": attendee.time_zone,
            },
        }
        if location:
            body["location"] = location
        result = self._request("POST", "/invitees", write=True, json=body)
        try:
            invitee = result["resource"]
            event_uuid = uuid_from_uri(invitee["event"], "scheduled_events")
            status = "confirmed" if invitee.get("status") == "active" else "rejected"
        except (KeyError, TypeError, ProviderRejected) as exc:
            raise OutcomeUnknown("malformed_response") from exc
        return Booking(event_uuid, status, start.astimezone(UTC), None)

    def find_booking(
        self, reference: str, event_type_id: str, start: datetime, attendee_email: str
    ) -> Booking | None:
        me = self._user()
        body = self._request(
            "GET",
            "/scheduled_events",
            params={
                "user": me["uri"],
                "invitee_email": attendee_email,
                "status": "active",
                "min_start_time": _iso(start - timedelta(minutes=1)),
                "max_start_time": _iso(start + timedelta(minutes=1)),
                "count": 100,
            },
        )
        for item in body.get("collection") or []:
            try:
                if item["event_type"] == event_type_id and _parse(
                    item["start_time"]
                ) == start.astimezone(UTC):
                    return Booking(
                        uuid_from_uri(item["uri"], "scheduled_events"),
                        "confirmed",
                        _parse(item["start_time"]),
                        _parse(item["end_time"]),
                    )
            except (KeyError, TypeError, ValueError, ProviderRejected):
                continue
        return None

    def cancel(self, provider_booking_id: str, reason: str | None) -> None:
        if not _UUID.match(provider_booking_id):
            raise ProviderRejected("invalid_booking_id")
        self._request(
            "POST",
            f"/scheduled_events/{provider_booking_id}/cancellation",
            write=True,
            json={"reason": reason or "Cancelled via the clinic"},
        )

    def reschedule(self, provider_booking_id: str, start: datetime) -> Booking:
        raise ProviderRejected("reschedule_not_supported")  # Calendly: patient uses its link

    def create_webhook(self, url: str, triggers: tuple[str, ...], secret: str) -> str:
        me = self._user()
        body = self._request(
            "POST",
            "/webhook_subscriptions",
            json={
                "url": url,
                "events": ["invitee.created", "invitee.canceled"],
                "organization": me["current_organization"],
                "user": me["uri"],
                "scope": "user",
                "signing_key": secret,
            },
        )
        try:
            return uuid_from_uri(body["resource"]["uri"], "webhook_subscriptions")
        except (KeyError, TypeError) as exc:
            raise ProviderUnavailable("malformed_response") from exc

    def delete_webhook(self, webhook_id: str) -> None:
        if not _UUID.match(webhook_id):
            raise ProviderRejected("invalid_webhook_id")
        self._request("DELETE", f"/webhook_subscriptions/{webhook_id}")

    def close(self) -> None:
        self._client.close()
