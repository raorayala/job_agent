"""Parse job listings from platform-specific email formats and email digests."""

from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from job_agent.config import load_yaml_config
from job_agent.logging_config import get_logger
from job_agent.models import ParsedJob

logger = get_logger(__name__)

# Pre-compiled regular expressions for email parsing
_RE_URL = re.compile(r"https?://[^\s\"'<>]+")
_RE_SALARY = re.compile(
    r"(\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?\s*(?:/hr|/hour|/yr|/year|a year|per year|an hour)?)",
    re.IGNORECASE,
)
_RE_PREFERRED_SECTION = re.compile(
    r"(preferred|nice to have|bonus|plus|desirable)[:\s-]+(.{0,500})",
    re.IGNORECASE | re.DOTALL,
)
_RE_COMPANY_CONTEXT = re.compile(r"at\s+([A-Z][A-Za-z0-9&\.\-\s]{2,50})")
_RE_LOCATION_CONTEXT = re.compile(r"([A-Z][A-Za-z\s]+,\s*[A-Z]{2}|Remote|Hybrid)")


@lru_cache(maxsize=256)
def _get_skill_regex(skill_clean: str) -> re.Pattern[str]:
    """Compile and cache word boundary regex pattern for skill extraction."""
    return re.compile(r"\b" + re.escape(skill_clean) + r"\b", re.IGNORECASE)


def clean_html_text(html_content: str) -> str:
    """
    Convert raw HTML string into clean plain text.

    Args:
        html_content: Raw HTML or plain text string.

    Returns:
        Stripped text without script/style tags.
    """
    if not html_content:
        return ""
    if "<" in html_content and ">" in html_content:
        soup = BeautifulSoup(html_content, "lxml")
        # Remove script and style tags
        for element in soup(["script", "style", "head"]):
            element.decompose()
        text = soup.get_text("\n", strip=True)
        return text
    return html_content.strip()


def detect_platform(sender: str, body: str, config_platforms: dict[str, Any] | None = None) -> str:
    """
    Identify job platform (ziprecruiter, indeed, glassdoor, dice, lensa) from sender or body.

    Args:
        sender: Sender email address or name.
        body: Raw or plain email body.
        config_platforms: Optional mapping of platform configs from config.yaml.

    Returns:
        Platform identifier string.
    """
    sender_lower = (sender or "").lower()
    body_lower = (body or "").lower()

    if config_platforms is None:
        try:
            config_platforms = load_yaml_config().get("platforms", {})
        except Exception:
            config_platforms = {}

    for platform_name, meta in (config_platforms or {}).items():
        sender_domains = meta.get("sender_domains", [])
        for domain in sender_domains:
            if domain.lower() in sender_lower or domain.lower() in body_lower:
                return platform_name

    # Keyword heuristics fallback
    if "ziprecruiter" in sender_lower or "ziprecruiter" in body_lower:
        return "ziprecruiter"
    if "indeed" in sender_lower or "indeed" in body_lower:
        return "indeed"
    if "glassdoor" in sender_lower or "glassdoor" in body_lower:
        return "glassdoor"
    if "dice" in sender_lower or "dice" in body_lower:
        return "dice"
    if "lensa" in sender_lower or "lensa" in body_lower:
        return "lensa"

    return "unknown"


def extract_links_with_patterns(body: str, patterns: list[str]) -> list[str]:
    """
    Find http/https links in email body matching configured platform URL patterns.

    Args:
        body: Email body text.
        patterns: List of target URL substring patterns.

    Returns:
        List of unique matching URLs.
    """
    raw_urls = _RE_URL.findall(body)
    cleaned_urls: list[str] = []
    seen: set[str] = set()

    for url in raw_urls:
        cleaned = url.rstrip(").,];:'\"")
        if cleaned not in seen:
            seen.add(cleaned)
            cleaned_urls.append(cleaned)

    if not patterns:
        return cleaned_urls

    matched_urls = [u for u in cleaned_urls if any(p.lower() in u.lower() for p in patterns)]
    return matched_urls if matched_urls else cleaned_urls


def extract_salary(text: str) -> str | None:
    """
    Extract salary or hourly pay ranges from text.

    Args:
        text: Text string to inspect.

    Returns:
        Extracted salary string or None.
    """
    match = _RE_SALARY.search(text)
    if match:
        return match.group(1).strip()
    return None


def extract_employment_type(text: str) -> str | None:
    """
    Extract employment type (full-time, part-time, contract, remote, etc.).

    Args:
        text: Text string to inspect.

    Returns:
        Comma-separated employment types string or None.
    """
    lower = text.lower()
    types: list[str] = []
    if "full-time" in lower or "full time" in lower:
        types.append("full-time")
    if "part-time" in lower or "part time" in lower:
        types.append("part-time")
    if "contract" in lower or "contractor" in lower:
        types.append("contract")
    if "remote" in lower:
        types.append("remote")
    if "hybrid" in lower:
        types.append("hybrid")

    return ", ".join(types) if types else None


