"""Reporting service for generating job search metrics and application pipeline summaries."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_agent.database import ContactRecord, InterviewRecord, JobRecord


def generate_pipeline_summary(session: Session) -> dict[str, Any]:
    """
    Generate real-time metrics for the personal job search dashboard.
    """
    stmt = select(JobRecord)
    all_jobs = list(session.scalars(stmt))

    status_counts = Counter(j.status for j in all_jobs)
    platform_counts = Counter(j.source_platform for j in all_jobs)

    high_score_jobs = [j for j in all_jobs if (j.match_score or 0) >= 65 and j.status in ("Saved", "Reviewing")]
    stale_jobs = [j for j in all_jobs if j.is_stale or (j.status == "Saved" and j.date_discovered < datetime.now(timezone.utc) - timedelta(days=30))]

    now = datetime.now(timezone.utc)
    stmt_interviews = select(InterviewRecord).where(InterviewRecord.interview_date >= now).order_by(InterviewRecord.interview_date.asc())
    upcoming_interviews = list(session.scalars(stmt_interviews))

    stmt_followups = select(JobRecord).where(JobRecord.follow_up_date.isnot(None), JobRecord.follow_up_date <= now)
    followups_due = list(session.scalars(stmt_followups))

    return {
        "total_jobs": len(all_jobs),
        "status_counts": dict(status_counts),
        "platform_counts": dict(platform_counts),
        "high_score_jobs": high_score_jobs,
        "stale_jobs_count": len(stale_jobs),
        "upcoming_interviews": upcoming_interviews,
        "followups_due": followups_due,
    }


def generate_report(session: Session, period: str = "weekly") -> str:
    """
    Generate a text-based analytical report showing applications by status, platform sources, response rates, and follow-ups.
    """
    days = 30 if period.lower() == "monthly" else 7
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(JobRecord).where(JobRecord.created_at >= cutoff)
    recent_jobs = list(session.scalars(stmt))

    total = len(recent_jobs)
    applied = [j for j in recent_jobs if j.status == "Applied" or j.date_applied]
    interviewing = [j for j in recent_jobs if j.status == "Interviewing"]
    offers = [j for j in recent_jobs if j.status == "Offer"]
    rejected = [j for j in recent_jobs if j.status == "Rejected"]

    response_rate = (len(interviewing) + len(offers) + len(rejected)) / max(len(applied), 1)

    lines = [
        f"=== Job Search Report ({period.capitalize()} - Last {days} Days) ===",
        f"Jobs Discovered: {total}",
        f"Applications Submitted: {len(applied)}",
        f"Interviews Scheduled: {len(interviewing)}",
        f"Offers Received: {len(offers)}",
        f"Rejections: {len(rejected)}",
        f"Response Rate: {response_rate:.1%}",
        "",
        "--- Applications by Platform ---",
    ]
    platform_counter = Counter(j.source_platform for j in recent_jobs)
    for plat, count in platform_counter.most_common():
        lines.append(f" - {plat}: {count}")

    lines.extend([
        "",
        "--- Applications by Status ---",
    ])
    status_counter = Counter(j.status for j in recent_jobs)
    for stat, count in status_counter.most_common():
        lines.append(f" - {stat}: {count}")

    return "\n".join(lines)
