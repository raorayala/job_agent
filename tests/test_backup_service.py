"""Tests for backup, restore, delete, and purge functions."""

from __future__ import annotations

from pathlib import Path
from job_agent.backup_service import create_backup, delete_job_record, purge_all_data, restore_backup
from job_agent.database import JobRecord, get_session_factory


def test_backup_and_restore(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "jobs.db"
    config_path = tmp_path / "config.yaml"
    config_path.write_text("profile:\n  target_titles: ['Test']", encoding="utf-8")

    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()
    job = JobRecord(title="Backend Dev", company="Acme", job_url="http://test.com", job_url_normalized="http://test.com")
    session.add(job)
    session.commit()
    job_id = job.id
    session.close()

    class DummySettings:
        pass

    settings = DummySettings()
    settings.project_root = tmp_path
    settings.database_path = db_path
    settings.config_path = config_path
    zip_path = create_backup(settings, destination_dir=tmp_path / "backups")
    assert zip_path.exists()

    # Delete record
    session = SessionLocal()
    delete_job_record(session, job_id)
    assert session.get(JobRecord, job_id) is None
    session.close()

    # Restore from backup
    restore_backup(zip_path, settings)
    session = SessionLocal()
    restored_job = session.get(JobRecord, job_id)
    assert restored_job is not None
    assert restored_job.title == "Backend Dev"
    session.close()


def test_purge_data(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs_purge.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    session.add(JobRecord(title="Dev", company="Corp", job_url="http://p.com", job_url_normalized="http://p.com"))
    session.commit()

    count = purge_all_data(session)
    assert count >= 1
    session.close()
