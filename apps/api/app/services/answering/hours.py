"""Opening-hours answers from structured, published branch hours (deterministic)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}
_SHORT = {k: v[:3] for k, v in DAY_NAMES.items()}


def _ranges(ranges: list[dict]) -> str:
    return ", ".join(f"{r['open']}–{r['close']}" for r in ranges)


def hours_on(hours: dict, day: date) -> tuple[bool, str, str | None]:
    """(open?, ranges text, exception note) for a calendar date, honouring exceptions."""
    for exception in hours.get("exceptions", []):
        if exception["date"] == day.isoformat():
            if exception["closed"]:
                return False, "", exception.get("note")
            return True, _ranges(exception["ranges"]), exception.get("note")
    weekly = {d["day"]: d for d in hours.get("weekly", [])}
    entry = weekly.get(DAYS[day.weekday()])
    if entry is None or entry["closed"] or not entry["ranges"]:
        return False, "", None
    return True, _ranges(entry["ranges"]), None


def open_now(hours: dict, now: datetime) -> bool:
    is_open, _, _ = hours_on(hours, now.date())
    if not is_open:
        return False
    hhmm = now.strftime("%H:%M")
    exception = next(
        (e for e in hours.get("exceptions", []) if e["date"] == now.date().isoformat()), None
    )
    ranges = (
        exception["ranges"]
        if exception
        else next(d["ranges"] for d in hours["weekly"] if d["day"] == DAYS[now.weekday()])
    )
    return any(r["open"] <= hhmm < r["close"] for r in ranges)


def weekly_summary(hours: dict) -> str:
    """Group consecutive identical days: 'Mon–Fri 08:00–17:00; Sat 09:00–13:00; Sun closed'."""
    weekly = {d["day"]: d for d in hours.get("weekly", [])}
    labels = []
    for day in DAYS:
        entry = weekly.get(day)
        labels.append("closed" if not entry or entry["closed"] else _ranges(entry["ranges"]))
    groups: list[tuple[str, str, str]] = []
    for day, label in zip(DAYS, labels, strict=True):
        if groups and groups[-1][2] == label:
            groups[-1] = (groups[-1][0], day, label)
        else:
            groups.append((day, day, label))
    return "; ".join(
        f"{_SHORT[a]}{'' if a == b else '–' + _SHORT[b]} {label}" for a, b, label in groups
    )


def upcoming_exceptions(hours: dict, today: date, days: int = 14) -> list[str]:
    end = today + timedelta(days=days)
    out = []
    for exception in sorted(hours.get("exceptions", []), key=lambda e: e["date"]):
        when = date.fromisoformat(exception["date"])
        if today <= when <= end:
            what = "closed" if exception["closed"] else _ranges(exception["ranges"])
            note = f" ({exception['note']})" if exception.get("note") else ""
            out.append(f"{when.strftime('%a %d %b')}: {what}{note}")
    return out


def local_now(timezone: str, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(timezone))
    except Exception:  # noqa: BLE001 - unknown zone: fall back to UTC rather than fail
        return now.astimezone(ZoneInfo("UTC"))
