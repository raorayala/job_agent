"""Tests for application answer library and draft suggestion."""

from __future__ import annotations

from pathlib import Path
from job_agent.answer_service import add_answer, list_answers, suggest_answer
from job_agent.database import JobRecord, get_session_factory
from job_agent.models import CandidateProfile


def test_answer_library(tmp_path: Path) -> None:
    db_path = tmp_path / "answers.db"
    SessionLocal = get_session_factory(db_path)
    session = SessionLocal()

    item = add_answer(session, question="What is your notice period?", answer="2 weeks notice")
    assert item.id is not None

    answers = list_answers(session)
    assert len(answers) == 1
    assert answers[0].approved_answer == "2 weeks notice"

    profile = CandidateProfile(years_experience=6, required_skills=["Python", "SQL"])
    job = JobRecord(title="Lead Engineer", company="Acme", job_url="http://a.com", job_url_normalized="http://a.com")
    session.add(job)
    session.commit()

    # Exact approved answer suggestion
    exact_sugg = suggest_answer(session, job.id, "What is your notice period?", profile)
    assert "2 weeks notice" in exact_sugg

    # Draft rule-based suggestion
    draft_sugg = suggest_answer(session, job.id, "How many years of experience do you have?", profile)
    assert "6 years" in draft_sugg
    assert "DRAFT SUGGESTION" in draft_sugg

    session.close()
