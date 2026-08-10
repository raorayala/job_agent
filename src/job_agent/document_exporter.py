"""Export tailored resumes and application packets to Desktop/Jobs Applied."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def safe_filename(text: str, max_len: int = 80) -> str:
    """
    Sanitize text into a clean filesystem-friendly string.

    Args:
        text: Raw text string to sanitize.
        max_len: Maximum length limit for sanitized string.

    Returns:
        Sanitized filename component.
    """
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")
    return (cleaned[:max_len] or "item").strip("_")


def application_folder(base: Path, company: str, job_title: str) -> Path:
    """
    Construct and ensure directory exists for a job application packet:
    ~/Desktop/Jobs Applied/<Company>/<Job Title>/

    Args:
        base: Base folder path (e.g. Jobs Applied).
        company: Company name string.
        job_title: Job title string.

    Returns:
        Path object pointing to created application directory.
    """
    path = base / safe_filename(company) / safe_filename(job_title)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resume_filename(company: str, job_title: str, when: date | None = None) -> str:
    """
    Construct standardized resume filename: <Company>_<JobTitle>_<YYYY-MM-DD>_Resume.docx

    Args:
        company: Company name string.
        job_title: Job title string.
        when: Optional date object (defaults to today).

    Returns:
        Formatted filename string.
    """
    day = (when or date.today()).isoformat()
    return f"{safe_filename(company)}_{safe_filename(job_title)}_{day}_Resume.docx"
