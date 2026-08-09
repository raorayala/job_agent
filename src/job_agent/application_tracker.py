"""Application tracking helpers with explicit-approval safeguards."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import JobRecord, get_job, list_jobs
from job_agent.job_normalizer import (
    check_duplicate,
    normalize_company,
    normalize_text,
    normalize_title,
    normalize_url,
)
from job_agent.logging_config import get_logger
from job_agent.matcher import score_job
from job_agent.models import (
    ApplicationStatus,
    CandidateProfile,
    DuplicateCheckResult,
    MatchExplanation,
    ParsedJob,
)

logger = get_logger(__name__)

APPLIED_STATUSES = {ApplicationStatus.APPLIED.value}


def record_parsed_job(
    session: Session,
    job: ParsedJob,
    profile: CandidateProfile,
    *,
    status: str = ApplicationStatus.SAVED.value,
) -> tuple[JobRecord, MatchExplanation, DuplicateCheckResult]:
    """
    Check duplicate status, evaluate match score, and persist job listing in SQLite.
    """
    dupe_result = check_duplicate(session, job)
    match = score_job(job, profile)

    norm_url = normalize_url(job.job_url)
    norm_comp = normalize_company(job.company)
    norm_title = normalize_title(job.title)
    norm_loc = normalize_text(job.location)

    # Check if a record with this normalized URL already exists
    stmt = select(JobRecord).where(JobRecord.job_url_normalized == norm_url)
    existing = session.scalars(stmt).first()

    if existing:
        existing.match_score = match.score
        existing.recommendation = match.recommendation.value
        existing.match_summary = match.summary
        existing.matched_skills = ", ".join(match.matched_skills)
        existing.missing_skills = ", ".join(match.missing_skills)
        existing.concerns = "; ".join(match.concerns)
        existing.is_duplicate = True
        if dupe_result.reason:
            existing.duplicate_reason = dupe_result.reason

        try:
            session.commit()
            session.refresh(existing)
        except Exception as exc:
            session.rollback()
            logger.warning("Failed updating existing job #%d: %s", existing.id, exc)

        return existing, match, dupe_result

    record = JobRecord(
        title=job.title,
        company=job.company,
        location=job.location,
        source_platform=job.source_platform,
        job_url=job.job_url,
        job_url_normalized=norm_url,
        salary=job.salary,
        employment_type=job.employment_type,
        description=job.description,
        status=status,
        match_score=match.score,
        recommendation=match.recommendation.value,
        match_summary=match.summary,
        matched_skills=", ".join(match.matched_skills),
        missing_skills=", ".join(match.missing_skills),
        concerns="; ".join(match.concerns),
        gmail_message_id=job.gmail_message_id,
        is_duplicate=dupe_result.is_duplicate,
        duplicate_of_id=dupe_result.existing_job_id,
        duplicate_reason=dupe_result.reason,
        company_normalized=norm_comp,
        title_normalized=norm_title,
        location_normalized=norm_loc,
    )

    session.add(record)
    try:
        session.commit()
        session.refresh(record)
    except Exception as exc:
        session.rollback()
        logger.warning("Failed saving new job record '%s': %s", job.title, exc)
        stmt_check = select(JobRecord).where(JobRecord.job_url_normalized == norm_url)
        found = session.scalars(stmt_check).first()
        if found:
            return found, match, dupe_result
        raise

    logger.info(
        "Recorded job #%d: '%s' @ '%s' (Score: %.0f, Duplicate: %s)",
        record.id,
        record.title,
        record.company,
        match.score,
        dupe_result.is_duplicate,
    )

    return record, match, dupe_result


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
