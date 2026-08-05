"""Parse job listings from platform-specific email formats."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.config import load_yaml_config


@dataclass
class ParsedJob:
    platform: str
    title: str
    company: str = "Unknown"
    location: str | None = None
    source_url: str = ""
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)


def _clean_text(html_or_text: str) -> str:
    if "<" in html_or_text and ">" in html_or_text:
        soup = BeautifulSoup(html_or_text, "lxml")
        return soup.get_text("\n", strip=True)
    return html_or_text.strip()


def _detect_platform(sender: str, body: str) -> str:
    sender_lower = sender.lower()
    body_lower = body.lower()
    config = load_yaml_config().get("platforms", {})

    for name, meta in config.items():
        for domain in meta.get("sender_domains", []):
            if domain in sender_lower or domain in body_lower:
                return name
    return "unknown"


def _extract_links(body: str, patterns: list[str]) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'<>]+", body)
    cleaned = [u.rstrip(").,]") for u in urls]
    if not patterns:
        return cleaned
    return [u for u in cleaned if any(p in u for p in patterns)]


def _guess_title(subject: str, body: str) -> str:
    subject = subject.strip()
    for prefix in ("Job Alert:", "New jobs:", "Recommended job:"):
        if subject.lower().startswith(prefix.lower()):
            subject = subject[len(prefix) :].strip()
    if subject and len(subject) < 120:
        return subject

    lines = _clean_text(body).splitlines()
    for line in lines[:15]:
        line = line.strip()
        if 5 < len(line) < 120 and not line.lower().startswith("http"):
            return line
    return "Untitled role"


def _extract_skills(text: str) -> tuple[list[str], list[str]]:
    """Lightweight skill extraction from job description text."""
    required: list[str] = []
    preferred: list[str] = []
    lower = text.lower()

    skill_keywords = load_yaml_config().get("target_skills", [])
    for skill in skill_keywords:
        if skill.lower() in lower:
            required.append(skill)

    pref_section = re.search(
        r"(preferred|nice to have|bonus)[:\s-]+(.{0,500})",
        lower,
        re.IGNORECASE | re.DOTALL,
    )
    if pref_section:
        chunk = pref_section.group(2)
        for skill in skill_keywords:
            if skill.lower() in chunk:
                preferred.append(skill)

    return required, preferred


def parse_email(email: dict) -> ParsedJob | None:
    """Parse a Gmail message dict into a structured job listing."""
    sender = email.get("from", "")
    subject = email.get("subject", "")
    body = email.get("body") or email.get("snippet", "")
    platform = _detect_platform(sender, body)

    config = load_yaml_config().get("platforms", {})
    patterns = config.get(platform, {}).get("link_patterns", [])
    links = _extract_links(body, patterns)
    if not links:
        links = _extract_links(body, [])

    source_url = links[0] if links else f"gmail://{email.get('id', 'unknown')}"
    description = _clean_text(body)
    required, preferred = _extract_skills(description)

    title = _guess_title(subject, body)
    company = "Unknown"
    company_match = re.search(r"at\s+([A-Z][A-Za-z0-9&\.\-\s]{2,60})", subject)
    if company_match:
        company = company_match.group(1).strip()

    return ParsedJob(
        platform=platform,
        title=title,
        company=company,
        source_url=source_url,
        description=description[:8000],
        required_skills=required,
        preferred_skills=preferred,
    )


def normalize_url(url: str) -> str:
    """Normalize URLs for duplicate detection."""
    if url.startswith("gmail://"):
        return url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
