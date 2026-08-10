"""Domain models and enums (Pydantic-free dataclasses for MVP simplicity)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ApplicationStatus(str, Enum):
    IMPORTED = "Imported"
    ANALYZED = "Analyzed"
    DRAFT_READY = "Resume draft ready"
    AWAITING_REVIEW = "Awaiting review"
    APPROVED = "Approved"
    SAVED = "Saved"
    REVIEWING = "Reviewing"
    READY_TO_APPLY = "Ready to apply"
    APPLIED = "Applied"
    INTERVIEWING = "Interviewing"
    REJECTED = "Rejected"
    OFFER = "Offer"
    WITHDRAWN = "Withdrawn"
    ARCHIVED = "Archived"


class Recommendation(str, Enum):
    STRONG_MATCH = "Strong match"
    WORTH_REVIEWING = "Worth reviewing"
    LOW_MATCH = "Low match"
    EXCLUDED = "Excluded"


@dataclass(slots=True)
class CandidateProfile:
    """Configurable career profile used for matching and resume tailoring."""

    target_titles: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    years_experience: int = 0
    locations: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    employment_types: list[str] = field(default_factory=list)
    work_authorization: str | None = None
    excluded_companies: list[str] = field(default_factory=list)
    excluded_titles: list[str] = field(default_factory=list)
    excluded_skills: list[str] = field(default_factory=list)
    excluded_locations: list[str] = field(default_factory=list)
    master_resume_path: str | None = None
    master_resumes: dict[str, str] = field(default_factory=dict)
    cover_letter_template_path: str | None = None

    def get_master_resume_path(self, job_title: str | None = None) -> str | None:
        """
        Return the best matching master resume path.
        If job_title is provided and matches a key in master_resumes, return that resume path.
        Otherwise return master_resume_path or default in master_resumes.
        """
        if job_title and self.master_resumes:
            title_lower = job_title.lower()
            for key, path in self.master_resumes.items():
                if key.lower() in title_lower or title_lower in key.lower():
                    return path
            if "default" in self.master_resumes:
                return self.master_resumes["default"]
        return self.master_resume_path

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParsedJob:
    """Normalized job extracted from a job-alert email."""

    title: str
    company: str = "Unknown"
    location: str | None = None
    source_platform: str = "unknown"
    salary: str | None = None
    employment_type: str | None = None
    job_url: str = ""
    date_received: datetime | None = None
    description: str = ""
    gmail_message_id: str | None = None
    raw_subject: str | None = None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MatchExplanation:
    """Explainable match score breakdown."""

    score: float
    recommendation: Recommendation
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    summary: str = ""


@dataclass(slots=True)
class DuplicateCheckResult:
    is_duplicate: bool
    reason: str | None = None
    existing_job_id: int | None = None
    similarity: float | None = None
