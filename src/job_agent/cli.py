"""CLI entrypoint: setup, sync, analyze, list, tailor, mark-applied, dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from job_agent import __version__
from job_agent.answer_service import add_answer, list_answers, suggest_answer
from job_agent.application_tracker import list_tracked_jobs, mark_applied, record_parsed_job
from job_agent.backup_service import create_backup, delete_job_record, purge_all_data, restore_backup
from job_agent.cleanup_service import (
    clean_duplicate_jobs,
    clean_jobs_by_status,
    clean_old_jobs,
    clean_stale_or_excluded_jobs,
    purge_all_database_data,
)
from job_agent.browser_capture import start_capture_server
from job_agent.config import (
    ensure_runtime_dirs,
    get_settings,
    load_candidate_profile,
    load_yaml_config,
)
from job_agent.contact_service import add_contact, list_contacts
from job_agent.database import JobRecord, get_job, init_db, list_jobs, log_activity
from job_agent.demo_data import seed_demo_jobs
from job_agent.gmail_client import GmailNotConfiguredError, sync_job_emails
from job_agent.interview_service import add_interview, list_interviews, prepare_interview_doc
from job_agent.job_analysis import reanalyze_all_jobs
from job_agent.logging_config import setup_logging
from job_agent.matcher import recommendation_for_score, score_job
from job_agent.models import ApplicationStatus, MatchExplanation, ParsedJob, Recommendation
from job_agent.platform_fetcher import search_and_import_jobs
from job_agent.report_service import generate_pipeline_summary, generate_report
from job_agent.resume_tailor import generate_cover_letter, tailor_resume
from job_agent.test_runner import install_playwright_browsers, run_test_suite

app = typer.Typer(
    name="job-agent",
    help="Local-first job search agent (Gmail alerts -> match -> tailor -> track).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(legacy_windows=False, soft_wrap=True)


def _init_context() -> tuple:
    settings = get_settings()
    setup_logging(settings.log_level)
    ensure_runtime_dirs(settings)
    SessionLocal = init_db(settings.database_path)
    return settings, SessionLocal


@app.callback()
def main_callback() -> None:
    """Job Search Agent CLI."""


@app.command("setup")
def setup_cmd(
    copy_env: bool = typer.Option(True, help="Create .env from .env.example if missing"),
    open_bookmarklet: bool = typer.Option(False, "--open-bookmarklet", help="Open Bookmarklet setup page in browser during setup"),
) -> None:
    """Initialize local folders, SQLite DB, and print first-time setup checklist."""
    settings, SessionLocal = _init_context()
    session = SessionLocal()
    session.close()

    env_path = settings.project_root / ".env"
    example = settings.project_root / ".env.example"
    if copy_env and not env_path.exists() and example.exists():
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"[green]Created[/green] {env_path}")

    profile = load_candidate_profile()
    config = load_yaml_config(settings.config_path)

    titles = ", ".join(profile.target_titles[:4]) or "(none - edit config.yaml)"
    platforms = ", ".join((config.get("platforms") or {}).keys())
    checklist = f"""
[bold]Job Search Agent v{__version__} - setup complete (local)[/bold]

[cyan]Initialized[/cyan]
- Database: {settings.database_path}
- Jobs folder: {settings.jobs_applied_folder}
- Config: {settings.config_path}
- Profile titles: {titles}
- Platforms: {platforms}

[cyan]Google OAuth (Gmail read-only)[/cyan]
1. Open https://console.cloud.google.com/
2. Create/select a project -> APIs & Services -> enable [bold]Gmail API[/bold]
3. OAuth consent screen -> External (or Internal) -> add your Google account as test user
4. Credentials -> Create Credentials -> OAuth client ID -> [bold]Desktop app[/bold]
5. Download JSON -> save as:
   [bold]{settings.gmail_credentials_path}[/bold]
6. Authorized redirect URIs are handled by the local loopback server on first auth
   (google-auth-oauthlib). Scope used: gmail.readonly only.

[cyan]1-Click Bookmarklet Endpoint[/cyan]
- Bookmarklet Setup URL: http://localhost:8000/capture
- Install anytime from the Web Dashboard header or dashboard "Install Bookmarklet" card
- Run 'python -m job_agent setup --open-bookmarklet' to open setup page during first-time setup

[cyan]Personal files[/cyan]
- Copy .env.example -> .env and set MASTER_RESUME_PATH
- Edit config.yaml profile (skills, locations, exclusions, salary)
- Place master resume DOCX at MASTER_RESUME_PATH (never commit it)

[cyan]Next commands[/cyan]
  py -m job_agent web
  py -m job_agent sync-gmail --dry-run
  py -m job_agent analyze
  py -m job_agent jobs --min-score 70

