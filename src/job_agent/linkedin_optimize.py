"""Dedicated LinkedIn Optimization helpers built on profile optimize."""

from __future__ import annotations

from typing import Any

from job_agent.config import Settings, get_settings, load_candidate_profile
from job_agent.profile_optimize import ProfileOptimizeResult, analyze_profile_against_target
from job_agent.resume_parser import extract_resume_text


def optimize_linkedin_profile(
    *,
    target_role: str = "",
    about_context: str = "",
    job_description: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Produce LinkedIn-focused headline, About summary, keyword gaps, and skills audit.
    Does not auto-publish to LinkedIn — user copies after review.
    """
    st = settings or get_settings()
    profile = load_candidate_profile()
    resume_path = profile.get_master_resume_path(target_role or None) or st.master_resume_path
    resume_text = extract_resume_text(resume_path) if resume_path else ""

    role = (target_role or (profile.target_titles[0] if profile.target_titles else "Professional")).strip()
    context = "\n".join(
        part for part in [
            f"LinkedIn target role: {role}",
            about_context.strip(),
            job_description.strip(),
        ]
        if part
    )

    result: ProfileOptimizeResult = analyze_profile_against_target(
        profile,
        job_description=job_description or context,
        resume_text=resume_text,
        industry_role=role,
    )

    # Ensure headline fits LinkedIn 220-char guideline
    headline = (result.headline or "")[:220]
    about = result.about_summary or ""
    if about_context and about_context.strip() and about_context.strip() not in about:
        about = f"{about}\n\n{about_context.strip()}".strip()

    payload = result.to_dict()
    payload["headline"] = headline
    payload["about_summary"] = about
    payload["target_role"] = role
    payload["linkedin_tips"] = [
        "Copy the headline into LinkedIn → Intro → Headline (max 220 characters).",
        "Paste the About draft into LinkedIn → About; edit for your voice before saving.",
        "Reorder Top Skills to match the suggested skills order (only add skills you truly have).",
        "Do not invent employers, titles, or certifications.",
    ]
    payload["status"] = "success"
    return payload
