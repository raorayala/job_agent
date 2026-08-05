"""Tests for URL/company normalization helpers."""

from __future__ import annotations

from job_agent.job_normalizer import normalize_company, normalize_text, normalize_url


def test_normalize_url_strips_query() -> None:
    assert (
        normalize_url("https://www.indeed.com/viewjob?jk=abc&from=email")
        == "https://www.indeed.com/viewjob"
    )


def test_normalize_company() -> None:
    assert normalize_company("Acme Corp") == "acme"
    assert normalize_company("Globex LLC") == "globex"


def test_normalize_text() -> None:
    assert normalize_text("  Senior   Engineer ") == "senior engineer"
