"""Tests for Desktop/Jobs Applied path helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from job_agent.document_exporter import application_folder, resume_filename, safe_filename


def test_safe_filename() -> None:
    assert "Acme" in safe_filename("Acme / Inc!")
    assert "/" not in safe_filename("A/B")


def test_resume_filename_format() -> None:
    name = resume_filename("Acme", "Python Developer", when=date(2026, 8, 5))
    assert name == "Acme_Python_Developer_2026-08-05_Resume.docx"


def test_application_folder_creates(tmp_path: Path) -> None:
    folder = application_folder(tmp_path, "Acme Inc", "Backend Engineer")
    assert folder.exists()
    assert folder.parent.name.startswith("Acme")
