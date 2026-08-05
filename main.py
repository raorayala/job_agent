"""CLI entry point for the job search agent."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from src.agent import run_scan, show_history

app = typer.Typer(help="Proactive Gmail job search agent with ATS resume tailoring.")
console = Console()


@app.command()
def scan(
    max_results: int = typer.Option(25, help="Maximum emails to fetch per run"),
    no_tailor: bool = typer.Option(False, help="Skip resume tailoring"),
):
    """Fetch job alert emails, analyze matches, and tailor resumes."""
    console.print("[bold]Scanning Gmail for job opportunities...[/bold]")
    try:
        summary = run_scan(max_results=max_results, tailor=not no_tailor)
    except FileNotFoundError as exc:
        console.print(f"[red]Setup required:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"Fetched {summary['emails_fetched']} emails | "
        f"New: {summary['new_jobs']} | "
        f"Duplicates skipped: {summary['skipped_duplicates']} | "
        f"Resumes tailored: {summary['tailored_resumes']}"
    )

    if summary["jobs"]:
        table = Table(title="Discovered Jobs")
        table.add_column("Score", style="cyan")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Platform")
        for job in summary["jobs"]:
            table.add_row(
                f"{job['score']:.0f}",
                job["title"][:50],
                job["company"][:30],
                job["platform"],
            )
        console.print(table)


@app.command()
def history():
    """Show all tracked job listings and application statuses."""
    listings = show_history()
    if not listings:
        console.print("No jobs tracked yet. Run [bold]scan[/bold] first.")
        raise typer.Exit()

    table = Table(title="Jobs Applied / Tracked")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Platform")
    for row in listings:
        table.add_row(
            row.status,
            f"{row.match_score:.0f}" if row.match_score else "-",
            row.title[:40],
            row.company[:25],
            row.platform,
        )
    console.print(table)


@app.command()
def setup():
    """Print first-time setup checklist."""
    console.print(
        """
[bold]First-time setup[/bold]

1. Create Google Cloud project → enable Gmail API
2. Create OAuth Desktop credentials → save as credentials.json in project root
3. Copy .env.example → .env and edit paths/skills in config.yaml
4. Place master resume at Desktop/Jobs Applied/master_resume.docx
5. python -m venv .venv && .venv\\Scripts\\activate
6. pip install -r requirements.txt
7. python main.py scan

[dim]Tip: Run on a schedule with Windows Task Scheduler or APScheduler later.[/dim]
"""
    )


if __name__ == "__main__":
    app()
