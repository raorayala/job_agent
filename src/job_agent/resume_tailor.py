"""Truthful resume tailoring. Implemented in Milestone 7."""

from __future__ import annotations

from pathlib import Path

from job_agent.models import MatchExplanation, ParsedJob


def tailor_resume(
    job: ParsedJob,
    match: MatchExplanation,
    master_resume_path: Path,
    output_dir: Path,
) -> Path:
    """
    Produce an ATS-friendly tailored resume using only factual master-resume content.

    Never invents qualifications.
    """
    raise NotImplementedError("Resume tailoring lands in Milestone 7.")
