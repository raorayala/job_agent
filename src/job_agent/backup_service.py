"""Backup and restore utilities for local database and configuration files."""

from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from job_agent.config import Settings
from job_agent.database import JobRecord
from job_agent.logging_config import get_logger

logger = get_logger(__name__)


def create_backup(settings: Settings, destination_dir: Path | None = None) -> Path:
    """
    Create a ZIP archive backup of local SQLite database, config.yaml, and .env.
    """
    dest_dir = destination_dir or settings.project_root / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = dest_dir / f"job_agent_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        if settings.database_path.exists():
            zipf.write(settings.database_path, arcname="jobs.db")
        if settings.config_path.exists():
            zipf.write(settings.config_path, arcname="config.yaml")

        env_file = settings.project_root / ".env"
        if env_file.exists():
            zipf.write(env_file, arcname=".env")

    logger.info("Backup successfully created at: %s", zip_path)
    return zip_path


def restore_backup(backup_zip_path: Path, settings: Settings) -> None:
    """
    Restore SQLite database and config files from a ZIP archive.
    """
    if not backup_zip_path.exists():
        raise FileNotFoundError(f"Backup file not found at: {backup_zip_path}")

    with zipfile.ZipFile(backup_zip_path, "r") as zipf:
        names = zipf.namelist()
        if "jobs.db" in names:
            settings.database_path.parent.mkdir(parents=True, exist_ok=True)
            with zipf.open("jobs.db") as src, settings.database_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        if "config.yaml" in names:
            settings.config_path.parent.mkdir(parents=True, exist_ok=True)
            with zipf.open("config.yaml") as src, settings.config_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    logger.info("Restore complete from: %s", backup_zip_path)


def delete_job_record(session: Session, job_id: int) -> bool:
    """
    Delete a single job record from the database.
    Returns True if record was found and deleted, False otherwise.
    """
    job = session.get(JobRecord, job_id)
    if job is None:
        return False
    session.delete(job)
    session.commit()
    logger.info("Deleted job record id #%d (%s @ %s)", job_id, job.title, job.company)
    return True


def purge_all_data(session: Session) -> int:
    """
    Purge all records from every database table.
    Returns total deleted count.
    """
    from job_agent.cleanup_service import purge_all_database_data

    counts = purge_all_database_data(session)
    total = sum(counts.values())
    logger.info("Purged %d total database records.", total)
    return total
