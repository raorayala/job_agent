"""Application answer library service for managing common job application questions and answers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.config import get_settings
from job_agent.database import ApplicationAnswer, JobRecord
from job_agent.logging_config import get_logger
from job_agent.models import CandidateProfile
from job_agent.ollama_service import generate_ollama_completion
from job_agent.resume_parser import extract_resume_text

logger = get_logger(__name__)


def _normalize_question(q: str) -> str:
    """Lowercase and condense whitespace for normalized question matching."""
    import re
    return re.sub(r"\s+", " ", q.strip().lower())


def add_answer(
    session: Session,
    question: str,
    answer: str,
    *,
    source_context: str | None = None,
    tags: str | None = None,
) -> ApplicationAnswer:
    norm_q = _normalize_question(question)
    item = ApplicationAnswer(
        original_question=question.strip(),
        normalized_question=norm_q,
        approved_answer=answer.strip(),
        source_context=source_context,
        tags=tags,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    logger.info("Saved application answer for question: '%s'", question[:50])
    return item


def list_answers(session: Session) -> Sequence[ApplicationAnswer]:
    stmt = select(ApplicationAnswer).order_by(ApplicationAnswer.id.desc())
    return session.scalars(stmt).all()


def suggest_answer(
    session: Session,
    job_id: int,
    question: str,
    profile: CandidateProfile,
) -> str:
    """
    Draft an answer suggestion using verified local profile and resume data.
    Suggestions are clearly marked as drafts and use only verified facts.
    """
    norm_q = _normalize_question(question)

    # 1. Check if an exact or near match exists in approved answers
    stmt = select(ApplicationAnswer).where(ApplicationAnswer.normalized_question == norm_q)
    exact = session.scalars(stmt).first()
    if exact:
        exact.last_used_at = datetime.now(timezone.utc)
        session.commit()
        return (
            f"[APPROVED EXISTING ANSWER]\n"
            f"{exact.approved_answer}\n\n"
            f"(Source: {exact.source_context or 'User approved answer'})"
        )

    job = session.get(JobRecord, job_id)
    job_title = job.title if job else ""
    job_company = job.company if job else ""

    resume_path = profile.get_master_resume_path(job_title)
    resume_text = extract_resume_text(resume_path)

    # 2. Check if local Ollama offline LLM is configured and available
    settings = get_settings()
    if settings.llm_provider == "ollama":
        prompt = (
            f"Draft a concise, factual, professional answer to the following job application question:\n"
            f"Question: '{question}'\n\n"
            f"Candidate Context:\n"
            f"- Target Roles: {', '.join(profile.target_titles)}\n"
            f"- Skills: {', '.join(profile.required_skills)}\n"
            f"- Years Experience: {profile.years_experience}\n"
            f"- Target Job: {job_title} at {job_company}\n"
            f"- Resume Context: {resume_text[:600] if resume_text else 'N/A'}\n\n"
            f"Constraint: Keep answer under 100 words. Be factual. Do NOT invent dates or employers."
        )
        ollama_res = generate_ollama_completion(prompt, settings)
        if ollama_res:
            return (
                f"[DRAFT SUGGESTION (OLLAMA LOCAL AI) - REQUIRES USER REVIEW]\n"
                f"{ollama_res}\n\n"
                f"Note: Verify and edit this draft before using in your job application."
            )

    # 3. Rule-based draft generation based on question keywords
    draft_body = ""
    if "years" in norm_q or "experience" in norm_q:
        draft_body = f"I have {profile.years_experience} years of experience in software development, targeting roles in {', '.join(profile.target_titles[:3])}."
    elif "salary" in norm_q or "compensation" in norm_q or "pay" in norm_q:
        if profile.salary_min:
            draft_body = f"My target salary range is ${profile.salary_min:,} - ${profile.salary_max or profile.salary_min:,} {profile.salary_currency}, negotiable depending on benefits and total compensation."
        else:
            draft_body = "Open to discussing market-rate compensation based on the responsibilities of the role."
    elif "work authorization" in norm_q or "sponsor" in norm_q or "citizen" in norm_q:
        auth_status = profile.work_authorization or "Authorized to work in target location"
        draft_body = f"Work Authorization Status: {auth_status}."
    elif "why" in norm_q or "interest" in norm_q or "cover" in norm_q:
        draft_body = (
            f"I am deeply interested in joining {job_company or 'your team'} as a {job_title or 'Software Engineer'}. "
            f"My technical background in {', '.join(profile.required_skills[:4])} aligns closely with the key responsibilities of this role."
        )
    else:
        # Generic factual summary from profile & resume
        draft_body = (
            f"Core Technical Background:\n"
            f" - Target Title: {', '.join(profile.target_titles[:2])}\n"
            f" - Key Skills: {', '.join(profile.required_skills[:6])}\n"
            f" - Experience: {profile.years_experience} years\n"
        )
        if resume_text:
            draft_body += f"\nRelevant Resume Snippet:\n{resume_text[:400]}"

    suggestion = (
        f"[DRAFT SUGGESTION - REQUIRES USER REVIEW]\n"
        f"{draft_body}\n\n"
        f"Note: Verify and edit this draft before using in your job application."
    )
    return suggestion
