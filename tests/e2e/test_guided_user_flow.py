"""Guided end-to-end walkthrough in visible Chrome with 30-second pauses between steps."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flow_helpers import accept_dialogs, click_tab, flow_step

pytestmark = [pytest.mark.e2e, pytest.mark.guided]

TOTAL_STEPS = 12


@pytest.fixture(autouse=True)
def _guided_pause_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guided tests always pause 30s per step unless overridden."""
    monkeypatch.setenv("E2E_FLOW_PAUSE_SECONDS", "30")


def test_guided_full_application_walkthrough(page: Page, web_base_url: str) -> None:
    """Walk through every major Web Console flow with pauses for user comprehension."""
    accept_dialogs(page)

    # Step 1 — Dashboard & health
    flow_step(
        page,
        1,
        TOTAL_STEPS,
        "Dashboard overview",
        "The dashboard shows pipeline stats, system health, and your onboarding checklist. "
        "Verify database path, Gmail OAuth, and master resume status here.",
    )
    page.goto(web_base_url)
    page.wait_for_load_state("networkidle")
    expect(page).to_have_title(re.compile(r"Job Search Agent Web Console"))
    expect(page.locator("#system-health-card")).to_be_visible()
    expect(page.locator("#getting-started-flow")).to_be_visible()

    # Step 2 — Load demo jobs
    flow_step(
        page,
        2,
        TOTAL_STEPS,
        "Load sample jobs",
        "Click Load Demo Jobs to insert three sample listings without network access. "
        "Use this to explore scoring, editing, and resume review before real imports.",
    )
    page.get_by_role("button", name="Load Demo Jobs").click()
    page.get_by_role("button", name="Load 3 Demo Jobs").click()
    page.locator("#seedDemoModal").wait_for(state="hidden", timeout=30000)
    expect(page.locator("#recent-jobs-table tbody tr").first).to_contain_text("#", timeout=20000)

    # Step 3 — Re-score jobs
    flow_step(
        page,
        3,
        TOTAL_STEPS,
        "Re-score against your profile",
        "Re-Score Jobs runs the matcher on every saved job using your config.yaml profile "
        "and master resume text. High-Match (≥65) appears in the table above.",
    )
    page.get_by_role("button", name="Re-Score Jobs").click()
    page.wait_for_timeout(2000)
    expect(page.locator("#stat-total-jobs")).not_to_have_text("-", timeout=30000)

    # Step 4 — Edit a job
    flow_step(
        page,
        4,
        TOTAL_STEPS,
        "Edit job details",
        "Fix incomplete imports by editing title, company, location, and description. "
        "Saving automatically re-scores the job for better match accuracy.",
    )
    page.locator("#recent-jobs-table button", has_text="Edit").first.click()
    expect(page.locator("#editJobModal")).to_be_visible()
    page.locator("#edit-job-title").fill("Guided Walkthrough Test Engineer")
    page.get_by_role("button", name="Save & Re-Score").click()
    expect(page.locator("#editJobModal")).to_be_hidden(timeout=15000)
    expect(page.locator("#recent-jobs-table")).to_contain_text("Guided Walkthrough Test Engineer", timeout=15000)

    # Step 5 — Job Discovery
    flow_step(
        page,
        5,
        TOTAL_STEPS,
        "Job Discovery platforms",
        "Select recommended platforms (Dice, ZipRecruiter, Indeed) or experimental sites. "
        "Each platform returns up to 3 recent jobs. Use Find Jobs Now to search.",
    )
    click_tab(page, "#discovery-tab")
    expect(page.locator("#platform-cb-dice")).to_be_attached()
    expect(page.get_by_role("button", name="Top 3 Recommended")).to_be_visible()

    # Step 6 — Mock platform search (reliable, no network)
    flow_step(
        page,
        6,
        TOTAL_STEPS,
        "Platform search results",
        "After searching, Last Platform Search Results shows per-site success, empty, or error status. "
        "If automated fetch returns zero, use Import URL or the Chrome bookmarklet.",
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

    # Step 7 — Resume Review
    flow_step(
        page,
        7,
        TOTAL_STEPS,
        "Resume Review & Approvals",
        "Select a job to compare your master resume, tailored draft, and finalized version. "
        "Approve only after you review keyword alignment and diff summary.",
    )
    click_tab(page, "#review-tab")
    expect(page.locator("#review-pane")).to_contain_text("Select Job for Resume Review")

    # Step 8 — Kanban board
    flow_step(
        page,
        8,
        TOTAL_STEPS,
        "Application Board (Kanban)",
        "Track lifecycle stages from Imported through Applied, Interviewing, Offer, or Rejected. "
        "Change status with the dropdown on each card.",
    )
    click_tab(page, "#kanban-tab")
    expect(page.locator("#kanban-board-container")).to_be_attached()

    # Step 9 — Profile editor
    flow_step(
        page,
        9,
        TOTAL_STEPS,
        "Profile & Skills Editor",
        "Edit target titles, skills, salary, and exclusions. Changes save directly to config.yaml. "
        "Live preview text under each field shows current values.",
    )
    click_tab(page, "#profile-tab")
    expect(page.locator("#preview-titles")).to_be_attached()
    expect(page.get_by_role("button", name="Save Profile Configuration")).to_be_visible()

    # Step 10 — CLI Runner
    flow_step(
        page,
        10,
        TOTAL_STEPS,
        "CLI Command Runner",
        "Run any CLI command from the browser with form controls and live terminal output. "
        "Useful when you prefer buttons over typing commands.",
    )
    click_tab(page, "#cheatsheet-tab")
    page.locator("#commands-accordion .command-card").first.wait_for(state="attached", timeout=15000)
    expect(page.get_by_text("seed-demo", exact=False).first).to_be_attached()

    # Step 11 — Database explorer
    flow_step(
        page,
        11,
        TOTAL_STEPS,
        "Database Explorer",
        "Browse SQLite tables, run read-only queries, and use cleanup tools for duplicates or test data. "
        "Purge requires explicit confirmation.",
    )
    click_tab(page, "#db-tab")
    expect(page.locator("#db-table-selector")).to_be_attached()

    # Step 12 — Bookmarklet capture
    flow_step(
        page,
        12,
        TOTAL_STEPS,
        "Chrome bookmarklet installer",
        "Install Capture Job on your Chrome bookmarks bar for sites that block automated fetch "
        "(LinkedIn, Glassdoor). Keep this server running while browsing job listings.",
    )
    page.goto(f"{web_base_url}/capture")
    expect(page.get_by_text("1-Click Bookmarklet Installer")).to_be_visible()
    expect(page.locator("#bm-code")).to_contain_text("javascript:(function()")
