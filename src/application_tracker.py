"""Application tracking and duplicate prevention."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.job_analyzer import MatchResult
from src.job_parser import ParsedJob, normalize_url
from src.models import ApplicationRecord, JobListing


def is_duplicate(session: Session, source_url: str) -> bool:
    normalized = normalize_url(source_url)
    existing = session.query(JobListing).filter_by(source_url=normalized).first()
    return existing is not None


def record_job(
    session: Session,
    job: ParsedJob,
    match: MatchResult,
    status: str = "discovered",
) -> JobListing:
    normalized = normalize_url(job.source_url)
    listing = session.query(JobListing).filter_by(source_url=normalized).first()

    if listing is None:
        listing = JobListing(
            platform=job.platform,
            title=job.title,
            company=job.company,
            location=job.location,
            source_url=normalized,
            description=job.description,
            required_skills=", ".join(job.required_skills),
            preferred_skills=", ".join(job.preferred_skills),
            match_score=match.score,
            status=status,
        )
        session.add(listing)
    else:
        listing.match_score = match.score
        listing.status = status
        listing.title = job.title
        listing.company = job.company

    session.commit()
    session.refresh(listing)
    return listing


def mark_applied(
    session: Session,
    listing: JobListing,
    resume_path: str | None = None,
    notes: str | None = None,
) -> ApplicationRecord:
    listing.status = "applied"
    record = ApplicationRecord(
        job_listing_id=listing.id,
        applied_at=datetime.now(timezone.utc),
        resume_path=resume_path,
        notes=notes,
        status="applied",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_applications(session: Session) -> list[JobListing]:
    return session.query(JobListing).order_by(JobListing.discovered_at.desc()).all()
