"""Normalize text/URLs and detect duplicate job listings."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import JobRecord
from job_agent.models import DuplicateCheckResult, ParsedJob


def normalize_text(value: str | None) -> str:
    """Lowercase and condense whitespace."""
    if not value:
        return ""
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    return cleaned


def normalize_url(url: str) -> str:
    """
    Normalize URLs by stripping tracking parameters, trailing slashes,
    while preserving identifying query parameters (like jk= for Indeed).
    """
    if not url:
        return ""
    if url.startswith("gmail://"):
        return url

    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # Keep critical parameters for platforms that use query params for job IDs
    critical_params = {"jk", "jobid", "id", "job_id", "jl"}
    query_dict = parse_qs(parsed.query)
    filtered_query = [
        f"{k}={v[0]}" for k, v in query_dict.items() if k.lower() in critical_params and v
    ]
    query_str = "&".join(sorted(filtered_query))

    normalized = urlunparse((scheme, netloc, path, "", query_str, ""))
    return normalized.rstrip("/")


def normalize_company(company: str | None) -> str:
    """Normalize company name by stripping common corporate suffixes."""
    text = normalize_text(company)
    for suffix in (
        " inc",
        " inc.",
        " llc",
        " ltd",
        " corp",
        " corporation",
        " co",
        " co.",
        " company",
        " tech",
        " technologies",
        " global",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def normalize_title(title: str | None) -> str:
    """Normalize job title by removing common level/location modifiers."""
    text = normalize_text(title)
    # Strip common noise prefix/suffixes
    text = re.sub(r"\b(sr\.?|senior|jr\.?|junior|lead|principal|staff)\b", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate ratio similarity between two strings using SequenceMatcher."""
    s1 = normalize_text(str1)
    s2 = normalize_text(str2)
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    return SequenceMatcher(None, s1, s2).ratio()


def check_duplicate(
    session: Session,
    job: ParsedJob,
    title_similarity_threshold: float = 0.88,
    content_similarity_threshold: float = 0.90,
) -> DuplicateCheckResult:
    """
    Check if a job listing is a duplicate of an existing database record.

    Check order:
    1. Exact normalized URL match
    2. Normalized company + normalized title + location match
    3. Similarity match across company and title
    """
    norm_url = normalize_url(job.job_url)

    # 1. Exact normalized URL match
    stmt = select(JobRecord).where(JobRecord.job_url_normalized == norm_url)
    existing_url = session.scalars(stmt).first()
    if existing_url:
        return DuplicateCheckResult(
            is_duplicate=True,
            reason=f"Exact URL match: {norm_url}",
            existing_job_id=existing_url.id,
            similarity=1.0,
        )

    # 2. Normalized company + title
    norm_comp = normalize_company(job.company)
    norm_title = normalize_title(job.title)

    if norm_comp and norm_comp != "unknown" and norm_title:
        stmt_comp = select(JobRecord).where(
            JobRecord.company_normalized == norm_comp,
            JobRecord.title_normalized == norm_title,
        )
        existing_comp_title = session.scalars(stmt_comp).first()
        if existing_comp_title:
            return DuplicateCheckResult(
                is_duplicate=True,
                reason=f"Company and title match: '{job.company}' - '{job.title}'",
                existing_job_id=existing_comp_title.id,
                similarity=1.0,
            )

    # 3. Similarity check against recent active jobs in the DB
    stmt_all = select(JobRecord).order_by(JobRecord.id.desc()).limit(200)
    recent_jobs = list(session.scalars(stmt_all))

    for existing in recent_jobs:
        if norm_comp and existing.company_normalized and norm_comp == existing.company_normalized:
            title_sim = calculate_similarity(job.title, existing.title)
            if title_sim >= title_similarity_threshold:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    reason=f"High title similarity ({title_sim:.0%}) at company '{job.company}' with job #{existing.id}",
                    existing_job_id=existing.id,
                    similarity=title_sim,
                )

    return DuplicateCheckResult(is_duplicate=False)