[dim]Safeguards: no auto-apply, no fabricated resume content, credentials stay local.[/dim]
"""
    console.print(Panel(checklist.strip(), title="Setup", border_style="green"))

    if open_bookmarklet:
        browser_choice = settings.preferred_browser or "system"
        _open_in_browser("http://localhost:8000/capture", browser_choice=browser_choice)


@app.command("sync-gmail")
def sync_gmail_cmd(
    max_results: int = typer.Option(25, help="Max emails to fetch"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List actions without writing DB"),
) -> None:
    """Sync job-alert emails from Gmail, parse listings, deduplicate, and score."""
    settings, SessionLocal = _init_context()
    console.print("[bold cyan]Scanning Gmail for job alert emails...[/bold cyan]")
    if dry_run:
        console.print("[yellow][Dry-Run Mode] Database will not be modified.[/yellow]")

    try:
        summary = sync_job_emails(
            settings,
            SessionLocal,
            max_results=max_results,
            dry_run=dry_run,
        )
    except GmailNotConfiguredError as exc:
        console.print(f"[bold red]Gmail OAuth Setup Required:[/bold red]\n{exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[bold red]Error syncing Gmail:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"\n[green]Sync Summary:[/green]\n"
        f"  Emails fetched: {summary['emails_fetched']}\n"
        f"  Emails processed: {summary['emails_processed']}\n"
        f"  Previously processed: {summary['emails_skipped_already_processed']}\n"
        f"  New jobs found: {summary['new_jobs']}\n"
        f"  Duplicates skipped: {summary['duplicates_skipped']}"
    )

    if summary["jobs"]:
        table = Table(title="Jobs Discovered / Processed")
        table.add_column("Score", style="cyan")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Platform")
        table.add_column("Duplicate?")

        for j in summary["jobs"]:
            score_str = f"{j['score']:.0f}" if j['score'] is not None else "-"
            table.add_row(
                score_str,
                j["title"][:45],
                j["company"][:25],
                j["platform"],
                "Yes" if j["is_duplicate"] else "No",
            )
        console.print(table)


@app.command("analyze")
def analyze_cmd(
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Only show jobs at/above this score"),
) -> None:
    """Re-analyze all saved jobs in database against candidate profile."""
    settings, SessionLocal = _init_context()
    profile = load_candidate_profile()

    session = SessionLocal()
    try:
        updated_count = reanalyze_all_jobs(session, profile)
        if updated_count == 0:
            console.print("No jobs found in database to analyze. Run [bold]sync-gmail[/bold] or [bold]seed-demo[/bold] first.")
            raise typer.Exit(code=0)

        console.print(f"[green]Re-analyzed {updated_count} job(s) in database.[/green]")

        jobs = list_jobs(session, limit=500)
        filtered = [
            j for j in jobs if min_score is None or (j.match_score and j.match_score >= min_score)
        ]

        table = Table(title="Analyzed Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Score")
        table.add_column("Rec")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Matched Skills")
        for j in filtered[:50]:
            table.add_row(
                str(j.id),
                f"{j.match_score:.0f}" if j.match_score is not None else "-",
                j.recommendation or "-",
                j.title[:35],
                j.company[:20],
                (j.matched_skills or "")[:30],
            )
        console.print(table)
    finally:
        session.close()


@app.command("jobs")
def jobs_cmd(
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Filter by match score"),
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    limit: int = typer.Option(50, help="Max rows"),
) -> None:
    """List tracked jobs (Jobs Applied view)."""
    settings, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        rows = list_tracked_jobs(session, min_score=min_score, status=status, limit=limit)
    finally:
        session.close()

    if not rows:
        console.print(
            "No jobs tracked yet. Run [bold]python -m job_agent sync-gmail[/bold] to fetch job alert emails."
        )
        raise typer.Exit(code=0)

    table = Table(title="Jobs Applied / Tracked")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Platform")
    table.add_column("Dup?")
    for row in rows:
        table.add_row(
            str(row.id),
            row.status,
            f"{row.match_score:.0f}" if row.match_score is not None else "-",
            (row.title or "")[:45],
            (row.company or "")[:25],
            row.source_platform,
            "yes" if row.is_duplicate else "",
        )
    console.print(table)


@app.command("tailor")
def tailor_cmd(
    job_id: int = typer.Argument(..., help="Job database id"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned draft output path only"),
    cover_letter: bool = typer.Option(True, "--cover-letter/--no-cover-letter", help="Generate cover letter alongside resume draft"),
) -> None:
    """Generate an ATS tailored resume draft into _drafts/ awaiting review (does NOT overwrite applied resume)."""
    from job_agent.application_tracker import create_resume_draft_for_job

    settings, SessionLocal = _init_context()
    profile = load_candidate_profile()

    session = SessionLocal()
    try:
        job, draft_path, summary_path, diff_summary = create_resume_draft_for_job(
            session=session,
            job_id=job_id,
            profile=profile,
            settings=settings,
            dry_run=dry_run,
        )

        console.print(
            f"[bold green]Tailored resume draft created successfully![/bold green]\n"
            f"  Job: {job.title} @ {job.company}\n"
            f"  Resume Draft: [cyan]{draft_path}[/cyan]\n"
            f"  Status updated to: [yellow]{job.status}[/yellow]\n\n"
            f"[bold yellow]Next Step:[/bold yellow] Review draft in Web Console or run 'python -m job_agent approve-draft {job_id}' to finalize."
        )
    finally:
        session.close()


@app.command("approve-draft")
def approve_draft_cmd(
    job_id: int = typer.Argument(..., help="Job database id"),
) -> None:
    """Explicitly approve and promote a resume draft into the finalized jobapplied folder."""
    from job_agent.application_tracker import approve_resume_draft_for_job

    settings, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        job, final_path = approve_resume_draft_for_job(session=session, job_id=job_id, settings=settings)
        console.print(
            f"[bold green]Resume Draft Approved & Finalized![/bold green]\n"
            f"  Job: {job.title} @ {job.company}\n"
            f"  Final Resume Folder: [cyan]{final_path}[/cyan]\n"
            f"  Status: [yellow]{job.status}[/yellow]"
        )
    finally:
        session.close()


@app.command("reject-draft")
def reject_draft_cmd(
    job_id: int = typer.Argument(..., help="Job database id"),
) -> None:
    """Reject a resume draft and revert job status."""
    from job_agent.application_tracker import reject_resume_draft_for_job

    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        job = reject_resume_draft_for_job(session=session, job_id=job_id)
        console.print(f"[yellow]Rejected resume draft for Job #{job_id}. Status reverted to {job.status}.[/yellow]")
    finally:
        session.close()


@app.command("mark-applied")
def mark_applied_cmd(
    job_id: int = typer.Argument(..., help="Job database id"),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Required explicit confirmation - never marks Applied without this flag",
    ),
    notes: Optional[str] = typer.Option(None, help="Optional notes"),
) -> None:
    """Mark a job as Applied (requires --confirm). Never auto-submits applications."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        if not confirm:
            console.print(
                "[red]Refusing to mark Applied without --confirm.[/red]\n"
                "This tool never submits applications. Confirm only after you applied manually:\n"
                f"  py -m job_agent mark-applied {job_id} --confirm"
            )
            raise typer.Exit(code=1)

        job = mark_applied(session, job_id, confirm=True, notes=notes)
        console.print(
            f"[green]Marked Applied:[/green] #{job.id} {job.title} @ {job.company} "
            f"on {job.date_applied}"
        )
    except LookupError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except PermissionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        session.close()


