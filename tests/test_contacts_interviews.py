"""Tests for contacts and interview prep tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from job_agent.contact_service import add_contact, list_contacts
from job_agent.database import JobRecord, get_session_factory
from job_agent.interview_service import add_interview, list_interviews, prepare_interview_doc
from job_agent.models import CandidateProfile


def test_contacts_and_interviews(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs_ci.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    job = JobRecord(title="Senior Python Dev", company="TechCorp", job_url="http://tc.com", job_url_normalized="http://tc.com")
    session.add(job)
    session.commit()
    job_id = job.id

    c = add_contact(session, name="Alice Recruiter", job_id=job_id, role="Recruiter", company="TechCorp", email="alice@tc.com")
    assert c.id is not None
    contacts = list_contacts(session, job_id=job_id)
    assert len(contacts) == 1
    assert contacts[0].name == "Alice Recruiter"

    dt = datetime.now(timezone.utc)
    iv = add_interview(session, job_id=job_id, interview_date=dt, interview_type="Technical", participants="Alice")
    assert iv.id is not None
    interviews = list_interviews(session, job_id=job_id)
    assert len(interviews) == 1

    profile = CandidateProfile(target_titles=["Senior Python Dev"], required_skills=["Python", "PostgreSQL"])
    doc_path = prepare_interview_doc(session, job_id=job_id, profile=profile, output_base_dir=tmp_path / "Desktop")
    assert doc_path.exists()
    assert doc_path.suffix == ".docx"

    session.close()
