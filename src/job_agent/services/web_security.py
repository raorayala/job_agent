"""Local Web Console security helpers: token auth, CORS, SQL/command guards."""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from job_agent.config import PROJECT_ROOT, get_env
from job_agent.logging_config import get_logger

logger = get_logger(__name__)

TOKEN_HEADER = "X-Console-Token"
ROLE_HEADER = "X-Console-Role"
TOKEN_FILE_NAME = "web_console_token"

# Privileged paths require a valid console token.
PRIVILEGED_API_PREFIXES = (
    "/api/db/",
    "/api/run-command",
    "/api/console-settings",
)

# DB explorer / destructive console APIs also require admin role header.
ADMIN_API_PREFIXES = (
    "/api/db/",
)

# CLI commands that must not run from User module even with a valid token.
ADMIN_ONLY_CLI_COMMANDS = frozenset(
    {
        "cleanup",
        "backup",
        "test",
        "setup",
        "seed-demo",
        "purge-data",
    }
)

_ALLOWED_ORIGINS_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

_SQL_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|"
    r"PRAGMA|VACUUM|REINDEX|GRANT|REVOKE|TRUNCATE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

_cached_token: str | None = None


def token_file_path(project_root: Path | None = None) -> Path:
    root = project_root or PROJECT_ROOT
    return root / "data" / TOKEN_FILE_NAME


def resolve_console_token(project_root: Path | None = None) -> str:
    """
    Return the Web Console API token.

    Prefer WEB_CONSOLE_TOKEN from the environment; otherwise load or create
    a persistent token under data/web_console_token (gitignored).
    """
    global _cached_token
    if _cached_token:
        return _cached_token

    env_token = (get_env("WEB_CONSOLE_TOKEN") or "").strip()
    if env_token:
        _cached_token = env_token
        return _cached_token

    path = token_file_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            _cached_token = existing
            return _cached_token

    generated = secrets.token_urlsafe(32)
    path.write_text(generated + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    logger.warning(
        "Generated WEB_CONSOLE_TOKEN at %s — keep private; required for admin/DB/CLI APIs.",
        path,
    )
    _cached_token = generated
    return _cached_token


def reset_token_cache() -> None:
    """Test helper to clear the in-process token cache."""
    global _cached_token
    _cached_token = None


def extract_request_token(headers: dict[str, str] | None) -> str:
    if not headers:
        return ""
    # BaseHTTPRequestHandler normalizes header keys; accept common casings.
    for key, value in headers.items():
        if key.lower() == TOKEN_HEADER.lower():
            return (value or "").strip()
    return ""


def is_valid_console_token(provided: str, project_root: Path | None = None) -> bool:
    expected = resolve_console_token(project_root)
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


def requires_console_token(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in PRIVILEGED_API_PREFIXES)


def requires_admin_role(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in ADMIN_API_PREFIXES)


def extract_request_role(headers: dict[str, str] | None) -> str:
    if not headers:
        return "user"
    for key, value in headers.items():
        if key.lower() == ROLE_HEADER.lower():
            role = (value or "").strip().lower()
            return role if role in {"user", "admin"} else "user"
    return "user"


def assert_admin_cli_allowed(cmd_name: str, role: str) -> None:
    if cmd_name in ADMIN_ONLY_CLI_COMMANDS and role != "admin":
        raise PermissionError(
            f"Command '{cmd_name}' requires Admin module access "
            f"(send {ROLE_HEADER}: admin)."
        )


def cors_allow_origin(origin: str | None) -> str | None:
    """
    Reflect Origin only for localhost loopback. Never return '*'.
    Same-origin browser requests typically omit Origin; callers may skip CORS headers then.
    """
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if host in _ALLOWED_ORIGINS_HOSTS:
        return origin
    return None


def validate_readonly_sql(sql: str) -> str:
    """
    Allow a single read-only SELECT/WITH query. Raises ValueError otherwise.
    """
    cleaned = (sql or "").strip()
    if not cleaned:
        raise ValueError("SQL query is required.")

    # Strip block and line comments before validation.
    no_block = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)
    no_line = re.sub(r"--.*?$", " ", no_block, flags=re.MULTILINE)
    normalized = " ".join(no_line.split())
    if not normalized:
        raise ValueError("SQL query is required.")

    # Reject stacked statements.
    if ";" in normalized.rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed.")

    core = normalized.rstrip(";").strip()
    upper = core.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("Only read-only SELECT/WITH queries are allowed.")

    if _SQL_FORBIDDEN.search(core):
        raise ValueError("SQL contains a forbidden keyword; only read-only SELECT is allowed.")

    return core


def allowed_cli_commands(command_metadata: Iterable[dict]) -> frozenset[str]:
    allowed: set[str] = set()
    for category in command_metadata:
        for cmd in category.get("commands") or []:
            name = str(cmd.get("cmd") or cmd.get("name") or "").strip()
            if name:
                allowed.add(name)
    # Always permit harmless discovery helpers used by the UI.
    allowed.update({"help", "statuses", "profile", "jobs"})
    return frozenset(allowed)


def validate_cli_command(cmd_name: str, allowed: frozenset[str]) -> str:
    name = (cmd_name or "").strip()
    if not name or name not in allowed:
        raise PermissionError(
            f"Command '{name}' is not in the Web Console allowlist. "
            "Use an approved job_agent CLI command only."
        )
    if name.startswith("-") or "/" in name or "\\" in name or ".." in name:
        raise PermissionError("Invalid command name.")
    return name
