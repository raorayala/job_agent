"""Rule-based explainable job matching. Implemented in Milestone 6."""

from __future__ import annotations

from job_agent.models import CandidateProfile, MatchExplanation, ParsedJob, Recommendation


def score_job(job: ParsedJob, profile: CandidateProfile) -> MatchExplanation:
    """Score a job 0–100 with an explainable breakdown (stub until Milestone 6)."""
    raise NotImplementedError("Rule-based matcher lands in Milestone 6.")


def recommendation_for_score(score: float, excluded: bool = False) -> Recommendation:
    if excluded:
        return Recommendation.EXCLUDED
    if score >= 80:
        return Recommendation.STRONG_MATCH
    if score >= 65:
        return Recommendation.WORTH_REVIEWING
    return Recommendation.LOW_MATCH
