"""Desktop notification service for Job Search Agent (Windows toast alerts)."""

from __future__ import annotations

import os
import subprocess
import sys
from job_agent.logging_config import get_logger

logger = get_logger(__name__)


def send_desktop_notification(title: str, message: str) -> bool:
    """
    Send a native desktop toast notification on Windows/macOS/Linux.
    Fails silently and safely if toast notifications are disabled.
    """
    try:
        if sys.platform == "win32":
            # Use PowerShell to invoke native Windows Notification toast
            title_clean = title.replace('"', '""').replace("'", "''")
            msg_clean = message.replace('"', '""').replace("'", "''")
            ps_script = (
                f'$wshell = New-Object -ComObject WScript.Shell; '
                f'$wshell.Popup("{msg_clean}", 5, "{title_clean}", 64)'
            )
            # Run PowerShell script in non-blocking background
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return True
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'display notification "{message}" with title "{title}"'])
            return True
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["notify-send", title, message])
            return True
    except Exception as exc:
        logger.debug("Desktop notification could not be delivered: %s", exc)

    return False
