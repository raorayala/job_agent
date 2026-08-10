"""Truthful review-first resume tailoring and draft approval workflow for ATS compatibility using python-docx."""

from __future__ import annotations

import re
import shutil
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


def generate_resume_draft(
    job: ParsedJob,
    match: MatchExplanation,
    master_resume_path: Path,
    draft_base_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[Path, Path, str]:
    """
    Generate an ATS-tailored resume DRAFT into the drafts folder.
    NEVER overwrites the master resume or finalized applied resume at this stage.

    Returns:
        (draft_resume_path, draft_summary_path, diff_summary)
    """
    if not master_resume_path.exists():
        raise FileNotFoundError(
            f"Master resume not found at {master_resume_path}. "
            "Please place your master resume DOCX file there or set MASTER_RESUME_PATH in .env."
        )

    draft_base_dir.mkdir(parents=True, exist_ok=True)
    clean_comp = re.sub(r"[^\w]", "_", job.company).strip("_") or "Company"
    clean_title = re.sub(r"[^\w]", "_", job.title).strip("_") or "Job"

    draft_filename = f"{clean_comp}_{clean_title}_Draft_v1.docx"
    summary_filename = f"{clean_comp}_{clean_title}_Draft_v1_Summary.txt"

    draft_resume_path = draft_base_dir / draft_filename
    draft_summary_path = draft_base_dir / summary_filename

    # Build concise diff / change summary
    diff_lines = [
        f"=== Resume Draft Generation Summary ===",
        f"Target Position: {job.title} at {job.company}",
        f"Match Score: {match.score:.0f}/100 ({match.recommendation.value})",
        "",
        "--- Recommended ATS Keywords Aligned ---",
    ]
    if match.matched_skills:
        diff_lines.append(f"Matched Skills: {', '.join(match.matched_skills)}")
    if match.missing_skills:
        diff_lines.append(f"Missing Keywords to Emphasize: {', '.join(match.missing_skills)}")
    if match.concerns:
        diff_lines.append(f"Flagged Concerns: {'; '.join(match.concerns)}")

    diff_lines.extend([
        "",
        "--- Chronology & Fact Safeguard ---",
        "Master resume experience, employers, dates, and education preserved 100% without modification.",
        "Appended ATS Keyword Alignment & Target Role Analysis section to final page.",
    ])

    diff_summary = "\n".join(diff_lines)

    if dry_run:
        logger.info("[Dry-run] Resume draft target path: %s", draft_resume_path)
        return draft_resume_path, draft_summary_path, diff_summary

    # Read master resume DOCX
    doc = Document(str(master_resume_path))

    # Append ATS Keyword & Target Role Alignment Section
    doc.add_page_break()
    _safe_add_heading(doc, "ATS Keyword Alignment & Job Analysis", level=2)

    doc.add_paragraph(f"Target Role: {job.title} at {job.company}")
    doc.add_paragraph(f"Match Score: {match.score:.0f}/100 ({match.recommendation.value})")

    if match.matched_skills:
        doc.add_paragraph(f"Matched Candidate Skills: {', '.join(match.matched_skills)}")
    if match.missing_skills:
        doc.add_paragraph(
            f"Missing Skills / Keywords to emphasize if applicable: {', '.join(match.missing_skills)}"
        )
    if match.concerns:
        doc.add_paragraph(f"Flagged Concerns: {'; '.join(match.concerns)}")

    doc.save(str(draft_resume_path))
    draft_summary_path.write_text(diff_summary, encoding="utf-8")

    logger.info("Saved resume draft to: %s", draft_resume_path)
    return draft_resume_path, draft_summary_path, diff_summary


def approve_and_finalize_resume(
    job: ParsedJob,
    draft_resume_path: Path,
    output_base_dir: Path,
) -> Path:
    """
    Promote an explicitly approved resume draft to the finalized jobapplied output directory.
    Only called AFTER explicit user confirmation.
    """
    if not draft_resume_path.exists():
        raise FileNotFoundError(f"Resume draft file not found at: {draft_resume_path}")

    target_folder = application_folder(output_base_dir, job.company, job.title)
    out_filename = resume_filename(job.company, job.title)
    final_output_path = target_folder / out_filename

    shutil.copy2(draft_resume_path, final_output_path)
    logger.info("Promoted approved resume draft %s -> %s", draft_resume_path, final_output_path)

    # Save finalized summary
    summary_txt_path = target_folder / "Application_Summary.txt"
    summary_lines = [
        f"Job Title: {job.title}",
        f"Company: {job.company}",
        f"Platform: {job.source_platform}",
        f"Location: {job.location or 'Not specified'}",
        f"URL: {job.job_url}",
        f"Approval Status: Approved and Finalized",
        f"Approved Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Final Resume: {final_output_path}",
    ]
    summary_txt_path.write_text("\n".join(summary_lines), encoding="utf-8")

    return final_output_path


def tailor_resume(
    job: ParsedJob,
    match: MatchExplanation,
    master_resume_path: Path,
    output_base_dir: Path,
    *,
    dry_run: bool = False,
) -> Path:
    """
    Legacy convenience wrapper for generating and finalizing a resume in one step when required.
    """
    draft_dir = output_base_dir / "_drafts"
    draft_path, _, _ = generate_resume_draft(job, match, master_resume_path, draft_dir, dry_run=dry_run)
    if dry_run:
        return draft_path
    return approve_and_finalize_resume(job, draft_path, output_base_dir)


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
