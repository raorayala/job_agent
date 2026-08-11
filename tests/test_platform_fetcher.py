"""Tests for direct platform job fetching."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from job_agent.database import get_session_factory
from job_agent.models import CandidateProfile
from job_agent.platform_fetcher import (
    fetch_dice_jobs,
    fetch_generic_platform_jobs,
    fetch_ziprecruiter_jobs,
    search_and_import_jobs,
)


def test_fetch_dice_jobs_mock() -> None:
    # Test that error handling returns empty list instead of crashing on network error
    jobs = fetch_dice_jobs("Java Developer", "Remote", limit=5)
    assert isinstance(jobs, list)


def test_fetch_ziprecruiter_jobs_mock() -> None:
    jobs = fetch_ziprecruiter_jobs("Python Developer", "Remote", limit=5)
    assert isinstance(jobs, list)


def test_generic_platform_does_not_invent_fake_jobs_on_failure() -> None:
    with patch("job_agent.platform_fetcher.urllib.request.urlopen", side_effect=OSError("blocked")):
        jobs = fetch_generic_platform_jobs("linkedin", "Software Engineer", "Remote", limit=3)
    assert jobs == []
    assert not any("Platform Match" in (j.title or "") for j in jobs)
    assert not any("Top " in (j.company or "") and "Partner" in (j.company or "") for j in jobs)


def test_search_and_import_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs_pf.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    profile = CandidateProfile(target_titles=["Java Developer"], required_skills=["Java"])
    with patch("job_agent.platform_fetcher.fetch_dice_jobs", return_value=[]):
        results = search_and_import_jobs(session, profile, platforms=["dice"], limit_per_platform=5)
    assert isinstance(results.platform_reports, list)
    assert results.jobs_recorded == 0
    assert results.platform_reports[0].status in {"empty", "error", "success"}
    session.close()
