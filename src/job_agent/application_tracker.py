"""Application tracking helpers with explicit-approval safeguards."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from job_agent.database import JobRecord, get_job, list_jobs
from job_agent.logging_config import get_logger
from job_agent.models import ApplicationStatus

logger = get_logger(__name__)

APPLIED_STATUSES = {ApplicationStatus.APPLIED.value}


def list_tracked_jobs(
    session: Session,
    *,
    min_score: float | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[JobRecord]:
    return list_jobs(session, min_score=min_score, status=status, limit=limit)


def update_status(
    session: Session,
    job_id: int,
    status: str,
    *,
    notes: str | None = None,
    confirm_applied: bool = False,
) -> JobRecord:
    """
    Update job status.

    Marking a job as Applied requires confirm_applied=True (explicit user approval).
    """
    job = get_job(session, job_id)
    if job is None:
        raise LookupError(f"Job id {job_id} not found")

    if status == ApplicationStatus.APPLIED.value and not confirm_applied:
        raise PermissionError(
            "Refusing to mark job as Applied without explicit confirmation "
            "(pass confirm_applied=True / --confirm)."
        )

    job.status = status
    if notes is not None:
        job.notes = notes
    if status == ApplicationStatus.APPLIED.value:
        job.date_applied = datetime.now(timezone.utc)

    session.commit()
    session.refresh(job)
    logger.info("Updated job %s status -> %s", job_id, status)
    return job


def mark_applied(
    session: Session,
    job_id: int,
    *,
    confirm: bool,
    notes: str | None = None,
    resume_path: str | None = None,
) -> JobRecord:
    job = update_status(
        session,
        job_id,
        ApplicationStatus.APPLIED.value,
        notes=notes,
        confirm_applied=confirm,
    )
    if resume_path:
        job.tailored_resume_path = resume_path
        session.commit()
        session.refresh(job)
    return job
