"""Tests for SQLite schema and job listing helpers."""

from __future__ import annotations

from pathlib import Path

from job_agent.database import JobRecord, get_job, init_db, is_email_processed, list_jobs, mark_email_processed
from job_agent.models import ApplicationStatus


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    SessionLocal = init_db(db_path)
    assert db_path.exists()

    session = SessionLocal()
    try:
        job = JobRecord(
            title="Backend Engineer",
            company="Acme",
            source_platform="indeed",
            job_url="https://indeed.com/viewjob?jk=abc",
            job_url_normalized="https://indeed.com/viewjob",
            gmail_message_id="msg-1",
            status=ApplicationStatus.SAVED.value,
            match_score=82.0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.id is not None
        fetched = get_job(session, job.id)
        assert fetched is not None
        assert fetched.company == "Acme"
        assert list_jobs(session, min_score=80)[0].id == job.id
    finally:
        session.close()


def test_processed_email_tracking(tmp_path: Path) -> None:
    SessionLocal = init_db(tmp_path / "jobs.db")
    session = SessionLocal()
    try:
        assert is_email_processed(session, "abc123") is False
        mark_email_processed(session, "abc123", subject="Job Alert", jobs_extracted=2)
        assert is_email_processed(session, "abc123") is True
    finally:
        session.close()
