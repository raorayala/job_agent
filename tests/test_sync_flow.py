"""Integration tests for Gmail sync pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from job_agent.database import JobRecord, ProcessedEmail, init_db, list_jobs
from job_agent.gmail_client import sync_job_emails


def test_sync_job_emails_end_to_end(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "jobs.db"
    SessionLocal = init_db(db_path)

    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    mock_emails = [
        {
            "id": "msg_101",
            "thread_id": "thread_101",
            "subject": "Job Alert: Senior Python Developer at Globex Corp",
            "from": "alert@indeed.com",
            "date": "Wed, 05 Aug 2026 12:00:00 -0000",
            "received_at": datetime.now(timezone.utc),
            "body": "<html><body>Senior Python Developer at Globex Corp.<br>Location: Remote<br>Salary: $150,000 per year<br>https://www.indeed.com/viewjob?jk=globex101</body></html>",
            "snippet": "Senior Python Developer at Globex Corp",
        }
    ]

    # Mock fetch_job_emails to return mock_emails
    monkeypatch.setattr(
        "job_agent.gmail_client.fetch_job_emails",
        lambda settings, max_results=25, service=None: mock_emails,
    )

    settings = monkeypatch.context()

    from job_agent.config import get_settings

    s = get_settings(project_root=tmp_path)

    summary = sync_job_emails(s, SessionLocal, max_results=25, dry_run=False)

    assert summary["emails_fetched"] == 1
    assert summary["emails_processed"] == 1
    assert summary["new_jobs"] == 1

    session = SessionLocal()
    try:
        jobs = list_jobs(session)
        assert len(jobs) == 1
        j = jobs[0]
        assert j.title == "Senior Python Developer"
        assert j.company == "Globex Corp"
        assert j.source_platform == "indeed"
        assert j.gmail_message_id == "msg_101"
        assert j.match_score is not None
        assert j.match_score > 0
    finally:
        session.close()

    # Second sync run with same email ID should skip as already processed
    summary2 = sync_job_emails(s, SessionLocal, max_results=25, dry_run=False)
    assert summary2["emails_skipped_already_processed"] == 1
    assert summary2["new_jobs"] == 0
