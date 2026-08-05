"""Tests for application status updates and Applied confirmation gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_agent.application_tracker import mark_applied, update_status
from job_agent.database import JobRecord, init_db
from job_agent.models import ApplicationStatus


def _seed_job(session) -> JobRecord:
    job = JobRecord(
        title="Python Developer",
        company="Globex",
        source_platform="dice",
        job_url="https://dice.com/job-detail/1",
        job_url_normalized="https://dice.com/job-detail/1",
        gmail_message_id="g-1",
        status=ApplicationStatus.REVIEWING.value,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_mark_applied_requires_confirmation(tmp_path: Path) -> None:
    SessionLocal = init_db(tmp_path / "jobs.db")
    session = SessionLocal()
    try:
        job = _seed_job(session)
        with pytest.raises(PermissionError):
            mark_applied(session, job.id, confirm=False)
        updated = mark_applied(session, job.id, confirm=True, notes="Submitted via company site")
        assert updated.status == ApplicationStatus.APPLIED.value
        assert updated.date_applied is not None
        assert updated.notes == "Submitted via company site"
    finally:
        session.close()


def test_update_status_reviewing(tmp_path: Path) -> None:
    SessionLocal = init_db(tmp_path / "jobs.db")
    session = SessionLocal()
    try:
        job = _seed_job(session)
        updated = update_status(session, job.id, ApplicationStatus.READY_TO_APPLY.value)
        assert updated.status == ApplicationStatus.READY_TO_APPLY.value
    finally:
        session.close()
