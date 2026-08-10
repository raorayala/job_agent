"""Playwright browser E2E tests for the Job Search Agent Web Console."""

from __future__ import annotations

import re
from typing import Callable

import pytest
from playwright.sync_api import Dialog, Page, expect

pytestmark = pytest.mark.e2e


def _accept_dialogs(page: Page) -> None:
    def handler(dialog: Dialog) -> None:
        dialog.accept()

    page.on("dialog", handler)


def _click_tab(page: Page, tab_id: str) -> None:
    tab = page.locator(tab_id)
    tab.click()
    expect(tab).to_have_attribute("aria-selected", "true")


def test_dashboard_homepage_loads(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    expect(page).to_have_title(re.compile(r"Job Search Agent Web Console"))
    expect(page.locator("h4")).to_contain_text("Job Search Agent")
    expect(page.locator("#global-progress-wrapper")).to_be_attached()
    expect(page.locator("#system-health-card")).to_be_visible()
    expect(page.locator("#getting-started-flow")).to_be_visible()


def test_main_navigation_tabs(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")

    tab_checks: list[tuple[str, str, Callable[[Page], None]]] = [
        (
            "#discovery-tab",
            "#discovery-pane",
            lambda p: expect(p.locator("#btn-find-jobs-now")).to_be_attached(),
        ),
        (
            "#review-tab",
            "#review-pane",
            lambda p: expect(p.locator("#review-pane")).to_contain_text("Select Job for Resume Review"),
        ),
        (
            "#kanban-tab",
            "#kanban-pane",
            lambda p: expect(p.locator("#kanban-board-container")).to_be_attached(),
        ),
        (
            "#db-tab",
            "#db-pane",
            lambda p: expect(p.locator("#db-table-selector")).to_be_attached(),
        ),
        (
            "#profile-tab",
            "#profile-pane",
            lambda p: expect(p.locator("#preview-titles")).to_be_attached(),
        ),
        (
            "#cheatsheet-tab",
            "#cheatsheet-pane",
            lambda p: expect(p.locator("#cheatsheet-pane")).to_contain_text("CLI Command Runner"),
        ),
    ]

    for tab_id, pane_id, verify in tab_checks:
        _click_tab(page, tab_id)
        expect(page.locator(pane_id)).to_be_attached()
        verify(page)

    _click_tab(page, "#dashboard-tab")
    expect(page.locator("#recent-jobs-table")).to_be_attached()


def test_system_health_shows_checklist(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    health = page.locator("#system-health-card")
    expect(health).to_contain_text("System Health")
    expect(health).to_contain_text("Database")


def test_load_demo_jobs_populates_recent_jobs(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Load Demo Jobs").click()
    page.get_by_role("button", name="Load 3 Demo Jobs").click()
    expect(page.locator("#recent-jobs-table tbody tr").first).to_contain_text("#", timeout=20000)


def test_discovery_platform_selection_ui(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    _click_tab(page, "#discovery-tab")
    dice = page.locator("#platform-cb-dice")
    dice.wait_for(state="attached", timeout=10000)
    expect(page.locator("#btn-find-jobs-now")).to_be_visible()
    expect(page.locator(".platform-checkbox").first).to_be_attached()
    expect(page.get_by_role("button", name="Top 3 Recommended")).to_be_visible()
    expect(dice).to_be_checked()


def test_capture_page_bookmarklet_installer(page: Page, web_base_url: str) -> None:
    page.goto(f"{web_base_url}/capture")
    expect(page.get_by_text("1-Click Bookmarklet Installer")).to_be_visible()
    expect(page.get_by_role("button", name="Mark as Installed")).to_be_visible()
    expect(page.locator("#bm-code")).to_contain_text("javascript:(function()")


def test_install_bookmarklet_link_from_dashboard(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    link = page.locator('a[href="/capture"]').first
    expect(link).to_be_visible()
    expect(link).to_contain_text("Install Bookmarklet")


def test_cli_runner_tab_lists_commands(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    _click_tab(page, "#cheatsheet-tab")
    page.locator("#commands-accordion .command-card").first.wait_for(state="attached", timeout=15000)
    expect(page.get_by_text("fetch-jobs", exact=False).first).to_be_attached()
    expect(page.get_by_text("sync-gmail", exact=False).first).to_be_attached()


def test_profile_editor_tab_loads_fields(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    _click_tab(page, "#profile-tab")
    expect(page.locator("#preview-titles")).to_be_attached()
    expect(page.locator("#preview-req-skills")).to_be_attached()
    expect(page.get_by_role("button", name="Save Profile Configuration")).to_be_visible()


def test_database_explorer_loads_tables(page: Page, web_base_url: str) -> None:
    page.goto(web_base_url)
    _click_tab(page, "#db-tab")
    select = page.locator("#db-table-selector")
    expect(select).to_be_attached()
    expect(select.locator("option[value='jobs']")).to_be_attached()
