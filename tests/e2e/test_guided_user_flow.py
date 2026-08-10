"""Guided end-to-end walkthrough in visible Chrome with configurable pauses between steps."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flow_helpers import accept_dialogs, click_tab, enter_module, flow_step, switch_console_mode

pytestmark = [pytest.mark.e2e, pytest.mark.guided]

TOTAL_STEPS = 13


def test_guided_user_and_admin_walkthrough(page: Page, web_base_url: str) -> None:
    """Walk through User daily flows, then Admin setup flows, with pauses for comprehension."""
    accept_dialogs(page)

    flow_step(
        page,
        1,
        TOTAL_STEPS,
        "User Module — choose role then dashboard",
        "The app opens on a USER / ADMIN module chooser so roles stay clear. "
        "Enter User Module for daily job search and resume review.",
    )
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    expect(page).to_have_title(re.compile(r"Job Search Agent Web Console"))
    expect(page.locator("#module-gate")).to_be_visible()
    enter_module(page, "user")
    expect(page.locator("#console-mode-badge")).to_contain_text("User Mode")
    expect(page.locator("#user-focus-banner")).to_be_visible()
    expect(page.locator("#user-setup-status-card")).to_be_visible()

    flow_step(
        page,
        2,
        TOTAL_STEPS,
        "User Mode — Job Discovery",
        "Select recommended platforms and run Find Jobs Now. Each platform returns up to 3 recent jobs.",
    )
    click_tab(page, "#discovery-tab")
    expect(page.locator("#platform-cb-dice")).to_be_attached()

    flow_step(
        page,
        3,
        TOTAL_STEPS,
        "User Mode — search results",
        "Per-platform status appears after searching. If a site blocks bots, use Import URL or the bookmarklet.",
    )
    page.route(
        "**/api/jobs/find",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"status":"success","jobs_recorded":1,"platforms_searched":["dice"],'
                '"limit_per_platform":3,"platform_reports":[{"platform":"dice","tier":"recommended",'
                '"status":"success","imported":1,"message":"Guided test mock"}]}'
            ),
        ),
    )
    page.locator("#btn-find-jobs-now").click()
    expect(page.locator("#platform-search-results-card")).to_be_visible(timeout=30000)

    flow_step(
        page,
        4,
        TOTAL_STEPS,
        "User Mode — Resume Review",
        "Compare master resume, tailored draft, and finalized version. Approve only after reviewing diffs.",
    )
    click_tab(page, "#review-tab")
    expect(page.locator("#review-pane")).to_contain_text("Select Job for Resume Review")

    flow_step(
        page,
        5,
        TOTAL_STEPS,
        "User Mode — Application Board",
        "Track Imported → Applied → Interviewing on the Kanban board using the status dropdown on each card.",
    )
    click_tab(page, "#kanban-tab")
    expect(page.locator("#kanban-board-container")).to_be_attached()

    flow_step(
        page,
        6,
        TOTAL_STEPS,
        "Switch to Admin Setup",
        "Administrators configure the app once in Admin Mode: profile, database, demo data, and CLI tools. "
        "Click Admin Setup in the header.",
    )
    switch_console_mode(page, "admin")
    expect(page.locator("#system-health-card")).to_be_visible()
    expect(page.locator("#getting-started-flow")).to_be_visible()

    flow_step(
        page,
        7,
        TOTAL_STEPS,
        "Admin — load demo jobs",
        "Insert three sample jobs for training and smoke tests. Safe on a fresh database.",
    )
    click_tab(page, "#dashboard-tab")
    page.get_by_role("button", name="Load Demo Jobs").click()
    page.get_by_role("button", name="Load 3 Demo Jobs").click()
    page.locator("#seedDemoModal").wait_for(state="hidden", timeout=30000)
    expect(page.locator("#recent-jobs-table tbody tr").first).to_contain_text("#", timeout=20000)

    flow_step(
        page,
        8,
        TOTAL_STEPS,
        "Admin — re-score jobs",
        "Re-Score Jobs updates match scores after profile or resume changes in config.yaml.",
    )
    page.get_by_role("button", name="Re-Score Jobs").click()
    expect(page.locator("#stat-total-jobs")).not_to_have_text("-", timeout=30000)

    flow_step(
        page,
        9,
        TOTAL_STEPS,
        "Admin — edit job details",
        "Fix incomplete imports; saving re-scores automatically for better match accuracy.",
    )
    page.locator("#recent-jobs-table button", has_text="Edit").first.click()
    expect(page.locator("#editJobModal")).to_be_visible()
    page.locator("#edit-job-title").fill("Guided Walkthrough Test Engineer")
    page.get_by_role("button", name="Save & Re-Score").click()
    expect(page.locator("#editJobModal")).to_be_hidden(timeout=15000)

    flow_step(
        page,
        10,
        TOTAL_STEPS,
        "Admin — Profile & Skills Editor",
        "Configure titles, skills, salary, and exclusions once. Changes persist in config.yaml.",
    )
    click_tab(page, "#profile-tab")
    expect(page.locator("#preview-titles")).to_be_attached()

    flow_step(
        page,
        11,
        TOTAL_STEPS,
        "Admin — CLI Command Runner",
        "Run maintenance and discovery commands with form controls and live terminal output.",
    )
    click_tab(page, "#cheatsheet-tab")
    page.locator("#commands-accordion .command-card").first.wait_for(state="attached", timeout=15000)
    expect(page.get_by_text("seed-demo", exact=False).first).to_be_attached()

    flow_step(
        page,
        12,
        TOTAL_STEPS,
        "Admin — Database Explorer",
        "Browse SQLite tables, run queries, and purge test data when needed.",
    )
    click_tab(page, "#db-tab")
    expect(page.locator("#db-table-selector")).to_be_attached()

    flow_step(
        page,
        13,
        TOTAL_STEPS,
        "Bookmarklet installer",
        "Install Capture Job on Chrome's bookmarks bar for LinkedIn, Glassdoor, and other blocked sites.",
    )
    page.goto(f"{web_base_url}/capture")
    expect(page.get_by_text("1-Click Bookmarklet Installer")).to_be_visible()
