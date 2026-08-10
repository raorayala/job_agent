"""Tests for unified email sync and Outlook/Hotmail IMAP helpers."""

from email.message import EmailMessage

from job_agent.config import Settings
from job_agent.email_sync_service import normalize_email_provider, email_provider_status
from job_agent.imap_email_client import _looks_like_job_alert, extract_imap_body


def test_normalize_email_provider_aliases():
    assert normalize_email_provider("gmail") == "gmail"
    assert normalize_email_provider("hotmail") == "outlook"
    assert normalize_email_provider("outlook") == "outlook"
    assert normalize_email_provider("live") == "outlook"


def test_job_alert_detection():
    assert _looks_like_job_alert("alerts@indeed.com", "New jobs for you", "Software Engineer")
    assert not _looks_like_job_alert("friend@example.com", "Lunch?", "See you soon")


def test_extract_imap_body_prefers_html():
    msg = EmailMessage()
    msg.set_content("plain text body")
    msg.add_alternative("<html><body><a href='https://indeed.com/viewjob'>Engineer</a></body></html>", subtype="html")
    body = extract_imap_body(msg)
    assert "indeed.com" in body or "Engineer" in body


def test_email_provider_status_outlook_requires_imap(tmp_path):
    settings = Settings(
        project_root=tmp_path,
        master_resume_path=None,
        jobs_applied_folder=tmp_path / "jobs",
        jobs_draft_folder=tmp_path / "drafts",
        preferred_browser="system",
        gmail_credentials_path=tmp_path / "missing.json",
        gmail_token_path=tmp_path / "token.json",
        gmail_search_query="",
        gmail_label=None,
        imap_host="outlook.office365.com",
        imap_port=993,
        imap_username="",
        imap_password="",
        imap_folder="INBOX",
        min_match_score=60.0,
        llm_provider="none",
        ollama_base_url="",
        ollama_model="",
        database_path=tmp_path / "db.sqlite",
        log_level="INFO",
        config_path=tmp_path / "config.yaml",
    )
    status = email_provider_status(settings)
    assert status["gmail"]["configured"] is False
    assert status["outlook"]["configured"] is False
