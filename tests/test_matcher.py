"""Tests for rule-based match scoring."""

from __future__ import annotations

from job_agent.matcher import score_job
from job_agent.models import CandidateProfile, ParsedJob, Recommendation


def test_score_job_high_match() -> None:
    profile = CandidateProfile(
        target_titles=["Python Developer", "Backend Engineer"],
        required_skills=["Python", "SQL", "Git"],
        preferred_skills=["Docker", "AWS", "FastAPI"],
        years_experience=5,
        locations=["Remote"],
        work_modes=["remote"],
        salary_min=100000,
    )

    job = ParsedJob(
        title="Senior Python Developer",
        company="TechCorp",
        location="Remote",
        source_platform="ziprecruiter",
        salary="$130,000 - $160,000 a year",
        job_url="https://ziprecruiter.com/jobs/123",
        description="We are looking for a Senior Python Developer with 5+ years experience. Required skills: Python, SQL, Git. Preferred: Docker, AWS, FastAPI.",
    )

    match = score_job(job, profile)
    assert match.score >= 80.0
    assert match.recommendation == Recommendation.STRONG_MATCH
    assert "Python" in match.matched_skills
    assert "SQL" in match.matched_skills


def test_score_job_exclusion() -> None:
    profile = CandidateProfile(
        target_titles=["Software Engineer"],
        excluded_companies=["BadCorp"],
        excluded_titles=["intern"],
    )

    job = ParsedJob(
        title="Software Engineer Intern",
        company="BadCorp",
        source_platform="indeed",
        job_url="https://indeed.com/viewjob?jk=999",
        description="Internship position.",
    )

    match = score_job(job, profile)
    assert match.score == 0.0
    assert match.recommendation == Recommendation.EXCLUDED
    assert len(match.concerns) > 0
