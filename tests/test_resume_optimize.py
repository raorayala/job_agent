"""Unit tests for AI Optimize resume suggestions and profile optimize."""

from pathlib import Path

from docx import Document

from job_agent.config import Settings
from job_agent.models import CandidateProfile, MatchExplanation, ParsedJob, Recommendation
from job_agent.profile_optimize import analyze_profile_against_target, apply_skills_order_to_profile
from job_agent.resume_optimize import (
    apply_accepted_suggestions_to_draft,
    generate_optimize_suggestions,
    load_optimize_bundle,
    update_suggestion,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        master_resume_path=tmp_path / "master.docx",
        jobs_applied_folder=tmp_path / "Jobs Applied",
        jobs_draft_folder=tmp_path / "_drafts",
        preferred_browser="system",
        gmail_credentials_path=tmp_path / "creds.json",
        gmail_token_path=tmp_path / "token.json",
        gmail_search_query="",
        gmail_label=None,
        min_match_score=60.0,
        llm_provider="none",
        ollama_base_url="",
        ollama_model="",
        database_path=tmp_path / "test.db",
        log_level="INFO",
        config_path=tmp_path / "config.yaml",
    )


def test_generate_optimize_suggestions_and_accept_apply(tmp_path: Path):
    master = tmp_path / "master.docx"
    doc = Document()
    doc.add_heading("Jane Doe", level=1)
    doc.add_paragraph("Senior Python Developer with Docker and AWS experience.")
    doc.add_paragraph("- Built APIs with Python and FastAPI")
    doc.add_paragraph("- Deployed services using Docker")
    doc.save(str(master))

    draft = tmp_path / "_drafts" / "Acme_Engineer_Draft_v1.docx"
    draft.parent.mkdir(parents=True, exist_ok=True)
    Document(str(master)).save(str(draft))

    job = ParsedJob(
        title="Senior Engineer",
        company="Acme",
        description="Looking for Python Docker Kubernetes AWS FastAPI engineer with strong leadership.",
    )
    match = MatchExplanation(
        score=78.0,
        recommendation=Recommendation.WORTH_REVIEWING,
        matched_skills=["Python", "Docker"],
        missing_skills=["Kubernetes"],
        summary="Partial match",
    )
    settings = _settings(tmp_path)
    settings.master_resume_path = master

    bundle = generate_optimize_suggestions(
        job=job,
        match=match,
        master_resume_path=master,
        draft_resume_path=draft,
        job_id=1,
        settings=settings,
    )
    assert bundle.suggestions
    assert bundle.readiness_score >= 0
    assert load_optimize_bundle(draft) is not None

    # Accept first non-confirm suggestion if possible
    target = next(
        (s for s in bundle.suggestions if not s.suggested_text.startswith("[CONFIRM BEFORE ADDING]")),
        bundle.suggestions[0],
    )
    updated = update_suggestion(draft, target.id, "accept")
    assert any(s.id == target.id and s.status == "accepted" for s in updated.suggestions)

    applied = apply_accepted_suggestions_to_draft(draft, master_resume_path=master)
    assert applied.exists()
    text = "\n".join(p.text for p in Document(str(applied)).paragraphs)
    assert "AI Optimize" in text or target.suggested_text[:20] in text


def test_profile_optimize_keyword_gap_and_skills_audit():
    profile = CandidateProfile(
        target_titles=["Staff Backend Engineer"],
        required_skills=["Python", "Docker", "PostgreSQL"],
        preferred_skills=["Kafka"],
        years_experience=8,
    )
    result = analyze_profile_against_target(
        profile,
        job_description="Staff Backend Engineer Python Docker Kubernetes AWS PostgreSQL Kafka leadership",
        resume_text="Python Docker PostgreSQL experience building APIs",
    )
    assert 0 <= result.readiness_score <= 100
    assert result.headline
    assert len(result.headline) <= 220
    assert result.about_summary
    assert result.skills_audit
    assert result.suggested_skills_order

    updated = apply_skills_order_to_profile(profile, result.suggested_skills_order, accepted_adds=["Kubernetes"])
    assert "Python" in updated.required_skills