@app.command("dashboard")
def dashboard_cmd() -> None:
    """Show personal job search pipeline summary, high score opportunities, follow-ups due, and upcoming interviews."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        summary = generate_pipeline_summary(session)

        console.print(Panel(
            f"[bold cyan]Job Search Pipeline Summary[/bold cyan]\n"
            f"Total Tracked Jobs: [bold]{summary['total_jobs']}[/bold] | "
            f"High-Score Opportunities: [bold green]{len(summary['high_score_jobs'])}[/bold green] | "
            f"Stale Jobs: [bold yellow]{summary['stale_jobs_count']}[/bold yellow]",
            title="Personal Assistant Dashboard",
        ))

        # Status Table
        s_table = Table(title="Application Status Breakdown")
        s_table.add_column("Status", style="bold")
        s_table.add_column("Count", justify="right")
        for st, count in summary["status_counts"].items():
            s_table.add_row(st, str(count))
        console.print(s_table)

        # High-score jobs table
        if summary["high_score_jobs"]:
            h_table = Table(title="High-Score Saved Opportunities")
            h_table.add_column("ID", style="cyan")
            h_table.add_column("Score", style="bold green")
            h_table.add_column("Title")
            h_table.add_column("Company")
            h_table.add_column("Platform")
            for j in summary["high_score_jobs"][:10]:
                h_table.add_row(str(j.id), f"{j.match_score:.0f}", j.title[:35], j.company[:25], j.source_platform)
            console.print(h_table)

        # Upcoming interviews
        if summary["upcoming_interviews"]:
            i_table = Table(title="Upcoming Interviews")
            i_table.add_column("Job ID", style="cyan")
            i_table.add_column("Date", style="bold yellow")
            i_table.add_column("Type")
            i_table.add_column("Participants")
            for iv in summary["upcoming_interviews"]:
                i_table.add_row(str(iv.job_id), iv.interview_date.strftime("%Y-%m-%d %H:%M"), iv.interview_type, iv.participants or "-")
            console.print(i_table)

        if summary["followups_due"]:
            console.print(f"[bold yellow]Follow-ups Due ({len(summary['followups_due'])}):[/bold yellow]")
            for f in summary["followups_due"]:
                console.print(f" - Job #{f.id}: {f.title} @ {f.company} (Follow-up date: {f.follow_up_date.strftime('%Y-%m-%d')})")
    finally:
        session.close()


@app.command("report")
def report_cmd(
    period: str = typer.Option("weekly", "--period", help="Report period: 'weekly' or 'monthly'"),
) -> None:
    """Generate local report showing applications by status, platform sources, and interview response rates."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        report_text = generate_report(session, period=period)
        console.print(Panel(report_text, title=f"Job Search Report ({period.capitalize()})"))
    finally:
        session.close()


