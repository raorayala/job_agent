"""Normalize and deduplicate job listings. Implemented in Milestone 5."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    return cleaned


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("gmail://"):
        return url
    parsed = urlparse(url.strip())
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def normalize_company(company: str | None) -> str:
    text = normalize_text(company)
    for suffix in (" inc", " inc.", " llc", " ltd", " corp", " corporation", " co"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text
