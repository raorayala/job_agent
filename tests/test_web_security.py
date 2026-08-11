"""Unit tests for Web Console security helpers."""

from __future__ import annotations

import pytest

from job_agent.services.web_security import (
    assert_admin_cli_allowed,
    cors_allow_origin,
    validate_cli_command,
    validate_readonly_sql,
)


def test_validate_readonly_sql_accepts_select() -> None:
    assert validate_readonly_sql("SELECT count(*) FROM jobs;") == "SELECT count(*) FROM jobs"
    assert validate_readonly_sql("  with x as (select 1) select * from x  ").lower().startswith("with")


def test_validate_readonly_sql_rejects_writes() -> None:
    with pytest.raises(ValueError):
        validate_readonly_sql("DELETE FROM jobs")
    with pytest.raises(ValueError):
        validate_readonly_sql("SELECT 1; DROP TABLE jobs")
    with pytest.raises(ValueError):
        validate_readonly_sql("UPDATE jobs SET status='x'")


def test_cors_loopback_only() -> None:
    assert cors_allow_origin("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert cors_allow_origin("http://localhost:8000") == "http://localhost:8000"
    assert cors_allow_origin("https://evil.example") is None
    assert cors_allow_origin(None) is None


def test_cli_allowlist_and_admin_gate() -> None:
    allowed = frozenset({"statuses", "cleanup", "jobs"})
    assert validate_cli_command("statuses", allowed) == "statuses"
    with pytest.raises(PermissionError):
        validate_cli_command("rm", allowed)
    assert_admin_cli_allowed("statuses", "user")
    with pytest.raises(PermissionError):
        assert_admin_cli_allowed("cleanup", "user")
    assert_admin_cli_allowed("cleanup", "admin")