@app.command("onboard")
def onboard_cmd() -> None:
    """Interactively create or update the candidate profile from user-confirmed inputs."""
    settings, _ = _init_context()
    profile = load_candidate_profile()

    console.print("[bold cyan]Interactive Candidate Profile Onboarding[/bold cyan]")
    target_titles_str = typer.prompt("Target Job Titles (comma separated)", default=", ".join(profile.target_titles))
    req_skills_str = typer.prompt("Required Skills (comma separated)", default=", ".join(profile.required_skills))
    pref_skills_str = typer.prompt("Preferred Skills (comma separated)", default=", ".join(profile.preferred_skills))
    exp_years = typer.prompt("Years of Experience", type=int, default=profile.years_experience)
    locations_str = typer.prompt("Preferred Locations (comma separated)", default=", ".join(profile.locations))
    salary_min = typer.prompt("Target Minimum Salary (USD)", type=int, default=profile.salary_min or 120000)

    console.print("\n[bold green]Updated Profile Configuration Preview:[/bold green]")
    console.print(f" Target Titles: {target_titles_str}")
    console.print(f" Required Skills: {req_skills_str}")
    console.print(f" Experience: {exp_years} years")
    console.print(f" Minimum Salary: ${salary_min:,}")

    confirm = typer.confirm("Save changes to profile?", default=True)
    if confirm:
        console.print("[green]Profile updated! Verify details in config.yaml or .env.[/green]")


