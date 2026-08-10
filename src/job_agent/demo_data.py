"""Seed demo jobs for onboarding and smoke testing."""

from __future__ import annotations

from sqlalchemy.orm import Session

from job_agent.application_tracker import record_parsed_job
from job_agent.database import log_activity
from job_agent.models import CandidateProfile, ParsedJob

DEMO_JOBS: list[dict[str, str]] = [
    {
        "title": "Senior Python Developer",
        "company": "Acme Corp",
        "url": "https://example.com/demo/acme-python",
        "description": "Python, FastAPI, PostgreSQL, AWS, Docker, REST APIs, 5+ years backend development.",
        "platform": "demo",
    },
    {
        "title": "Full Stack Engineer",
        "company": "Beta Systems",
        "url": "https://example.com/demo/beta-fullstack",
        "description": "JavaScript, TypeScript, React, Node.js, SQL, cloud, agile team collaboration.",
        "platform": "demo",
    },
    {
        "title": "Backend Software Engineer",
        "company": "Gamma Analytics",
        "url": "https://example.com/demo/gamma-backend",
        "description": "Python, Django, Redis, Kubernetes, microservices, CI/CD, system design.",
        "platform": "demo",
    },
]


def seed_demo_jobs(session: Session, profile: CandidateProfile) -> list[int]:
    """Insert demo jobs and return their database IDs."""
    job_ids: list[int] = []
    for item in DEMO_JOBS:
        parsed = ParsedJob(
            title=item["title"],
            company=item["company"],
            location="Remote",
            job_url=item["url"],
            description=item["description"],
            source_platform=item["platform"],
        )
        record, _, _ = record_parsed_job(session, parsed, profile)
        job_ids.append(record.id)

    log_activity(
        session,
        event_type="import",
        title=f"Seeded {len(job_ids)} demo jobs",
        description="Demo data for dashboard smoke testing.",
    )
    return job_ids
