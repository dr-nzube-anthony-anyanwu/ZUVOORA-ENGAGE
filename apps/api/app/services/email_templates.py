"""Email content. Plain text plus escaped HTML; staff alerts never include patient details."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.email import Email

FOOTER = "ZUVOORA Engage — sent to clinic staff. Please do not reply to this email."


def _html(
    paragraphs: list[str], link: tuple[str, str] | None = None, footer: str = FOOTER
) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    if link:
        label, url = link
        body += f'<p><a href="{escape(url, quote=True)}">{escape(label)}</a></p>'
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
        f'color:#203040">{body}<p style="color:#607080;font-size:12px">{escape(footer)}</p></div>'
    )


def _local(moment: datetime, timezone: str) -> str:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return moment.astimezone(zone).strftime("%A %d %B %Y, %H:%M ") + zone.key


def handover_alert(
    to: tuple[str, ...], clinic: str, asked_at: datetime, timezone: str, inbox_url: str
) -> Email:
    when = _local(asked_at, timezone)
    lines = [
        f"A website visitor asked {clinic} to contact them ({when}).",
        "Their contact details are in the dashboard inbox. For their privacy, they are not "
        "included in this email.",
    ]
    return Email(
        to=to,
        subject=f"New call-back request — {clinic}",
        text="\n\n".join([*lines, f"Open the inbox: {inbox_url}", FOOTER]),
        html=_html(lines, ("Open the inbox", inbox_url)),
    )


def domain_lapsed(to: tuple[str, ...], clinic: str, hostname: str, domains_url: str) -> Email:
    lines = [
        f"The chat assistant for {clinic} has stopped on {hostname}.",
        "We could no longer find the domain's verification record (a DNS TXT record) after "
        "several daily checks. If you still own the website, add the record again and press "
        "Verify on the Website domains page.",
    ]
    return Email(
        to=to,
        subject=f"Website chat stopped on {hostname}",
        text="\n\n".join([*lines, f"Website domains: {domains_url}", FOOTER]),
        html=_html(lines, ("Open Website domains", domains_url)),
    )


PATIENT_FOOTER = (
    "You receive this email because you booked through the clinic's website chat. "
    "Please do not reply to this email."
)


def patient_footer(clinic: str, clinic_email: str | None) -> str:
    if not clinic_email:
        return PATIENT_FOOTER
    return (
        "You receive this email because you booked through the clinic's website chat. "
        f"Replies to this email go to {clinic}."
    )


def _patient_html(paragraphs: list[str], footer: str = PATIENT_FOOTER) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
        f'color:#203040">{body}<p style="color:#607080;font-size:12px">'
        f"{escape(footer)}</p></div>"
    )


def _patient_email(
    to: str, subject: str, lines: list[str], clinic: str, clinic_email: str | None
) -> Email:
    """Patient emails carry the clinic's name as sender and, when the clinic published an email
    address, Reply-To it, so patients' replies reach the clinic (Phase 6, D3)."""
    footer = patient_footer(clinic, clinic_email)
    return Email(
        to=(to,),
        subject=subject,
        text="\n\n".join([*lines, footer]),
        html=_patient_html(lines, footer),
        sender_name=clinic,
        reply_to=clinic_email or None,
    )


def booking_confirmation(
    to: str,
    name: str,
    clinic: str,
    type_name: str,
    start: datetime,
    attendee_zone: str,
    pending: bool,
    clinic_phone: str | None,
    clinic_email: str | None = None,
) -> Email:
    when = _local(start, attendee_zone)
    if pending:
        subject = f"Your appointment request at {clinic}"
        first = (
            f"Hello {name}, your request for {type_name} at {clinic} on {when} has been "
            "received. The clinic will confirm it and you will receive another email."
        )
    else:
        subject = f"Your appointment at {clinic} is booked"
        first = f"Hello {name}, your {type_name} at {clinic} is booked for {when}."
    contact = f"To change or cancel, please contact {clinic}" + (
        f" on {clinic_phone}." if clinic_phone else "."
    )
    lines = [first, contact]
    return _patient_email(to, subject, lines, clinic, clinic_email)


