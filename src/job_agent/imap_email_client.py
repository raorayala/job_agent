"""IMAP inbox sync for Outlook / Hotmail / other IMAP providers."""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Any

from job_agent.config import Settings
from job_agent.logging_config import get_logger

logger = get_logger(__name__)

# Default Outlook / Hotmail IMAP endpoint
OUTLOOK_IMAP_HOST = "outlook.office365.com"
OUTLOOK_IMAP_PORT = 993

_JOB_SENDER_HINTS = (
    "indeed",
    "linkedin",
    "glassdoor",
    "ziprecruiter",
    "dice",
    "monster",
    "careerbuilder",
    "simplyhired",
    "wellfound",
    "lensa",
    "googlejobs",
)


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _part_to_text(part: email.message.Message) -> str:
    try:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def extract_imap_body(msg: email.message.Message) -> str:
    """Prefer HTML, fall back to plain text parts."""
    html_parts: list[str] = []
    text_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            body = _part_to_text(part)
            if not body.strip():
                continue
            if ctype == "text/html":
                html_parts.append(body)
            elif ctype == "text/plain":
                text_parts.append(body)
    else:
        body = _part_to_text(msg)
        if (msg.get_content_type() or "").lower() == "text/html":
            html_parts.append(body)
        else:
            text_parts.append(body)
    return "\n\n".join(html_parts or text_parts)


def _looks_like_job_alert(sender: str, subject: str, body: str) -> bool:
    hay = f"{sender} {subject} {body[:2000]}".lower()
    return any(hint in hay for hint in _JOB_SENDER_HINTS)


def fetch_imap_job_emails(
    settings: Settings,
    *,
    max_results: int = 25,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    folder: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent messages from an IMAP mailbox (Outlook/Hotmail compatible).

    Requires an app password or IMAP-enabled account credentials in settings/.env.
    Returns dicts compatible with ``parse_email``.
    """
    imap_host = host or settings.imap_host or OUTLOOK_IMAP_HOST
    imap_port = int(port or settings.imap_port or OUTLOOK_IMAP_PORT)
    user = username or settings.imap_username or ""
    pwd = password or settings.imap_password or ""
    mailbox = folder or settings.imap_folder or "INBOX"

    if not user or not pwd:
        raise RuntimeError(
            "Outlook/Hotmail IMAP is not configured. Set IMAP_USERNAME and IMAP_PASSWORD "
            "(use a Microsoft app password) in .env, then retry."
        )

    logger.info("Connecting to IMAP %s:%s folder=%s as %s", imap_host, imap_port, mailbox, user)
    client = imaplib.IMAP4_SSL(imap_host, imap_port)
    try:
        client.login(user, pwd)
        typ, _ = client.select(mailbox, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"Could not open IMAP folder '{mailbox}'")

        typ, data = client.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []

        ids = data[0].split()
        ids = ids[-max(max_results * 4, max_results) :]
        results: list[dict[str, Any]] = []

        for raw_id in reversed(ids):
            if len(results) >= max_results:
                break
            typ, msg_data = client.fetch(raw_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_bytes = msg_data[0][1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw_bytes)
            sender = _decode_mime_header(msg.get("From"))
            subject = _decode_mime_header(msg.get("Subject"))
            body = extract_imap_body(msg)
            if not _looks_like_job_alert(sender, subject, body):
                continue

            date_hdr = msg.get("Date")
            received_at: datetime | None = None
            if date_hdr:
                try:
                    received_at = parsedate_to_datetime(date_hdr)
                    if received_at and received_at.tzinfo is None:
                        received_at = received_at.replace(tzinfo=timezone.utc)
                except Exception:
                    received_at = None

            msg_id = (msg.get("Message-ID") or f"imap-{imap_host}-{raw_id.decode()}").strip()
            msg_id = re.sub(r"[<>\s]", "", msg_id) or f"imap-{raw_id.decode()}"

            results.append(
                {
                    "id": msg_id,
                    "thread_id": None,
                    "subject": subject,
                    "from": sender,
                    "date": date_hdr or "",
                    "received_at": received_at,
                    "body": body,
                    "snippet": body[:240],
                    "provider": "outlook",
                }
            )
        logger.info("IMAP fetched %d job-like messages from %s", len(results), imap_host)
        return results
    finally:
        try:
            client.logout()
        except Exception:
            pass
