"""Allowlisted CLI execution for the local Web Console."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Iterable

from job_agent.logging_config import get_logger
from job_agent.services.web_security import allowed_cli_commands, validate_cli_command

logger = get_logger(__name__)


def execute_cli_command(
    cmd_name: str,
    raw_args: list[str],
    *,
    command_metadata: Iterable[dict] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """
    Execute `python -m job_agent <cmd_name> <args>` for allowlisted commands only.
    """
    allowed = allowed_cli_commands(command_metadata or [])
    safe_name = validate_cli_command(cmd_name, allowed)

    # Reject args that look like shell metacharacter injection into unrelated tools.
    safe_args: list[str] = []
    for arg in raw_args:
        text = str(arg)
        if "\x00" in text:
            raise PermissionError("Null bytes are not allowed in command arguments.")
        safe_args.append(text)

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [sys.executable, "-m", "job_agent", safe_name, *safe_args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        output = (stdout + ("\n" + stderr if stderr else "")).strip()
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": output or "(Command produced no console output)",
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "output": f"Command timed out after {timeout_seconds}s.",
            "command": " ".join(cmd),
        }
    except PermissionError:
        raise
    except Exception as exc:
        logger.exception("CLI runner failed for %s", safe_name)
        return {
            "success": False,
            "exit_code": -1,
            "output": f"Command failed: {exc}",
            "command": " ".join(cmd),
        }
