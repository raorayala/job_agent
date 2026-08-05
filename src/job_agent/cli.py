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
from job_agent.database import init_db
from job_agent.logging_config import setup_logging
from job_agent.models import ApplicationStatus

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
    """Sync job-alert emails from Gmail (Milestone 3)."""
    settings, _ = _init_context()
    try:
        from job_agent.gmail_client import sync_job_emails

        result = sync_job_emails(settings, max_results=max_results, dry_run=dry_run)
        console.print(result)
    except NotImplementedError as exc:
        console.print(f"[yellow]Not ready yet:[/yellow] {exc}")
        if dry_run:
            console.print(
                f"[dim]Dry-run would search:[/dim] {settings.gmail_search_query}\n"
                f"[dim]Credentials path:[/dim] {settings.gmail_credentials_path}\n"
                f"[dim]Token path:[/dim] {settings.gmail_token_path}"
            )
        raise typer.Exit(code=2) from exc


@app.command("analyze")
def analyze_cmd(
    min_score: Optional[float] = typer.Option(None, help="Only show jobs at/above this score"),
) -> None:
    """Score saved jobs against your candidate profile (Milestone 6)."""
    _init_context()
    console.print(
        "[yellow]Not ready yet:[/yellow] Rule-based analyze lands in Milestone 6. "
        "Profile + DB are ready - run [bold]setup[/bold] and edit config.yaml."
    )
    raise typer.Exit(code=2)


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
            "No jobs tracked yet. After Gmail sync is available, run "
            "[bold]sync-gmail[/bold]. Database is ready at "
            f"[dim]{settings.database_path}[/dim]."
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
) -> None:
    """Create a tailored ATS resume for a job (Milestone 7)."""
    settings, SessionLocal = _init_context()
    from job_agent.database import get_job
    from job_agent.document_exporter import application_folder, resume_filename

    session = SessionLocal()
    try:
        job = get_job(session, job_id)
    finally:
        session.close()

    if job is None:
        console.print(f"[red]Job id {job_id} not found.[/red]")
        raise typer.Exit(code=1)

    folder = application_folder(settings.jobs_applied_folder, job.company, job.title)
    filename = resume_filename(job.company, job.title)
    target = folder / filename

    if dry_run:
        console.print(f"[dim]Would write:[/dim] {target}")
        raise typer.Exit(code=0)

    console.print(
        "[yellow]Not ready yet:[/yellow] Resume tailoring lands in Milestone 7. "
        f"Planned path: {target}"
    )
    raise typer.Exit(code=2)


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


@app.command("profile")
def profile_cmd() -> None:
    """Show the loaded candidate profile (sanity check)."""
    settings, _ = _init_context()
    profile = load_candidate_profile()
    table = Table(title="Candidate Profile")
    table.add_column("Field")
    table.add_column("Value")
    rows = [
        ("Target titles", ", ".join(profile.target_titles) or "-"),
        ("Industries", ", ".join(profile.industries) or "-"),
        ("Required skills", ", ".join(profile.required_skills) or "-"),
        ("Preferred skills", ", ".join(profile.preferred_skills) or "-"),
        ("Years experience", str(profile.years_experience)),
        ("Locations", ", ".join(profile.locations) or "-"),
        ("Work modes", ", ".join(profile.work_modes) or "-"),
        ("Salary", f"{profile.salary_min}-{profile.salary_max} {profile.salary_currency}"),
        ("Employment types", ", ".join(profile.employment_types) or "-"),
        ("Work auth", profile.work_authorization or "-"),
        ("Excluded companies", ", ".join(profile.excluded_companies) or "-"),
        ("Excluded titles", ", ".join(profile.excluded_titles) or "-"),
        ("Master resume", profile.master_resume_path or str(settings.master_resume_path) or "-"),
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
