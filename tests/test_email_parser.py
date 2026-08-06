"""Tests for platform email parsing."""

from __future__ import annotations

from datetime import datetime, timezone

from job_agent.email_parser import (
    clean_html_text,
    detect_platform,
    extract_employment_type,
    extract_salary,
    extract_skills_from_text,
    parse_email,
)


def test_detect_platform() -> None:
    assert detect_platform("jobs-noreply@ziprecruiter.com", "") == "ziprecruiter"
    assert detect_platform("alert@indeed.com", "") == "indeed"
    assert detect_platform("noreply@glassdoor.com", "") == "glassdoor"
    assert detect_platform("alerts@dice.com", "") == "dice"
    assert detect_platform("notifications@lensa.com", "") == "lensa"
    assert detect_platform("unknown@random.com", "Hello world") == "unknown"


def test_clean_html_text() -> None:
    html = "<html><body><h1>Senior Python Developer</h1><p>Location: Remote</p></body></html>"
    text = clean_html_text(html)
    assert "Senior Python Developer" in text
    assert "Location: Remote" in text


def test_extract_salary() -> None:
    text = "We offer $130,000 - $160,000 a year with great benefits."
    sal = extract_salary(text)
    assert sal is not None
    assert "$130,000" in sal


def test_extract_employment_type() -> None:
    text = "This is a full-time remote contract position."
    emp = extract_employment_type(text)
    assert emp is not None
    assert "full-time" in emp
    assert "remote" in emp


def test_parse_email_single_job() -> None:
    email = {
        "id": "msg_001",
        "subject": "Job Alert: Senior Python Developer at Acme Corp",
        "from": "alert@indeed.com",
        "received_at": datetime.now(timezone.utc),
        "body": "<html><body>Senior Python Developer at Acme Corp.<br>Location: Remote<br>Salary: $140,000 per year<br>https://www.indeed.com/viewjob?jk=12345</body></html>",
    }

    jobs = parse_email(email)
    assert len(jobs) == 1
    job = jobs[0]
    assert "Python" in job.title
    assert job.company == "Acme Corp"
    assert job.source_platform == "indeed"
    assert "indeed.com/viewjob" in job.job_url
