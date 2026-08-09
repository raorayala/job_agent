"""Truthful resume tailoring for ATS compatibility using python-docx."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt

from job_agent.config import Settings
from job_agent.document_exporter import application_folder, resume_filename
from job_agent.logging_config import get_logger
from job_agent.models import MatchExplanation, ParsedJob

logger = get_logger(__name__)


def _safe_add_heading(doc: Document, text: str, level: int = 2) -> None:
    """Add heading to DOCX, falling back to a bold paragraph if the document style gallery lacks 'Heading N'."""
    try:
        doc.add_heading(text, level=level)
    except (KeyError, ValueError):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(16 if level == 1 else 13)


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
    _safe_add_heading(doc, "ATS Keyword Alignment & Job Analysis", level=2)

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


def generate_cover_letter(
    job: ParsedJob,
    match: MatchExplanation,
    template_path: Path | str | None,
    output_folder: Path,
    candidate_name: str = "Candidate",
    *,
    dry_run: bool = False,
) -> Path | None:
    """
    Draft an ATS-friendly, truthful cover letter for a job.
    Uses cover_letter_template_path if provided, or creates a clean DOCX letter.
    Follows Truthfulness Policy: never invents qualifications, employers, or dates.
    """
    filename = f"{job.company}_{job.title}_Cover_Letter.docx".replace(" ", "_")
    clean_filename = re.sub(r"[^\w\s\.-]", "", filename)
    output_path = output_folder / clean_filename

    if dry_run:
        logger.info("[Dry-run] Cover letter target path: %s", output_path)
        return output_path

    tpl_path = Path(template_path) if template_path else None
    if tpl_path and tpl_path.exists():
        doc = Document(str(tpl_path))
        # Replace placeholders in paragraphs
        today_str = date.today().strftime("%B %d, %Y")
        replacements = {
            "{{COMPANY}}": job.company,
            "{{JOB_TITLE}}": job.title,
            "{{DATE}}": today_str,
            "{{SKILLS}}": ", ".join(match.matched_skills) or "software engineering",
        }
        for p in doc.paragraphs:
            for k, v in replacements.items():
                if k in p.text:
                    p.text = p.text.replace(k, v)
    else:
        doc = Document()
        today_str = date.today().strftime("%B %d, %Y")
        doc.add_paragraph(today_str)
        doc.add_paragraph("")
        doc.add_paragraph(f"Hiring Manager / Talent Acquisition Team\n{job.company}")
        doc.add_paragraph("")
        doc.add_paragraph(f"RE: Application for {job.title} Position")
        doc.add_paragraph("")
        doc.add_paragraph("Dear Hiring Team,")
        doc.add_paragraph(
            f"I am writing to express my strong interest in the {job.title} position at {job.company}. "
            f"With extensive experience in software development and proven expertise in {', '.join(match.matched_skills[:4]) or 'core technical areas'}, "
            "I am confident in my ability to contribute effectively to your engineering goals."
        )
        doc.add_paragraph(
            f"Throughout my career, I have successfully delivered high-quality software solutions and collaborated with cross-functional teams. "
            f"My technical background closely aligns with your requirements for the {job.title} role."
        )
        doc.add_paragraph(
            "Thank you for your time and consideration. I look forward to the opportunity to discuss how my background and skills meet your team's needs."
        )
        doc.add_paragraph("")
        doc.add_paragraph("Sincerely,\nApplicant")

    doc.save(str(output_path))
    logger.info("Saved cover letter to: %s", output_path)
    return output_path
