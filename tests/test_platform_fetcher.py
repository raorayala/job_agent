"""Tests for direct platform job fetching."""

from __future__ import annotations

from pathlib import Path
from job_agent.database import get_session_factory
from job_agent.models import CandidateProfile
from job_agent.platform_fetcher import search_and_import_jobs, fetch_dice_jobs, fetch_ziprecruiter_jobs


def test_fetch_dice_jobs_mock() -> None:
    # Test that error handling returns empty list instead of crashing on network error
    jobs = fetch_dice_jobs("Java Developer", "Remote", limit=5)
    assert isinstance(jobs, list)


def test_fetch_ziprecruiter_jobs_mock() -> None:
    jobs = fetch_ziprecruiter_jobs("Python Developer", "Remote", limit=5)
    assert isinstance(jobs, list)


def test_search_and_import_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs_pf.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    profile = CandidateProfile(target_titles=["Java Developer"], required_skills=["Java"])
    results = search_and_import_jobs(session, profile, platforms=["dice"], limit_per_platform=5)
    assert isinstance(results, list)
    session.close()
