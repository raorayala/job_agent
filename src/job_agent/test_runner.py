"""Unified test suite runner for unit, API, and browser E2E tests."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class TestRunResult:
    exit_code: int
    command: list[str]


def install_playwright_browsers(*, chrome: bool = True) -> int:
    """Install browser binaries for Playwright E2E tests (Google Chrome by default)."""
    browser = "chrome" if chrome else "chromium"
    return subprocess.call([sys.executable, "-m", "playwright", "install", browser])


def run_test_suite(
    *,
    coverage: bool = False,
    e2e: bool = True,
    verbose: bool = False,
    headless: bool = False,
    extra_args: list[str] | None = None,
) -> TestRunResult:
    """Run pytest across unit, HTTP API, and optional browser E2E tests."""
    cmd: list[str] = [sys.executable, "-m", "pytest", "tests"]

    if not e2e:
        cmd.extend(["-m", "not e2e"])
    elif headless:
        cmd.extend(["--browser-channel=chromium"])
    else:
        # Visible Google Chrome — matches end-user testing expectations.
        cmd.extend(["--headed", "--browser-channel=chrome"])

    if coverage:
        cmd.extend(["--cov=job_agent", "--cov-report=term-missing"])

    cmd.append("-v" if verbose else "-q")

    if extra_args:
        cmd.extend(extra_args)

    exit_code = subprocess.call(cmd)
    return TestRunResult(exit_code=exit_code, command=cmd)
