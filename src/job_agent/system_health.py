"""System health and onboarding status for dashboard display."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_agent.config import Settings, load_candidate_profile, load_yaml_config, validate_config
from job_agent.database import JobRecord, list_jobs


def _gmail_status(settings: Settings) -> dict[str, Any]:
    creds_path = settings.gmail_credentials_path
    token_path = settings.gmail_token_path
    creds_ok = creds_path.exists()
    token_ok = token_path.exists()

    if not creds_ok:
        status = "not_configured"
        message = f"Missing credentials at {creds_path.name}. Run setup checklist."
    elif not token_ok:
        status = "needs_auth"
        message = "Credentials found. Run sync-gmail once to authorize."
    else:
        status = "token_present"
        message = "OAuth token file found. Gmail sync should work."

    return {
        "status": status,
        "message": message,
        "credentials_path": str(creds_path),
        "token_path": str(token_path),
        "credentials_exists": creds_ok,
        "token_exists": token_ok,
    }


def _master_resume_status(settings: Settings) -> dict[str, Any]:
    profile = load_candidate_profile()
    path_str = profile.get_master_resume_path() or (
        str(settings.master_resume_path) if settings.master_resume_path else None
    )
    if not path_str:
        return {
            "status": "not_configured",
            "message": "Set master_resume_path in config.yaml or MASTER_RESUME_PATH in .env",
            "path": None,
            "exists": False,
        }

    path = Path(path_str)
    exists = path.exists()
    return {
        "status": "ready" if exists else "missing_file",
        "message": "Master resume found." if exists else f"File not found: {path}",
        "path": str(path),
        "exists": exists,
    }


def get_system_health(settings: Settings, session: Session) -> dict[str, Any]:
    """Return database, Gmail, resume, and profile readiness for the web dashboard."""
    profile = load_candidate_profile()
    config_warnings = validate_config(load_yaml_config(settings.config_path))

    total = session.scalar(select(func.count()).select_from(JobRecord)) or 0
    sample_jobs = list_jobs(session, limit=20)

    onboarding_steps = [
        {
            "id": "profile",
            "label": "Configure profile (titles & skills)",
            "done": bool(profile.target_titles and profile.required_skills),
        },
        {
            "id": "resume",
            "label": "Add master resume path",
            "done": _master_resume_status(settings)["exists"],
        },
        {
            "id": "jobs",
            "label": "Import or discover at least one job",
            "done": total > 0,
        },
        {
            "id": "analyze",
            "label": "Run score analyzer on jobs",
            "done": any(j.match_score is not None for j in sample_jobs),
        },
    ]

    return {
        "database_path": str(settings.database_path),
        "total_jobs": total,
        "gmail": _gmail_status(settings),
        "master_resume": _master_resume_status(settings),
        "profile_warnings": config_warnings,
        "onboarding_steps": onboarding_steps,
        "onboarding_complete": all(s["done"] for s in onboarding_steps),
    }
