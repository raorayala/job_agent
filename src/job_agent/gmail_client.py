"""Gmail OAuth client (read-only). Implemented in Milestone 3."""

from __future__ import annotations

from typing import Any

from job_agent.config import Settings


class GmailNotConfiguredError(RuntimeError):
    """Raised when OAuth credentials are missing."""


def sync_job_emails(
    settings: Settings,
    *,
    max_results: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Fetch job-alert emails incrementally.

    Milestone 1 stub — full OAuth sync arrives in a later milestone.
    """
    raise NotImplementedError(
        "Gmail sync is not implemented yet (Milestone 3). "
        f"Credentials expected at: {settings.gmail_credentials_path}"
    )
