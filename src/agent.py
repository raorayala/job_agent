"""Main orchestration loop for the job search agent."""

from __future__ import annotations

from src.application_tracker import is_duplicate, list_applications, record_job
from src.config import get_env, get_jobs_applied_folder
from src.gmail_client import fetch_job_emails
from src.job_analyzer import analyze_job
from src.job_parser import parse_email
from src.models import init_db
from src.resume_tailor import export_application_summary, tailor_resume


def run_scan(max_results: int = 25, tailor: bool = True) -> dict:
    """
    Scan Gmail for job alerts, analyze matches, and optionally tailor resumes.

    Returns a summary dict suitable for CLI display.
    """
    get_jobs_applied_folder()  # ensure Desktop folder exists
    Session = init_db()
    session = Session()

    min_score = float(get_env("MIN_MATCH_SCORE", "65"))
    emails = fetch_job_emails(max_results=max_results)

    summary = {
        "emails_fetched": len(emails),
        "new_jobs": 0,
        "skipped_duplicates": 0,
        "tailored_resumes": 0,
        "below_threshold": 0,
        "jobs": [],
    }

    try:
        for email in emails:
            parsed = parse_email(email)
            if parsed is None:
                continue

            if is_duplicate(session, parsed.source_url):
                summary["skipped_duplicates"] += 1
                continue

            match = analyze_job(parsed)
            listing = record_job(session, parsed, match, status="reviewed")
            summary["new_jobs"] += 1

            job_info = {
                "title": parsed.title,
                "company": parsed.company,
                "platform": parsed.platform,
                "score": match.score,
                "url": parsed.source_url,
            }

            if match.score >= min_score and tailor:
                resume_path = tailor_resume(parsed, match)
                export_application_summary(parsed, match, resume_path)
                listing.status = "resume_tailored"
                session.commit()
                summary["tailored_resumes"] += 1
                job_info["resume"] = str(resume_path)
            elif match.score < min_score:
                summary["below_threshold"] += 1

            summary["jobs"].append(job_info)
    finally:
        session.close()

    return summary


def show_history() -> list:
    Session = init_db()
    session = Session()
    try:
        return list_applications(session)
    finally:
        session.close()
