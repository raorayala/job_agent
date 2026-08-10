"""Data cleanup service for managing test data, removing duplicates, and purging database records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from job_agent.database import (
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
    Purge all records from all tables (jobs, contacts, interviews, application_answers, processed_emails).
    Resets test database to a completely clean state.
    """
    counts = {}

    r1 = session.execute(delete(JobRecord))
    counts["jobs"] = r1.rowcount or 0

    r2 = session.execute(delete(ContactRecord))
    counts["contacts"] = r2.rowcount or 0

    r3 = session.execute(delete(InterviewRecord))
    counts["interviews"] = r3.rowcount or 0

    r4 = session.execute(delete(ApplicationAnswer))
    counts["answers"] = r4.rowcount or 0

    r5 = session.execute(delete(ProcessedEmail))
    counts["processed_emails"] = r5.rowcount or 0

    session.commit()
    logger.info("Purged all database tables: %s", counts)
    return counts
