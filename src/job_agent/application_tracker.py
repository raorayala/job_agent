"""Application tracking helpers with explicit-approval safeguards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import JobRecord, get_job, list_jobs, log_activity
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
from job_agent.notification_service import send_desktop_notification
from job_agent.resume_tailor import approve_and_finalize_resume, generate_resume_draft

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

    if match.score >= 70 and not dupe_result.is_duplicate:
        send_desktop_notification(
            f"High Match Job Discovered ({match.score:.0f}/100)",
            f"{record.title} @ {record.company}"
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
        now_utc = datetime.now(timezone.utc)
        job.date_applied = now_utc
        if job.follow_up_date is None:
            job.follow_up_date = now_utc + timedelta(days=7)

    session.commit()
    session.refresh(job)
    logger.info("Updated job %s status -> %s", job_id, status)
    return job


def update_job_details(
    session: Session,
    job_id: int,
    *,
    title: str | None = None,
    company: str | None = None,
    description: str | None = None,
    location: str | None = None,
    salary: str | None = None,
    user_notes: str | None = None,
) -> JobRecord:
    """Update editable job fields (e.g. after incomplete URL import)."""
    job = get_job(session, job_id)
    if job is None:
        raise LookupError(f"Job id {job_id} not found")

    if title is not None:
        job.title = title
    if company is not None:
        job.company = company
    if description is not None:
        job.description = description
    if location is not None:
        job.location = location
    if salary is not None:
        job.salary = salary
    if user_notes is not None:
        job.user_notes = user_notes

    session.commit()
    session.refresh(job)
    logger.info("Updated job #%d details", job_id)
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


def create_resume_draft_for_job(
    session: Session,
    job_id: int,
    profile: CandidateProfile,
    settings: Any,
    *,
    dry_run: bool = False,
) -> tuple[JobRecord, Path, Path, str]:
    """
    Generate a resume draft for a job without overwriting the master or finalized applied resume.
    If an active draft already exists, returns the existing draft paths.
    """
    from pathlib import Path
    job = get_job(session, job_id)
    if not job:
        raise LookupError(f"Job #{job_id} not found")

    parsed = ParsedJob(
        title=job.title,
        company=job.company,
        location=job.location,
        source_platform=job.source_platform,
        salary=job.salary,
        employment_type=job.employment_type,
        job_url=job.job_url,
        description=job.description or "",
    )
    match = score_job(parsed, profile)

    master_path = Path(profile.get_master_resume_path(job.title) or settings.master_resume_path or "")

    # Prevent duplicate draft generation if active draft exists
    if job.draft_resume_path and Path(job.draft_resume_path).exists():
        logger.info("Active resume draft already exists for job #%d: %s", job_id, job.draft_resume_path)
        draft_p = Path(job.draft_resume_path)
        summary_p = Path(job.draft_summary_path) if job.draft_summary_path else draft_p
        return job, draft_p, summary_p, job.diff_summary or "Active draft exists."

    draft_path, summary_path, diff_summary = generate_resume_draft(
        job=parsed,
        match=match,
        master_resume_path=master_path,
        draft_base_dir=settings.jobs_draft_folder,
        dry_run=dry_run,
    )

    if not dry_run:
        job.draft_resume_path = str(draft_path)
        job.draft_summary_path = str(summary_path)
        job.draft_created_at = datetime.now(timezone.utc)
        job.approval_status = "awaiting_review"
        job.diff_summary = diff_summary
        job.status = ApplicationStatus.DRAFT_READY.value
        session.commit()
        session.refresh(job)

        log_activity(
            session,
            event_type="draft",
            title=f"Generated Resume Draft for #{job.id}",
            description=f"Created ATS draft resume at {draft_path}. Awaiting user review.",
            job_id=job.id,
        )

    return job, draft_path, summary_path, diff_summary


def approve_resume_draft_for_job(
    session: Session,
    job_id: int,
    settings: Any,
) -> tuple[JobRecord, Path]:
    """
    Explicitly approve and promote a resume draft to the finalized jobapplied folder.
    Updates approval_status='approved' and status='Approved'.
    """
    from pathlib import Path
    job = get_job(session, job_id)
    if not job:
        raise LookupError(f"Job #{job_id} not found")

    if not job.draft_resume_path or not Path(job.draft_resume_path).exists():
        raise FileNotFoundError(f"No active draft found for job #{job_id}. Generate a draft first.")

    parsed = ParsedJob(
        title=job.title,
        company=job.company,
        job_url=job.job_url,
        description=job.description or "",
    )

    final_path = approve_and_finalize_resume(
        job=parsed,
        draft_resume_path=Path(job.draft_resume_path),
        output_base_dir=settings.jobs_applied_folder,
    )

    job.final_resume_path = str(final_path)
    job.tailored_resume_path = str(final_path)
    job.approval_status = "approved"
    job.status = ApplicationStatus.APPROVED.value
    session.commit()
    session.refresh(job)

    log_activity(
        session,
        event_type="approval",
        title=f"Approved & Finalized Resume for Job #{job.id}",
        description=f"Promoted draft to {final_path}. Master resume remains unchanged.",
        job_id=job.id,
    )

    return job, final_path


def reject_resume_draft_for_job(session: Session, job_id: int) -> JobRecord:
    """Reject a draft resume, reverting status."""
    job = get_job(session, job_id)
    if not job:
        raise LookupError(f"Job #{job_id} not found")

    job.approval_status = "rejected"
    job.status = ApplicationStatus.SAVED.value
    session.commit()
    session.refresh(job)

    log_activity(
        session,
        event_type="status_change",
        title=f"Rejected Resume Draft for Job #{job.id}",
        description="Draft rejected by user. Reverted status to Saved.",
        job_id=job.id,
    )

    return job
