"""Update E2E tests for admin/user mode separation."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flow_helpers import accept_dialogs, click_tab, switch_console_mode

pytestmark = pytest.mark.e2e


def test_dashboard_user_mode_default(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    expect(page).to_have_title(re.compile(r"Job Search Agent Web Console"))
    expect(page.locator("#console-mode-badge")).to_contain_text("User Mode")
    expect(page.locator("#user-focus-banner")).to_be_visible()
    expect(page.locator("#user-setup-status-card")).to_be_visible()
    expect(page.locator("#system-health-card")).to_be_hidden()
    expect(page.locator("#db-tab")).to_be_hidden()


def test_console_mode_toggle_shows_admin_tools(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    expect(page.locator("#system-health-card")).to_be_visible()
    expect(page.locator("#db-tab")).to_be_attached()
    expect(page.locator("#profile-tab")).to_be_attached()
    switch_console_mode(page, "user")
    expect(page.locator("#user-focus-banner")).to_be_visible()
    expect(page.locator("#db-tab")).to_be_hidden()


def test_load_demo_jobs_in_admin_mode(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    page.get_by_role("button", name="Load Demo Jobs").click()
    page.get_by_role("button", name="Load 3 Demo Jobs").click()
    expect(page.locator("#recent-jobs-table tbody tr").first).to_contain_text("#", timeout=20000)


def test_main_navigation_user_tabs(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    for tab_id, pane_id in [
        ("#discovery-tab", "#discovery-pane"),
        ("#review-tab", "#review-pane"),
        ("#kanban-tab", "#kanban-pane"),
    ]:
        click_tab(page, tab_id)
        expect(page.locator(pane_id)).to_be_attached()


def test_system_health_shows_checklist_in_admin_mode(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    health = page.locator("#system-health-card")
    expect(health).to_contain_text("System Health")
    expect(health).to_contain_text("Database")


def test_discovery_platform_selection_ui(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    click_tab(page, "#discovery-tab")
    expect(page.locator("#platform-cb-dice")).to_be_attached()
    expect(page.get_by_role("button", name="Top 3 Recommended")).to_be_visible()


def test_capture_page_bookmarklet_installer(page: Page, web_base_url: str) -> None:
    page.goto(f"{web_base_url}/capture")
    expect(page.get_by_text("1-Click Bookmarklet Installer")).to_be_visible()
    expect(page.locator("#bm-code")).to_contain_text("javascript:(function()")


def test_cli_runner_admin_only(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    click_tab(page, "#cheatsheet-tab")
    page.locator("#commands-accordion .command-card").first.wait_for(state="attached", timeout=15000)
    expect(page.get_by_text("fetch-jobs", exact=False).first).to_be_attached()


def test_profile_editor_admin_only(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    click_tab(page, "#profile-tab")
    expect(page.get_by_role("button", name="Save Profile Configuration")).to_be_visible()


def test_database_explorer_admin_only(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    click_tab(page, "#db-tab")
    expect(page.locator("#db-table-selector")).to_be_attached()
