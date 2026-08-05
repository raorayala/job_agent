"""SQLite persistence for jobs and application history."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from job_agent.models import ApplicationStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    """Primary 'Jobs Applied' / discovered-jobs table."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("job_url_normalized", name="uq_job_url_normalized"),
        UniqueConstraint("gmail_message_id", name="uq_gmail_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="Unknown")
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_platform: Mapped[str] = mapped_column(String(50), default="unknown")
    job_url: Mapped[str] = mapped_column(String(1000), default="")
    job_url_normalized: Mapped[str] = mapped_column(String(1000), default="")
    salary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_discovered: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    date_applied: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default=ApplicationStatus.SAVED.value)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    concerns: Mapped[str | None] = mapped_column(Text, nullable=True)

    tailored_resume_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    gmail_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    company_normalized: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title_normalized: Mapped[str | None] = mapped_column(String(300), nullable=True)
    location_normalized: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ProcessedEmail(Base):
    """Tracks Gmail message IDs already processed for incremental sync."""

    __tablename__ = "processed_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gmail_message_id: Mapped[str] = mapped_column(String(200), unique=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    jobs_extracted: Mapped[int] = mapped_column(Integer, default=0)


def _sqlite_enable_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_path: str | Path) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False, future=True)
    event.listen(engine, "connect", _sqlite_enable_foreign_keys)
    return engine


def init_db(db_path: str | Path) -> sessionmaker[Session]:
    """Create tables and return a session factory."""
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session_factory(db_path: str | Path) -> sessionmaker[Session]:
    return init_db(db_path)


def list_jobs(
    session: Session,
    *,
    min_score: float | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[JobRecord]:
    stmt = select(JobRecord).order_by(JobRecord.date_discovered.desc()).limit(limit)
    if min_score is not None:
        stmt = stmt.where(JobRecord.match_score >= min_score)
    if status is not None:
        stmt = stmt.where(JobRecord.status == status)
    return list(session.scalars(stmt))


def get_job(session: Session, job_id: int) -> JobRecord | None:
    return session.get(JobRecord, job_id)


def is_email_processed(session: Session, gmail_message_id: str) -> bool:
    stmt = select(ProcessedEmail).where(ProcessedEmail.gmail_message_id == gmail_message_id)
    return session.scalars(stmt).first() is not None


def mark_email_processed(
    session: Session,
    gmail_message_id: str,
    *,
    subject: str | None = None,
    jobs_extracted: int = 0,
) -> ProcessedEmail:
    row = ProcessedEmail(
        gmail_message_id=gmail_message_id,
        subject=subject,
        jobs_extracted=jobs_extracted,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
