"""Normalize text, URLs, company/job titles, and detect duplicate job listings."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Sequence
from urllib.parse import parse_qs, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import JobRecord
from job_agent.models import DuplicateCheckResult, ParsedJob

# Pre-compiled regular expressions for performance optimization
_RE_WHITESPACE = re.compile(r"\s+")
_RE_TITLE_NOISE = re.compile(
    r"\b(sr\.?|senior|jr\.?|junior|lead|principal|staff)\b", re.IGNORECASE
)
_COMPANY_SUFFIXES: tuple[str, ...] = (
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
)


def normalize_text(value: str | None) -> str:
    """
    Lowercase and condense whitespace in input text.

    Args:
        value: Input string to normalize.

    Returns:
        Cleaned, lowercased string with collapsed spaces.
    """
    if not value:
        return ""
    return _RE_WHITESPACE.sub(" ", value.strip().lower())


def normalize_url(url: str) -> str:
    """
    Normalize URLs by stripping tracking parameters and trailing slashes,
    while preserving identifying query parameters (like jk= for Indeed).

    Args:
        url: Raw web URL or internal URI string.

    Returns:
        Canonicalized URL string suitable for exact duplication checks.
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
    """
    Normalize company name by stripping common corporate suffixes.

    Args:
        company: Raw company name string.

    Returns:
        Cleaned company name string.
    """
    text = normalize_text(company)
    for suffix in _COMPANY_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def normalize_title(title: str | None) -> str:
    """
    Normalize job title by removing common level/seniority modifiers.

    Args:
        title: Raw job title string.

    Returns:
        Cleaned title string.
    """
    text = normalize_text(title)
    text = _RE_TITLE_NOISE.sub("", text).strip()
    return _RE_WHITESPACE.sub(" ", text)


@lru_cache(maxsize=2048)
def calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate ratio similarity between two strings using SequenceMatcher with caching.

    Args:
        str1: First string.
        str2: Second string.

    Returns:
        Similarity score from 0.0 to 1.0.
    """
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
    2. Normalized company + normalized title match
    3. Fuzzy similarity check across company, title, and description

    Args:
        session: Active SQLAlchemy database session.
        job: ParsedJob object to inspect.
        title_similarity_threshold: Threshold for title fuzzy match.
        content_similarity_threshold: Threshold for description fuzzy match.

    Returns:
        DuplicateCheckResult indicating whether a duplicate exists and why.
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

    # 3. Fuzzy similarity check across company, title, and location
    stmt_all = select(JobRecord).order_by(JobRecord.id.desc()).limit(300)
    recent_jobs: Sequence[JobRecord] = list(session.scalars(stmt_all))

    for existing in recent_jobs:
        comp_sim = calculate_similarity(job.company, existing.company) if job.company and existing.company else 0.0
        title_sim = calculate_similarity(job.title, existing.title)

        # Same or near-identical company + high title similarity
        if (norm_comp and existing.company_normalized and norm_comp == existing.company_normalized) or comp_sim >= 0.85:
            if title_sim >= title_similarity_threshold:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    reason=f"Near-duplicate match ({title_sim:.0%} title similarity) at '{existing.company}' with job #{existing.id}",
                    existing_job_id=existing.id,
                    similarity=title_sim,
                )

        # High content/description similarity if descriptions present
        if job.description and existing.description and len(job.description) > 100 and len(existing.description) > 100:
            desc_sim = calculate_similarity(job.description[:500], existing.description[:500])
            if desc_sim >= content_similarity_threshold and (title_sim >= 0.70 or comp_sim >= 0.70):
                return DuplicateCheckResult(
                    is_duplicate=True,
                    reason=f"High content similarity ({desc_sim:.0%}) with job #{existing.id}",
                    existing_job_id=existing.id,
                    similarity=desc_sim,
                )

    return DuplicateCheckResult(is_duplicate=False)
