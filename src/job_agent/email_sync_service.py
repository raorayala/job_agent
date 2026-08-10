"""Unified email alert sync for Gmail and Outlook/Hotmail (IMAP)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import sessionmaker

from job_agent.application_tracker import record_parsed_job
from job_agent.config import Settings, load_candidate_profile
from job_agent.database import is_email_processed, log_activity, mark_email_processed
from job_agent.email_parser import parse_email
from job_agent.gmail_client import sync_job_emails
from job_agent.imap_email_client import fetch_imap_job_emails
from job_agent.job_normalizer import check_duplicate
from job_agent.logging_config import get_logger
from job_agent.matcher import score_job

logger = get_logger(__name__)

SUPPORTED_EMAIL_PROVIDERS = ("gmail", "outlook", "hotmail")


def normalize_email_provider(provider: str | None) -> str:
    value = (provider or "gmail").strip().lower()
    if value in {"hotmail", "live", "msn", "outlook.com", "office365"}:
        return "outlook"
    if value not in {"gmail", "outlook"}:
        raise ValueError(
            f"Unsupported email provider '{provider}'. Use: gmail, outlook, or hotmail."
        )
    return value


def _ingest_parsed_emails(
    settings: Settings,
    SessionLocal: sessionmaker,
    emails: list[dict[str, Any]],
    *,
    provider_label: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    profile = load_candidate_profile()
    summary: dict[str, Any] = {
        "provider": provider_label,
        "emails_fetched": len(emails),
        "emails_processed": 0,
        "emails_skipped_already_processed": 0,
        "new_jobs": 0,
        "duplicates_skipped": 0,
        "dry_run": dry_run,
        "jobs": [],
    }

    session = SessionLocal()
    try:
        for mail in emails:
            msg_id = mail["id"]
            if is_email_processed(session, msg_id):
                summary["emails_skipped_already_processed"] += 1
                continue

            parsed_jobs = parse_email(mail)
            summary["emails_processed"] += 1

            for job in parsed_jobs:
                if dry_run:
                    dupe_res = check_duplicate(session, job)
                    match = score_job(job, profile)
                    if dupe_res.is_duplicate:
                        summary["duplicates_skipped"] += 1
                    else:
                        summary["new_jobs"] += 1
                    summary["jobs"].append(
                        {
                            "title": job.title,
                            "company": job.company,
                            "platform": job.source_platform,
                            "score": match.score,
                            "url": job.job_url,
                            "is_duplicate": dupe_res.is_duplicate,
                        }
                    )
                else:
                    try:
                        record, _match, dupe_res = record_parsed_job(session, job, profile)
                        if dupe_res.is_duplicate:
                            summary["duplicates_skipped"] += 1
                        else:
                            summary["new_jobs"] += 1
                        summary["jobs"].append(
                            {
                                "id": record.id,
                                "title": record.title,
                                "company": record.company,
                                "platform": record.source_platform,
                                "score": record.match_score,
                                "url": record.job_url,
                                "is_duplicate": record.is_duplicate,
                            }
                        )
                    except Exception as exc:
                        session.rollback()
                        logger.error("Failed recording job from %s: %s", provider_label, exc)

            if not dry_run:
                mark_email_processed(
                    session,
                    msg_id,
                    subject=mail.get("subject"),
                    jobs_extracted=len(parsed_jobs),
                )

        if not dry_run and summary["emails_processed"] > 0:
            log_activity(
                session,
                event_type="import",
                title=f"{provider_label} Sync Imported {summary['new_jobs']} New Jobs",
                description=(
                    f"Processed {summary['emails_processed']} emails "
                    f"({summary['duplicates_skipped']} duplicates skipped)."
                ),
            )
    finally:
        session.close()

    return summary


def sync_email_alerts(
    settings: Settings,
    SessionLocal: sessionmaker,
    *,
    provider: str = "gmail",
    max_results: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Sync job-alert emails from Gmail (OAuth) or Outlook/Hotmail (IMAP).
    """
    normalized = normalize_email_provider(provider)
    if normalized == "gmail":
        summary = sync_job_emails(
            settings,
            SessionLocal,
            max_results=max_results,
            dry_run=dry_run,
        )
        summary["provider"] = "gmail"
        return summary

    emails = fetch_imap_job_emails(settings, max_results=max_results)
    return _ingest_parsed_emails(
        settings,
        SessionLocal,
        emails,
        provider_label="Outlook/Hotmail",
        dry_run=dry_run,
    )


def email_provider_status(settings: Settings) -> dict[str, Any]:
    """Return configuration readiness for dashboard primary actions."""
    gmail_ready = settings.gmail_credentials_path.exists()
    outlook_ready = bool(settings.imap_username and settings.imap_password)
    return {
        "gmail": {
            "configured": gmail_ready,
            "message": "OAuth credentials present" if gmail_ready else "Add credentials.json for Gmail OAuth",
        },
        "outlook": {
            "configured": outlook_ready,
            "host": settings.imap_host or "outlook.office365.com",
            "username": settings.imap_username or "",
            "message": (
                "IMAP credentials present"
                if outlook_ready
                else "Set IMAP_USERNAME + IMAP_PASSWORD (Microsoft app password) in .env"
            ),
        },
        "providers": list(SUPPORTED_EMAIL_PROVIDERS),
    }
