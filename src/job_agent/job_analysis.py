"""Re-score stored jobs against the candidate profile."""

from __future__ import annotations

from sqlalchemy.orm import Session

from job_agent.database import list_jobs
from job_agent.matcher import score_job
from job_agent.models import CandidateProfile, ParsedJob


def reanalyze_all_jobs(session: Session, profile: CandidateProfile, *, limit: int = 500) -> int:
    """Re-score all stored jobs. Returns count updated."""
    jobs = list_jobs(session, limit=limit)
    if not jobs:
        return 0

    for job in jobs:
        parsed = ParsedJob(
            title=job.title,
            company=job.company,
            location=job.location,
            source_platform=job.source_platform,
            salary=job.salary,
            employment_type=job.employment_type,
            job_url=job.job_url,
            description=job.description or "",
            gmail_message_id=job.gmail_message_id,
        )
        match = score_job(parsed, profile)
        job.match_score = match.score
        job.recommendation = match.recommendation.value
        job.match_summary = match.summary
        job.matched_skills = ", ".join(match.matched_skills)
        job.missing_skills = ", ".join(match.missing_skills)
        job.concerns = "; ".join(match.concerns)

    session.commit()
    return len(jobs)
