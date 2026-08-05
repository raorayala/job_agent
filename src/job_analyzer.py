"""Score job listings against your target profile."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import load_yaml_config
from src.job_parser import ParsedJob


@dataclass
class MatchResult:
    score: float
    matched_roles: list[str]
    matched_skills: list[str]
    summary: str


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#\.]+", text.lower()))


def analyze_job(job: ParsedJob) -> MatchResult:
    """Rule-based relevance scoring (Phase 1). Swap for LLM analysis later."""
    config = load_yaml_config()
    target_roles = [r.lower() for r in config.get("target_roles", [])]
    target_skills = [s.lower() for s in config.get("target_skills", [])]

    haystack = " ".join([job.title, job.company, job.description]).lower()
    tokens = _tokenize(haystack)

    matched_roles = [r for r in target_roles if r in haystack]
    matched_skills = [s for s in target_skills if s in tokens or s in haystack]

    role_score = min(len(matched_roles) * 25, 50)
    skill_score = min(len(matched_skills) * 10, 40)
    platform_bonus = 10 if job.platform != "unknown" else 0

    score = float(min(role_score + skill_score + platform_bonus, 100))
    summary = (
        f"Matched {len(matched_roles)} role keyword(s) and "
        f"{len(matched_skills)} skill(s). Platform: {job.platform}."
    )

    return MatchResult(
        score=score,
        matched_roles=matched_roles,
        matched_skills=matched_skills,
        summary=summary,
    )
