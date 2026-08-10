"""Load environment variables, YAML config, and candidate profile."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from job_agent.models import CandidateProfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(slots=True)
class Settings:
    """Runtime settings resolved from .env + defaults."""

    project_root: Path
    master_resume_path: Path | None
    jobs_applied_folder: Path
    gmail_credentials_path: Path
    gmail_token_path: Path
    gmail_search_query: str
    gmail_label: str | None
    min_match_score: float
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    database_path: Path
    log_level: str
    config_path: Path


def load_dotenv_files(project_root: Path | None = None) -> None:
    root = project_root or PROJECT_ROOT
    load_dotenv(root / ".env")


def get_env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def require_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def load_yaml_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or Path(get_env("CONFIG_PATH", str(DEFAULT_CONFIG_PATH)) or DEFAULT_CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def _clean_str_list(items: Any) -> list[str]:
    if not items or not isinstance(items, list):
        return []
    return [str(x) for x in items if x is not None and str(x).strip()]


def profile_from_mapping(data: dict[str, Any]) -> CandidateProfile:
    """Build CandidateProfile from config.yaml `profile` section."""
    master_resumes = data.get("master_resumes") or {}
    if not isinstance(master_resumes, dict):
        master_resumes = {}

    return CandidateProfile(
        target_titles=_clean_str_list(data.get("target_titles")),
        industries=_clean_str_list(data.get("industries")),
        required_skills=_clean_str_list(data.get("required_skills")),
        preferred_skills=_clean_str_list(data.get("preferred_skills")),
        years_experience=int(data.get("years_experience") or 0),
        locations=_clean_str_list(data.get("locations")),
        work_modes=[m.lower() for m in _clean_str_list(data.get("work_modes"))],
        salary_min=data.get("salary_min"),
        salary_max=data.get("salary_max"),
        salary_currency=str(data.get("salary_currency") or "USD"),
        employment_types=[t.lower() for t in _clean_str_list(data.get("employment_types"))],
        work_authorization=data.get("work_authorization"),
        excluded_companies=_clean_str_list(data.get("excluded_companies")),
        excluded_titles=_clean_str_list(data.get("excluded_titles")),
        excluded_skills=_clean_str_list(data.get("excluded_skills")),
        excluded_locations=_clean_str_list(data.get("excluded_locations")),
        master_resume_path=data.get("master_resume_path"),
        master_resumes={str(k): str(v) for k, v in master_resumes.items() if k and v},
        cover_letter_template_path=data.get("cover_letter_template_path"),
    )


def load_candidate_profile(config: dict[str, Any] | None = None) -> CandidateProfile:
    cfg = config if config is not None else load_yaml_config()
    profile = profile_from_mapping(cfg.get("profile") or {})

    env_resume = get_env("MASTER_RESUME_PATH")
    if env_resume:
        profile.master_resume_path = env_resume
    return profile


def save_candidate_profile(profile: CandidateProfile, config_path: Path | None = None) -> None:
    """Save CandidateProfile data back into config.yaml profile mapping."""
    path = config_path or Path(get_env("CONFIG_PATH", str(DEFAULT_CONFIG_PATH)) or DEFAULT_CONFIG_PATH)
    cfg = load_yaml_config(path) if path.exists() else {}

    cfg["profile"] = {
        "target_titles": profile.target_titles,
        "industries": profile.industries,
        "required_skills": profile.required_skills,
        "preferred_skills": profile.preferred_skills,
        "years_experience": profile.years_experience,
        "locations": profile.locations,
        "work_modes": profile.work_modes,
        "salary_min": profile.salary_min,
        "salary_max": profile.salary_max,
        "salary_currency": profile.salary_currency,
        "employment_types": profile.employment_types,
        "work_authorization": profile.work_authorization,
        "excluded_companies": profile.excluded_companies,
        "excluded_titles": profile.excluded_titles,
        "excluded_skills": profile.excluded_skills,
        "excluded_locations": profile.excluded_locations,
        "master_resume_path": profile.master_resume_path,
        "master_resumes": profile.master_resumes,
        "cover_letter_template_path": profile.cover_letter_template_path,
    }
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False, allow_unicode=True)


def get_settings(project_root: Path | None = None) -> Settings:
    root = project_root or PROJECT_ROOT
    load_dotenv_files(root)

    jobs_folder = Path(
        get_env("JOBS_APPLIED_FOLDER", str(Path.home() / "Desktop" / "Jobs Applied"))
        or (Path.home() / "Desktop" / "Jobs Applied")
    )
    db_path = Path(get_env("DATABASE_PATH", str(root / "data" / "jobs.db")) or (root / "data" / "jobs.db"))
    if not db_path.is_absolute():
        db_path = (root / db_path).resolve()

    creds = Path(get_env("GMAIL_CREDENTIALS_PATH", str(root / "credentials.json")) or (root / "credentials.json"))
    if not creds.is_absolute():
        creds = (root / creds).resolve()

    token = Path(get_env("GMAIL_TOKEN_PATH", str(root / "token.json")) or (root / "token.json"))
    if not token.is_absolute():
        token = (root / token).resolve()

    master = get_env("MASTER_RESUME_PATH")
    label = get_env("GMAIL_LABEL") or None
    if label == "":
        label = None

    return Settings(
        project_root=root,
        master_resume_path=Path(master) if master else None,
        jobs_applied_folder=jobs_folder,
        gmail_credentials_path=creds,
        gmail_token_path=token,
        gmail_search_query=get_env(
            "GMAIL_SEARCH_QUERY",
            "from:(ziprecruiter.com OR indeed.com OR glassdoor.com OR dice.com OR lensa.com) newer_than:14d",
        )
        or "",
        gmail_label=label,
        min_match_score=float(get_env("MIN_MATCH_SCORE", "65") or "65"),
        llm_provider=(get_env("LLM_PROVIDER", "none") or "none").lower(),
        ollama_base_url=get_env("OLLAMA_BASE_URL", "http://localhost:11434") or "http://localhost:11434",
        ollama_model=get_env("OLLAMA_MODEL", "llama3.2") or "llama3.2",
        database_path=db_path,
        log_level=(get_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        config_path=Path(get_env("CONFIG_PATH", str(DEFAULT_CONFIG_PATH)) or DEFAULT_CONFIG_PATH),
    )


def ensure_runtime_dirs(settings: Settings) -> None:
    """Create local data and Jobs Applied folders (no network side effects)."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.jobs_applied_folder.mkdir(parents=True, exist_ok=True)
