"""Tests for database purge and cleanup."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from job_agent.cleanup_service import purge_all_database_data
from job_agent.database import ActivityLogRecord, JobRecord, get_session_factory, log_activity


def test_purge_all_database_data_includes_activity_logs(tmp_path: Path) -> None:
    db_path = tmp_path / "purge_all.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    job = JobRecord(
        title="Engineer",
        company="Acme",
        job_url="http://example.com/job",
        job_url_normalized="http://example.com/job",
    )
    session.add(job)
    session.commit()

    log_activity(
        session,
        event_type="import",
        title="Imported job",
        description="Test activity",
        job_id=job.id,
    )

    counts = purge_all_database_data(session)
    assert counts["jobs"] >= 1
    assert counts["activity_logs"] >= 1
    assert list(session.scalars(select(JobRecord)).all()) == []
    assert list(session.scalars(select(ActivityLogRecord)).all()) == []
    session.close()
