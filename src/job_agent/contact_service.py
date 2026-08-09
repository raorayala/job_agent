"""Service for managing local networking contacts and recruiters."""

from __future__ import annotations

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import ContactRecord
from job_agent.logging_config import get_logger

logger = get_logger(__name__)


def add_contact(
    session: Session,
    name: str,
    *,
    job_id: int | None = None,
    role: str | None = None,
    company: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    linkedin_url: str | None = None,
    notes: str | None = None,
) -> ContactRecord:
    contact = ContactRecord(
        job_id=job_id,
        name=name,
        role=role,
        company=company,
        email=email,
        phone=phone,
        linkedin_url=linkedin_url,
        notes=notes,
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    logger.info("Added contact '%s' (%s at %s)", name, role or "", company or "")
    return contact


def list_contacts(
    session: Session,
    job_id: int | None = None,
) -> Sequence[ContactRecord]:
    stmt = select(ContactRecord).order_by(ContactRecord.id.desc())
    if job_id is not None:
        stmt = stmt.where(ContactRecord.job_id == job_id)
    return session.scalars(stmt).all()
