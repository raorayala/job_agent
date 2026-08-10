"""Profile readiness scoring, recruiter keyword gaps, skills audit, and headline/summary drafts."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from job_agent.config import Settings, get_settings
from job_agent.job_normalizer import normalize_text
from job_agent.logging_config import get_logger
from job_agent.models import CandidateProfile
from job_agent.ollama_service import generate_ollama_completion
from job_agent.resume_optimize import extract_jd_keywords

logger = get_logger(__name__)


@dataclass
class SkillsAuditItem:
    skill: str
    action: str  # keep | promote | add_if_true | demote
    reason: str
    weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfileOptimizeResult:
    readiness_score: float
    matched_keywords: list[str] = field(default_factory=list)
    keyword_gaps: list[str] = field(default_factory=list)
    skills_audit: list[SkillsAuditItem] = field(default_factory=list)
    suggested_skills_order: list[str] = field(default_factory=list)
    headline: str = ""
    about_summary: str = ""
    source: str = "rule"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness_score": self.readiness_score,
            "matched_keywords": self.matched_keywords,
            "keyword_gaps": self.keyword_gaps,
            "skills_audit": [s.to_dict() for s in self.skills_audit],
            "suggested_skills_order": self.suggested_skills_order,
            "headline": self.headline,
            "about_summary": self.about_summary,
            "source": self.source,
            "notes": self.notes,
        }


def _skill_present(skill: str, text: str) -> bool:
    if not skill or not text:
        return False
    return bool(re.search(r"\b" + re.escape(skill.strip()) + r"\b", text, re.IGNORECASE))


def analyze_profile_against_target(
    profile: CandidateProfile,
    *,
    job_description: str = "",
    resume_text: str = "",
    industry_role: str = "",
) -> ProfileOptimizeResult:
    """
    Score profile/resume readiness vs a job description or industry role category.
    Also produces recruiter keyword gap analysis and a skills section audit.
    """
    target_blob = " ".join(
        part for part in [job_description, industry_role, " ".join(profile.target_titles)] if part
    )
    profile_blob = " ".join(
        [
            " ".join(profile.required_skills),
            " ".join(profile.preferred_skills),
            " ".join(profile.target_titles),
            resume_text or "",
        ]
    )
    profile_norm = normalize_text(profile_blob)
    ranked = extract_jd_keywords(target_blob or profile_blob, limit=30)

    matched: list[str] = []
    gaps: list[str] = []
    for term, freq in ranked:
        if _skill_present(term, profile_norm) or term in profile_norm:
            matched.append(term)
        else:
            gaps.append(term)

    # Profile skills vs JD weighting
    audit: list[SkillsAuditItem] = []
    jd_weights = {term: float(freq) for term, freq in ranked}
    ordered_required = list(profile.required_skills)
    ordered_preferred = list(profile.preferred_skills)

    for idx, skill in enumerate(ordered_required):
        weight = jd_weights.get(skill.lower(), 0.0)
        if weight >= 2:
            action = "promote" if idx > 2 else "keep"
            reason = f"High recruiter frequency in target text (weight={weight:.0f})."
        elif weight == 0 and target_blob:
            action = "demote"
            reason = "Not mentioned in target job/role text; consider lower priority."
        else:
            action = "keep"
            reason = "Present in required skills."
        audit.append(SkillsAuditItem(skill=skill, action=action, reason=reason, weight=weight))

    for skill in gaps[:8]:
        # Only recommend add if soft-related or user confirms
        if skill.lower() in {s.lower() for s in ordered_required + ordered_preferred}:
            continue
        audit.append(
            SkillsAuditItem(
                skill=skill,
                action="add_if_true",
                reason="High-frequency target keyword missing from profile — add only if truthful.",
                weight=float(jd_weights.get(skill.lower(), 1.0)),
            )
        )

    # Suggested order: JD-weighted skills first, then remaining required, then preferred
    scored = sorted(
        {(s.lower(), s) for s in ordered_required + ordered_preferred},
        key=lambda pair: (-jd_weights.get(pair[0], 0.0), pair[1].lower()),
    )
    suggested_order = [orig for _, orig in scored]
    for item in audit:
        if item.action == "add_if_true" and item.skill not in suggested_order:
            # Keep advisory adds out of auto-order unless accepted later
            pass

    total = max(len(matched) + len(gaps), 1)
    readiness = round(100.0 * len(matched) / total, 1)

    headline, about, source = generate_headline_and_summary(
        profile,
        resume_text=resume_text,
        job_description=job_description or industry_role,
        keyword_hints=matched[:6] + [g for g in gaps if _skill_present(g, profile_norm)][:3],
    )

    notes = [
        "Suggestions are drafts — review before saving to your profile or LinkedIn.",
        "Skills marked add_if_true must only be added if you truly have that experience.",
    ]
    if not target_blob.strip():
        notes.append("No job description provided; scored against your target titles and skills.")

    return ProfileOptimizeResult(
        readiness_score=readiness,
        matched_keywords=matched[:20],
        keyword_gaps=gaps[:20],
        skills_audit=audit,
        suggested_skills_order=suggested_order,
        headline=headline,
        about_summary=about,
        source=source,
        notes=notes,
    )


def generate_headline_and_summary(
    profile: CandidateProfile,
    *,
    resume_text: str = "",
    job_description: str = "",
    keyword_hints: list[str] | None = None,
    settings: Settings | None = None,
) -> tuple[str, str, str]:
    """Return (headline <=220 chars, about summary, source)."""
    st = settings or get_settings()
    hints = keyword_hints or (profile.required_skills[:5] + profile.preferred_skills[:3])
    title = (profile.target_titles[0] if profile.target_titles else "Software Professional")
    years = profile.years_experience or 0
    skills = ", ".join(hints[:5]) or "software engineering"

    rule_headline = f"{title} | {years}+ yrs | {skills}"
    rule_headline = rule_headline[:220]
    rule_about = (
        f"Results-driven {title.lower()} with {years}+ years of experience. "
        f"Strengths include {skills}. "
        f"Focused on delivering reliable systems and collaborating across teams."
    )
    if job_description:
        rule_about += " Tailoring profile language toward the target role requirements."
    source = "rule"

    if st.llm_provider == "ollama":
        prompt = (
            "Draft a truthful professional headline (max 220 characters) and an About summary "
            "(2-4 sentences). Do NOT invent employers, degrees, or skills not listed.\n"
            "Return ONLY JSON: {\"headline\": \"...\", \"about\": \"...\"}\n"
            f"Target titles: {', '.join(profile.target_titles)}\n"
            f"Years experience: {years}\n"
            f"Skills: {', '.join(profile.required_skills + profile.preferred_skills)}\n"
            f"Keyword hints: {', '.join(hints)}\n"
            f"Job/role context (excerpt): {(job_description or '')[:1500]}\n"
            f"Resume excerpt: {(resume_text or '')[:2000]}\n"
        )
        raw = generate_ollama_completion(prompt, st)
        if raw:
            try:
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(raw[start : end + 1])
                    hl = str(data.get("headline") or "").strip()
                    about = str(data.get("about") or "").strip()
                    if hl:
                        rule_headline = hl[:220]
                    if about:
                        rule_about = about
                    source = "ollama"
            except Exception as exc:
                logger.debug("Ollama headline parse failed: %s", exc)

    return rule_headline, rule_about, source


def apply_skills_order_to_profile(
    profile: CandidateProfile,
    suggested_order: list[str],
    *,
    accepted_adds: list[str] | None = None,
) -> CandidateProfile:
    """
    Return a shallow-updated profile with reordered required_skills.
    New skills are only appended when explicitly listed in accepted_adds.
    """
    accepted = {s.strip().lower() for s in (accepted_adds or []) if s and s.strip()}
    existing = list(profile.required_skills)
    existing_l = {s.lower() for s in existing}
    ordered: list[str] = []
    seen: set[str] = set()

    for skill in suggested_order:
        key = skill.lower()
        if key in seen:
            continue
        if key in existing_l:
            # Preserve original casing from profile
            original = next(s for s in existing if s.lower() == key)
            ordered.append(original)
            seen.add(key)
        elif key in accepted:
            ordered.append(skill)
            seen.add(key)

    for skill in existing:
        if skill.lower() not in seen:
            ordered.append(skill)
            seen.add(skill.lower())

    profile.required_skills = ordered
    return profile
