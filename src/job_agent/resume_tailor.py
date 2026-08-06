"""Truthful resume tailoring for ATS compatibility using python-docx."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from docx import Document

from job_agent.config import Settings
from job_agent.document_exporter import application_folder, resume_filename
from job_agent.logging_config import get_logger
from job_agent.models import MatchExplanation, ParsedJob

logger = get_logger(__name__)


def tailor_resume(
    job: ParsedJob,
    match: MatchExplanation,
    master_resume_path: Path,
    output_base_dir: Path,
    *,
    dry_run: bool = False,
) -> Path:
    """
    Produce an ATS-friendly tailored DOCX resume using only factual master resume content.

    Safeguards:
    - Never invents qualifications, employers, dates, or certifications.
    - Appends an advisory ATS keyword summary and alignment section.
    - Preserves master resume paragraphs and chronology.
    """
    if not master_resume_path.exists():
        raise FileNotFoundError(
            f"Master resume not found at {master_resume_path}. "
            "Please place your master resume DOCX file there or set MASTER_RESUME_PATH in .env."
        )

    target_folder = application_folder(output_base_dir, job.company, job.title)
    out_filename = resume_filename(job.company, job.title)
    output_path = target_folder / out_filename

    if dry_run:
        logger.info("[Dry-run] Tailored resume target path: %s", output_path)
        return output_path

    # Read master resume
    doc = Document(str(master_resume_path))

    # Append ATS Keyword & Target Role Alignment Section
    doc.add_page_break()
    heading = doc.add_heading("ATS Keyword Alignment & Job Analysis", level=2)

    doc.add_paragraph(f"Target Role: {job.title} at {job.company}")
    doc.add_paragraph(f"Match Score: {match.score:.0f}/100 ({match.recommendation.value})")

    if match.matched_skills:
        doc.add_paragraph(
            f"Matched Candidate Skills: {', '.join(match.matched_skills)}"
        )
    if match.missing_skills:
        doc.add_paragraph(
            f"Missing Skills / Keywords to emphasize if applicable: {', '.join(match.missing_skills)}"
        )
    if match.concerns:
        doc.add_paragraph(f"Flagged Concerns: {'; '.join(match.concerns)}")

    all_keywords = sorted(
        set(
            [s for s in job.required_skills + job.preferred_skills + match.matched_skills if s]
        )
    )
    if all_keywords:
        doc.add_paragraph(
            "Recommended Keywords to Highlight in Summary & Bullet Points: "
            + ", ".join(all_keywords)
        )

    doc.save(str(output_path))
    logger.info("Saved tailored resume to: %s", output_path)

    # Export plain-text application summary sidecar
    summary_txt_path = target_folder / "Application_Summary.txt"
    summary_lines = [
        f"Job Title: {job.title}",
        f"Company: {job.company}",
        f"Platform: {job.source_platform}",
        f"Location: {job.location or 'Not specified'}",
        f"Salary: {job.salary or 'Not specified'}",
        f"URL: {job.job_url}",
        f"Gmail Message ID: {job.gmail_message_id or 'N/A'}",
        f"Date Discovered: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Match Score: {match.score:.0f}/100 ({match.recommendation.value})",
        f"Summary: {match.summary}",
        f"Tailored Resume: {output_path}",
    ]
    summary_txt_path.write_text("\n".join(summary_lines), encoding="utf-8")

    return output_path
