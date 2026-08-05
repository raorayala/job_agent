"""Export tailored resumes and application packets to Desktop/Jobs Applied."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def safe_filename(text: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")
    return (cleaned[:max_len] or "item").strip("_")


def application_folder(base: Path, company: str, job_title: str) -> Path:
    """~/Desktop/Jobs Applied/<Company>/<Job Title>/"""
    path = base / safe_filename(company) / safe_filename(job_title)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resume_filename(company: str, job_title: str, when: date | None = None) -> str:
    day = (when or date.today()).isoformat()
    return f"{safe_filename(company)}_{safe_filename(job_title)}_{day}_Resume.docx"