def extract_skills_from_text(text: str, target_skills: list[str] | None = None) -> tuple[list[str], list[str]]:
    """
    Extract required and preferred skills mentioned in text.

    Args:
        text: Plain text job description.
        target_skills: Optional list of skill keywords to search for.

    Returns:
        Tuple of (required_skills_list, preferred_skills_list).
    """
    if target_skills is None:
        try:
            config = load_yaml_config()
            target_skills = config.get("profile", {}).get("required_skills", []) + config.get(
                "profile", {}
            ).get("preferred_skills", [])
        except Exception:
            target_skills = []

    text_lower = text.lower()
    required: list[str] = []
    preferred: list[str] = []

    # Check preferred section first if present
    pref_match = _RE_PREFERRED_SECTION.search(text_lower)
    pref_chunk = pref_match.group(2) if pref_match else ""

    seen: set[str] = set()
    for skill in target_skills:
        skill_clean = skill.strip().lower()
        if not skill_clean or skill_clean in seen:
            continue

        pattern = _get_skill_regex(skill_clean)
        if pattern.search(text_lower):
            seen.add(skill_clean)
            if pref_chunk and pattern.search(pref_chunk):
                preferred.append(skill)
            else:
                required.append(skill)

    return required, preferred


def parse_email(
    email: dict[str, Any],
    platforms_config: dict[str, Any] | None = None,
) -> list[ParsedJob]:
    """
    Extract structured job listings from a Gmail message dictionary.

    Args:
        email: Gmail message dict containing 'id', 'subject', 'from', 'body', 'received_at'.
        platforms_config: Optional platform configuration dict.

    Returns:
        List of ParsedJob objects extracted from single or multi-job email.
    """
    msg_id = email.get("id")
    subject = email.get("subject", "").strip()
    sender = email.get("from", "").strip()
    body = email.get("body") or email.get("snippet", "")
    date_received: datetime | None = email.get("received_at")

    config = load_yaml_config()
    if platforms_config is None:
        platforms_config = config.get("platforms", {})

    platform = detect_platform(sender, body, platforms_config)
    link_patterns = platforms_config.get(platform, {}).get("link_patterns", [])

    clean_text_body = clean_html_text(body)

    # Attempt to parse HTML for structured multi-job cards
    parsed_jobs: list[ParsedJob] = []

    if "<html" in body.lower() or "<a " in body.lower():
        soup = BeautifulSoup(body, "lxml")
        anchors = soup.find_all("a", href=True)
        job_anchors = []
        for a in anchors:
            href = a["href"].strip()
            text = a.get_text(" ", strip=True)
            if link_patterns:
                if any(p.lower() in href.lower() for p in link_patterns) and len(text) > 3:
                    job_anchors.append((text, href, a))
            elif "job" in href.lower() or "detail" in href.lower() or "viewjob" in href.lower():
                if len(text) > 3 and not href.startswith("mailto:"):
                    job_anchors.append((text, href, a))

        if len(job_anchors) > 1:
            # Multi-job email digest detected
            seen_urls: set[str] = set()
            for text, href, anchor_elem in job_anchors:
                clean_url = href.rstrip(").,];:'\"")
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)

                parent = anchor_elem.parent
                context_text = parent.get_text(" ", strip=True) if parent else text

                company = "Unknown"
                company_match = _RE_COMPANY_CONTEXT.search(context_text)
                if company_match:
                    company = company_match.group(1).strip()

                loc_match = _RE_LOCATION_CONTEXT.search(context_text)
                location = loc_match.group(1).strip() if loc_match else None

                salary = extract_salary(context_text)
                emp_type = extract_employment_type(context_text)
                req_skills, pref_skills = extract_skills_from_text(context_text)

                parsed_jobs.append(
                    ParsedJob(
                        title=text[:250],
                        company=company,
                        location=location,
                        source_platform=platform,
                        salary=salary,
                        employment_type=emp_type,
                        job_url=clean_url,
                        date_received=date_received,
                        description=context_text[:4000],
                        gmail_message_id=msg_id,
                        raw_subject=subject,
                        required_skills=req_skills,
                        preferred_skills=pref_skills,
                    )
                )

    if parsed_jobs:
        return parsed_jobs

    # Fallback to single job extraction from overall email
    links = extract_links_with_patterns(body, link_patterns)
    source_url = links[0] if links else f"gmail://{msg_id or 'unknown'}"

    # Deduce job title from subject line or top lines
    title = subject
    for prefix in ("Job Alert:", "New jobs:", "Recommended job:", "Job recommendation:"):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix) :].strip()

    if not title or len(title) > 150:
        lines = clean_text_body.splitlines()
        for line in lines[:15]:
            s = line.strip()
            if 5 < len(s) < 120 and not s.lower().startswith("http"):
                title = s
                break

    if not title:
        title = "Untitled Role"

    company = "Unknown"
    company_match = _RE_COMPANY_CONTEXT.search(subject)
    if not company_match:
        company_match = _RE_COMPANY_CONTEXT.search(clean_text_body[:500])
    if company_match:
        company = company_match.group(1).strip()

    # Clean "at <Company>" off title if present
    if company != "Unknown" and f" at {company}".lower() in title.lower():
        title = re.sub(re.escape(f" at {company}"), "", title, flags=re.IGNORECASE).strip()

    loc_match = _RE_LOCATION_CONTEXT.search(clean_text_body[:1000])
    location = loc_match.group(1).strip() if loc_match else None

    salary = extract_salary(clean_text_body)
    emp_type = extract_employment_type(clean_text_body)
    req_skills, pref_skills = extract_skills_from_text(clean_text_body)

    return [
        ParsedJob(
            title=title[:250],
            company=company,
            location=location,
            source_platform=platform,
            salary=salary,
            employment_type=emp_type,
            job_url=source_url,
            date_received=date_received,
            description=clean_text_body[:8000],
            gmail_message_id=msg_id,
            raw_subject=subject,
            required_skills=req_skills,
            preferred_skills=pref_skills,
        )
    ]
