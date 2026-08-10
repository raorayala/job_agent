"""Schema FK integrity for contacts / interviews / activity_logs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from job_agent.database import (
    ActivityLogRecord,
    ContactRecord,
    InterviewRecord,
    JobRecord,
    create_db_engine,
    init_db,
)


def test_child_tables_have_fk_to_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "fk.db"
    init_db(db_path)
    engine = create_db_engine(db_path)
    with engine.connect() as conn:
        for table in ("contacts", "interviews", "activity_logs"):
            fks = conn.execute(text(f"PRAGMA foreign_key_list({table})")).fetchall()
            assert any(str(row[2]).lower() == "jobs" for row in fks), table


def test_interview_fk_rejects_orphan_and_cascades(tmp_path: Path) -> None:
    SessionLocal = init_db(tmp_path / "fk2.db")
    session = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            session.add(
                InterviewRecord(
                    job_id=999999,
                    interview_date=datetime.now(timezone.utc),
                    interview_type="Screening",
                )
            )
            session.commit()
        session.rollback()

        job = JobRecord(
            title="Eng",
            company="Acme",
            job_url="https://example.com/j1",
            job_url_normalized="https://example.com/j1",
            source_platform="indeed",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        session.add(
            InterviewRecord(
                job_id=job.id,
                interview_date=datetime.now(timezone.utc),
                interview_type="Screening",
            )
        )
        session.add(ContactRecord(job_id=job.id, name="Pat"))
        session.add(
            ActivityLogRecord(job_id=job.id, event_type="import", title="Imported")
        )
        session.commit()

        session.delete(job)
        session.commit()

        assert session.scalars(select(InterviewRecord)).first() is None
        contacts = list(session.scalars(select(ContactRecord)))
        assert len(contacts) == 1
        assert contacts[0].job_id is None
        logs = list(session.scalars(select(ActivityLogRecord)))
        assert len(logs) == 1
        assert logs[0].job_id is None
    finally:
        session.close()
