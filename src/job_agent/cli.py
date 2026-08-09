"""CLI entrypoint: setup, sync, analyze, list, tailor, mark-applied, dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from job_agent import __version__
from job_agent.application_tracker import list_tracked_jobs, mark_applied
from job_agent.config import (
    ensure_runtime_dirs,
    get_settings,
    load_candidate_profile,
    load_yaml_config,
)
from job_agent.database import get_job, init_db, list_jobs
from job_agent.gmail_client import GmailNotConfiguredError, sync_job_emails
from job_agent.logging_config import setup_logging
from job_agent.matcher import recommendation_for_score, score_job
from job_agent.models import ApplicationStatus, MatchExplanation, ParsedJob, Recommendation
from job_agent.resume_tailor import generate_cover_letter, tailor_resume

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

[cyan]Personal files[/cyan]
- Copy .env.example -> .env and set MASTER_RESUME_PATH
- Edit config.yaml profile (skills, locations, exclusions, salary)
- Place master resume DOCX at MASTER_RESUME_PATH (never commit it)

[cyan]Next commands[/cyan]
  py -m job_agent sync-gmail --dry-run
  py -m job_agent analyze
  py -m job_agent jobs --min-score 70

[dim]Safeguards: no auto-apply, no fabricated resume content, credentials stay local.[/dim]
"""
    console.print(Panel(checklist.strip(), title="Setup", border_style="green"))


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
        jobs = list_jobs(session, limit=500)
        if not jobs:
            console.print("No jobs found in database to analyze. Run [bold]sync-gmail[/bold] first.")
            raise typer.Exit(code=0)

        updated_count = 0
        for job in jobs:
            parsed = ParsedJob(
                title=job.title,
                company=job.company,
                location=job.location,
                source_platform=job.source_platform,
                salary=job.salary,
                employment_type=job.employment_type,
                job_url=job.job_url,
                description=job.description or "",
                gmail_message_id=job.gmail_message_id,
            )
            match = score_job(parsed, profile)
            job.match_score = match.score
            job.recommendation = match.recommendation.value
            job.match_summary = match.summary
            job.matched_skills = ", ".join(match.matched_skills)
            job.missing_skills = ", ".join(match.missing_skills)
            job.concerns = "; ".join(match.concerns)
            updated_count += 1

        session.commit()
        console.print(f"[green]Re-analyzed {updated_count} job(s) in database.[/green]")

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
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned output path only"),
    cover_letter: bool = typer.Option(True, "--cover-letter/--no-cover-letter", help="Generate cover letter alongside resume"),
) -> None:
    """Create a tailored ATS resume and cover letter for a job and save to Desktop/Jobs Applied."""
    settings, SessionLocal = _init_context()
    profile = load_candidate_profile()

    session = SessionLocal()
    try:
        job = get_job(session, job_id)
        if job is None:
            console.print(f"[red]Job id {job_id} not found.[/red]")
            raise typer.Exit(code=1)

        resume_path_str = profile.get_master_resume_path(job.title) or (
            str(settings.master_resume_path) if settings.master_resume_path else None
        )
        if not resume_path_str:
            console.print(
                "[red]MASTER_RESUME_PATH is not set in .env or config.yaml.[/red]\n"
                "Please copy .env.example to .env and set MASTER_RESUME_PATH to your master resume DOCX."
            )
            raise typer.Exit(code=1)

        master_resume_path = Path(resume_path_str)

        parsed = ParsedJob(
            title=job.title,
            company=job.company,
            location=job.location,
            source_platform=job.source_platform,
            salary=job.salary,
            employment_type=job.employment_type,
            job_url=job.job_url,
            description=job.description or "",
            gmail_message_id=job.gmail_message_id,
        )

        match = MatchExplanation(
            score=job.match_score or 0.0,
            recommendation=recommendation_for_score(job.match_score or 0.0),
            matched_skills=[s.strip() for s in (job.matched_skills or "").split(",") if s.strip()],
            missing_skills=[s.strip() for s in (job.missing_skills or "").split(",") if s.strip()],
            concerns=[c.strip() for c in (job.concerns or "").split(";") if c.strip()],
            summary=job.match_summary or "",
        )

        output_path = tailor_resume(
            job=parsed,
            match=match,
            master_resume_path=master_resume_path,
            output_base_dir=settings.jobs_applied_folder,
            dry_run=dry_run,
        )

        cover_letter_path = None
        if cover_letter:
            cover_letter_path = generate_cover_letter(
                job=parsed,
                match=match,
                template_path=profile.cover_letter_template_path,
                output_folder=output_path.parent,
                dry_run=dry_run,
            )

        if not dry_run:
            job.status = ApplicationStatus.READY_TO_APPLY.value
            job.tailored_resume_path = str(output_path)
            session.commit()
            console.print(
                f"[bold green]Tailored application documents created successfully![/bold green]\n"
                f"  Job: {job.title} @ {job.company}\n"
                f"  Tailored Resume: [cyan]{output_path}[/cyan]\n"
                + (f"  Cover Letter: [cyan]{cover_letter_path}[/cyan]\n" if cover_letter_path else "")
                + f"  Status updated to: [yellow]{job.status}[/yellow]"
            )
        else:
            console.print(f"[yellow][Dry-Run][/yellow] Planned tailored resume path: {output_path}")

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
    """Optional Streamlit dashboard (install extras: pip install .[dashboard])."""
    console.print(
        "[yellow]Optional dashboard[/yellow] arrives after CLI workflows are solid.\n"
        "Install later with: [bold]pip install -e \".[dashboard]\"[/bold]"
    )
    raise typer.Exit(code=2)


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


if __name__ == "__main__":
    app()
