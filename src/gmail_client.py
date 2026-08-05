"""Gmail API integration for fetching job alert emails."""

from __future__ import annotations

import base64
import os.path
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import PROJECT_ROOT, get_env

# Read-only Gmail access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _token_path() -> Path:
    return PROJECT_ROOT / "token.json"


def _credentials_path() -> Path:
    return Path(get_env("GMAIL_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json")))


def get_gmail_service():
    """Authenticate and return a Gmail API service client."""
    creds: Credentials | None = None
    token_file = _token_path()

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_credentials_path()), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def list_messages(service, query: str, max_results: int = 25) -> list[dict[str, Any]]:
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return response.get("messages", [])


def get_message(service, message_id: str) -> dict[str, Any]:
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def _decode_part(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def extract_email_body(message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    if "parts" in payload:
        texts: list[str] = []
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime in ("text/plain", "text/html"):
                texts.append(_decode_part(part))
            elif "parts" in part:
                for nested in part["parts"]:
                    if nested.get("mimeType") in ("text/plain", "text/html"):
                        texts.append(_decode_part(nested))
        return "\n".join(texts)
    return _decode_part(payload)


def extract_headers(message: dict[str, Any]) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", [])
    return {h["name"].lower(): h["value"] for h in headers}


def fetch_job_emails(query: str | None = None, max_results: int = 25) -> list[dict[str, Any]]:
    """Fetch recent job alert emails matching the configured query."""
    service = get_gmail_service()
    search = query or get_env("GMAIL_SEARCH_QUERY")
    messages = list_messages(service, search, max_results=max_results)

    results: list[dict[str, Any]] = []
    for item in messages:
        msg = get_message(service, item["id"])
        headers = extract_headers(msg)
        internal_date = msg.get("internalDate")
        received_at = None
        if internal_date:
            received_at = int(internal_date)
        elif "date" in headers:
            try:
                received_at = int(parsedate_to_datetime(headers["date"]).timestamp() * 1000)
            except (TypeError, ValueError, OverflowError):
                pass

        results.append(
            {
                "id": msg["id"],
                "thread_id": msg.get("threadId"),
                "subject": headers.get("subject", ""),
                "from": headers.get("from", ""),
                "date": headers.get("date", ""),
                "received_at": received_at,
                "body": extract_email_body(msg),
                "snippet": msg.get("snippet", ""),
            }
        )
    return results
