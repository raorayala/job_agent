"""Fixtures for Playwright browser E2E tests against the local Web Console."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from job_agent.web_dashboard import start_web_dashboard_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def e2e_database_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Isolated SQLite database for browser E2E tests."""
    db_dir = tmp_path_factory.mktemp("e2e_db")
    return db_dir / "jobs.db"


@pytest.fixture(scope="session")
def e2e_config_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Isolated config so E2E mode toggles do not mutate the project config.yaml."""
    cfg_dir = tmp_path_factory.mktemp("e2e_cfg")
    cfg = cfg_dir / "config.yaml"
    cfg.write_text(
        "web_console:\n  default_mode: user\n  guided_flow_pause_seconds: 15\n  setup_locked: false\n",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture(scope="session")
def web_base_url(e2e_database_path: Path, e2e_config_path: Path) -> str:
    """Start Web Console on a dynamic port with an isolated test database."""
    os.environ["DATABASE_PATH"] = str(e2e_database_path)
    os.environ["CONFIG_PATH"] = str(e2e_config_path)
    port = _free_port()
    server = start_web_dashboard_server(host="127.0.0.1", port=port)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def isolate_console_mode_storage(page) -> None:
    """Each E2E test starts in User Mode without prior browser state."""
    page.add_init_script("localStorage.removeItem('job_agent_console_mode');")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Desktop viewport matching typical Chrome usage."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict, pytestconfig: pytest.Config) -> dict:
    """Default: visible Google Chrome. Use --headless for automation/CI."""
    args = {**browser_type_launch_args}
    headed = pytestconfig.getoption("--headed")
    channel = pytestconfig.getoption("--browser-channel")
    if headed:
        args["headless"] = False
        args["channel"] = channel or "chrome"
    elif channel:
        args["channel"] = channel
    return args
