"""Gmail OAuth client (read-only) for fetching job-alert emails."""

from __future__ import annotations

import base64
import os.path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from sqlalchemy.orm import sessionmaker

from job_agent.application_tracker import record_parsed_job
from job_agent.config import Settings, load_candidate_profile
from job_agent.database import is_email_processed, log_activity, mark_email_processed
from job_agent.email_parser import parse_email
from job_agent.job_normalizer import check_duplicate
from job_agent.logging_config import get_logger
from job_agent.matcher import score_job

logger = get_logger(__name__)

# Read-only Gmail scope (least-privilege)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailNotConfiguredError(RuntimeError):
    """Raised when OAuth credentials file is missing."""


def get_gmail_service(
    credentials_path: Path,
    token_path: Path,
) -> Resource:
    """Authenticate and return a Gmail API discovery client resource."""
    creds: Credentials | None = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as exc:
            logger.warning("Failed to load existing token file %s: %s", token_path, exc)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.warning("Failed to refresh OAuth token: %s", exc)
                creds = None

        if not creds:
            if not credentials_path.exists():
                raise GmailNotConfiguredError(
                    f"Gmail OAuth client secrets file not found at: {credentials_path}\n"
                    "Follow setup instructions to download credentials.json from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _decode_part_data(data_str: str) -> str:
    if not data_str:
        return ""
    try:
        decoded_bytes = base64.urlsafe_b64decode(data_str)
        return decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_email_body(message: dict[str, Any]) -> str:
    """Extract plain text and HTML body contents from a Gmail API message resource."""
    payload = message.get("payload", {})
    body_texts: list[str] = []

    def _walk_parts(parts: list[dict[str, Any]]) -> None:
        for part in parts:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if mime in ("text/plain", "text/html") and data:
                text = _decode_part_data(data)
                if text:
                    body_texts.append(text)
            if "parts" in part:
                _walk_parts(part["parts"])

    if "parts" in payload:
        _walk_parts(payload["parts"])
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body_texts.append(_decode_part_data(data))

    return "\n\n".join(body_texts) if body_texts else message.get("snippet", "")


def extract_headers(message: dict[str, Any]) -> dict[str, str]:
    """Extract message headers into a lower-case key dict."""
    headers = message.get("payload", {}).get("headers", [])
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


def fetch_job_emails(
    settings: Settings,
    *,
    max_results: int = 25,
    service: Resource | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent job alert emails matching the configured search query.
    """
    if service is None:
        service = get_gmail_service(
            settings.gmail_credentials_path,
            settings.gmail_token_path,
        )

    query = settings.gmail_search_query
    label_ids = [settings.gmail_label] if settings.gmail_label else None

    logger.info("Listing Gmail messages with query='%s', label_ids=%s", query, label_ids)
    list_kwargs: dict[str, Any] = {
        "userId": "me",
        "q": query,
        "maxResults": max_results,
    }
    if label_ids:
        list_kwargs["labelIds"] = label_ids

    response = service.users().messages().list(**list_kwargs).execute()
    messages_meta = response.get("messages", [])
    logger.info("Found %d matching messages in Gmail", len(messages_meta))

    results: list[dict[str, Any]] = []
    for item in messages_meta:
        msg_id = item["id"]
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = extract_headers(msg)

        internal_date_ms = msg.get("internalDate")
        date_received: datetime | None = None
        if internal_date_ms:
            try:
                date_received = datetime.fromtimestamp(int(internal_date_ms) / 1000.0, tz=timezone.utc)
            except (ValueError, TypeError, OverflowError):
                date_received = None

        if date_received is None and "date" in headers:
            try:
                date_received = parsedate_to_datetime(headers["date"])
            except Exception:
                date_received = None

        body = extract_email_body(msg)

        results.append(
            {
                "id": msg_id,
                "thread_id": msg.get("threadId"),
                "subject": headers.get("subject", ""),
                "from": headers.get("from", ""),
                "date": headers.get("date", ""),
                "received_at": date_received,
                "body": body,
                "snippet": msg.get("snippet", ""),
            }
        )

    return results


def sync_job_emails(
    settings: Settings,
    SessionLocal: sessionmaker,
    *,
    max_results: int = 25,
    dry_run: bool = False,
    service: Resource | None = None,
) -> dict[str, Any]:
    """
    Fetch job-alert emails incrementally and persist parsed jobs to SQLite.
    """
    profile = load_candidate_profile()
    emails = fetch_job_emails(settings, max_results=max_results, service=service)

    summary: dict[str, Any] = {
        "emails_fetched": len(emails),
        "emails_processed": 0,
        "emails_skipped_already_processed": 0,
        "new_jobs": 0,
        "duplicates_skipped": 0,
        "dry_run": dry_run,
        "jobs": [],
    }

    session = SessionLocal()
    try:
        for email in emails:
            msg_id = email["id"]
            if is_email_processed(session, msg_id):
                summary["emails_skipped_already_processed"] += 1
                logger.debug("Skipping already processed message ID %s", msg_id)
                continue

            parsed_jobs = parse_email(email)
            summary["emails_processed"] += 1

            for job in parsed_jobs:
                if dry_run:
                    dupe_res = check_duplicate(session, job)
                    match = score_job(job, profile)
                    if dupe_res.is_duplicate:
                        summary["duplicates_skipped"] += 1
                    else:
                        summary["new_jobs"] += 1
                    summary["jobs"].append(
                        {
                            "title": job.title,
                            "company": job.company,
                            "platform": job.source_platform,
                            "score": match.score,
                            "url": job.job_url,
                            "is_duplicate": dupe_res.is_duplicate,
                        }
                    )
                else:
                    try:
                        record, match, dupe_res = record_parsed_job(session, job, profile)
                        if dupe_res.is_duplicate:
                            summary["duplicates_skipped"] += 1
                        else:
                            summary["new_jobs"] += 1

                        summary["jobs"].append(
                            {
                                "id": record.id,
                                "title": record.title,
                                "company": record.company,
                                "platform": record.source_platform,
                                "score": record.match_score,
                                "url": record.job_url,
                                "is_duplicate": record.is_duplicate,
                            }
                        )
                    except Exception as exc:
                        session.rollback()
                        logger.error("Failed recording job '%s' @ '%s': %s", job.title, job.company, exc)

            if not dry_run:
                mark_email_processed(
                    session,
                    msg_id,
                    subject=email.get("subject"),
                    jobs_extracted=len(parsed_jobs),
                )

        if not dry_run and summary["emails_processed"] > 0:
            log_activity(
                session,
                event_type="import",
                title=f"Gmail Sync Imported {summary['new_jobs']} New Jobs",
                description=f"Processed {summary['emails_processed']} emails ({summary['duplicates_skipped']} duplicates skipped).",
            )

    finally:
        session.close()

    return summary