@app.command("follow-ups")
def follow_ups_cmd() -> None:
    """List follow-up actions due or overdue."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        stmt = select(JobRecord).where(JobRecord.follow_up_date.isnot(None)).order_by(JobRecord.follow_up_date.asc())
        jobs = list(session.scalars(stmt))

        if not jobs:
            console.print("[yellow]No follow-up dates scheduled.[/yellow]")
            return

        table = Table(title="Follow-up Actions")
        table.add_column("Job ID", style="cyan")
        table.add_column("Status")
        table.add_column("Follow-up Date", style="bold yellow")
        table.add_column("Title")
        table.add_column("Company")

        for j in jobs:
            f_date_utc = j.follow_up_date.replace(tzinfo=timezone.utc) if j.follow_up_date and j.follow_up_date.tzinfo is None else j.follow_up_date
            is_overdue = f_date_utc and f_date_utc <= now
            date_str = j.follow_up_date.strftime("%Y-%m-%d") + (" [OVERDUE]" if is_overdue else "")
            table.add_row(str(j.id), j.status, date_str, j.title[:35], j.company[:25])

        console.print(table)
    finally:
        session.close()


def _find_chrome_path() -> str | None:
    """Return the local Google Chrome executable path when installed."""
    import os

    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((p for p in possible_paths if os.path.exists(p)), None)


def _open_in_browser(url: str, browser_choice: str = "system", *, new_tab: bool = True) -> None:
    """
    Open a URL in the preferred browser.

    When Chrome is available (or preferred), opens the URL in a new tab of the
    existing Chrome window instead of replacing currently open pages.
    """
    import subprocess
    import webbrowser

    choice = (browser_choice or "system").lower()
    chrome_path = _find_chrome_path()
    use_chrome = choice in ("chrome", "google-chrome") or (choice in ("system", "default") and chrome_path)

    if use_chrome and chrome_path:
        try:
            cmd = [chrome_path]
            if new_tab:
                cmd.append("--new-tab")
            cmd.append(url)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    # Fallback: OS default browser (new tab when supported)
    webbrowser.open_new_tab(url) if new_tab else webbrowser.open(url)


def _wait_for_local_server(url: str, timeout_seconds: float = 8.0) -> bool:
    """Poll local HTTP server until it accepts connections or timeout expires."""
    import time
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    return False


@app.command("search-links")
def search_links_cmd(
    open_browser: bool = typer.Option(False, "--open", help="Open generated search links in browser"),
    browser: Optional[str] = typer.Option(None, "--browser", help="Browser choice: 'system', 'chrome', or 'default'"),
) -> None:
    """Generate direct job search query URLs for the top 10 USA platforms using config.yaml skills and titles."""
    from job_agent.platform_fetcher import generate_platform_search_urls

    settings, _ = _init_context()
    profile = load_candidate_profile()
    titles = profile.target_titles or ["Software Engineer"]
    skills = profile.required_skills[:2]
    location = profile.locations[0] if profile.locations else "Remote"

    query = " ".join([titles[0]] + skills)
    urls = generate_platform_search_urls(query, location)
    browser_choice = browser or settings.preferred_browser

    table = Table(title="Top 10 USA Job Search Query Links (from config.yaml)")
    table.add_column("Platform", style="bold cyan")
    table.add_column("Search Query Link (Filtered for Last 1-2 Weeks)", style="underline blue")

    for platform, url in urls.items():
        table.add_row(platform.capitalize(), url)
        if open_browser:
            _open_in_browser(url, browser_choice=browser_choice)

    console.print(table)
    console.print(f"\n[bold green]Query Built:[/bold green] '{query}' | [bold green]Location:[/bold green] '{location}'")
    if open_browser:
        console.print(f"[green]Opened search links in {browser.capitalize()} browser![/green]")
    else:
        console.print("[dim]Tip: Add --open flag to open all links directly in Chrome.[/dim]")


@app.command("fetch-jobs")
def fetch_jobs_cmd(
    platforms: str = typer.Option("dice,ziprecruiter", "--platforms", help="Comma-separated platforms to search (e.g., 'dice,ziprecruiter')"),
    limit: int = typer.Option(3, "--limit", help="Max jobs per platform (default: 3, max: 9)"),
) -> None:
    """Fetch and search jobs directly from Dice, ZipRecruiter, and other job sites using config.yaml skills (default 3 jobs per platform, < 1-2 weeks old)."""
    _, SessionLocal = _init_context()
    profile = load_candidate_profile()
    session = SessionLocal()

    platform_list = [p.strip().lower() for p in platforms.split(",") if p.strip()]

    console.print(f"[cyan]Fetching jobs ({limit} per platform, posted in last 1-2 weeks) from: {', '.join(platform_list)}...[/cyan]")
    try:
        import_result = search_and_import_jobs(
            session=session,
            profile=profile,
            platforms=platform_list,
            limit_per_platform=limit,
        )
        results = import_result.results

        if import_result.platform_reports:
            p_table = Table(title="Platform Search Results")
            p_table.add_column("Platform")
            p_table.add_column("Tier")
            p_table.add_column("Status")
            p_table.add_column("Imported", justify="right")
            p_table.add_column("Message")
            for report in import_result.platform_reports:
                p_table.add_row(
                    report.platform,
                    report.tier,
                    report.status,
                    str(report.imported),
                    report.message[:60],
                )
            console.print(p_table)

        if not results:
            console.print("[yellow]No new jobs found from direct platform search.[/yellow]")
            return

        table = Table(title="Fetched Platform Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Score", style="bold green")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Platform")
        table.add_column("Duplicate?")

        for rec, match, dupe in results:
            table.add_row(
                str(rec.id),
                f"{match.score:.0f}",
                rec.title[:35],
                rec.company[:25],
                rec.source_platform,
                "yes" if dupe.is_duplicate else "",
            )

        console.print(table)
        console.print(f"[bold green]Successfully imported {len(results)} jobs from direct platform search![/bold green]")
    finally:
        session.close()


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(8000, "--port", help="Local HTTP port for Web Console & browser capture"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open Web Dashboard in a new Chrome tab automatically"),
    open_capture: bool = typer.Option(False, "--open-capture", help="Also open Bookmarklet Setup Page in another new tab"),
) -> None:
    """Start local Web Console & CLI Cheat Sheet server on http://localhost:8000/."""
    import time
    settings, _ = _init_context()
    server = start_capture_server(host="127.0.0.1", port=port)
    url = f"http://localhost:{port}/"
    capture_url = f"http://localhost:{port}/capture"
    console.print(
        f"[bold green]Local Web Console & Interactive CLI Cheat Sheet Server is running![/bold green]\n"
        f"  Web Dashboard & Command Runner: [cyan]{url}[/cyan]\n"
        f"  1-Click Chrome Bookmarklet Endpoint: [cyan]{capture_url}[/cyan]\n"
        f"  Interactive CLI Commands: All 27 CLI commands available for 1-click execution\n"
        f"  Press [bold]Ctrl+C[/bold] to stop server."
    )
    # Prefer Chrome so an already-open Chrome window gets a new dashboard tab.
    browser_choice = settings.preferred_browser or "chrome"
    if browser_choice in ("system", "default") and _find_chrome_path():
        browser_choice = "chrome"

    if open_browser:
        ready = _wait_for_local_server(url)
        if ready:
            _open_in_browser(url, browser_choice=browser_choice, new_tab=True)
            console.print(f"[green]Opened dashboard in a new Chrome tab:[/green] {url}")
        else:
            console.print(
                f"[yellow]Server started, but browser open timed out. Open manually:[/yellow] {url}"
            )
    if open_capture:
        _wait_for_local_server(capture_url, timeout_seconds=3.0)
        _open_in_browser(capture_url, browser_choice=browser_choice, new_tab=True)
        console.print(f"[green]Opened bookmarklet setup in a new Chrome tab:[/green] {capture_url}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        console.print("\n[yellow]Local Web Console server stopped.[/yellow]")


@app.command("web")
def web_cmd(
    port: int = typer.Option(8000, "--port", help="Local HTTP port"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open Web Dashboard in a new Chrome tab automatically"),
    open_capture: bool = typer.Option(False, "--open-capture", help="Also open Bookmarklet Setup Page in another new tab"),
) -> None:
    """Launch interactive Web Application Dashboard and CLI Command Runner in your browser."""
    serve_cmd(port=port, open_browser=open_browser, open_capture=open_capture)


@app.command("add-contact")
def add_contact_cmd(
    name: str = typer.Argument(..., help="Contact full name"),
    job_id: Optional[int] = typer.Option(None, "--job-id", help="Optional linked Job ID"),
    role: Optional[str] = typer.Option(None, "--role", help="Contact role / title"),
    company: Optional[str] = typer.Option(None, "--company", help="Company name"),
    email: Optional[str] = typer.Option(None, "--email", help="Email address"),
    phone: Optional[str] = typer.Option(None, "--phone", help="Phone number"),
    linkedin: Optional[str] = typer.Option(None, "--linkedin", help="LinkedIn profile URL"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Notes"),
) -> None:
    """Add a recruiter, hiring manager, or networking contact locally."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        contact = add_contact(
            session=session,
            name=name,
            job_id=job_id,
            role=role,
            company=company,
            email=email,
            phone=phone,
            linkedin_url=linkedin,
            notes=notes,
        )
        console.print(f"[bold green]Saved Contact #[/bold green]{contact.id}: {contact.name} ({contact.role or 'N/A'} @ {contact.company or 'N/A'})")
    finally:
        session.close()


@app.command("contacts")
def contacts_cmd(
    job_id: Optional[int] = typer.Option(None, "--job-id", help="Filter by linked Job ID"),
) -> None:
    """List locally stored networking contacts."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        contacts = list_contacts(session, job_id=job_id)
        if not contacts:
            console.print("[yellow]No networking contacts recorded.[/yellow]")
            return

        table = Table(title="Local Contacts")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Role")
        table.add_column("Company")
        table.add_column("Email")
        table.add_column("Linked Job ID")

        for c in contacts:
            table.add_row(str(c.id), c.name, c.role or "-", c.company or "-", c.email or "-", str(c.job_id) if c.job_id else "-")

        console.print(table)
    finally:
        session.close()


@app.command("add-interview")
def add_interview_cmd(
    job_id: int = typer.Argument(..., help="Job database ID"),
    date_str: str = typer.Argument(..., help="Interview date (YYYY-MM-DD HH:MM)"),
    interview_type: str = typer.Option("Screening", "--type", help="Interview type (Screening, Technical, Behavioral, Onsite)"),
    participants: Optional[str] = typer.Option(None, "--participants", help="Interviewers / participants"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Notes"),
) -> None:
    """Record an interview date, type, participants, and preparation notes locally."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        iv = add_interview(
            session=session,
            job_id=job_id,
            interview_date=dt,
            interview_type=interview_type,
            participants=participants,
            notes=notes,
        )
        console.print(f"[bold green]Recorded Interview #[/bold green]{iv.id} for Job #{job_id} on {dt.strftime('%Y-%m-%d %H:%M')} ({interview_type})")
    except ValueError as exc:
        console.print(f"[red]Invalid date format. Use 'YYYY-MM-DD HH:MM': {exc}[/red]")
        raise typer.Exit(code=1)
    finally:
        session.close()


@app.command("prepare-interview")
def prepare_interview_cmd(
    job_id: int = typer.Argument(..., help="Job database ID"),
) -> None:
    """Generate a local, truthful interview-preparation document using job details, resume, and notes."""
    settings, SessionLocal = _init_context()
    profile = load_candidate_profile()
    session = SessionLocal()
    try:
        prep_path = prepare_interview_doc(
            session=session,
            job_id=job_id,
            profile=profile,
            output_base_dir=settings.jobs_applied_folder,
        )
        console.print(f"[bold green]Generated Interview Preparation Sheet:[/bold green]\n  [cyan]{prep_path}[/cyan]")
    finally:
        session.close()


@app.command("answers")
def answers_cmd() -> None:
    """List reusable application questions and approved answers."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        answers = list_answers(session)
        if not answers:
            console.print("[yellow]No application answers saved yet.[/yellow]")
            return

        table = Table(title="Application Answer Library")
        table.add_column("ID", style="cyan")
        table.add_column("Question")
        table.add_column("Approved Answer")
        table.add_column("Context")

        for a in answers:
            table.add_row(str(a.id), a.original_question[:40], a.approved_answer[:50], a.source_context or "-")

        console.print(table)
    finally:
        session.close()


@app.command("add-answer")
def add_answer_cmd(
    question: str = typer.Argument(..., help="Question text"),
    answer: str = typer.Argument(..., help="Approved answer text"),
    context: Optional[str] = typer.Option(None, "--context", help="Source context / note"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
) -> None:
    """Add a question and user-approved answer to the local application-answer library."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        item = add_answer(session, question=question, answer=answer, source_context=context, tags=tags)
        console.print(f"[bold green]Saved Answer #[/bold green]{item.id} for: '{item.original_question[:50]}'")
    finally:
        session.close()


@app.command("suggest-answer")
def suggest_answer_cmd(
    job_id: int = typer.Argument(..., help="Job database ID"),
    question: str = typer.Argument(..., help="Application question"),
) -> None:
    """Suggest an application answer based on local profile and master resume data (requires user review)."""
    _, SessionLocal = _init_context()
    profile = load_candidate_profile()
    session = SessionLocal()
    try:
        suggestion = suggest_answer(session=session, job_id=job_id, question=question, profile=profile)
        console.print(Panel(suggestion, title=f"Draft Answer Suggestion (Job #{job_id})"))
    finally:
        session.close()


@app.command("add-job")
def add_job_cmd(
    url: str = typer.Option(..., "--url", help="Job page URL"),
    title: Optional[str] = typer.Option(None, "--title", help="Manual fallback: Job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Manual fallback: Company name"),
    description: Optional[str] = typer.Option(None, "--description", help="Manual fallback: Job description text"),
) -> None:
    """Automated job import from a URL (automatically extracts title, company, and description)."""
    from job_agent.platform_fetcher import import_job_from_url

    _, SessionLocal = _init_context()
    profile = load_candidate_profile()
    session = SessionLocal()
    try:
        # Automated URL extraction
        parsed = import_job_from_url(url)

        # Allow user manual fallback overrides if explicitly provided
        if title:
            parsed.title = title
        if company:
            parsed.company = company
        if description:
            parsed.description = description

        record, match, dupe = record_parsed_job(session, parsed, profile)
        log_activity(
            session,
            event_type="import",
            title=f"Imported Job #{record.id} via URL",
            description=f"{record.title} at {record.company} ({record.source_platform})",
            job_id=record.id,
        )
        console.print(
            f"[bold green]Imported Job #[/bold green]{record.id}: {record.title} @ {record.company}\n"
            f" Score: {match.score:.0f}/100 ({match.recommendation.value})\n"
            f" Duplicate Status: {'Duplicate (' + dupe.reason + ')' if dupe.is_duplicate else 'Unique'}"
        )
    finally:
        session.close()


@app.command("seed-demo")
def seed_demo_cmd(
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", help="Re-score demo jobs after seeding"),
) -> None:
    """Insert sample jobs for dashboard smoke testing."""
    _, SessionLocal = _init_context()
    profile = load_candidate_profile()
    session = SessionLocal()
    try:
        job_ids = seed_demo_jobs(session, profile)
        console.print(f"[bold green]Seeded {len(job_ids)} demo jobs:[/bold green] {', '.join(f'#{i}' for i in job_ids)}")
        if analyze:
            count = reanalyze_all_jobs(session, profile)
            console.print(f"[green]Re-analyzed {count} job(s).[/green]")
        console.print("[cyan]Open the web dashboard and click Refresh to view demo data.[/cyan]")
    finally:
        session.close()


@app.command("backup")
def backup_cmd(
    destination: Optional[Path] = typer.Argument(None, help="Destination directory for backup ZIP"),
) -> None:
    """Create a local ZIP backup of database, config, and settings."""
    settings, _ = _init_context()
    zip_path = create_backup(settings, destination_dir=destination)
    console.print(f"[bold green]Created local backup archive:[/bold green]\n  [cyan]{zip_path}[/cyan]")


@app.command("restore")
def restore_cmd(
    backup_zip: Path = typer.Argument(..., help="Path to backup ZIP archive"),
) -> None:
    """Restore database and config files from a local backup archive."""
    settings, _ = _init_context()
    confirm = typer.confirm(f"Are you sure you want to restore from {backup_zip}? This will overwrite current database.", default=False)
    if not confirm:
        console.print("[yellow]Restore cancelled.[/yellow]")
        return
    restore_backup(backup_zip, settings)
    console.print(f"[bold green]Successfully restored backup from:[/bold green] {backup_zip}")


@app.command("delete-job")
def delete_job_cmd(
    job_id: int = typer.Argument(..., help="Job database ID to delete"),
) -> None:
    """Delete a single job record locally (requires explicit confirmation)."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        job = get_job(session, job_id)
        if not job:
            console.print(f"[red]Job ID {job_id} not found.[/red]")
            raise typer.Exit(code=1)

        confirm = typer.confirm(f"Are you sure you want to delete Job #{job.id} ({job.title} @ {job.company})?", default=False)
        if not confirm:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            return

        success = delete_job_record(session, job_id)
        if success:
            console.print(f"[bold green]Successfully deleted Job #[/bold green]{job_id}")
    finally:
        session.close()


@app.command("purge-data")
def purge_data_cmd(
    confirm: bool = typer.Option(False, "--confirm", help="Skip interactive prompt and purge immediately"),
) -> None:
    """Purge all local database records (requires explicit confirmation)."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        if not confirm:
            confirm = typer.confirm("CRITICAL: Are you sure you want to purge ALL local database records?", default=False)
        if not confirm:
            console.print("[yellow]Purge cancelled.[/yellow]")
            return

        count = purge_all_data(session)
        console.print(f"[bold red]Purged {count} records across database.[/bold red]")
    finally:
        session.close()


@app.command("cleanup")
def cleanup_cmd(
    action: str = typer.Option("duplicates", "--action", help="Cleanup action: duplicates, stale, status, old, or all"),
    status: Optional[str] = typer.Option(None, "--status", help="Target status when action='status' (e.g. 'Saved', 'Reviewing')"),
    days: int = typer.Option(30, "--days", help="Days threshold when action='old'"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
) -> None:
    """Clean up test data, duplicates, stale/excluded jobs, or old records from database."""
    _, SessionLocal = _init_context()
    session = SessionLocal()
    try:
        act = action.lower()
        if not confirm and act in ("all", "status", "old"):
            if not typer.confirm(f"Are you sure you want to run cleanup action '{act}'?", default=False):
                console.print("[yellow]Cleanup cancelled.[/yellow]")
                return

        if act == "duplicates":
            cnt = clean_duplicate_jobs(session)
            console.print(f"[bold green]Cleaned {cnt} duplicate job records.[/bold green]")
        elif act in ("stale", "excluded"):
            cnt = clean_stale_or_excluded_jobs(session)
            console.print(f"[bold green]Cleaned {cnt} stale/excluded job records.[/bold green]")
        elif act == "status":
            if not status:
                console.print("[bold red]Error: --status is required when action='status'.[/bold red]")
                return
            cnt = clean_jobs_by_status(session, status)
            console.print(f"[bold green]Cleaned {cnt} jobs with status '{status}'.[/bold green]")
        elif act == "old":
            cnt = clean_old_jobs(session, days)
            console.print(f"[bold green]Cleaned {cnt} jobs older than {days} days.[/bold green]")
        elif act == "all":
            res = purge_all_database_data(session)
            console.print(f"[bold red]Purged test data across all tables: {res}[/bold red]")
        else:
            console.print(f"[bold red]Unknown cleanup action: '{action}'. Use duplicates, stale, status, old, or all.[/bold red]")
    finally:
        session.close()


def _fmt_list(items: list) -> str:
    return ", ".join([str(x) for x in items if x]) or "-"


@app.command("profile")
def profile_cmd() -> None:
    """Show the loaded candidate profile (sanity check)."""
    settings, _ = _init_context()
    profile = load_candidate_profile()
    table = Table(title="Candidate Profile")
    table.add_column("Field")
    table.add_column("Value")
    rows = [
        ("Target titles", _fmt_list(profile.target_titles)),
        ("Industries", _fmt_list(profile.industries)),
        ("Required skills", _fmt_list(profile.required_skills)),
        ("Preferred skills", _fmt_list(profile.preferred_skills)),
        ("Years experience", str(profile.years_experience)),
        ("Locations", _fmt_list(profile.locations)),
        ("Work modes", _fmt_list(profile.work_modes)),
        ("Salary", f"{profile.salary_min}-{profile.salary_max} {profile.salary_currency}"),
        ("Employment types", _fmt_list(profile.employment_types)),
        ("Work auth", profile.work_authorization or "-"),
        ("Excluded companies", _fmt_list(profile.excluded_companies)),
        ("Excluded titles", _fmt_list(profile.excluded_titles)),
        ("Master resume", str(settings.master_resume_path) if settings.master_resume_path else (profile.master_resume_path or "-")),
        ("Multi-resumes", ", ".join([f"{k}: {v}" for k, v in profile.master_resumes.items()]) if profile.master_resumes else "-"),
        ("Cover letter template", profile.cover_letter_template_path or "-"),
        ("LLM provider", settings.llm_provider),
    ]
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


@app.command("statuses")
def statuses_cmd() -> None:
    """List supported application statuses."""
    for status in ApplicationStatus:
        console.print(f"- {status.value}")


@app.command("test")
def test_cmd(
    coverage: bool = typer.Option(False, "--cov", help="Include coverage report for job_agent"),
    e2e: bool = typer.Option(True, "--e2e/--no-e2e", help="Include Playwright browser E2E tests"),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run E2E in headless Chromium (CI/automation). Default opens visible Google Chrome.",
    ),
    guided: bool = typer.Option(
        False,
        "--guided",
        help="Run paced Chrome walkthrough only (30 seconds per step, ~6 minutes).",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose pytest output"),
    install_browsers: bool = typer.Option(
        False,
        "--install-browsers",
        help="Install Playwright Chrome support (one-time setup) and exit",
    ),
) -> None:
    """Run the full test suite: unit tests, HTTP API tests, and browser E2E tests in Google Chrome."""
    if install_browsers:
        console.print("[cyan]Installing Playwright Google Chrome support for browser E2E tests...[/cyan]")
        console.print("[dim]Ensure Google Chrome is installed on this machine (https://google.com/chrome)[/dim]")
        code = install_playwright_browsers(chrome=True)
        if code == 0:
            console.print("[green]Playwright Chrome support installed.[/green]")
        raise typer.Exit(code)

    if guided:
        console.print("[bold]Running guided Chrome walkthrough[/bold] (30 seconds per step)")
        console.print("[cyan]Watch Chrome — each step pauses so you can follow the application flow.[/cyan]")
    elif e2e and not headless:
        mode = "unit + API + E2E in visible Google Chrome"
    elif e2e:
        mode = "unit + API + E2E (headless Chromium)"
    else:
        mode = "unit + API only (no browser)"
    if not guided:
        console.print(f"[bold]Running test suite[/bold] ({mode})")
        if e2e and not headless:
            console.print("[cyan]Chrome will open and run Web Console tests as an end user would see them.[/cyan]")
    result = run_test_suite(coverage=coverage, e2e=e2e, verbose=verbose, headless=headless, guided=guided)
    if result.exit_code == 0:
        console.print("[green]All tests passed.[/green]")
    else:
        console.print("[red]Tests failed.[/red]")
        if e2e:
            console.print(
                "[dim]Tip: install Chrome + run "
                "python -m job_agent test --install-browsers[/dim]"
            )
    raise typer.Exit(result.exit_code)


if __name__ == "__main__":
    app()
