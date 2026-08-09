"""Rule-based job matching and explainable scoring."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from job_agent.config import load_yaml_config
from job_agent.job_normalizer import calculate_similarity, normalize_text
from job_agent.models import CandidateProfile, MatchExplanation, ParsedJob, Recommendation
from job_agent.resume_parser import extract_resume_text


def recommendation_for_score(score: float, excluded: bool = False) -> Recommendation:
    if excluded:
        return Recommendation.EXCLUDED
    if score >= 80:
        return Recommendation.STRONG_MATCH
    if score >= 65:
        return Recommendation.WORTH_REVIEWING
    return Recommendation.LOW_MATCH


def score_job(
    job: ParsedJob,
    profile: CandidateProfile,
    resume_text: str | None = None,
) -> MatchExplanation:
    """
    Score a job listing (0-100) against candidate profile and master resume with explainable breakdown.

    Weighted factors (configurable in config.yaml):
    - Required skill overlap (30)
    - Preferred skill overlap (15)
    - Job title similarity (20)
    - Experience alignment (10)
    - Location / work mode compatibility (15)
    - Salary compatibility (10)
    - Exclusions (forces score=0, recommendation=Excluded)
    """
    try:
        config = load_yaml_config()
        weights = config.get("match_weights", {})
    except Exception:
        weights = {}

    w_req = float(weights.get("required_skills", 30))
    w_pref = float(weights.get("preferred_skills", 15))
    w_title = float(weights.get("title_similarity", 20))
    w_exp = float(weights.get("experience_alignment", 10))
    w_loc = float(weights.get("location_work_mode", 15))
    w_sal = float(weights.get("salary_compatibility", 10))

    concerns: list[str] = []
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    factor_scores: dict[str, float] = {}

    haystack = normalize_text(f"{job.title} {job.company} {job.description}")

    # Extract resume text if not provided
    if resume_text is None:
        resume_path = profile.get_master_resume_path(job.title)
        if resume_path:
            resume_text = extract_resume_text(resume_path)

    resume_haystack = normalize_text(resume_text or "")

    # 1. Exclusions check
    # Excluded companies
    if profile.excluded_companies:
        for exc_comp in profile.excluded_companies:
            if exc_comp.strip() and exc_comp.strip().lower() in normalize_text(job.company):
                concerns.append(f"Excluded company: '{job.company}' matches '{exc_comp}'")
                return MatchExplanation(
                    score=0.0,
                    recommendation=Recommendation.EXCLUDED,
                    matched_skills=[],
                    missing_skills=profile.required_skills,
                    concerns=concerns,
                    factor_scores={"exclusions": 0.0},
                    summary=f"Job excluded because company '{job.company}' is in candidate exclusion list.",
                )

    # Excluded titles
    if profile.excluded_titles:
        for exc_title in profile.excluded_titles:
            if exc_title.strip() and exc_title.strip().lower() in normalize_text(job.title):
                concerns.append(f"Excluded title: '{job.title}' contains '{exc_title}'")
                return MatchExplanation(
                    score=0.0,
                    recommendation=Recommendation.EXCLUDED,
                    matched_skills=[],
                    missing_skills=profile.required_skills,
                    concerns=concerns,
                    factor_scores={"exclusions": 0.0},
                    summary=f"Job excluded because title '{job.title}' contains excluded keyword '{exc_title}'.",
                )

    # Excluded skills
    if profile.excluded_skills:
        for exc_skill in profile.excluded_skills:
            if exc_skill.strip() and re.search(
                r"\b" + re.escape(exc_skill.strip().lower()) + r"\b", haystack
            ):
                concerns.append(f"Excluded skill keyword found: '{exc_skill}'")
                return MatchExplanation(
                    score=0.0,
                    recommendation=Recommendation.EXCLUDED,
                    matched_skills=[],
                    missing_skills=profile.required_skills,
                    concerns=concerns,
                    factor_scores={"exclusions": 0.0},
                    summary=f"Job excluded because description contains excluded skill keyword '{exc_skill}'.",
                )

    # Excluded locations
    if profile.excluded_locations and job.location:
        for exc_loc in profile.excluded_locations:
            if exc_loc.strip() and exc_loc.strip().lower() in normalize_text(job.location):
                concerns.append(f"Excluded location: '{job.location}' matches '{exc_loc}'")
                return MatchExplanation(
                    score=0.0,
                    recommendation=Recommendation.EXCLUDED,
                    matched_skills=[],
                    missing_skills=profile.required_skills,
                    concerns=concerns,
                    factor_scores={"exclusions": 0.0},
                    summary=f"Job excluded because location '{job.location}' is in exclusion list.",
                )

    # 2. Required skills score
    if profile.required_skills:
        req_found = 0
        for skill in profile.required_skills:
            sk_clean = skill.strip().lower()
            if not sk_clean:
                continue
            in_job = bool(re.search(r"\b" + re.escape(sk_clean) + r"\b", haystack))
            in_resume = bool(re.search(r"\b" + re.escape(sk_clean) + r"\b", resume_haystack)) if resume_haystack else True

            if in_job:
                req_found += 1
                matched_skills.append(skill)
                if resume_haystack and not in_resume:
                    concerns.append(f"Required skill '{skill}' requested by job but not found in master resume text")
            else:
                missing_skills.append(skill)
        req_ratio = req_found / max(len(profile.required_skills), 1)
        s_req = req_ratio * w_req
    else:
        s_req = w_req
    factor_scores["required_skills"] = round(s_req, 1)

    # 3. Preferred skills score
    if profile.preferred_skills:
        pref_found = 0
        for skill in profile.preferred_skills:
            sk_clean = skill.strip().lower()
            if not sk_clean:
                continue
            if re.search(r"\b" + re.escape(sk_clean) + r"\b", haystack):
                pref_found += 1
                if skill not in matched_skills:
                    matched_skills.append(skill)
        pref_ratio = pref_found / max(len(profile.preferred_skills), 1)
        s_pref = pref_ratio * w_pref
    else:
        s_pref = w_pref * 0.5
    factor_scores["preferred_skills"] = round(s_pref, 1)

    # 4. Job title similarity score
    s_title = 0.0
    if profile.target_titles:
        max_sim = 0.0
        for target in profile.target_titles:
            if not target or not isinstance(target, str):
                continue
            job_title_str = job.title or ""
            sim = calculate_similarity(job_title_str, target)
            # Substring match boost
            if target.lower() in job_title_str.lower() or job_title_str.lower() in target.lower():
                sim = max(sim, 0.85)
            max_sim = max(max_sim, sim)
        s_title = max_sim * w_title
    else:
        s_title = w_title * 0.5
    factor_scores["title_similarity"] = round(s_title, 1)

    # 5. Experience alignment score
    s_exp = w_exp * 0.8  # default baseline
    years_match = re.search(r"(\d+)\+?\s*(?:-\s*\d+\+?)?\s*years?(?:\s+of\s+experience)?", haystack)
    if years_match:
        job_years = int(years_match.group(1))
        cand_years = profile.years_experience
        if cand_years >= job_years:
            s_exp = w_exp
        elif cand_years >= job_years - 2:
            s_exp = w_exp * 0.7
            concerns.append(f"Requires {job_years}+ years experience (candidate has {cand_years})")
        else:
            s_exp = w_exp * 0.3
            concerns.append(f"High experience gap: requires {job_years}+ years (candidate has {cand_years})")
    factor_scores["experience_alignment"] = round(s_exp, 1)

    # 6. Location / Work mode compatibility
    s_loc = w_loc * 0.5
    loc_text = normalize_text(f"{job.location} {job.title} {job.description}")
    cand_modes = [m.lower() for m in profile.work_modes]

    if "remote" in loc_text:
        if "remote" in cand_modes:
            s_loc = w_loc
        else:
            s_loc = w_loc * 0.5
            concerns.append("Job is remote; candidate work mode preference does not include remote")
    elif "hybrid" in loc_text:
        if "hybrid" in cand_modes or "remote" in cand_modes:
            s_loc = w_loc * 0.9
        else:
            s_loc = w_loc * 0.5
    elif profile.locations:
        loc_matched = False
        for pref_loc in profile.locations:
            if pref_loc.strip().lower() in loc_text:
                s_loc = w_loc
                loc_matched = True
                break
        if not loc_matched and job.location:
            concerns.append(f"Location '{job.location}' outside preferred locations {profile.locations}")
            s_loc = w_loc * 0.3
    else:
        s_loc = w_loc * 0.8
    factor_scores["location_work_mode"] = round(s_loc, 1)

    # 7. Salary compatibility
    s_sal = w_sal * 0.7
    if job.salary and profile.salary_min:
        sal_numbers = re.findall(r"\$(\d{2,3}(?:,\d{3})*)", job.salary)
        if sal_numbers:
            parsed_sals = [int(s.replace(",", "")) for s in sal_numbers]
            max_job_sal = max(parsed_sals)
            # If specified as hourly, convert approx
            if max_job_sal < 500:
                max_job_sal = max_job_sal * 2000

            if max_job_sal >= profile.salary_min:
                s_sal = w_sal
            else:
                s_sal = w_sal * 0.4
                concerns.append(f"Salary ${max_job_sal:,} below minimum target ${profile.salary_min:,}")
    factor_scores["salary_compatibility"] = round(s_sal, 1)

    total_score = min(
        round(s_req + s_pref + s_title + s_exp + s_loc + s_sal, 1),
        100.0,
    )
    rec = recommendation_for_score(total_score)

    summary_parts = [
        f"Score {total_score:.0f}/100 ({rec.value}).",
        f"Matched {len(matched_skills)} skill(s).",
    ]
    if missing_skills:
        summary_parts.append(f"Missing required: {', '.join(missing_skills[:3])}.")
    if concerns:
        summary_parts.append(f"Concerns: {'; '.join(concerns[:2])}.")

    return MatchExplanation(
        score=total_score,
        recommendation=rec,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        concerns=concerns,
        factor_scores=factor_scores,
        summary=" ".join(summary_parts),
    )
