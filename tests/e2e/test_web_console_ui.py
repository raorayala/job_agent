"""E2E tests for exclusive admin/user modules and left sidebar navigation."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flow_helpers import click_tab, enter_module, switch_console_mode

pytestmark = pytest.mark.e2e


def test_module_gate_shows_user_and_admin(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    expect(page).to_have_title(re.compile(r"Job Search Agent Web Console"))
    expect(page.locator("#module-gate")).to_be_visible()
    expect(page.locator("#enter-user-module")).to_contain_text("USER Module")
    expect(page.locator("#enter-admin-module")).to_contain_text("ADMIN Module")


def test_user_module_exclusive_sidebar(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    enter_module(page, "user")
    expect(page.locator("#console-mode-badge")).to_contain_text("User Mode")
    expect(page.locator("#app-sidebar")).to_be_visible()
    expect(page.locator("#user-sidebar-nav")).to_be_visible()
    expect(page.locator("#admin-sidebar-nav")).to_be_hidden()
    expect(page.locator("#dashboard-tab")).to_be_visible()
    expect(page.locator("#cls-tab")).to_contain_text("CLS")
    expect(page.locator("#discovery-tab")).to_be_visible()
    expect(page.locator("#db-tab")).to_be_hidden()
    expect(page.locator("#profile-tab")).to_be_hidden()
    expect(page.locator("#system-health-card")).to_be_hidden()
    expect(page.locator("#user-focus-banner")).to_be_visible()


def test_admin_module_exclusive_sidebar(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    expect(page.locator("#admin-sidebar-nav")).to_be_visible()
    expect(page.locator("#user-sidebar-nav")).to_be_hidden()
    expect(page.locator("#system-health-card")).to_be_visible()
    expect(page.locator("#db-tab")).to_be_visible()
    expect(page.locator("#profile-tab")).to_be_visible()
    expect(page.locator("#discovery-tab")).to_be_hidden()
    expect(page.locator("#review-tab")).to_be_hidden()
    expect(page.locator("#cls-tab")).to_be_hidden()


def test_load_demo_jobs_in_admin_mode(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    page.get_by_role("button", name="Load Demo Jobs").click()
    page.get_by_role("button", name="Load 3 Demo Jobs").click()
    expect(page.locator("#admin-recent-jobs-table tbody tr").first).to_contain_text("#", timeout=20000)


def test_main_navigation_user_web_tasks(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    enter_module(page, "user")
    for tab_id, pane_id in [
        ("#discovery-tab", "#discovery-pane"),
        ("#review-tab", "#review-pane"),
        ("#kanban-tab", "#kanban-pane"),
        ("#cls-tab", "#cls-pane"),
    ]:
        click_tab(page, tab_id)
        expect(page.locator(pane_id)).to_be_visible()


def test_ai_optimize_panel_on_review_tab(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    enter_module(page, "user")
    click_tab(page, "#review-tab")
    expect(page.locator("#ai-optimize-panel")).to_be_attached()
    expect(page.get_by_role("button", name="Run AI Optimize")).to_be_attached()


def test_system_health_shows_checklist_in_admin_mode(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    health = page.locator("#system-health-card")
    expect(health).to_contain_text("System Health")
    expect(health).to_contain_text("Database")


def test_discovery_platform_selection_ui(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    enter_module(page, "user")
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
    expect(page.locator("#profile-optimize-panel")).to_be_attached()
    expect(page.get_by_role("button", name="Analyze Profile")).to_be_visible()


def test_database_explorer_admin_only(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    switch_console_mode(page, "admin")
    click_tab(page, "#db-tab")
    expect(page.locator("#db-table-selector")).to_be_attached()
