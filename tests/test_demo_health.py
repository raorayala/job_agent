"""Tests for demo seed and system health."""

from __future__ import annotations

from pathlib import Path

from job_agent.config import get_settings, load_candidate_profile
from job_agent.database import init_db, list_jobs
from job_agent.demo_data import seed_demo_jobs
from job_agent.job_analysis import reanalyze_all_jobs
from job_agent.system_health import get_system_health


def test_seed_demo_and_health(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "profile:\n  target_titles: ['Python Developer']\n  required_skills: ['Python']\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "data" / "jobs.db"
    SessionLocal = init_db(db_path)
    session = SessionLocal()
    profile = load_candidate_profile()
    job_ids = seed_demo_jobs(session, profile)
    assert len(job_ids) == 3
    reanalyze_all_jobs(session, profile)
    assert len(list_jobs(session)) == 3

    settings = get_settings()
    settings.database_path = db_path
    settings.config_path = tmp_path / "config.yaml"
    health = get_system_health(settings, session)
    assert health["total_jobs"] == 3
    assert len(health["onboarding_steps"]) == 4
    session.close()
