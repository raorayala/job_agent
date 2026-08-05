"""Parse job listings from alert email HTML/text. Implemented in Milestone 4."""

from __future__ import annotations

from typing import Any

from job_agent.models import ParsedJob


def parse_email(email: dict[str, Any], platforms: dict[str, Any] | None = None) -> list[ParsedJob]:
    """Extract zero or more jobs from a single email message dict."""
    raise NotImplementedError("Email parsing lands in Milestone 4.")
