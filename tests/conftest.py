"""Shared pytest configuration for all test modules."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: browser end-to-end tests (require Playwright Chromium)")
    config.addinivalue_line("markers", "guided: paced Chrome walkthrough (30s per step)")