def booking_alert(
    to: tuple[str, ...],
    clinic: str,
    type_name: str,
    start: datetime,
    clinic_zone: str,
    pending: bool,
    conversation_url: str,
) -> Email:
    when = _local(start, clinic_zone)
    state = (
        "was requested and needs your confirmation in your scheduling account"
        if pending
        else "was booked"
    )
    lines = [
        f"{type_name} on {when} {state} through the {clinic} website chat.",
        "The patient's details are in the dashboard. For their privacy, they are not included "
        "in this email.",
    ]
    return Email(
        to=to,
        subject=f"New online booking — {clinic}",
        text="\n\n".join([*lines, f"Open the conversation: {conversation_url}", FOOTER]),
        html=_html(lines, ("Open the conversation", conversation_url)),
    )


def booking_reminder(
    to: str,
    name: str,
    clinic: str,
    type_name: str,
    start: datetime,
    attendee_zone: str,
    clinic_phone: str | None,
    clinic_email: str | None = None,
) -> Email:
    when = _local(start, attendee_zone)
    lines = [
        f"Hello {name}, this is a reminder of your {type_name} at {clinic} on {when}.",
        f"If you cannot attend, please contact {clinic}"
        + (f" on {clinic_phone}." if clinic_phone else "."),
    ]
    subject = f"Reminder: your appointment at {clinic}"
    return _patient_email(to, subject, lines, clinic, clinic_email)


def booking_cancelled(
    to: str,
    name: str,
    clinic: str,
    type_name: str,
    start: datetime,
    attendee_zone: str,
    clinic_phone: str | None,
    clinic_email: str | None = None,
) -> Email:
    when = _local(start, attendee_zone)
    lines = [
        f"Hello {name}, your {type_name} at {clinic} on {when} has been cancelled.",
        f"To book another time, use the chat on the clinic's website or contact {clinic}"
        + (f" on {clinic_phone}." if clinic_phone else "."),
    ]
    subject = f"Your appointment at {clinic} was cancelled"
    return _patient_email(to, subject, lines, clinic, clinic_email)


QUOTA_EFFECT = {
    "messages": "AI answers pause until next month; the assistant keeps giving answers from your "
    "published information, emergency guidance and call-back requests.",
    "ai_usd": "AI answers pause until next month; the assistant keeps giving answers from your "
    "published information, emergency guidance and call-back requests.",
    "bookings": "New online bookings pause until next month; existing bookings, their emails and "
    "call-back requests continue.",
    "emails": "Emails keep being sent; ZUVOORA may contact you about your plan.",
}
QUOTA_LABEL = {
    "messages": "chat messages",
    "ai_usd": "AI allowance",
    "bookings": "online bookings",
    "emails": "emails",
}


def quota_alert(
    to: tuple[str, ...],
    clinic: str,
    plan: str,
    metric: str,
    threshold: int,
    period: str,
    plan_url: str,
) -> Email:
    label = QUOTA_LABEL.get(metric, metric)
    lines = [
        f"{clinic} has used {threshold}% of this month's {label} ({period}) on the {plan} plan."
    ]
    if threshold >= 100:
        lines.append(QUOTA_EFFECT.get(metric, ""))
    lines.append("Contact ZUVOORA if you need a higher limit.")
    return Email(
        to=to,
        subject=f"{clinic}: {threshold}% of monthly {label} used",
        text="\n\n".join([*lines, f"Plan & usage: {plan_url}", FOOTER]),
        html=_html(lines, ("Open Plan & usage", plan_url)),
    )


INTERNAL_FOOTER = "ZUVOORA Engage — internal notification for ZubeVision."

INTEREST_LABEL = {
    "demo": "a demo", "pilot": "the pilot programme", "pricing": "pricing",
    "accessibility": "accessibility feedback", "other": "something else",
}


def demo_request_alert(
    to: tuple[str, ...], clinic: str, place: str, interest: str, received_at: datetime,
    console_url: str,
) -> Email:
    """Internal ZubeVision notice. Contact details stay in the platform console."""
    where = f" ({place})" if place else ""
    lines = [
        f"New request from {clinic}{where} about {INTEREST_LABEL.get(interest, interest)}, "
        f"received {_local(received_at, 'Africa/Lagos')}.",
        "Contact details are in the platform console. For privacy, they are not included in "
        "this email.",
    ]
    return Email(
        to=to,
        subject=f"New ZUVOORA Engage request: {clinic}",
        text="\n\n".join([*lines, f"Platform console: {console_url}", INTERNAL_FOOTER]),
        html=_html(lines, ("Open demo requests", console_url), INTERNAL_FOOTER),
    )
