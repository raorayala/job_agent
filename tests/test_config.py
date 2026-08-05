"""Tests for configuration and candidate profile loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_agent.config import (
    get_settings,
    load_candidate_profile,
    load_yaml_config,
    profile_from_mapping,
)
from job_agent.models import CandidateProfile


def test_profile_from_mapping_defaults() -> None:
    profile = profile_from_mapping({})
    assert isinstance(profile, CandidateProfile)
    assert profile.years_experience == 0
    assert profile.required_skills == []
    assert profile.salary_currency == "USD"


def test_load_yaml_config_and_profile(tmp_path: Path, monkeypatch) -> None:
    config = {
        "platforms": {"indeed": {"sender_domains": ["indeed.com"], "link_patterns": []}},
        "profile": {
            "target_titles": ["Python Developer"],
            "required_skills": ["Python", "SQL"],
            "preferred_skills": ["Docker"],
            "years_experience": 7,
            "locations": ["Remote"],
            "work_modes": ["Remote", "Hybrid"],
            "salary_min": 120000,
            "salary_max": 170000,
            "excluded_titles": ["intern"],
        },
        "match_weights": {"required_skills": 30},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    monkeypatch.setenv("CONFIG_PATH", str(path))
    monkeypatch.delenv("MASTER_RESUME_PATH", raising=False)

    loaded = load_yaml_config(path)
    assert "indeed" in loaded["platforms"]

    profile = load_candidate_profile(loaded)
    assert profile.target_titles == ["Python Developer"]
    assert profile.years_experience == 7
    assert profile.work_modes == ["remote", "hybrid"]
    assert "intern" in profile.excluded_titles


def test_get_settings_resolves_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("JOBS_APPLIED_FOLDER", str(tmp_path / "Jobs Applied"))
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    monkeypatch.setenv("GMAIL_TOKEN_PATH", "token.json")
    monkeypatch.setenv("MIN_MATCH_SCORE", "70")
    monkeypatch.setenv("LLM_PROVIDER", "none")

    settings = get_settings(project_root=tmp_path)
    assert settings.database_path == (tmp_path / "jobs.db").resolve()
    assert settings.jobs_applied_folder == tmp_path / "Jobs Applied"
    assert settings.min_match_score == 70.0
    assert settings.llm_provider == "none"
