"""Email content. Plain text plus escaped HTML; staff alerts never include patient details."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.email import Email

FOOTER = "ZUVOORA Engage — sent to clinic staff. Please do not reply to this email."


def _html(paragraphs: list[str], link: tuple[str, str] | None = None) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    if link:
        label, url = link
        body += f'<p><a href="{escape(url, quote=True)}">{escape(label)}</a></p>'
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
        f'color:#203040">{body}<p style="color:#607080;font-size:12px">{escape(FOOTER)}</p></div>'
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


def _patient_html(paragraphs: list[str]) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
        f'color:#203040">{body}<p style="color:#607080;font-size:12px">'
        f"{escape(PATIENT_FOOTER)}</p></div>"
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
    return Email(
        to=(to,),
        subject=subject,
        text="\n\n".join([*lines, PATIENT_FOOTER]),
        html=_patient_html(lines),
    )


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
