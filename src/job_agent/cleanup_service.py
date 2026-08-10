"""Data cleanup service for managing test data, removing duplicates, and purging database records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from job_agent.database import (
    ActivityLogRecord,
    ApplicationAnswer,
    ContactRecord,
    InterviewRecord,
    JobRecord,
    ProcessedEmail,
)
from job_agent.logging_config import get_logger

logger = get_logger(__name__)


def clean_duplicate_jobs(session: Session) -> int:
    """Delete all job records flagged as duplicates (is_duplicate = True)."""
    stmt = delete(JobRecord).where(JobRecord.is_duplicate.is_(True))
    result = session.execute(stmt)
    session.commit()
    count = result.rowcount or 0
    logger.info("Cleaned %d duplicate job records", count)
    return count


def clean_stale_or_excluded_jobs(session: Session) -> int:
    """Delete job records flagged as stale or status = 'Excluded'."""
    stmt = delete(JobRecord).where(
        (JobRecord.is_stale.is_(True)) | (JobRecord.status == "Excluded")
    )
    result = session.execute(stmt)
    session.commit()
    count = result.rowcount or 0
    logger.info("Cleaned %d stale/excluded job records", count)
    return count


def clean_jobs_by_status(session: Session, status: str) -> int:
    """Delete all job records matching a given status (e.g. 'Saved', 'Reviewing')."""
    stmt = delete(JobRecord).where(JobRecord.status == status)
    result = session.execute(stmt)
    session.commit()
    count = result.rowcount or 0
    logger.info("Cleaned %d job records with status '%s'", count, status)
    return count


def clean_old_jobs(session: Session, days: int = 30) -> int:
    """Delete job records created older than specified days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = delete(JobRecord).where(JobRecord.created_at < cutoff)
    result = session.execute(stmt)
    session.commit()
    count = result.rowcount or 0
    logger.info("Cleaned %d job records older than %d days", count, days)
    return count


def purge_all_database_data(session: Session) -> dict[str, int]:
    """
    Purge all records from all tables (jobs, activity_logs, contacts, interviews,
    application_answers, processed_emails). Resets the database to a clean empty state.
    """
    counts: dict[str, int] = {}

    table_models: list[tuple[str, type]] = [
        ("jobs", JobRecord),
        ("activity_logs", ActivityLogRecord),
        ("contacts", ContactRecord),
        ("interviews", InterviewRecord),
        ("application_answers", ApplicationAnswer),
        ("processed_emails", ProcessedEmail),
    ]

    for table_name, model in table_models:
        result = session.execute(delete(model))
        counts[table_name] = result.rowcount or 0

    seq_table = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
    ).fetchone()
    if seq_table:
        session.execute(text("DELETE FROM sqlite_sequence"))

    session.commit()
    logger.info("Purged all database tables: %s", counts)
    return counts
