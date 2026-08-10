"""Web application dashboard, visual Kanban board, job discovery, review-first resume approval, and CLI execution server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import Thread
from typing import Any

from sqlalchemy import select, text

from job_agent.application_tracker import (
    approve_resume_draft_for_job,
    create_resume_draft_for_job,
    list_tracked_jobs,
    mark_applied,
    record_parsed_job,
    reject_resume_draft_for_job,
    update_job_details,
    update_status,
)
from job_agent.auto_apply_service import evaluate_auto_apply_eligibility, launch_auto_apply
from job_agent.backup_service import create_backup
from job_agent.cleanup_service import (
    clean_duplicate_jobs,
    clean_jobs_by_status,
    clean_old_jobs,
    clean_stale_or_excluded_jobs,
    purge_all_database_data,
)
from job_agent.config import get_settings, get_web_console_settings, load_candidate_profile, save_candidate_profile, save_web_console_settings
from job_agent.database import ActivityLogRecord, JobRecord, create_db_engine, get_job, init_db, list_jobs, log_activity
from job_agent.demo_data import seed_demo_jobs
from job_agent.document_exporter import application_folder
from job_agent.email_sync_service import email_provider_status, sync_email_alerts
from job_agent.gmail_client import sync_job_emails
from job_agent.job_analysis import reanalyze_all_jobs
from job_agent.linkedin_optimize import optimize_linkedin_profile
from job_agent.logging_config import get_logger
from job_agent.matcher import score_job
from job_agent.models import CandidateProfile, ParsedJob
from job_agent.platform_fetcher import (
    TOP_10_PLATFORMS,
    generate_platform_search_urls,
    import_job_from_url,
    search_and_import_jobs,
)
from job_agent.profile_optimize import analyze_profile_against_target
from job_agent.report_service import generate_ics_calendar, generate_pipeline_summary, generate_report
from job_agent.resume_optimize import (
    apply_accepted_suggestions_to_draft,
    generate_optimize_suggestions,
    load_optimize_bundle,
    update_suggestion,
)
from job_agent.resume_parser import extract_resume_text
from job_agent.system_health import get_system_health

logger = get_logger(__name__)

CLI_COMMANDS_METADATA = [
    {
        "category": "Setup & Environment",
        "commands": [
            {
                "id": "setup",
                "name": "setup",
                "cmd": "setup",
                "description": "Initialize local database, runtime directories, and verify configuration.",
                "params": [
                    {"name": "copy_env", "flag": "--copy-env/--no-copy-env", "type": "bool", "default": True, "label": "Copy .env from .env.example if missing"}
                ]
            },
            {
                "id": "profile",
                "name": "profile",
                "cmd": "profile",
                "description": "Inspect candidate career profile, skills, target titles, and master resumes.",
                "params": []
            },
            {
                "id": "statuses",
                "name": "statuses",
                "cmd": "statuses",
                "description": "List all supported application lifecycle statuses.",
                "params": []
            }
        ]
    },
    {
        "category": "Job Discovery & Ingestion",
        "commands": [
            {
                "id": "fetch-jobs",
                "name": "fetch-jobs",
                "cmd": "fetch-jobs",
                "description": "Search job platforms directly (default 3 jobs per platform, max 9, last 14 days). Recommended: dice, ziprecruiter, indeed.",
                "params": [
                    {"name": "platforms", "flag": "--platforms", "type": "text", "default": "dice,ziprecruiter,indeed", "label": "Platforms (comma-separated)"},
                    {"name": "limit", "flag": "--limit", "type": "number", "default": 3, "label": "Max jobs per platform (default 3, max 9)"}
                ]
            },
            {
                "id": "search-links",
                "name": "search-links",
                "cmd": "search-links",
                "description": "Generate platform search URLs filtered for jobs posted in the last 1-2 weeks.",
                "params": [
                    {"name": "open", "flag": "--open", "type": "bool", "default": False, "label": "Open links in browser"},
                    {"name": "browser", "flag": "--browser", "type": "text", "default": "system", "label": "Browser (system/chrome/default)"}
                ]
            },
            {
                "id": "sync-gmail",
                "name": "sync-gmail",
                "cmd": "sync-gmail",
                "description": "Sync job alert emails from Gmail via read-only OAuth 2.0.",
                "params": [
                    {"name": "max_results", "flag": "--max-results", "type": "number", "default": 25, "label": "Max emails to fetch"},
                    {"name": "dry_run", "flag": "--dry-run", "type": "bool", "default": False, "label": "Dry Run mode"}
                ]
            },
            {
                "id": "sync-email",
                "name": "sync-email",
                "cmd": "sync-email",
                "description": "Sync job alerts from Gmail or Hotmail/Outlook IMAP (--provider gmail|outlook|hotmail).",
                "params": [
                    {"name": "provider", "flag": "--provider", "type": "text", "default": "gmail", "label": "Provider (gmail/outlook/hotmail)"},
                    {"name": "max_results", "flag": "--max-results", "type": "number", "default": 25, "label": "Max emails to fetch"},
                    {"name": "dry_run", "flag": "--dry-run", "type": "bool", "default": False, "label": "Dry Run mode"}
                ]
            },
            {
                "id": "add-job",
                "name": "add-job",
                "cmd": "add-job",
                "description": "Automated job import from a URL (extracts title, company, location, and description).",
                "params": [
                    {"name": "url", "flag": "--url", "type": "text", "default": "", "label": "Job URL (required)", "required": True},
                    {"name": "title", "flag": "--title", "type": "text", "default": "", "label": "Fallback Title"},
                    {"name": "company", "flag": "--company", "type": "text", "default": "", "label": "Fallback Company"}
                ]
            },
            {
                "id": "seed-demo",
                "name": "seed-demo",
                "cmd": "seed-demo",
                "description": "Insert 3 sample jobs for dashboard smoke testing (no network).",
                "params": [
                    {"name": "analyze", "flag": "--analyze/--no-analyze", "type": "bool", "default": True, "label": "Re-score after seeding"}
                ]
            }
        ]
    },
    {
        "category": "Analysis & Review-First Resume Tailoring",
        "commands": [
            {
                "id": "analyze",
                "name": "analyze",
                "cmd": "analyze",
                "description": "Re-score all stored jobs against profile and master resume text.",
                "params": [
                    {"name": "min_score", "flag": "--min-score", "type": "number", "default": 0, "label": "Minimum score filter"}
                ]
            },
            {
                "id": "jobs",
                "name": "jobs",
                "cmd": "jobs",
                "description": "List tracked jobs with status, match score, and platform.",
                "params": [
                    {"name": "min_score", "flag": "--min-score", "type": "number", "default": 0, "label": "Minimum match score"},
                    {"name": "limit", "flag": "--limit", "type": "number", "default": 50, "label": "Max rows"}
                ]
            },
            {
                "id": "tailor",
                "name": "tailor",
                "cmd": "tailor",
                "description": "Generate ATS tailored DOCX resume draft into _drafts/ awaiting user review.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "dry_run", "flag": "--dry-run", "type": "bool", "default": False, "label": "Dry Run mode"}
                ]
            },
            {
                "id": "approve-draft",
                "name": "approve-draft",
                "cmd": "approve-draft",
                "description": "Explicitly approve and promote resume draft into finalized jobapplied folder.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True}
                ]
            },
            {
                "id": "reject-draft",
                "name": "reject-draft",
                "cmd": "reject-draft",
                "description": "Reject resume draft and revert job status.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True}
                ]
            }
        ]
    },
    {
        "category": "Maintenance & Data Security",
        "commands": [
            {
                "id": "cleanup",
                "name": "cleanup",
                "cmd": "cleanup",
                "description": "Clean up test data, duplicates, stale/excluded jobs, or reset database.",
                "params": [
                    {"name": "action", "flag": "--action", "type": "select", "default": "duplicates", "options": ["duplicates", "stale", "status", "old", "all"], "label": "Cleanup Action"},
                    {"name": "status", "flag": "--status", "type": "text", "default": "", "label": "Status filter (if action=status)"},
                    {"name": "confirm", "flag": "--confirm", "type": "bool", "default": True, "label": "Confirm deletion"}
                ]
            },
            {
                "id": "backup",
                "name": "backup",
                "cmd": "backup",
                "description": "Create local ZIP backup archive of SQLite DB, settings, and documents.",
                "params": []
            },
            {
                "id": "test",
                "name": "test",
                "cmd": "test",
                "description": "Run full test suite; use --guided for paced Chrome walkthrough.",
                "params": [
                    {"name": "guided", "flag": "--guided", "type": "bool", "default": False, "label": "Guided Chrome walkthrough (30s per step)"},
                    {"name": "no_e2e", "flag": "--no-e2e", "type": "bool", "default": False, "label": "Skip browser tests"}
                ]
            }
        ]
    }
]


def execute_cli_command(cmd_name: str, raw_args: list[str]) -> dict[str, Any]:
    """Execute python -m job_agent <cmd_name> <args> in a subprocess and return output."""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [sys.executable, "-m", "job_agent", cmd_name] + raw_args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        output = (stdout + ("\n" + stderr if stderr else "")).strip()
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": output or "(Command produced no console output)",
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "output": "Error: Command execution timed out after 120 seconds.",
            "command": " ".join(cmd),
        }
    except Exception as exc:
        return {
            "success": False,
            "exit_code": -1,
            "output": f"Error executing command: {exc}",
            "command": " ".join(cmd),
        }


HTML_APP_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Search Agent Web Console — CLI Command Cheat Sheet & Review-First Web Application</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        :root {
            --bg-main: #f1f5f9;
            --surface: #ffffff;
            --card-border: #e2e8f0;
            --text-primary: #0f172a;
            --text-muted: #64748b;
            --brand-primary: #2563eb;
            --brand-primary-soft: #eff6ff;
            --score-high-bg: #dcfce7; --score-high-fg: #166534;
            --score-mid-bg: #fef3c7;  --score-mid-fg: #92400e;
            --score-low-bg: #fee2e2;  --score-low-fg: #991b1b;
            --score-none-bg: #f1f5f9; --score-none-fg: #64748b;
            --radius-md: 12px;
            --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
            --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.08);
        }
        body {
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
            font-size: 0.9375rem;
            line-height: 1.45;
        }
        .app-header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: #ffffff;
            padding: 1rem 1.35rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .btn-header-secondary {
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.35);
            color: #fff;
        }
        .btn-header-secondary:hover {
            background: rgba(255,255,255,0.22);
            border-color: rgba(255,255,255,0.5);
            color: #fff;
        }
        .btn-header-tertiary {
            background: transparent;
            border: 1px solid transparent;
            color: #cbd5e1;
        }
        .btn-header-tertiary:hover {
            background: rgba(255,255,255,0.08);
            color: #fff;
        }
        .nav-tabs .nav-link {
            color: #64748b;
            font-weight: 600;
            border: none;
            padding: 0.75rem 1.25rem;
        }
        .nav-tabs .nav-link.active {
            color: var(--brand-primary);
            border-bottom: 3px solid var(--brand-primary);
            background: transparent;
        }
        .stat-card {
            position: relative;
            border: 1px solid var(--card-border);
            border-radius: var(--radius-md);
            background: var(--surface);
            padding: 1rem 1.1rem 1rem 1.15rem;
            box-shadow: var(--shadow-sm);
            overflow: hidden;
            transition: box-shadow 0.15s ease, transform 0.15s ease, border-color 0.15s ease;
        }
        .stat-card::before {
            content: "";
            position: absolute;
            left: 0; top: 0; bottom: 0;
            width: 3px;
            background: var(--stat-accent, var(--brand-primary));
        }
        .stat-card:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-md);
            border-color: #cbd5e1;
        }
        .stat-card.is-zero { opacity: 0.72; }
        .stat-card.is-zero .stat-value { color: var(--text-muted) !important; }
        .stat-card[data-accent="jobs"] { --stat-accent: #2563eb; }
        .stat-card[data-accent="review"] { --stat-accent: #d97706; }
        .stat-card[data-accent="drafts"] { --stat-accent: #dc2626; }
        .stat-card[data-accent="apps"] { --stat-accent: #059669; }
        .stat-label {
            font-size: 0.72rem;
            font-weight: 650;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.35rem;
        }
        .stat-value {
            font-size: 1.75rem;
            font-weight: 750;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }
        .action-tile {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 0.25rem;
            width: 100%;
            height: 100%;
            text-align: left;
            padding: 1rem 1.05rem;
            border-radius: var(--radius-md);
            border: 1px solid var(--card-border);
            background: var(--surface);
            box-shadow: var(--shadow-sm);
            color: var(--text-primary);
            transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
        }
        .action-tile:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
            border-color: #93c5fd;
            color: var(--text-primary);
        }
        .action-tile.is-primary {
            background: linear-gradient(160deg, #2563eb, #1d4ed8);
            color: #fff;
            border-color: transparent;
        }
        .action-tile.is-primary:hover { color: #fff; border-color: transparent; }
        .action-tile.is-primary .action-sub { color: rgba(255,255,255,0.78); }
        .action-tile.is-warning {
            background: linear-gradient(160deg, #fbbf24, #f59e0b);
            border-color: transparent;
            color: #1c1917;
        }
        .action-tile.is-warning:hover { color: #1c1917; }
        .action-tile .action-title { font-weight: 700; font-size: 0.95rem; }
        .action-tile .action-sub { font-size: 0.8rem; color: var(--text-muted); }
        .kanban-col {
            background: #f1f5f9;
            border-radius: 10px;
            padding: 1rem;
            min-height: 500px;
        }
        .kanban-card {
            background: #ffffff;
            border-radius: 8px;
            padding: 0.85rem;
            margin-bottom: 0.85rem;
            border: 1px solid var(--card-border);
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .kanban-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .platform-card {
            border: 1px solid var(--card-border);
            border-radius: 10px;
            background: #ffffff;
            padding: 0.85rem 0.75rem;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .platform-card:hover {
            border-color: #93c5fd;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12);
        }
        .platform-card.is-selected {
            border-color: #2563eb;
            background: #eff6ff;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.15);
        }
        .platform-card .form-check-input {
            float: none;
            margin: 0 auto 0.5rem auto;
            display: block;
        }
        .terminal-box {
            background-color: #0f172a;
            color: #38bdf8;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.85rem;
            border-radius: 8px;
            padding: 1.25rem;
            max-height: 450px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .badge-score {
            font-size: 0.75rem;
            font-weight: 700;
            min-width: 2.4rem;
            padding: 0.35em 0.55em;
            border-radius: 6px;
            font-variant-numeric: tabular-nums;
        }
        .badge-score.score-high { background: var(--score-high-bg); color: var(--score-high-fg); }
        .badge-score.score-mid  { background: var(--score-mid-bg);  color: var(--score-mid-fg); }
        .badge-score.score-low  { background: var(--score-low-bg);  color: var(--score-low-fg); }
        .badge-score.score-none { background: var(--score-none-bg); color: var(--score-none-fg); }
        .badge-status {
            font-size: 0.7rem;
            font-weight: 650;
            border-radius: 999px;
            padding: 0.3em 0.65em;
        }
        .badge-status.status-review { background: #ffedd5; color: #9a3412; }
        .badge-status.status-draft  { background: #ede9fe; color: #5b21b6; }
        .badge-status.status-applied{ background: #d1fae5; color: #065f46; }
        .badge-status.status-default{ background: #e2e8f0; color: #334155; }
        .jobs-table {
            --bs-table-hover-bg: #f8fafc;
            font-size: 0.875rem;
        }
        .jobs-table thead th {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-muted);
            font-weight: 700;
            border-bottom-width: 1px;
            white-space: nowrap;
            background: #f8fafc !important;
        }
        .jobs-table tbody td {
            padding: 0.65rem 0.85rem;
            border-color: #eef2f7;
            vertical-align: middle;
        }
        .jobs-table .col-id { width: 4.5rem; }
        .jobs-table .col-score { width: 4.75rem; text-align: center; }
        .jobs-table .col-platform { width: 7.5rem; }
        .jobs-table .col-actions { width: 8.5rem; }
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 2.25rem 1.5rem;
            gap: 0.35rem;
        }
        .empty-state .empty-icon {
            width: 2.75rem;
            height: 2.75rem;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--brand-primary-soft);
            color: var(--brand-primary);
            font-size: 1.25rem;
            margin-bottom: 0.35rem;
        }
        .empty-state .empty-title { font-weight: 700; color: var(--text-primary); font-size: 0.95rem; }
        .empty-state .empty-copy { color: var(--text-muted); font-size: 0.85rem; max-width: 28rem; }
        .activity-timeline { list-style: none; margin: 0; padding: 0.5rem 0.85rem 0.85rem; }
        .activity-item {
            position: relative;
            padding: 0.65rem 0 0.65rem 1.15rem;
            border: none;
            background: transparent;
        }
        .activity-item::before {
            content: "";
            position: absolute;
            left: 0.28rem;
            top: 1.15rem;
            bottom: -0.15rem;
            width: 2px;
            background: #e2e8f0;
        }
        .activity-item:last-child::before { display: none; }
        .activity-item::after {
            content: "";
            position: absolute;
            left: 0.1rem;
            top: 0.95rem;
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: #94a3b8;
            border: 2px solid #fff;
            box-shadow: 0 0 0 1px #e2e8f0;
        }
        .activity-item.cat-discover::after { background: #2563eb; }
        .activity-item.cat-sync::after { background: #7c3aed; }
        .activity-item.cat-draft::after { background: #d97706; }
        .activity-item.cat-apply::after { background: #059669; }
        .activity-tag {
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 0.15em 0.45em;
            border-radius: 4px;
            background: #f1f5f9;
            color: #475569;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .spin {
            display: inline-block;
            animation: spin 1s infinite linear;
        }
        #global-progress-wrapper {
            position: sticky;
            top: 0;
            z-index: 1080;
            display: none;
            background: #eff6ff;
            border-bottom: 2px solid #2563eb;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.18);
            padding: 0.85rem 1.25rem;
        }
        #global-progress-wrapper.is-visible {
            display: block !important;
        }
        #global-progress-wrapper .progress {
            height: 14px;
            border-radius: 8px;
            background-color: #dbeafe;
        }
        #global-progress-status {
            font-size: 0.95rem;
            font-weight: 600;
            color: #1e3a8a;
        }
        #global-progress-percent {
            font-size: 0.95rem;
            font-weight: 700;
            color: #1d4ed8;
        }
        body.console-mode-user .admin-only {
            display: none !important;
        }
        body.console-mode-admin .user-only {
            display: none !important;
        }
        #console-mode-badge {
            font-size: 0.75rem;
            letter-spacing: 0.03em;
        }
        body.module-gate-open #app-shell {
            display: none !important;
        }
        body.module-gate-open #module-gate {
            display: flex !important;
        }
        #app-shell {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .app-layout {
            display: flex;
            flex: 1;
            min-height: 0;
        }
        #app-sidebar {
            width: 268px;
            flex-shrink: 0;
            background: #0b1220;
            color: #cbd5e1;
            border-right: 1px solid #1e293b;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }
        #app-sidebar .sidebar-brand {
            padding: 1rem 1rem 0.75rem;
            border-bottom: 1px solid #1e293b;
        }
        #app-sidebar .sidebar-brand .brand-title {
            color: #f8fafc;
            font-weight: 700;
            font-size: 0.95rem;
        }
        #app-sidebar .sidebar-section-label {
            margin: 1rem 1rem 0.4rem;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #64748b;
            font-weight: 700;
        }
        #app-sidebar .sidebar-group {
            margin: 0.35rem 0.55rem 0.75rem;
            padding: 0.35rem 0.2rem 0.45rem;
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.45);
            border: 1px solid #1e293b;
        }
        #app-sidebar .sidebar-group.is-cls {
            background: rgba(15, 23, 42, 0.25);
            border-style: dashed;
        }
        #app-sidebar .sidebar-group-title {
            margin: 0.15rem 0.45rem 0.35rem;
            padding: 0.4rem 0.55rem;
            border-radius: 8px;
            color: #e2e8f0;
            font-size: 0.78rem;
            font-weight: 650;
        }
        #app-sidebar .sidebar-nav-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            width: calc(100% - 0.9rem);
            margin: 0.12rem 0.45rem;
            padding: 0.5rem 0.65rem;
            border: none;
            border-radius: 7px;
            background: transparent;
            color: #94a3b8;
            text-align: left;
            font-size: 0.84rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }
        #app-sidebar .sidebar-nav-btn:hover {
            background: #1e293b;
            color: #f1f5f9;
        }
        #app-sidebar .sidebar-nav-btn.active {
            background: rgba(37, 99, 235, 0.28);
            color: #f8fafc;
            box-shadow: inset 3px 0 0 #60a5fa;
        }
        #app-sidebar .sidebar-nav-btn .step-num {
            width: 1.25rem;
            height: 1.25rem;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.2);
            color: inherit;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: 700;
            flex-shrink: 0;
        }
        #app-sidebar .sidebar-nav-btn.active .step-num {
            background: rgba(255,255,255,0.22);
        }
        #app-sidebar .nav-ico {
            width: 1.1rem;
            text-align: center;
            opacity: 0.85;
            flex-shrink: 0;
        }
        #app-sidebar .sidebar-footer {
            margin-top: auto;
            padding: 0.85rem;
            border-top: 1px solid #1e293b;
        }
        #app-main {
            flex: 1;
            min-width: 0;
            overflow-y: auto;
            background: var(--bg-main);
        }
        #app-main .main-pane-wrap {
            padding: 1.1rem 1.35rem 2rem;
        }
        .page-title-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .page-title-bar h2 {
            margin: 0;
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #0f172a;
        }
        @media (max-width: 900px) {
            .app-layout { flex-direction: column; }
            #app-sidebar { width: 100%; max-height: none; }
        }
        #module-gate {
            display: none;
            min-height: 100vh;
            align-items: center;
            justify-content: center;
            padding: 2rem 1rem;
            background:
                radial-gradient(ellipse at 20% 20%, rgba(37, 99, 235, 0.18), transparent 50%),
                radial-gradient(ellipse at 80% 0%, rgba(15, 23, 42, 0.12), transparent 45%),
                linear-gradient(160deg, #0f172a 0%, #1e293b 45%, #334155 100%);
            color: #f8fafc;
        }
        .module-gate-card {
            background: rgba(255, 255, 255, 0.96);
            color: #0f172a;
            border-radius: 18px;
            border: 1px solid #e2e8f0;
            padding: 1.75rem;
            height: 100%;
            cursor: pointer;
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
        }
        .module-gate-card:hover {
            transform: translateY(-4px);
            border-color: #2563eb;
            box-shadow: 0 16px 36px rgba(37, 99, 235, 0.22);
        }
        .module-gate-card.admin-card:hover {
            border-color: #d97706;
        }
        .module-icon {
            width: 56px;
            height: 56px;
            border-radius: 14px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            margin-bottom: 1rem;
        }
        .suggestion-card {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.75rem;
            background: #fff;
        }
        .suggestion-card.accepted { border-color: #86efac; background: #f0fdf4; }
        .suggestion-card.rejected { border-color: #fecaca; background: #fef2f2; opacity: 0.75; }
        .suggestion-card.edited { border-color: #93c5fd; background: #eff6ff; }
    </style>
</head>
<body class="console-mode-user module-gate-open">

<!-- Initial module chooser: keeps USER vs ADMIN workflows separate -->
<section id="module-gate" aria-label="Choose application module">
    <div class="container" style="max-width: 980px;">
        <div class="text-center mb-4">
            <div class="badge bg-light text-dark mb-3 px-3 py-2">Job Search Agent</div>
            <h1 class="fw-bold display-6 mb-2">Choose your module</h1>
            <p class="mb-0 opacity-75">Pick <strong>User</strong> for daily job search &amp; resume review, or <strong>Admin</strong> for setup, database, and profile tools. Roles stay separate to avoid confusion.</p>
        </div>
        <div class="row g-4">
            <div class="col-md-6">
                <div class="module-gate-card" id="enter-user-module" role="button" tabindex="0" onclick="enterModule('user')" onkeydown="if(event.key==='Enter')enterModule('user')">
                    <div class="module-icon bg-primary-subtle text-primary"><i class="bi bi-person-check"></i></div>
                    <h3 class="fw-bold h4">USER Module</h3>
                    <p class="text-muted mb-3">Daily workflow only: Web Tasks (discover → review → track) and CLS Tasks. No admin/database tools here.</p>
                    <ul class="small text-muted mb-4">
                        <li>Web Tasks: Discover → Review &amp; Optimize → Auto Apply → LinkedIn → Board</li>
                        <li>CLS Tasks: sync, analyze, list, report helpers</li>
                    </ul>
                    <span class="btn btn-primary w-100"><i class="bi bi-box-arrow-in-right"></i> Enter User Module</span>
                </div>
            </div>
            <div class="col-md-6">
                <div class="module-gate-card admin-card" id="enter-admin-module" role="button" tabindex="0" onclick="enterModule('admin')" onkeydown="if(event.key==='Enter')enterModule('admin')">
                    <div class="module-icon bg-warning-subtle text-warning"><i class="bi bi-shield-lock"></i></div>
                    <h3 class="fw-bold h4">ADMIN Module</h3>
                    <p class="text-muted mb-3">Setup &amp; maintenance only: health, profile optimize, database, full CLI. No daily discovery/review board here.</p>
                    <ul class="small text-muted mb-4">
                        <li>System Health, Profile &amp; Skills</li>
                        <li>Database Explorer &amp; Cleanup</li>
                        <li>Full CLI Runner &amp; Demo Seed</li>
                    </ul>
                    <span class="btn btn-warning text-dark w-100"><i class="bi bi-gear-wide-connected"></i> Enter Admin Module</span>
                </div>
            </div>
        </div>
    </div>
</section>

<div id="app-shell">
<header class="app-header d-flex justify-content-between align-items-center">
    <div>
        <h4 class="mb-0 fw-bold"><i class="bi bi-robot"></i> Job Search Agent</h4>
        <small class="text-light-50" id="header-module-subtitle">Select a module to begin</small>
    </div>
    <div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">
        <span class="badge bg-light text-dark" id="console-mode-badge">User Mode</span>
        <button class="btn btn-sm btn-primary" onclick="loadAllData()"><i class="bi bi-arrow-clockwise"></i> Refresh</button>
        <button class="btn btn-sm btn-header-secondary user-only" onclick="openImportUrlModal()"><i class="bi bi-link-45deg"></i> Import URL</button>
        <a href="/capture" class="btn btn-sm btn-header-tertiary user-only" title="Install or re-install the 1-click Chrome bookmarklet"><i class="bi bi-bookmark-star"></i> Bookmarklet</a>
        <a href="/api/calendar.ics" class="btn btn-sm btn-header-tertiary user-only"><i class="bi bi-calendar-event"></i> Calendar</a>
        <button type="button" class="btn btn-sm btn-header-tertiary" id="console-mode-home" onclick="showModuleGate()" title="Return to USER / ADMIN module chooser">
            <i class="bi bi-grid-1x2"></i> Switch Module
        </button>
    </div>
</header>

<!-- Global Event Progress Bar Container (sticky, always visible while an action runs) -->
<div id="global-progress-wrapper" aria-live="polite" aria-busy="false">
    <div class="d-flex justify-content-between align-items-center mb-2">
        <span id="global-progress-status"><i class="bi bi-arrow-repeat spin text-primary me-1"></i> Processing event...</span>
        <span id="global-progress-percent">0%</span>
    </div>
    <div class="progress">
        <div id="global-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated bg-primary" role="progressbar" style="width: 0%; transition: width 0.25s ease;" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"></div>
    </div>
</div>

<div class="app-layout">
    <aside id="app-sidebar" aria-label="Module navigation">
        <div class="sidebar-brand">
            <div class="brand-title" id="sidebar-module-title">USER Module</div>
            <div class="small text-secondary" id="sidebar-module-hint">Step-by-step daily workflow</div>
        </div>

        <!-- USER exclusive navigation -->
        <div class="user-only" id="user-sidebar-nav">
            <div class="sidebar-section-label">User</div>
            <div class="sidebar-group">
                <div class="sidebar-group-title"><i class="bi bi-window-sidebar me-1"></i> Web Tasks</div>
                <button type="button" class="sidebar-nav-btn active" id="dashboard-tab" data-pane="dashboard-pane" onclick="navigateTo('dashboard-tab')"><span class="step-num">1</span><i class="bi bi-speedometer2 nav-ico"></i> Dashboard</button>
                <button type="button" class="sidebar-nav-btn" id="discovery-tab" data-pane="discovery-pane" onclick="navigateTo('discovery-tab')"><span class="step-num">2</span><i class="bi bi-compass nav-ico"></i> Discover Jobs</button>
                <button type="button" class="sidebar-nav-btn" id="review-tab" data-pane="review-pane" onclick="navigateTo('review-tab')"><span class="step-num">3</span><i class="bi bi-file-earmark-check nav-ico"></i> Review &amp; Optimize</button>
                <button type="button" class="sidebar-nav-btn" id="auto-apply-tab" data-pane="auto-apply-pane" onclick="navigateTo('auto-apply-tab')"><span class="step-num">4</span><i class="bi bi-send-check nav-ico"></i> Auto Apply</button>
                <button type="button" class="sidebar-nav-btn" id="linkedin-tab" data-pane="linkedin-pane" onclick="navigateTo('linkedin-tab')"><span class="step-num">5</span><i class="bi bi-linkedin nav-ico"></i> LinkedIn Optimization</button>
                <button type="button" class="sidebar-nav-btn" id="kanban-tab" data-pane="kanban-pane" onclick="navigateTo('kanban-tab')"><span class="step-num">6</span><i class="bi bi-kanban nav-ico"></i> Application Board</button>
            </div>
            <div class="sidebar-group is-cls">
                <div class="sidebar-group-title"><i class="bi bi-terminal me-1"></i> CLS Tasks</div>
                <button type="button" class="sidebar-nav-btn" id="cls-tab" data-pane="cls-pane" onclick="navigateTo('cls-tab')"><span class="step-num">7</span><i class="bi bi-code-slash nav-ico"></i> CLS Command Tasks</button>
            </div>
        </div>

        <!-- ADMIN exclusive navigation -->
        <div class="admin-only" id="admin-sidebar-nav">
            <div class="sidebar-section-label">Admin</div>
            <div class="sidebar-group">
                <button type="button" class="sidebar-nav-btn" id="admin-home-tab" data-pane="admin-home-pane" onclick="navigateTo('admin-home-tab');"><span class="step-num">1</span><i class="bi bi-heart-pulse nav-ico"></i> System Health &amp; Setup</button>
                <button type="button" class="sidebar-nav-btn" id="profile-tab" data-pane="profile-pane" onclick="navigateTo('profile-tab')"><span class="step-num">2</span><i class="bi bi-person-gear nav-ico"></i> Profile &amp; Skills</button>
                <button type="button" class="sidebar-nav-btn" id="db-tab" data-pane="db-pane" onclick="navigateTo('db-tab'); loadDbExplorer();"><span class="step-num">3</span><i class="bi bi-database nav-ico"></i> Database Explorer</button>
                <button type="button" class="sidebar-nav-btn" id="cheatsheet-tab" data-pane="cheatsheet-pane" onclick="navigateTo('cheatsheet-tab')"><span class="step-num">4</span><i class="bi bi-terminal-fill nav-ico"></i> Full CLI Runner</button>
            </div>
        </div>

        <div class="sidebar-footer">
            <button type="button" class="btn btn-sm btn-outline-light w-100" onclick="showModuleGate()"><i class="bi bi-box-arrow-left"></i> Exit to Module Chooser</button>
        </div>
    </aside>

    <main id="app-main">
    <div class="main-pane-wrap">
    <!-- Hidden bootstrap-compatible tab triggers kept for compatibility -->
    <ul class="nav nav-tabs d-none" id="mainTabs" role="tablist">
        <li class="nav-item user-only"><button class="nav-link active" id="dashboard-tab-bs" data-bs-toggle="tab" data-bs-target="#dashboard-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="discovery-tab-bs" data-bs-toggle="tab" data-bs-target="#discovery-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="review-tab-bs" data-bs-toggle="tab" data-bs-target="#review-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="auto-apply-tab-bs" data-bs-toggle="tab" data-bs-target="#auto-apply-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="linkedin-tab-bs" data-bs-toggle="tab" data-bs-target="#linkedin-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="kanban-tab-bs" data-bs-toggle="tab" data-bs-target="#kanban-pane"></button></li>
        <li class="nav-item user-only"><button class="nav-link" id="cls-tab-bs" data-bs-toggle="tab" data-bs-target="#cls-pane"></button></li>
        <li class="nav-item admin-only"><button class="nav-link" id="admin-home-tab-bs" data-bs-toggle="tab" data-bs-target="#admin-home-pane"></button></li>
        <li class="nav-item admin-only"><button class="nav-link" id="db-tab-bs" data-bs-toggle="tab" data-bs-target="#db-pane"></button></li>
        <li class="nav-item admin-only"><button class="nav-link" id="profile-tab-bs" data-bs-toggle="tab" data-bs-target="#profile-pane"></button></li>
        <li class="nav-item admin-only"><button class="nav-link" id="cheatsheet-tab-bs" data-bs-toggle="tab" data-bs-target="#cheatsheet-pane"></button></li>
    </ul>

    <div class="tab-content" id="mainTabsContent">
        
        <!-- DASHBOARD PANE (USER Web Tasks step 1) -->
        <div class="tab-pane fade show active user-only" id="dashboard-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-speedometer2 text-primary"></i> Dashboard</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks</span>
            </div>

            <!-- Primary Actions first (actions over metrics) -->
            <div class="card border-0 shadow-sm mb-4" id="primary-actions-card">
                <div class="card-header bg-white fw-bold py-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <span><i class="bi bi-lightning-charge-fill text-warning"></i> Primary Actions</span>
                    <span class="badge bg-primary-subtle text-primary">Start here</span>
                </div>
                <div class="card-body">
                    <p class="small text-muted mb-3 mb-md-4">Daily workflow: discover on platforms, sync inbox alerts (Gmail or Hotmail/Outlook), import a job URL, then review ATS resume drafts.</p>
                    <div class="row g-3">
                        <div class="col-md-6 col-xl-3">
                            <button type="button" class="action-tile is-primary" onclick="goFindJobsNow()">
                                <span class="action-title"><i class="bi bi-search me-1"></i> Job Discovery</span>
                                <span class="action-sub">Choose platforms &amp; find jobs</span>
                            </button>
                        </div>
                        <div class="col-md-6 col-xl-3">
                            <button type="button" class="action-tile" onclick="openEmailSyncModal()">
                                <span class="action-title"><i class="bi bi-envelope-at me-1"></i> Sync Email Alerts</span>
                                <span class="action-sub">Gmail + Hotmail / Outlook</span>
                            </button>
                        </div>
                        <div class="col-md-6 col-xl-3">
                            <button type="button" class="action-tile" onclick="openImportUrlModal()">
                                <span class="action-title"><i class="bi bi-link-45deg me-1"></i> Import Job URL</span>
                                <span class="action-sub">Paste a listing link</span>
                            </button>
                        </div>
                        <div class="col-md-6 col-xl-3">
                            <button type="button" class="action-tile is-warning" onclick="navigateTo('review-tab')">
                                <span class="action-title"><i class="bi bi-file-earmark-check me-1"></i> Review Resume Drafts</span>
                                <span class="action-sub">Approve ATS-optimized drafts</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="stat-card" data-accent="jobs" id="stat-card-jobs">
                        <div class="stat-label">Discovered Jobs</div>
                        <div class="stat-value text-primary" id="stat-total-jobs">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card" data-accent="review" id="stat-card-review">
                        <div class="stat-label">Requiring Review</div>
                        <div class="stat-value text-warning" id="stat-review-count">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card" data-accent="drafts" id="stat-card-drafts">
                        <div class="stat-label">Draft Resumes</div>
                        <div class="stat-value text-danger" id="stat-drafts-count">0</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card" data-accent="apps" id="stat-card-apps">
                        <div class="stat-label">Applications In Progress</div>
                        <div class="stat-value text-success" id="stat-applied-count">0</div>
                    </div>
                </div>
            </div>

            <div class="alert alert-primary border-0 shadow-sm mb-3 py-2" id="user-focus-banner">
                <div class="small mb-0"><i class="bi bi-briefcase-fill me-1"></i> Daily workspace: use <strong>Primary Actions</strong> above, then follow <strong>Web Tasks</strong> in the sidebar. Expand Getting started for setup tools.</div>
            </div>

            <!-- Getting started (collapsed by default to reduce first-viewport clutter) -->
            <div class="accordion mb-4" id="getting-started-accordion">
                <div class="accordion-item border-0 shadow-sm">
                    <h2 class="accordion-header">
                        <button class="accordion-button collapsed py-3 fw-semibold" type="button" data-bs-toggle="collapse" data-bs-target="#getting-started-body" aria-expanded="false" aria-controls="getting-started-body">
                            <i class="bi bi-rocket-takeoff text-primary me-2"></i> Getting started &amp; tools
                        </button>
                    </h2>
                    <div id="getting-started-body" class="accordion-collapse collapse" data-bs-parent="#getting-started-accordion">
                        <div class="accordion-body">
                            <div class="card border mb-3" id="user-setup-status-card">
                                <div class="card-body py-3 d-flex flex-wrap align-items-center justify-content-between gap-2">
                                    <div>
                                        <div class="fw-bold mb-1"><i class="bi bi-check2-circle text-success"></i> Ready to search</div>
                                        <div class="small text-muted mb-0" id="user-setup-summary">Loading setup status...</div>
                                    </div>
                                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="showModuleGate()"><i class="bi bi-grid-1x2"></i> Switch to Admin Module</button>
                                </div>
                            </div>
                            <div class="card border" id="bookmarklet-install-card">
                                <div class="card-body d-flex flex-wrap gap-3 align-items-center justify-content-between py-3">
                                    <div>
                                        <div class="fw-bold mb-1"><i class="bi bi-bookmark-star-fill text-warning"></i> Chrome Bookmarklet</div>
                                        <div class="text-muted small mb-0">
                                            Save jobs from Indeed, LinkedIn, Dice, and other sites with one click while browsing.
                                            <span id="bookmarklet-install-status" class="ms-1"></span>
                                        </div>
                                    </div>
                                    <div class="d-flex gap-2 flex-wrap">
                                        <a href="/capture" class="btn btn-warning text-dark"><i class="bi bi-bookmark-plus"></i> Install Bookmarklet</a>
                                        <button class="btn btn-outline-secondary btn-sm" onclick="clearBookmarkletInstalledFlag()" id="bookmarklet-reset-btn" style="display:none;"><i class="bi bi-arrow-counterclockwise"></i> Reset Install Status</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row g-3">
                <div class="col-md-8">
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-3">
                            <span><i class="bi bi-star-fill text-warning"></i> High-Match Opportunities <small class="text-muted fw-normal">(score ≥ 65)</small></span>
                            <button class="btn btn-sm btn-outline-primary" onclick="runAnalyzeJobs()"><i class="bi bi-cpu"></i> Re-Score Jobs</button>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive">
                                <table class="table table-hover align-middle mb-0 jobs-table" id="high-score-table">
                                    <colgroup>
                                        <col class="col-id"><col class="col-score"><col>
                                        <col><col class="col-platform"><col class="col-actions">
                                    </colgroup>
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th class="text-center">Score</th>
                                            <th>Job Title</th>
                                            <th>Company</th>
                                            <th>Platform</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr><td colspan="6" class="text-center py-3 text-muted">Loading high score jobs...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-3">
                            <span><i class="bi bi-clock-history text-primary"></i> Recently Discovered Jobs</span>
                            <small class="text-muted">All scores · newest first</small>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive">
                                <table class="table table-hover align-middle mb-0 jobs-table" id="recent-jobs-table">
                                    <colgroup>
                                        <col class="col-id"><col class="col-score"><col>
                                        <col><col class="col-platform"><col class="col-actions">
                                    </colgroup>
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th class="text-center">Score</th>
                                            <th>Title</th>
                                            <th>Company</th>
                                            <th>Platform</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr><td colspan="6" class="text-center py-3 text-muted">Loading recent jobs...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-md-4">
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold py-3">
                            <i class="bi bi-activity text-primary"></i> Recent Activity
                        </div>
                        <div class="card-body p-0" style="max-height: 420px; overflow-y: auto;">
                            <ul class="activity-timeline" id="activity-feed-list">
                                <li class="text-muted text-center py-3">Loading recent events...</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- JOB DISCOVERY PANE (USER Web Tasks step 2) -->
        <div class="tab-pane fade user-only" id="discovery-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-compass text-primary"></i> Discover Jobs</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks · Step 2</span>
            </div>
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-white fw-bold py-3">
                    <i class="bi bi-globe-americas text-primary"></i> Top 10 USA Job Platforms Adapter Suite
                </div>
                <div class="card-body">
                    <p class="text-muted small mb-3">Select the job sites you want to search, then click <strong>Find Jobs Now</strong>. Each selected platform returns up to <strong>3 recent jobs</strong> (posted in the last 14 days). The top 3 recommended platforms are pre-selected.</p>
                    <div class="d-flex flex-wrap gap-2 mb-3">
                        <button type="button" class="btn btn-sm btn-outline-primary" onclick="selectRecommendedPlatforms()"><i class="bi bi-star-fill"></i> Top 3 Recommended</button>
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="selectAllPlatforms(true)"><i class="bi bi-check2-all"></i> Select All</button>
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="selectAllPlatforms(false)"><i class="bi bi-x-lg"></i> Clear All</button>
                    </div>
                    <div class="row row-cols-2 row-cols-md-5 g-2 mb-3" id="top-10-platforms-grid">
                        <!-- Platform checkboxes generated dynamically -->
                    </div>
                    <div class="d-flex justify-content-between align-items-center border-top pt-3">
                        <div class="d-flex gap-2 align-items-center flex-wrap">
                            <span class="small fw-bold">Selected:</span>
                            <span class="badge bg-primary" id="selected-platform-count">0</span>
                            <span class="small text-muted">· up to 3 jobs per site</span>
                        </div>
                        <button class="btn btn-primary" id="btn-find-jobs-now" onclick="runTop10JobSearch()"><i class="bi bi-search"></i> Find Jobs Now</button>
                    </div>
                </div>
            </div>

            <div class="card border-0 shadow-sm mb-4" id="platform-search-results-card" style="display:none;">
                <div class="card-header bg-white fw-bold py-3"><i class="bi bi-bar-chart-steps text-info"></i> Last Platform Search Results</div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-sm table-hover mb-0" id="platform-search-results-table">
                            <thead class="table-light">
                                <tr>
                                    <th>Platform</th>
                                    <th>Tier</th>
                                    <th>Status</th>
                                    <th>Imported</th>
                                    <th>Message</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Job Listings Table -->
            <div class="card border-0 shadow-sm">
                <div class="card-header bg-white d-flex justify-content-between align-items-center py-3">
                    <h5 class="fw-bold mb-0"><i class="bi bi-list-stars"></i> Discovered Job Listings</h5>
                    <button class="btn btn-sm btn-outline-primary" onclick="fetchJobs()"><i class="bi bi-arrow-clockwise"></i> Refresh List</button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle mb-0 jobs-table" id="all-jobs-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Status</th>
                                    <th class="text-center">Score</th>
                                    <th>Title</th>
                                    <th>Company</th>
                                    <th>Platform</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td colspan="7" class="text-center py-4 text-muted">Loading job listings...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- RESUME REVIEW & APPROVALS PANE (USER Web Tasks step 3) -->
        <div class="tab-pane fade user-only" id="review-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-file-earmark-check text-success"></i> Review &amp; Optimize</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks · Step 3</span>
            </div>
            <div class="card border-0 shadow-sm max-w-900 mx-auto">
                <div class="card-header bg-white fw-bold py-3 d-flex justify-content-between align-items-center">
                    <span><i class="bi bi-shield-check text-success"></i> Review-First Resume Tailoring & Draft Approval</span>
                    <span class="badge bg-warning text-dark"><i class="bi bi-lock-fill"></i> Human Approval Required</span>
                </div>
                <div class="card-body">
                    <div class="alert alert-info small mb-4">
                        <i class="bi bi-info-circle-fill"></i> <strong>Safety Rule:</strong> Generating ATS tailored resumes creates a versioned draft in <code>_drafts/</code>. Your master resume and finalized applied resume are <strong>never overwritten</strong> until you click "Approve & Finalize".
                    </div>

                    <div class="mb-4">
                        <label class="form-label fw-semibold">Select Job for Resume Review:</label>
                        <select class="form-select" id="review-job-select" onchange="loadJobForReview(this.value)">
                            <option value="">Select a job from list...</option>
                        </select>
                    </div>

                    <div id="resume-review-details" style="display: none;">
                        <!-- 3-Way Resume Version Cards -->
                        <div class="row g-3 mb-4">
                            <div class="col-md-4">
                                <div class="card border-secondary h-100">
                                    <div class="card-header bg-light fw-bold small text-muted">1. Master Resume</div>
                                    <div class="card-body fs-8">
                                        <p class="mb-1"><strong>Source:</strong> <code id="rev-master-path">-</code></p>
                                        <small class="text-muted">Factual source of truth. Unchanged.</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="card border-warning h-100">
                                    <div class="card-header bg-warning-subtle text-dark fw-bold small">2. Tailored Draft Resume</div>
                                    <div class="card-body fs-8">
                                        <p class="mb-1"><strong>Draft File:</strong> <code id="rev-draft-path">-</code></p>
                                        <span class="badge bg-warning text-dark mb-2" id="rev-approval-badge">Awaiting Review</span>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="card border-success h-100">
                                    <div class="card-header bg-success-subtle text-success fw-bold small">3. Finalized Resume</div>
                                    <div class="card-body fs-8">
                                        <p class="mb-1"><strong>Final Folder:</strong> <code id="rev-final-path">Not finalized yet</code></p>
                                        <small class="text-muted">Promoted only upon explicit approval.</small>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Diff / Change Summary Box -->
                        <div class="card border-0 shadow-sm mb-4">
                            <div class="card-header bg-dark text-white fw-bold small">
                                <i class="bi bi-file-diff"></i> Tailoring Analysis & Change Summary
                            </div>
                            <div class="card-body bg-dark text-info font-monospace fs-8 p-3" id="rev-diff-summary" style="max-height: 250px; overflow-y: auto; white-space: pre-wrap;">
                                Select a job above to view ATS keyword alignment and change summary...
                            </div>
                        </div>

                        <!-- AI Optimize (Jobscan-style) -->
                        <div class="card border-0 shadow-sm mb-4" id="ai-optimize-panel">
                            <div class="card-header bg-white d-flex justify-content-between align-items-center flex-wrap gap-2 py-3">
                                <div>
                                    <div class="fw-bold"><i class="bi bi-magic text-primary"></i> AI Optimize</div>
                                    <div class="small text-muted">Keyword weaving, bullet rewrites, and ATS phrasing — accept, reject, or edit each suggestion before applying.</div>
                                </div>
                                <div class="d-flex gap-2">
                                    <button type="button" class="btn btn-sm btn-primary" id="btn-run-optimize" onclick="runAiOptimize()"><i class="bi bi-stars"></i> Run AI Optimize</button>
                                    <button type="button" class="btn btn-sm btn-outline-success" id="btn-apply-optimize" onclick="applyAcceptedOptimize()" disabled><i class="bi bi-check2-all"></i> Apply Accepted to Draft</button>
                                </div>
                            </div>
                            <div class="card-body">
                                <div class="row g-3 mb-3" id="optimize-score-row" style="display:none;">
                                    <div class="col-md-3">
                                        <div class="stat-card py-2">
                                            <div class="text-muted small">Profile Readiness</div>
                                            <div class="stat-value text-primary fs-3" id="opt-readiness">-</div>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="small fw-semibold mb-1">Matched keywords</div>
                                        <div id="opt-matched" class="small text-success"></div>
                                    </div>
                                    <div class="col-md-5">
                                        <div class="small fw-semibold mb-1">Recruiter keyword gaps</div>
                                        <div id="opt-gaps" class="small text-danger"></div>
                                    </div>
                                </div>
                                <div id="optimize-suggestions-list" class="text-muted small">Generate a draft first, then run AI Optimize to see editable suggestions.</div>
                            </div>
                        </div>

                        <!-- Approval Actions -->
                        <div class="d-flex justify-content-between align-items-center bg-light p-3 rounded border">
                            <div>
                                <button class="btn btn-sm btn-outline-secondary" id="btn-create-draft" onclick="generateDraftForSelectedJob()"><i class="bi bi-cpu"></i> Generate New Draft</button>
                            </div>
                            <div class="d-flex gap-2">
                                <button class="btn btn-danger" onclick="rejectDraftForSelectedJob()"><i class="bi bi-x-circle"></i> Reject Draft</button>
                                <button class="btn btn-success fw-bold" onclick="promptApproveDraftModal()"><i class="bi bi-check-circle-fill"></i> Approve & Finalize Resume</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- AUTO APPLY PANE (USER Web Tasks step 4) -->
        <div class="tab-pane fade user-only" id="auto-apply-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-send-check text-success"></i> Auto Apply</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks · Step 4</span>
            </div>
            <div class="alert alert-info small">
                <strong>Review-gated assisted apply:</strong> available only after you approve an ATS-optimized resume.
                This opens the employer application page and your finalized resume folder. It does <em>not</em> bypass CAPTCHAs or silently submit forms.
            </div>
            <div class="card border-0 shadow-sm mb-3">
                <div class="card-body">
                    <label class="form-label fw-semibold">Select approved job</label>
                    <select class="form-select mb-3" id="auto-apply-job-select" onchange="loadAutoApplyEligibility(this.value)">
                        <option value="">Select a job...</option>
                    </select>
                    <div id="auto-apply-eligibility" class="small text-muted mb-3">Select a job to check Auto Apply readiness.</div>
                    <div class="d-flex flex-wrap gap-2">
                        <button type="button" class="btn btn-success" id="btn-launch-auto-apply" onclick="launchAutoApply(false)" disabled>
                            <i class="bi bi-box-arrow-up-right"></i> Launch Auto Apply
                        </button>
                        <button type="button" class="btn btn-outline-danger" id="btn-launch-auto-apply-mark" onclick="launchAutoApply(true)" disabled>
                            <i class="bi bi-check2-circle"></i> Launch &amp; Mark Applied
                        </button>
                        <button type="button" class="btn btn-outline-secondary" onclick="navigateTo('review-tab')">
                            <i class="bi bi-file-earmark-check"></i> Go to Review &amp; Optimize
                        </button>
                    </div>
                </div>
            </div>
            <div class="card border-0 shadow-sm">
                <div class="card-header bg-white fw-bold">Apply checklist</div>
                <ul class="list-group list-group-flush" id="auto-apply-checklist">
                    <li class="list-group-item text-muted small">Checklist appears after launch.</li>
                </ul>
            </div>
        </div>

        <!-- LINKEDIN OPTIMIZATION PANE (USER Web Tasks step 5) -->
        <div class="tab-pane fade user-only" id="linkedin-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-linkedin text-primary"></i> LinkedIn Optimization</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks · Step 5</span>
            </div>
            <div class="alert alert-secondary small">
                Dedicated LinkedIn optimizer: readiness score, recruiter keyword gaps, 220-character headline, About summary, and skills audit.
                Nothing is published to LinkedIn automatically — copy after you review.
            </div>
            <div class="card border-0 shadow-sm mb-3">
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label fw-semibold" for="li-target-role">Target LinkedIn role / headline focus</label>
                            <input type="text" class="form-control" id="li-target-role" placeholder="e.g. Staff Backend Engineer">
                        </div>
                        <div class="col-md-6 d-flex align-items-end">
                            <button type="button" class="btn btn-primary" onclick="runLinkedInOptimize()"><i class="bi bi-stars"></i> Optimize LinkedIn Profile</button>
                        </div>
                        <div class="col-12">
                            <label class="form-label fw-semibold" for="li-job-description">Optional job description / industry keywords</label>
                            <textarea class="form-control" id="li-job-description" rows="4" placeholder="Paste a target job description or industry keywords to optimize against..."></textarea>
                        </div>
                    </div>
                </div>
            </div>
            <div id="linkedin-optimize-results" class="small text-muted">Run Optimize LinkedIn Profile to generate headline, About, gaps, and skills audit.</div>
        </div>

        <!-- KANBAN BOARD PANE (USER Web Tasks step 6) -->
        <div class="tab-pane fade user-only" id="kanban-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-kanban text-primary"></i> Application Board</h2>
                <span class="badge bg-primary-subtle text-primary">Web Tasks · Step 6</span>
            </div>
            <div class="row g-3" id="kanban-board-container">
                <!-- Columns loaded dynamically -->
            </div>
        </div>

        <!-- CLS TASKS PANE (USER) -->
        <div class="tab-pane fade user-only" id="cls-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-terminal text-dark"></i> CLS Tasks</h2>
                <span class="badge bg-dark-subtle text-dark">User · Command helpers</span>
            </div>
            <div class="alert alert-secondary small">
                Safe day-to-day command tasks for users (sync, analyze, list jobs, tailor, reports). Full admin CLI (setup, purge, backups) lives only in the <strong>Admin</strong> module.
            </div>
            <div class="row g-3">
                <div class="col-lg-7">
                    <div class="card border-0 shadow-sm">
                        <div class="card-header bg-white fw-bold">Common CLS Tasks</div>
                        <div class="card-body" id="cls-task-cards">
                            <div class="d-grid gap-2">
                                <button class="btn btn-outline-primary text-start" onclick="openEmailSyncModal()"><i class="bi bi-envelope-at"></i> Sync Email Alerts (Gmail / Hotmail)</button>
                                <button class="btn btn-outline-primary text-start" onclick="runClsTask('analyze', [])"><i class="bi bi-cpu"></i> Re-Score All Jobs</button>
                                <button class="btn btn-outline-primary text-start" onclick="runClsTask('jobs', [])"><i class="bi bi-list-ul"></i> List Tracked Jobs</button>
                                <button class="btn btn-outline-primary text-start" onclick="runClsTask('report', [])"><i class="bi bi-graph-up"></i> Pipeline Report</button>
                                <button class="btn btn-outline-primary text-start" onclick="runClsTask('follow-ups', [])"><i class="bi bi-alarm"></i> Follow-ups Due</button>
                                <button class="btn btn-outline-secondary text-start" onclick="runClsTask('statuses', [])"><i class="bi bi-tags"></i> List Status Values</button>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-lg-5">
                    <div class="card border-0 shadow-sm">
                        <div class="card-header bg-dark text-white fw-bold d-flex justify-content-between">
                            <span><i class="bi bi-terminal-fill text-success"></i> CLS Output</span>
                            <button class="btn btn-sm btn-outline-secondary text-white" onclick="clearClsTerminal()">Clear</button>
                        </div>
                        <div class="card-body p-2 bg-dark">
                            <div class="terminal-box" id="cls-terminal-output">Ready. Pick a CLS task on the left.</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- ADMIN HOME PANE -->
        <div class="tab-pane fade admin-only" id="admin-home-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-shield-lock text-warning"></i> System Health &amp; Setup</h2>
                <span class="badge bg-warning-subtle text-dark">Admin · Step 1</span>
            </div>
            <div class="alert alert-warning border-0 shadow-sm mb-4">
                <div class="fw-semibold mb-1">Admin-only workspace</div>
                <div class="small mb-0">Configure profile, inspect database, and run full CLI tools here. Daily discovery / resume review / application tracking are exclusive to the <strong>User</strong> module.</div>
            </div>
            <div class="card border-0 shadow-sm mb-4 border-start border-primary border-4" id="getting-started-flow">
                <div class="card-body py-3">
                    <div class="fw-bold mb-2"><i class="bi bi-signpost-split-fill text-primary"></i> Admin setup workflow</div>
                    <ol class="mb-0 small text-muted ps-3">
                        <li class="mb-1"><strong class="text-dark">Health</strong> — Confirm DB, Gmail OAuth, and master resume below.</li>
                        <li class="mb-1"><strong class="text-dark">Profile</strong> — Edit skills/titles and run Profile Optimize.</li>
                        <li class="mb-1"><strong class="text-dark">Data</strong> — Use Database Explorer for cleanup and inspection.</li>
                        <li class="mb-1"><strong class="text-dark">CLI</strong> — Use Full CLI Runner for advanced ops (backup, purge, setup).</li>
                        <li><strong class="text-dark">Handoff</strong> — Switch Module → User for daily Web Tasks.</li>
                    </ol>
                </div>
            </div>
            <div class="card border-0 shadow-sm mb-4" id="system-health-card">
                <div class="card-header bg-white fw-bold py-3 d-flex justify-content-between align-items-center">
                    <span><i class="bi bi-heart-pulse text-danger"></i> System Health & Setup Checklist</span>
                    <button class="btn btn-sm btn-outline-success" onclick="openSeedDemoModal()"><i class="bi bi-database-add"></i> Load Demo Jobs</button>
                </div>
                <div class="card-body">
                    <div class="row g-3 mb-3">
                        <div class="col-md-4">
                            <div class="small text-muted">Database</div>
                            <div class="fw-semibold text-truncate" id="health-db-path" title="">-</div>
                        </div>
                        <div class="col-md-4">
                            <div class="small text-muted">Gmail OAuth</div>
                            <div id="health-gmail-status">-</div>
                        </div>
                        <div class="col-md-4">
                            <div class="small text-muted">Master Resume</div>
                            <div id="health-resume-status">-</div>
                        </div>
                    </div>
                    <div class="mb-2 fw-semibold small">Getting started checklist:</div>
                    <ul class="list-group list-group-flush small" id="onboarding-checklist"></ul>
                </div>
            </div>
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-white fw-bold py-3">Recent jobs (admin verify)</div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle mb-0" id="admin-recent-jobs-table">
                            <thead class="table-light">
                                <tr><th>ID</th><th>Score</th><th>Title</th><th>Company</th><th>Platform</th></tr>
                            </thead>
                            <tbody>
                                <tr><td colspan="5" class="text-center py-3 text-muted">Load demo jobs or wait for user imports...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- DATABASE EXPLORER PANE -->
        <div class="tab-pane fade admin-only" id="db-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-database-gear text-primary"></i> Database Explorer</h2>
                <span class="badge bg-warning-subtle text-dark">Admin · Step 3</span>
            </div>
            <div class="row g-3 mb-4">
                <div class="col-md-4">
                    <div class="card border-0 shadow-sm h-100">
                        <div class="card-header bg-white fw-bold py-3">
                            <i class="bi bi-trash3 text-danger"></i> Data Cleanup Tools
                        </div>
                        <div class="card-body">
                            <p class="text-muted small">Select an automated cleanup action to reset or prune your local SQLite database before testing.</p>
                            <div class="d-grid gap-2">
                                <button class="btn btn-outline-secondary text-start" onclick="triggerQuickCleanup('duplicates')"><i class="bi bi-copy"></i> Delete Duplicate Jobs</button>
                                <button class="btn btn-outline-warning text-start" onclick="triggerQuickCleanup('stale')"><i class="bi bi-hourglass-bottom"></i> Delete Stale & Excluded Jobs</button>
                                <button class="btn btn-danger text-start fw-bold" onclick="triggerQuickCleanup('all')"><i class="bi bi-exclamation-triangle-fill"></i> Purge All Database Test Data</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-md-8">
                    <div class="card border-0 shadow-sm h-100">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-2">
                            <span><i class="bi bi-table text-primary"></i> SQLite Table Browser</span>
                            <select class="form-select form-select-sm" id="db-table-selector" style="width: auto;" onchange="loadTableData(this.value)">
                                <option value="jobs">jobs</option>
                                <option value="activity_logs">activity_logs</option>
                                <option value="contacts">contacts</option>
                                <option value="interviews">interviews</option>
                                <option value="application_answers">application_answers</option>
                                <option value="processed_emails">processed_emails</option>
                            </select>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive" style="max-height: 380px; overflow-y: auto;">
                                <table class="table table-sm table-hover align-middle mb-0 fs-8" id="db-browser-table">
                                    <thead class="table-light"><tr><th>Select a table above...</th></tr></thead>
                                    <tbody><tr><td class="text-center py-4 text-muted">Loading table data...</td></tr></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- PROFILE & SKILLS EDITOR PANE -->
        <div class="tab-pane fade admin-only" id="profile-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-person-gear text-primary"></i> Profile &amp; Skills</h2>
                <span class="badge bg-warning-subtle text-dark">Admin · Step 2</span>
            </div>
            <div class="card border-0 shadow-sm max-w-800 mx-auto">
                <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <h5 class="fw-bold mb-0 text-dark">
                            <i class="bi bi-person-gear text-primary me-2"></i>Profile &amp; Skills Editor
                        </h5>
                        <div class="text-muted small mt-1">
                            <i class="bi bi-info-circle me-1"></i> Optional candidate preferences used for job matching, scoring &amp; resume tailoring.
                        </div>
                    </div>
                    <span class="badge bg-light text-primary border border-primary-subtle px-3 py-2 rounded-pill fs-6 fw-normal">
                        <i class="bi bi-arrow-repeat text-success me-1"></i> Optional &amp; Synced with <code>config.yaml</code>
                    </span>
                </div>
                <div class="card-body">
                    <form id="profile-editor-form" onsubmit="saveProfileForm(event)">
                        <!-- Section: Target Job Titles & Experience -->
                        <div class="row g-3 mb-3">
                            <div class="col-md-8">
                                <label class="form-label fw-semibold" for="prof-titles">Target Job Titles (comma separated)</label>
                                <input type="text" class="form-control" id="prof-titles" placeholder="e.g. Staff Software Engineer, Senior Developer, Tech Lead">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-titles-input" placeholder="Add keyword title..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-titles', 'add-kw-titles-input');}">
                                    <button class="btn btn-outline-primary" type="button" onclick="addKeywordFromInput('prof-titles', 'add-kw-titles-input')"><i class="bi bi-plus-lg"></i> Add Title Keyword</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-titles">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-semibold" for="prof-exp">Years of Experience</label>
                                <input type="number" class="form-control" id="prof-exp" min="0" placeholder="e.g. 8">
                                <small class="text-muted d-block mt-1" id="preview-exp">Config.yaml current: (loading...)</small>
                            </div>
                        </div>

                        <!-- Section: Skills -->
                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold" for="prof-req-skills">Required Skills (comma separated)</label>
                                <textarea class="form-control" id="prof-req-skills" rows="3" placeholder="e.g. Python, Docker, PostgreSQL, AWS"></textarea>
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-req-skills-input" placeholder="Add required skill keyword..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-req-skills', 'add-kw-req-skills-input');}">
                                    <button class="btn btn-outline-primary" type="button" onclick="addKeywordFromInput('prof-req-skills', 'add-kw-req-skills-input')"><i class="bi bi-plus-lg"></i> Add Skill Keyword</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-req-skills">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold" for="prof-pref-skills">Preferred Skills (comma separated)</label>
                                <textarea class="form-control" id="prof-pref-skills" rows="3" placeholder="e.g. Kubernetes, Kafka, GraphQL, React"></textarea>
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-pref-skills-input" placeholder="Add preferred skill keyword..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-pref-skills', 'add-kw-pref-skills-input');}">
                                    <button class="btn btn-outline-primary" type="button" onclick="addKeywordFromInput('prof-pref-skills', 'add-kw-pref-skills-input')"><i class="bi bi-plus-lg"></i> Add Skill Keyword</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-pref-skills">Config.yaml current: (loading...)</small>
                            </div>
                        </div>

                        <!-- Section: Location & Salary -->
                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold" for="prof-locations">Target Locations (comma separated)</label>
                                <input type="text" class="form-control" id="prof-locations" placeholder="e.g. Remote, San Francisco, CA, Austin, TX">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-locations-input" placeholder="Add location keyword..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-locations', 'add-kw-locations-input');}">
                                    <button class="btn btn-outline-primary" type="button" onclick="addKeywordFromInput('prof-locations', 'add-kw-locations-input')"><i class="bi bi-plus-lg"></i> Add Location Keyword</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-locations">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-3">
                                <label class="form-label fw-semibold" for="prof-salary">Target Minimum Salary (USD)</label>
                                <input type="number" class="form-control" id="prof-salary" placeholder="e.g. 130000" step="1000">
                                <div class="d-flex gap-1 mt-1 flex-wrap">
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary', 100000)">$100k</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary', 130000)">$130k</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary', 150000)">$150k</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-salary">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-3">
                                <label class="form-label fw-semibold" for="prof-salary-max">Target Maximum Salary (USD)</label>
                                <input type="number" class="form-control" id="prof-salary-max" placeholder="e.g. 180000" step="1000">
                                <div class="d-flex gap-1 mt-1 flex-wrap">
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary-max', 180000)">$180k</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary-max', 200000)">$200k</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="setSalaryValue('prof-salary-max', 250000)">$250k</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-salary-max">Config.yaml current: (loading...)</small>
                            </div>
                        </div>

                        <!-- Section: Additional Target Fields & Work Preferences -->
                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold" for="prof-industries">Target Industries (comma separated)</label>
                                <input type="text" class="form-control" id="prof-industries" placeholder="e.g. Financial Services, Fintech, SaaS">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-industries-input" placeholder="Add industry keyword..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-industries', 'add-kw-industries-input');}">
                                    <button class="btn btn-outline-primary" type="button" onclick="addKeywordFromInput('prof-industries', 'add-kw-industries-input')"><i class="bi bi-plus-lg"></i> Add Industry Keyword</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-industries">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold" for="prof-work-modes">Work Modes (comma separated)</label>
                                <input type="text" class="form-control" id="prof-work-modes" placeholder="e.g. remote, hybrid, on-site">
                                <div class="d-flex gap-1 mt-1 flex-wrap">
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="addKeyword('prof-work-modes', 'remote')">+ remote</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="addKeyword('prof-work-modes', 'hybrid')">+ hybrid</button>
                                    <button type="button" class="btn btn-sm btn-light border py-0 px-2 text-muted" onclick="addKeyword('prof-work-modes', 'on-site')">+ on-site</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-work-modes">Config.yaml current: (loading...)</small>
                            </div>
                        </div>

                        <!-- Section: Exclusions -->
                        <div class="row g-3 mb-3">
                            <div class="col-md-4">
                                <label class="form-label fw-semibold" for="prof-excluded-companies">Excluded Companies (comma separated)</label>
                                <input type="text" class="form-control" id="prof-excluded-companies" placeholder="e.g. SpamCorp, Bad Company">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-ex-comp-input" placeholder="Exclude company..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-excluded-companies', 'add-kw-ex-comp-input');}">
                                    <button class="btn btn-outline-secondary" type="button" onclick="addKeywordFromInput('prof-excluded-companies', 'add-kw-ex-comp-input')"><i class="bi bi-plus-lg"></i> Exclude</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-excluded-companies">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-semibold" for="prof-excluded-titles">Excluded Titles (comma separated)</label>
                                <input type="text" class="form-control" id="prof-excluded-titles" placeholder="e.g. intern, unpaid">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-ex-titles-input" placeholder="Exclude title..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-excluded-titles', 'add-kw-ex-titles-input');}">
                                    <button class="btn btn-outline-secondary" type="button" onclick="addKeywordFromInput('prof-excluded-titles', 'add-kw-ex-titles-input')"><i class="bi bi-plus-lg"></i> Exclude</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-excluded-titles">Config.yaml current: (loading...)</small>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-semibold" for="prof-excluded-skills">Excluded Skills (comma separated)</label>
                                <input type="text" class="form-control" id="prof-excluded-skills" placeholder="e.g. PHP, legacy COBOL">
                                <div class="input-group input-group-sm mt-1">
                                    <input type="text" class="form-control" id="add-kw-ex-skills-input" placeholder="Exclude skill..." onkeydown="if(event.key==='Enter'){event.preventDefault();addKeywordFromInput('prof-excluded-skills', 'add-kw-ex-skills-input');}">
                                    <button class="btn btn-outline-secondary" type="button" onclick="addKeywordFromInput('prof-excluded-skills', 'add-kw-ex-skills-input')"><i class="bi bi-plus-lg"></i> Exclude</button>
                                </div>
                                <small class="text-muted d-block mt-1" id="preview-excluded-skills">Config.yaml current: (loading...)</small>
                            </div>
                        </div>

                        <div class="pt-2 d-flex flex-wrap gap-2 align-items-center">
                            <button type="submit" class="btn btn-primary"><i class="bi bi-save-fill me-1"></i> Save Profile Configuration to config.yaml</button>
                        </div>
                    </form>

                    <hr class="my-4">
                    <div class="card border-0 bg-light" id="profile-optimize-panel">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start flex-wrap gap-2 mb-3">
                                <div>
                                    <h6 class="fw-bold mb-1"><i class="bi bi-graph-up-arrow text-primary"></i> AI Profile Optimize</h6>
                                    <p class="small text-muted mb-0">Readiness score, recruiter keyword gaps, skills audit, and draft headline / About summary. Nothing is saved until you copy or apply intentionally.</p>
                                </div>
                                <button type="button" class="btn btn-sm btn-outline-primary" onclick="runProfileOptimize()"><i class="bi bi-stars"></i> Analyze Profile</button>
                            </div>
                            <div class="mb-3">
                                <label class="form-label small fw-semibold" for="prof-opt-jd">Optional target job description or industry role</label>
                                <textarea class="form-control form-control-sm" id="prof-opt-jd" rows="3" placeholder="Paste a job description or role category (e.g. Staff Backend Engineer) to score against..."></textarea>
                            </div>
                            <div id="profile-optimize-results" class="small text-muted">Run Analyze Profile to see readiness, gaps, skills audit, and draft headline/summary.</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- CHEAT SHEET & COMMAND EXECUTOR PANE -->
        <div class="tab-pane fade admin-only" id="cheatsheet-pane">
            <div class="page-title-bar">
                <h2><i class="bi bi-terminal text-success"></i> Full CLI Runner</h2>
                <span class="badge bg-warning-subtle text-dark">Admin · Step 4</span>
            </div>
            <div class="row">
                <div class="col-md-7">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="fw-bold mb-0"><i class="bi bi-journal-code"></i> CLI Command Runner</h5>
                        <input type="text" id="cmd-search-input" class="form-control form-control-sm w-50" placeholder="🔍 Search commands..." onkeyup="filterCommands()">
                    </div>
                    <div id="commands-accordion"></div>
                </div>

                <div class="col-md-5">
                    <div class="card border-0 shadow-sm sticky-top" style="top: 1rem;">
                        <div class="card-header bg-dark text-white fw-bold d-flex justify-content-between align-items-center">
                            <span><i class="bi bi-terminal-fill text-success"></i> Terminal Output Console</span>
                            <button class="btn btn-sm btn-outline-secondary text-white" onclick="clearTerminal()">Clear</button>
                        </div>
                        <div class="card-body p-2 bg-dark">
                            <div class="terminal-box" id="terminal-output">Ready. Select a CLI command on the left and click "Run Command".</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

    </div>
</div>
</div><!-- /.main-pane-wrap -->
</main>
</div><!-- /.app-layout -->
</div><!-- /#app-shell -->

<!-- EMAIL SYNC MODAL (Gmail + Hotmail/Outlook) -->
<div class="modal fade" id="emailSyncModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header bg-light">
                <h5 class="modal-title fw-bold"><i class="bi bi-envelope-at"></i> Sync Email Alerts</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="text-muted small mb-3">Import job alerts from Gmail (OAuth) or Hotmail/Outlook (IMAP). Platform discovery stays separate under <strong>Job Discovery</strong>.</p>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Email provider</label>
                    <select class="form-select" id="email-sync-provider">
                        <option value="gmail">Gmail</option>
                        <option value="outlook">Hotmail / Outlook</option>
                    </select>
                    <div class="form-text" id="email-sync-provider-hint">Uses Gmail OAuth (credentials.json / token.json).</div>
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Max emails to scan</label>
                    <input type="number" class="form-control" id="email-sync-max" value="25" min="1" max="100">
                </div>
                <div class="small text-muted" id="email-sync-status-box">Checking provider configuration...</div>
            </div>
            <div class="modal-footer bg-light">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-primary btn-sm" onclick="runEmailSync()"><i class="bi bi-arrow-repeat"></i> Sync Now</button>
            </div>
        </div>
    </div>
</div>

<!-- IMPORT URL MODAL -->
<div class="modal fade" id="importUrlModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header bg-light">
                <h5 class="modal-title fw-bold"><i class="bi bi-link-45deg"></i> Automated Job Import from URL</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="text-muted small mb-3">Paste a job listing URL below. Title, company, location, and description will be extracted automatically.</p>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Job Page URL:</label>
                    <input type="url" class="form-control" id="import-url-input" placeholder="https://www.linkedin.com/jobs/view/123456 or https://www.indeed.com/viewjob?jk=abc">
                </div>
            </div>
            <div class="modal-footer bg-light">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-success btn-sm" onclick="runAutomatedUrlImport()"><i class="bi bi-download"></i> Import Job</button>
            </div>
        </div>
    </div>
</div>

<!-- SEED DEMO CONFIRMATION MODAL -->
<div class="modal fade" id="seedDemoModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header bg-light">
                <h5 class="modal-title fw-bold"><i class="bi bi-database-add text-success"></i> Load Demo Jobs</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="mb-2">Insert <strong>3 sample jobs</strong> for smoke testing and exploration?</p>
                <p class="text-muted small mb-0">No network required. Safe to use on a fresh database. You can purge test data later from Database Explorer.</p>
            </div>
            <div class="modal-footer bg-light">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-success btn-sm fw-bold" onclick="executeSeedDemo()"><i class="bi bi-check-lg"></i> Load 3 Demo Jobs</button>
            </div>
        </div>
    </div>
</div>

<!-- EDIT JOB MODAL -->
<div class="modal fade" id="editJobModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header bg-light">
                <h5 class="modal-title fw-bold"><i class="bi bi-pencil-square"></i> Edit Job Details</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <input type="hidden" id="edit-job-id">
                <div class="mb-3">
                    <label class="form-label fw-semibold">Title</label>
                    <input type="text" class="form-control" id="edit-job-title">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Company</label>
                    <input type="text" class="form-control" id="edit-job-company">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Location</label>
                    <input type="text" class="form-control" id="edit-job-location">
                </div>
                <div class="mb-3">
                    <label class="form-label fw-semibold">Description</label>
                    <textarea class="form-control" id="edit-job-description" rows="6"></textarea>
                    <div class="form-text">Improve incomplete imports for better match scores.</div>
                </div>
            </div>
            <div class="modal-footer bg-light">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-primary btn-sm" onclick="saveJobEdits()"><i class="bi bi-save"></i> Save & Re-Score</button>
            </div>
        </div>
    </div>
</div>

<!-- APPROVE DRAFT CONFIRMATION MODAL -->
<div class="modal fade" id="approveDraftModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header bg-success text-white">
                <h5 class="modal-title fw-bold"><i class="bi bi-check-circle-fill"></i> Confirm Resume Approval</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
                <p class="fw-semibold text-dark">Are you sure you want to approve and finalize this tailored resume?</p>
                <div class="p-3 bg-light rounded border text-muted small mb-3">
                    <i class="bi bi-shield-check text-success"></i> <strong>Explicit Action:</strong> This will save the approved version to the <code>jobapplied</code> folder (<code>~/Desktop/Jobs Applied/&lt;Company&gt;/&lt;Job Title&gt;/</code>). Your master resume remains unchanged.
                </div>
            </div>
            <div class="modal-footer bg-light">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-success btn-sm fw-bold" onclick="executeApproveDraft()"><i class="bi bi-check-lg"></i> Confirm & Finalize</button>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    let metadataCommands = [];
    let currentReviewJobId = null;
    let progressInterval = null;
    let progressHideTimer = null;
    let progressStartedAt = 0;
    const PROGRESS_MIN_VISIBLE_MS = 1500;

    const KANBAN_STATUSES = ["Imported", "Analyzed", "Resume draft ready", "Awaiting review", "Approved", "Applied", "Interviewing", "Offer", "Rejected"];
    const TOP_10 = ["indeed", "linkedin", "glassdoor", "monster", "ziprecruiter", "careerbuilder", "simplyhired", "dice", "wellfound", "google_jobs"];
    const DEFAULT_PLATFORMS = ["dice", "ziprecruiter", "indeed"];
    const SEARCH_LIMIT_PER_PLATFORM = 3;
    const PLATFORM_LABELS = {
        indeed: "Indeed",
        linkedin: "LinkedIn",
        glassdoor: "Glassdoor",
        monster: "Monster",
        ziprecruiter: "ZipRecruiter",
        careerbuilder: "CareerBuilder",
        simplyhired: "SimplyHired",
        dice: "Dice",
        wellfound: "Wellfound",
        google_jobs: "Google Jobs",
    };

    function showProgress(statusText, initialPercent = 15, colorClass = 'bg-primary') {
        const wrapper = document.getElementById('global-progress-wrapper');
        const statusEl = document.getElementById('global-progress-status');
        const percentEl = document.getElementById('global-progress-percent');
        const barEl = document.getElementById('global-progress-bar');
        if (!wrapper || !statusEl || !percentEl || !barEl) {
            console.warn('Progress bar elements missing from page');
            return;
        }

        if (progressInterval) clearInterval(progressInterval);
        if (progressHideTimer) clearTimeout(progressHideTimer);

        progressStartedAt = Date.now();
        wrapper.classList.add('is-visible');
        wrapper.setAttribute('aria-busy', 'true');
        statusEl.innerHTML = `<i class="bi bi-arrow-repeat spin text-primary me-1"></i> ${statusText}`;
        percentEl.innerText = `${Math.round(initialPercent)}%`;
        barEl.style.width = `${initialPercent}%`;
        barEl.setAttribute('aria-valuenow', String(Math.round(initialPercent)));
        barEl.className = `progress-bar progress-bar-striped progress-bar-animated ${colorClass}`;

        let current = initialPercent;
        progressInterval = setInterval(() => {
            if (current < 92) {
                current += (92 - current) * 0.10 + 0.5;
                const shown = Math.round(current);
                percentEl.innerText = `${shown}%`;
                barEl.style.width = `${current}%`;
                barEl.setAttribute('aria-valuenow', String(shown));
            }
        }, 200);
    }

    function updateProgressStep(statusText, percent) {
        const statusEl = document.getElementById('global-progress-status');
        const percentEl = document.getElementById('global-progress-percent');
        const barEl = document.getElementById('global-progress-bar');
        if (!statusEl || !percentEl || !barEl) return;

        if (statusText) statusEl.innerHTML = `<i class="bi bi-arrow-repeat spin text-primary me-1"></i> ${statusText}`;
        if (percent !== undefined) {
            percentEl.innerText = `${Math.round(percent)}%`;
            barEl.style.width = `${percent}%`;
            barEl.setAttribute('aria-valuenow', String(Math.round(percent)));
        }
    }

    function finishProgress(statusText = 'Completed!', isSuccess = true, autoHideMs = 2200) {
        if (progressInterval) clearInterval(progressInterval);
        if (progressHideTimer) clearTimeout(progressHideTimer);

        const wrapper = document.getElementById('global-progress-wrapper');
        const statusEl = document.getElementById('global-progress-status');
        const percentEl = document.getElementById('global-progress-percent');
        const barEl = document.getElementById('global-progress-bar');
        if (!wrapper || !statusEl || !percentEl || !barEl) return;

        const icon = isSuccess ? '<i class="bi bi-check-circle-fill text-success me-1"></i>' : '<i class="bi bi-exclamation-triangle-fill text-danger me-1"></i>';
        wrapper.classList.add('is-visible');
        wrapper.setAttribute('aria-busy', 'false');
        statusEl.innerHTML = `${icon} ${statusText}`;
        percentEl.innerText = isSuccess ? '100%' : 'Failed';
        barEl.style.width = '100%';
        barEl.setAttribute('aria-valuenow', isSuccess ? '100' : '0');
        barEl.className = `progress-bar ${isSuccess ? 'bg-success' : 'bg-danger'}`;

        const elapsed = Date.now() - (progressStartedAt || Date.now());
        const waitMs = Math.max(autoHideMs, PROGRESS_MIN_VISIBLE_MS - elapsed);
        progressHideTimer = setTimeout(() => {
            wrapper.classList.remove('is-visible');
            barEl.style.width = '0%';
            barEl.setAttribute('aria-valuenow', '0');
        }, waitMs);
    }

    const BOOKMARKLET_INSTALLED_KEY = 'job_agent_bookmarklet_installed';
    const CONSOLE_MODE_KEY = 'job_agent_console_mode';
    const MODULE_ENTERED_KEY = 'job_agent_module_entered';
    const USER_TAB_IDS = ['dashboard-tab', 'discovery-tab', 'review-tab', 'auto-apply-tab', 'linkedin-tab', 'kanban-tab', 'cls-tab'];
    const ADMIN_TAB_IDS = ['admin-home-tab', 'db-tab', 'profile-tab', 'cheatsheet-tab'];
    let currentOptimizeBundle = null;
    let currentAutoApplyJobId = null;

    function showModuleGate() {
        document.body.classList.add('module-gate-open');
        localStorage.removeItem(MODULE_ENTERED_KEY);
    }

    function enterModule(mode) {
        const normalized = mode === 'admin' ? 'admin' : 'user';
        localStorage.setItem(MODULE_ENTERED_KEY, '1');
        document.body.classList.remove('module-gate-open');
        applyConsoleMode(normalized, true);
        if (normalized === 'admin') {
            navigateTo('admin-home-tab');
        } else {
            navigateTo('dashboard-tab');
        }
        if (typeof loadAllData === 'function') loadAllData();
    }

    function applyConsoleMode(mode, persistRemote = true) {
        const normalized = mode === 'admin' ? 'admin' : 'user';
        document.body.classList.remove('console-mode-user', 'console-mode-admin');
        document.body.classList.add(normalized === 'admin' ? 'console-mode-admin' : 'console-mode-user');
        localStorage.setItem(CONSOLE_MODE_KEY, normalized);
        const badge = document.getElementById('console-mode-badge');
        const subtitle = document.getElementById('header-module-subtitle');
        const sideTitle = document.getElementById('sidebar-module-title');
        const sideHint = document.getElementById('sidebar-module-hint');
        if (badge) {
            badge.textContent = normalized === 'admin' ? 'Admin Mode' : 'User Mode';
            badge.className = normalized === 'admin' ? 'badge bg-warning text-dark' : 'badge bg-light text-dark';
        }
        if (subtitle) {
            subtitle.textContent = normalized === 'admin'
                ? 'Admin module — setup, profile, database, full CLI'
                : 'User module — Web Tasks + CLS Tasks';
        }
        if (sideTitle) sideTitle.textContent = normalized === 'admin' ? 'ADMIN Module' : 'USER Module';
        if (sideHint) {
            sideHint.textContent = normalized === 'admin'
                ? 'Setup & maintenance only'
                : 'Step-by-step daily workflow';
        }
        if (persistRemote) {
            fetch('/api/console-settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ default_mode: normalized })
            }).catch(err => console.warn('Could not persist console mode:', err));
        }
    }

    function toggleConsoleMode(forceAdmin) {
        // Kept for compatibility: always route through module chooser for clear separation.
        showModuleGate();
    }

    function initConsoleMode() {
        showModuleGate();
        const stored = localStorage.getItem(CONSOLE_MODE_KEY);
        if (stored === 'admin' || stored === 'user') {
            applyConsoleMode(stored, false);
            return;
        }
        fetch('/api/console-settings')
            .then(res => res.json())
            .then(settings => {
                applyConsoleMode(settings.default_mode || 'user', false);
            })
            .catch(() => applyConsoleMode('user', false));
    }

    function navigateTo(tabId) {
        const isAdmin = document.body.classList.contains('console-mode-admin');
        const allowed = isAdmin ? ADMIN_TAB_IDS : USER_TAB_IDS;
        if (!allowed.includes(tabId)) {
            tabId = isAdmin ? 'admin-home-tab' : 'dashboard-tab';
        }
        document.querySelectorAll('#app-sidebar .sidebar-nav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.id === tabId);
        });
        const bsId = tabId + '-bs';
        const el = document.getElementById(bsId) || document.getElementById(tabId);
        if (el && typeof bootstrap !== 'undefined') {
            bootstrap.Tab.getInstance(el)?.show() || new bootstrap.Tab(el).show();
        }
        // Fallback: manually toggle panes if bootstrap tab wiring is incomplete
        const paneId = (document.getElementById(tabId)?.getAttribute('data-pane')) || '';
        if (paneId) {
            document.querySelectorAll('#mainTabsContent > .tab-pane').forEach(p => {
                const on = p.id === paneId;
                p.classList.toggle('show', on);
                p.classList.toggle('active', on);
            });
        }
    }

    function switchTab(tabId) {
        navigateTo(tabId);
    }

    function runClsTask(cmd, args) {
        const term = document.getElementById('cls-terminal-output');
        if (term) term.innerText = `[CLS] python -m job_agent ${cmd} ${(args || []).join(' ')}...\n\nRunning...`;
        showProgress(`Running CLS task '${cmd}'...`, 15);
        fetch('/api/run-command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: cmd, args: args || []})
        })
        .then(res => res.json())
        .then(data => {
            if (term) term.innerText = `$ ${data.command}\n\n${data.output}`;
            finishProgress(`CLS task '${cmd}' finished (exit ${data.exit_code})`, data.success);
            loadAllData();
        })
        .catch(err => {
            if (term) term.innerText = `Error: ${err}`;
            finishProgress(`CLS task '${cmd}' failed`, false);
        });
    }

    function clearClsTerminal() {
        const term = document.getElementById('cls-terminal-output');
        if (term) term.innerText = 'Terminal cleared.';
    }

    function updateBookmarkletInstallStatus() {
        const statusEl = document.getElementById('bookmarklet-install-status');
        const resetBtn = document.getElementById('bookmarklet-reset-btn');
        if (!statusEl) return;
        const installed = localStorage.getItem(BOOKMARKLET_INSTALLED_KEY) === 'true';
        if (installed) {
            statusEl.innerHTML = '<span class="badge bg-success"><i class="bi bi-check-circle-fill"></i> Marked installed in this browser</span>';
            if (resetBtn) resetBtn.style.display = '';
        } else {
            statusEl.innerHTML = '<span class="badge bg-secondary">Not confirmed in this browser yet</span>';
            if (resetBtn) resetBtn.style.display = 'none';
        }
    }

    function markBookmarkletInstalled() {
        localStorage.setItem(BOOKMARKLET_INSTALLED_KEY, 'true');
        updateBookmarkletInstallStatus();
    }

    function clearBookmarkletInstalledFlag() {
        localStorage.removeItem(BOOKMARKLET_INSTALLED_KEY);
        updateBookmarkletInstallStatus();
    }

    document.addEventListener("DOMContentLoaded", function() {
        try { initConsoleMode(); } catch (err) { console.error("initConsoleMode failed:", err); }
        try { renderTop10PlatformsGrid(); } catch (err) { console.error("renderTop10PlatformsGrid failed:", err); }
        try { updateBookmarkletInstallStatus(); } catch (err) { console.error("updateBookmarkletInstallStatus failed:", err); }
        loadAllData();
        try { loadCommandsMetadata(); } catch (err) { console.error("loadCommandsMetadata failed:", err); }
        try { fetchProfile(); } catch (err) { console.error("fetchProfile failed:", err); }
    });

    function goFindJobsNow() {
        navigateTo('discovery-tab');
    }

    function openEmailSyncModal() {
        const modal = new bootstrap.Modal(document.getElementById('emailSyncModal'));
        const providerSel = document.getElementById('email-sync-provider');
        if (providerSel && !providerSel._bound) {
            providerSel.addEventListener('change', refreshEmailSyncHints);
            providerSel._bound = true;
        }
        refreshEmailSyncHints();
        fetch('/api/email/providers')
            .then(res => res.json())
            .then(data => {
                const box = document.getElementById('email-sync-status-box');
                if (!box) return;
                const g = data.gmail || {};
                const o = data.outlook || {};
                box.innerHTML = `
                    <div><strong>Gmail:</strong> ${g.configured ? '<span class="text-success">ready</span>' : '<span class="text-warning">not configured</span>'} — ${escapeHtml(g.message || '')}</div>
                    <div class="mt-1"><strong>Hotmail/Outlook:</strong> ${o.configured ? '<span class="text-success">ready</span>' : '<span class="text-warning">not configured</span>'} — ${escapeHtml(o.message || '')}</div>
                `;
            })
            .catch(() => {});
        modal.show();
    }

    function refreshEmailSyncHints() {
        const provider = document.getElementById('email-sync-provider')?.value || 'gmail';
        const hint = document.getElementById('email-sync-provider-hint');
        if (!hint) return;
        hint.textContent = provider === 'outlook'
            ? 'Uses IMAP (IMAP_USERNAME / IMAP_PASSWORD app password in .env). Host defaults to outlook.office365.com.'
            : 'Uses Gmail OAuth (credentials.json / token.json).';
    }

    function runEmailSync() {
        const provider = document.getElementById('email-sync-provider')?.value || 'gmail';
        const maxResults = parseInt(document.getElementById('email-sync-max')?.value || '25', 10);
        showProgress(`Syncing ${provider === 'outlook' ? 'Hotmail/Outlook' : 'Gmail'} job alerts...`, 18);
        fetch('/api/email/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ provider, max_results: maxResults, dry_run: false })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Email sync failed');
            return data;
        })
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('emailSyncModal'))?.hide();
            finishProgress(`Imported ${data.new_jobs || 0} new jobs from ${data.provider || provider}`, true);
            alert(`✅ Email sync complete\\nProvider: ${data.provider}\\nFetched: ${data.emails_fetched}\\nNew jobs: ${data.new_jobs}\\nDuplicates skipped: ${data.duplicates_skipped}`);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Email sync failed', false);
            alert('❌ ' + err.message);
        });
    }

    function formatPlatformLabel(platformKey) {
        return PLATFORM_LABELS[platformKey] || platformKey.replace('_', ' ');
    }

    function updatePlatformSelectionUI() {
        document.querySelectorAll('.platform-checkbox').forEach(cb => {
            const card = cb.closest('.platform-card');
            if (card) card.classList.toggle('is-selected', cb.checked);
        });
        const countEl = document.getElementById('selected-platform-count');
        const selected = getSelectedPlatforms();
        if (countEl) countEl.innerText = `${selected.length} site${selected.length === 1 ? '' : 's'}`;
    }

    function getSelectedPlatforms() {
        return Array.from(document.querySelectorAll('.platform-checkbox:checked')).map(cb => cb.value);
    }

    function selectRecommendedPlatforms() {
        document.querySelectorAll('.platform-checkbox').forEach(cb => {
            cb.checked = DEFAULT_PLATFORMS.includes(cb.value);
        });
        updatePlatformSelectionUI();
    }

    function selectAllPlatforms(checked) {
        document.querySelectorAll('.platform-checkbox').forEach(cb => { cb.checked = checked; });
        updatePlatformSelectionUI();
    }

    function renderTop10PlatformsGrid() {
        const grid = document.getElementById('top-10-platforms-grid');
        if (!grid) return;
        grid.innerHTML = '';
        TOP_10.forEach(p => {
            const checked = DEFAULT_PLATFORMS.includes(p) ? 'checked' : '';
            const label = formatPlatformLabel(p);
            const tierBadge = DEFAULT_PLATFORMS.includes(p)
                ? '<span class="badge bg-success fs-9 mt-1">Recommended</span>'
                : '<span class="badge bg-secondary fs-9 mt-1">Experimental</span>';
            grid.innerHTML += `
                <div class="col">
                    <label class="platform-card shadow-sm d-block mb-0 ${DEFAULT_PLATFORMS.includes(p) ? 'is-selected' : ''}" for="platform-cb-${p}">
                        <input type="checkbox" class="form-check-input platform-checkbox" id="platform-cb-${p}" value="${p}" ${checked} onchange="updatePlatformSelectionUI()">
                        <div class="fw-bold text-dark fs-8">${label}</div>
                        ${tierBadge}
                    </label>
                </div>`;
        });
        updatePlatformSelectionUI();
    }

    function loadAllData() {
        showProgress('Refreshing dashboard statistics, job list, and activity feed...', 20);
        return Promise.all([fetchStats(), fetchJobs(), fetchActivityFeed()])
            .then(() => finishProgress('Dashboard refreshed successfully', true, 1200))
            .catch((err) => {
                console.error("Error refreshing dashboard data:", err);
                finishProgress('Refresh complete', true, 1200);
            });
    }

    function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        return fetch(url, { ...options, signal: controller.signal })
            .finally(() => clearTimeout(timer));
    }

    function setStat(valueId, cardId, value) {
        const n = Number(value) || 0;
        const el = document.getElementById(valueId);
        if (el) el.innerText = n;
        const card = document.getElementById(cardId);
        if (card) card.classList.toggle('is-zero', n === 0);
    }

    function scoreBadge(score) {
        if (score == null || score === '' || Number.isNaN(Number(score))) {
            return '<span class="badge badge-score score-none">—</span>';
        }
        const n = Math.round(Number(score));
        const tier = n >= 80 ? 'score-high' : n >= 65 ? 'score-mid' : 'score-low';
        return `<span class="badge badge-score ${tier}">${n}</span>`;
    }

    function statusBadge(status) {
        const s = (status || '').toLowerCase();
        let cls = 'status-default';
        if (s.includes('review') || s.includes('imported')) cls = 'status-review';
        else if (s.includes('draft')) cls = 'status-draft';
        else if (s.includes('applied') || s.includes('approved')) cls = 'status-applied';
        return `<span class="badge badge-status ${cls}">${escapeHtml(status || '—')}</span>`;
    }

    function emptyStateRow(colspan, { icon, title, copy, ctaHtml = '' }) {
        return `<tr><td colspan="${colspan}" class="p-0">
            <div class="empty-state">
                <div class="empty-icon"><i class="bi ${icon}"></i></div>
                <div class="empty-title">${title}</div>
                <div class="empty-copy">${copy}</div>
                ${ctaHtml}
            </div>
        </td></tr>`;
    }

    function activityCategory(title = '', description = '') {
        const t = `${title} ${description}`.toLowerCase();
        if (t.includes('email') || t.includes('sync') || t.includes('imap') || t.includes('gmail') || t.includes('outlook') || t.includes('hotmail')) return 'sync';
        if (t.includes('draft') || t.includes('resume') || t.includes('optimize')) return 'draft';
        if (t.includes('apply') || t.includes('application')) return 'apply';
        if (t.includes('discover') || t.includes('import') || t.includes('job') || t.includes('search') || t.includes('seed')) return 'discover';
        return 'default';
    }

    function relativeTime(iso) {
        if (!iso) return '';
        const then = new Date(iso);
        if (Number.isNaN(then.getTime())) return String(iso);
        const sec = Math.round((Date.now() - then.getTime()) / 1000);
        if (sec < 60) return `${Math.max(sec, 0)}s ago`;
        if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
        if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
        if (sec < 86400 * 7) return `${Math.floor(sec / 86400)}d ago`;
        return then.toLocaleDateString();
    }

    function fetchStats() {
        return fetchWithTimeout('/api/stats')
            .then(res => {
                if (!res.ok) throw new Error("HTTP error " + res.status);
                return res.json();
            })
            .then(data => {
                data = data || {};
                const counts = data.status_counts || {};
                setStat('stat-total-jobs', 'stat-card-jobs', data.total_jobs || 0);
                setStat('stat-review-count', 'stat-card-review', counts['Awaiting review'] || counts['Imported'] || 0);
                setStat('stat-drafts-count', 'stat-card-drafts', counts['Resume draft ready'] || counts['Draft ready'] || 0);
                setStat('stat-applied-count', 'stat-card-apps', counts['Applied'] || counts['Approved'] || 0);

                // High score table
                const hsBody = document.querySelector('#high-score-table tbody');
                if (hsBody) {
                    hsBody.innerHTML = '';
                    const highScores = data.high_score_jobs || [];
                    if (highScores.length === 0) {
                        const noJobs = (data.total_jobs || 0) === 0;
                        hsBody.innerHTML = emptyStateRow(6, {
                            icon: 'bi-stars',
                            title: 'No high-match opportunities yet',
                            copy: noJobs
                                ? 'Discover jobs, sync email alerts, or import a URL to get started.'
                                : 'Nothing scored ≥ 65 yet. Re-score jobs or check Recently Discovered below.',
                            ctaHtml: noJobs
                                ? `<button class="btn btn-sm btn-primary mt-2" onclick="goFindJobsNow()"><i class="bi bi-search"></i> Job Discovery</button>`
                                : `<button class="btn btn-sm btn-outline-primary mt-2" onclick="runAnalyzeJobs()"><i class="bi bi-cpu"></i> Re-Score Jobs</button>`
                        });
                    } else {
                        highScores.slice(0, 8).forEach(j => {
                            const title = escapeHtml(j.title || 'Untitled Job');
                            const company = escapeHtml(j.company || 'Unknown Company');
                            const platform = escapeHtml(j.source_platform || 'N/A');
                            hsBody.innerHTML += `
                                <tr>
                                    <td><strong>#${j.id}</strong></td>
                                    <td class="text-center">${scoreBadge(j.match_score)}</td>
                                    <td><strong class="text-primary">${title}</strong></td>
                                    <td>${company}</td>
                                    <td><small class="text-muted">${platform}</small></td>
                                    <td>
                                        <button class="btn btn-xs btn-outline-primary py-0 px-2" onclick="createDraftForJob('${j.id}')">Tailor Draft</button>
                                    </td>
                                </tr>`;
                        });
                    }
                }

                renderRecentJobsTable(data.recent_jobs || []);
                renderSystemHealth(data.health || {});
            })
            .catch(err => {
                console.error("Error in fetchStats:", err);
                const hsBody = document.querySelector('#high-score-table tbody');
                if (hsBody) {
                    const hint = err && err.name === 'AbortError'
                        ? 'Dashboard stats timed out. If a job search is running, wait for it to finish or click Refresh.'
                        : 'Failed to load high score jobs. Click Refresh or check the server terminal for errors.';
                    hsBody.innerHTML = emptyStateRow(6, {
                        icon: 'bi-exclamation-triangle',
                        title: 'Could not load high-match jobs',
                        copy: hint,
                        ctaHtml: `<button class="btn btn-sm btn-outline-primary mt-2" onclick="loadAllData()"><i class="bi bi-arrow-clockwise"></i> Refresh</button>`
                    });
                }
            });
    }

    function renderSystemHealth(health) {
        const dbPath = document.getElementById('health-db-path');
        if (dbPath) {
            dbPath.innerText = health.database_path || '-';
            dbPath.title = health.database_path || '';
        }
        const gmailEl = document.getElementById('health-gmail-status');
        if (gmailEl && health.gmail) {
            const g = health.gmail;
            const badge = g.status === 'token_present' ? 'success' : (g.status === 'needs_auth' ? 'warning' : 'secondary');
            gmailEl.innerHTML = `<span class="badge bg-${badge}">${escapeHtml(g.status.replace('_', ' '))}</span> <small class="text-muted">${escapeHtml(g.message || '')}</small>`;
        }
        const resumeEl = document.getElementById('health-resume-status');
        if (resumeEl && health.master_resume) {
            const r = health.master_resume;
            const badge = r.status === 'ready' ? 'success' : (r.status === 'missing_file' ? 'danger' : 'secondary');
            resumeEl.innerHTML = `<span class="badge bg-${badge}">${escapeHtml(r.status.replace('_', ' '))}</span> <small class="text-muted">${escapeHtml(r.message || '')}</small>`;
        }
        const checklist = document.getElementById('onboarding-checklist');
        if (checklist && health.onboarding_steps) {
            checklist.innerHTML = health.onboarding_steps.map(step => `
                <li class="list-group-item d-flex align-items-center gap-2 py-2">
                    <i class="bi ${step.done ? 'bi-check-circle-fill text-success' : 'bi-circle text-muted'}"></i>
                    <span>${escapeHtml(step.label)}</span>
                </li>`).join('');
        }
        const userSummary = document.getElementById('user-setup-summary');
        if (userSummary && health.onboarding_steps) {
            const done = health.onboarding_steps.filter(s => s.done).length;
            const total = health.onboarding_steps.length;
            if (health.onboarding_complete) {
                userSummary.innerHTML = `Setup complete (${done}/${total}). Use Job Discovery and Resume Review for your daily workflow.`;
            } else {
                userSummary.innerHTML = `Setup in progress (${done}/${total} complete). An administrator should finish profile, resume, and Gmail in <strong>Admin Setup</strong>.`;
            }
        }
    }

    function renderRecentJobsTable(jobs) {
        const fill = (selector, withActions) => {
            const tbody = document.querySelector(selector);
            if (!tbody) return;
            tbody.innerHTML = '';
            if (!jobs || jobs.length === 0) {
                tbody.innerHTML = emptyStateRow(withActions ? 6 : 5, {
                    icon: 'bi-briefcase',
                    title: 'No jobs yet',
                    copy: 'Load demo jobs, run a platform search, or import a job URL.',
                    ctaHtml: `<button class="btn btn-sm btn-primary mt-2" onclick="goFindJobsNow()"><i class="bi bi-search"></i> Job Discovery</button>`
                });
                return;
            }
            jobs.forEach(j => {
                const actions = withActions
                    ? `<td><button class="btn btn-xs btn-outline-secondary py-0 px-2" onclick="openEditJobModal(${j.id})">Edit</button></td>`
                    : '';
                tbody.innerHTML += `
                    <tr>
                        <td><strong>#${j.id}</strong></td>
                        <td class="text-center">${scoreBadge(j.match_score)}</td>
                        <td><strong class="text-primary">${escapeHtml(j.title || '')}</strong></td>
                        <td>${escapeHtml(j.company || '')}</td>
                        <td><small class="text-muted">${escapeHtml(j.source_platform || '')}</small></td>
                        ${actions}
                    </tr>`;
            });
        };
        fill('#recent-jobs-table tbody', true);
        fill('#admin-recent-jobs-table tbody', false);
    }

    function renderPlatformSearchResults(reports) {
        const card = document.getElementById('platform-search-results-card');
        const tbody = document.querySelector('#platform-search-results-table tbody');
        if (!card || !tbody) return;
        if (!reports || reports.length === 0) {
            card.style.display = 'none';
            return;
        }
        card.style.display = '';
        tbody.innerHTML = reports.map(r => {
            const statusBadge = r.status === 'success' ? 'success' : (r.status === 'empty' ? 'warning' : 'danger');
            const tierBadge = r.tier === 'recommended' ? 'primary' : 'secondary';
            return `<tr>
                <td><strong>${escapeHtml(formatPlatformLabel(r.platform))}</strong></td>
                <td><span class="badge bg-${tierBadge}">${escapeHtml(r.tier)}</span></td>
                <td><span class="badge bg-${statusBadge}">${escapeHtml(r.status)}</span></td>
                <td>${r.imported != null ? r.imported : 0}</td>
                <td class="small text-muted">${escapeHtml(r.message || '')}</td>
            </tr>`;
        }).join('');
    }

    function runAnalyzeJobs() {
        showProgress('Re-scoring all jobs against your profile...', 25);
        return fetchWithTimeout('/api/jobs/analyze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' }, 120000)
            .then(res => {
                if (!res.ok) throw new Error('HTTP error ' + res.status);
                return res.json();
            })
            .then(data => {
                finishProgress(`Re-scored ${data.jobs_updated || 0} job(s)`, true);
                loadAllData();
            })
            .catch(err => {
                finishProgress('Analyze failed', false);
                alert('Analyze failed: ' + err);
            });
    }

    function openSeedDemoModal() {
        new bootstrap.Modal(document.getElementById('seedDemoModal')).show();
    }

    function executeSeedDemo() {
        bootstrap.Modal.getInstance(document.getElementById('seedDemoModal'))?.hide();
        showProgress('Seeding demo jobs...', 20);
        fetch('/api/jobs/seed-demo', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' })
            .then(res => res.json())
            .then(data => {
                finishProgress(`Loaded ${data.jobs_seeded || 0} demo jobs (#${(data.job_ids || []).join(', #')})`, true);
                loadAllData();
            })
            .catch(err => {
                finishProgress('Demo seed failed', false);
                alert('Demo seed failed: ' + err);
            });
    }

    function seedDemoJobs() {
        openSeedDemoModal();
    }

    function openEditJobModal(jobId) {
        fetch(`/api/jobs/${jobId}`)
            .then(res => res.json())
            .then(job => {
                document.getElementById('edit-job-id').value = job.id;
                document.getElementById('edit-job-title').value = job.title || '';
                document.getElementById('edit-job-company').value = job.company || '';
                document.getElementById('edit-job-location').value = job.location || '';
                document.getElementById('edit-job-description').value = job.description || '';
                new bootstrap.Modal(document.getElementById('editJobModal')).show();
            })
            .catch(err => alert('Failed to load job: ' + err));
    }

    function saveJobEdits() {
        const jobId = parseInt(document.getElementById('edit-job-id').value);
        const payload = {
            job_id: jobId,
            title: document.getElementById('edit-job-title').value,
            company: document.getElementById('edit-job-company').value,
            location: document.getElementById('edit-job-location').value,
            description: document.getElementById('edit-job-description').value,
        };
        showProgress(`Saving job #${jobId} and re-scoring...`, 30);
        fetch('/api/jobs/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('editJobModal'))?.hide();
            finishProgress('Job updated and re-scored', true);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Save failed', false);
            alert('Save failed: ' + err);
        });
    }

    function fetchJobs() {
        return fetchWithTimeout('/api/jobs')
            .then(res => {
                if (!res.ok) throw new Error("HTTP error " + res.status);
                return res.json();
            })
            .then(jobs => {
                renderAllJobsTable(jobs);
                renderKanbanBoard(jobs);
                populateReviewJobSelect(jobs);
                populateAutoApplyJobSelect(jobs);
            })
            .catch(err => {
                console.error("Error in fetchJobs:", err);
                const tbody = document.querySelector('#all-jobs-table tbody');
                if (tbody) {
                    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Failed to load job listings.</td></tr>';
                }
            });
    }

    function renderAllJobsTable(jobs) {
        const tbody = document.querySelector('#all-jobs-table tbody');
        tbody.innerHTML = '';
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = emptyStateRow(7, {
                icon: 'bi-inbox',
                title: 'No jobs tracked',
                copy: 'Click Find Jobs Now or Import URL to start building your pipeline.',
                ctaHtml: `<button class="btn btn-sm btn-primary mt-2" onclick="goFindJobsNow()"><i class="bi bi-search"></i> Find Jobs Now</button>`
            });
            return;
        }
        jobs.forEach(j => {
            tbody.innerHTML += `
                <tr>
                    <td><strong>#${j.id}</strong></td>
                    <td>${statusBadge(j.status)}</td>
                    <td class="text-center">${scoreBadge(j.match_score)}</td>
                    <td><strong class="text-primary">${escapeHtml(j.title)}</strong></td>
                    <td>${escapeHtml(j.company)}</td>
                    <td><small class="text-muted">${j.source_platform}</small></td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-secondary" onclick="openEditJobModal(${j.id})"><i class="bi bi-pencil"></i></button>
                            <button class="btn btn-outline-primary" onclick="createDraftForJob('${j.id}')"><i class="bi bi-file-earmark-diff"></i> Draft Resume</button>
                            <button class="btn btn-outline-success" onclick="selectForReview('${j.id}')"><i class="bi bi-check-lg"></i> Review</button>
                        </div>
                    </td>
                </tr>`;
        });
    }

    function renderKanbanBoard(jobs) {
        const container = document.getElementById('kanban-board-container');
        container.innerHTML = '';

        KANBAN_STATUSES.forEach(status => {
            const statusJobs = (jobs || []).filter(j => j.status === status);
            let cardsHtml = '';

            statusJobs.forEach(j => {
                const scoreHtml = j.match_score != null ? `<span class="ms-auto">${scoreBadge(j.match_score)}</span>` : '';
                cardsHtml += `
                    <div class="kanban-card" onclick="selectForReview('${j.id}')">
                        <div class="d-flex align-items-center mb-1">
                            <strong class="text-dark fs-7">#${j.id}</strong>
                            ${scoreHtml}
                        </div>
                        <div class="fw-bold text-primary text-truncate mb-1" style="font-size:0.85rem;">${escapeHtml(j.title)}</div>
                        <div class="text-muted small text-truncate mb-2">${escapeHtml(j.company)}</div>
                        <div class="d-flex justify-content-between align-items-center border-top pt-2 mt-2">
                            <small class="text-muted fs-8">${j.source_platform}</small>
                            <select class="form-select form-select-sm py-0 px-1 fs-8" style="width: auto;" onclick="event.stopPropagation()" onchange="moveJobStatus('${j.id}', this.value)">
                                ${KANBAN_STATUSES.map(s => `<option value="${s}" ${s === status ? 'selected' : ''}>${s}</option>`).join('')}
                            </select>
                        </div>
                    </div>`;
            });

            container.innerHTML += `
                <div class="col">
                    <div class="kanban-col">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h6 class="fw-bold mb-0 text-dark fs-8">${status}</h6>
                            <span class="badge bg-white text-dark border">${statusJobs.length}</span>
                        </div>
                        ${cardsHtml || '<div class="text-muted fs-8 text-center py-4">No jobs</div>'}
                    </div>
                </div>`;
        });
    }

    function fetchActivityFeed() {
        return fetch('/api/activities')
            .then(res => {
                if (!res.ok) throw new Error("HTTP error " + res.status);
                return res.json();
            })
            .then(acts => {
                const list = document.getElementById('activity-feed-list');
                if (!list) return;
                list.className = 'activity-timeline';
                if (!acts || !Array.isArray(acts) || acts.length === 0) {
                    list.innerHTML = `<li class="empty-state py-4">
                        <div class="empty-icon"><i class="bi bi-activity"></i></div>
                        <div class="empty-title">No activity yet</div>
                        <div class="empty-copy">Discover jobs or sync email alerts to see events here.</div>
                    </li>`;
                    return;
                }
                list.innerHTML = acts.map(a => {
                    const cat = activityCategory(a.title, a.description);
                    return `<li class="activity-item cat-${cat}">
                        <div class="d-flex justify-content-between align-items-start gap-2 mb-1">
                            <span class="activity-tag">${cat}</span>
                            <small class="text-muted" title="${escapeHtml(a.created_at || '')}">${relativeTime(a.created_at)}</small>
                        </div>
                        <div class="fw-semibold text-dark" style="font-size:0.85rem">${escapeHtml(a.title || '')}</div>
                        <div class="text-muted" style="font-size:0.78rem">${escapeHtml(a.description || '')}</div>
                    </li>`;
                }).join('');
            })
            .catch(err => {
                console.error("Error in fetchActivityFeed:", err);
                const list = document.getElementById('activity-feed-list');
                if (list) {
                    list.className = 'activity-timeline';
                    list.innerHTML = `<li class="empty-state py-4">
                        <div class="empty-icon"><i class="bi bi-exclamation-triangle"></i></div>
                        <div class="empty-title">Failed to load activity</div>
                        <div class="empty-copy">Click Refresh to try again.</div>
                    </li>`;
                }
            });
    }

    function populateReviewJobSelect(jobs) {
        const sel = document.getElementById('review-job-select');
        if (!sel) return;
        sel.innerHTML = '<option value="">Select a job from list...</option>';
        (jobs || []).forEach(j => {
            sel.innerHTML += `<option value="${j.id}">#${j.id}: ${escapeHtml(j.title)} at ${escapeHtml(j.company)} (${j.status})</option>`;
        });
    }

    function populateAutoApplyJobSelect(jobs) {
        const sel = document.getElementById('auto-apply-job-select');
        if (!sel) return;
        sel.innerHTML = '<option value="">Select a job...</option>';
        (jobs || []).forEach(j => {
            sel.innerHTML += `<option value="${j.id}">#${j.id}: ${escapeHtml(j.title)} at ${escapeHtml(j.company)} (${j.status})</option>`;
        });
    }

    function loadAutoApplyEligibility(jobId) {
        currentAutoApplyJobId = jobId || null;
        const box = document.getElementById('auto-apply-eligibility');
        const btn = document.getElementById('btn-launch-auto-apply');
        const btnMark = document.getElementById('btn-launch-auto-apply-mark');
        if (!jobId) {
            if (box) box.innerHTML = 'Select a job to check Auto Apply readiness.';
            if (btn) btn.disabled = true;
            if (btnMark) btnMark.disabled = true;
            return;
        }
        fetch(`/api/auto-apply/eligibility?job_id=${jobId}`)
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Eligibility check failed');
                return data;
            })
            .then(data => {
                const blockers = (data.blockers || []).map(b => `<li class="text-danger">${escapeHtml(b)}</li>`).join('');
                const warnings = (data.warnings || []).map(w => `<li class="text-warning">${escapeHtml(w)}</li>`).join('');
                box.innerHTML = `
                    <div class="mb-2"><strong>${escapeHtml(data.title)}</strong> at ${escapeHtml(data.company)}</div>
                    <div class="mb-1">Approval: <code>${escapeHtml(data.approval_status || '-')}</code> · Status: <code>${escapeHtml(data.status || '-')}</code></div>
                    <div class="mb-1">ATS optimize accepts: <strong>${data.optimize_accepted || 0}</strong> · ATS ready flag: <strong>${data.ats_ready ? 'yes' : 'no'}</strong></div>
                    <div class="mb-1">Resume: <code>${escapeHtml(data.final_resume_path || 'n/a')}</code></div>
                    ${blockers ? `<ul class="mb-1">${blockers}</ul>` : '<div class="text-success mb-1">Ready for assisted Auto Apply.</div>'}
                    ${warnings ? `<ul class="mb-0">${warnings}</ul>` : ''}
                `;
                const ok = !!data.eligible;
                if (btn) btn.disabled = !ok;
                if (btnMark) btnMark.disabled = !ok;
            })
            .catch(err => {
                box.innerHTML = `<span class="text-danger">${escapeHtml(err.message)}</span>`;
                if (btn) btn.disabled = true;
                if (btnMark) btnMark.disabled = true;
            });
    }

    function launchAutoApply(markApplied) {
        if (!currentAutoApplyJobId) return;
        const confirmMsg = markApplied
            ? 'Open employer page + resume folder, then mark this job as Applied? Only confirm if you will submit now.'
            : 'Open employer application page and finalized resume folder for assisted Auto Apply?';
        if (!confirm(confirmMsg)) return;
        showProgress('Launching assisted Auto Apply...', 20);
        fetch('/api/auto-apply/launch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                job_id: parseInt(currentAutoApplyJobId),
                mark_as_applied: !!markApplied,
                confirm: !!markApplied,
                open_browser: true,
                open_resume_folder: true
            })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Auto Apply failed');
            return data;
        })
        .then(data => {
            finishProgress(data.message || 'Auto Apply launched', true);
            const list = document.getElementById('auto-apply-checklist');
            if (list) {
                list.innerHTML = (data.checklist || []).map(i => `<li class="list-group-item small">${escapeHtml(i)}</li>`).join('')
                    + `<li class="list-group-item small text-muted">Resume: <code>${escapeHtml(data.resume_path || '')}</code></li>`
                    + `<li class="list-group-item small text-muted">URL: <code>${escapeHtml(data.job_url || '')}</code></li>`;
            }
            loadAutoApplyEligibility(currentAutoApplyJobId);
            loadAllData();
            alert('✅ ' + (data.message || 'Auto Apply launched'));
        })
        .catch(err => {
            finishProgress('Auto Apply failed', false);
            alert('❌ ' + err.message);
        });
    }

    function runLinkedInOptimize() {
        const role = (document.getElementById('li-target-role')?.value || '').trim();
        const jd = (document.getElementById('li-job-description')?.value || '').trim();
        showProgress('Optimizing LinkedIn headline, About, and skills...', 18);
        fetch('/api/linkedin/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ target_role: role, job_description: jd })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'LinkedIn optimize failed');
            return data;
        })
        .then(data => {
            finishProgress('LinkedIn optimization ready', true);
            const el = document.getElementById('linkedin-optimize-results');
            const audit = (data.skills_audit || []).map(a =>
                `<li><strong>${escapeHtml(a.skill)}</strong> — <em>${escapeHtml(a.action)}</em>: ${escapeHtml(a.reason)}</li>`
            ).join('');
            const tips = (data.linkedin_tips || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
            el.innerHTML = `
                <div class="row g-3 mb-3">
                    <div class="col-md-3"><div class="stat-card py-2"><div class="text-muted small">Readiness</div><div class="stat-value text-primary fs-3">${data.readiness_score}%</div></div></div>
                    <div class="col-md-9">
                        <div class="mb-2"><strong>Matched:</strong> ${escapeHtml((data.matched_keywords||[]).join(', ') || '—')}</div>
                        <div><strong>Gaps:</strong> ${escapeHtml((data.keyword_gaps||[]).join(', ') || '—')}</div>
                    </div>
                </div>
                <div class="mb-3">
                    <div class="fw-semibold mb-1">LinkedIn headline (≤220)</div>
                    <div class="border rounded p-2 bg-white mb-2" id="li-headline">${escapeHtml(data.headline || '')}</div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="navigator.clipboard.writeText(document.getElementById('li-headline').innerText)">Copy headline</button>
                </div>
                <div class="mb-3">
                    <div class="fw-semibold mb-1">LinkedIn About</div>
                    <div class="border rounded p-2 bg-white mb-2" id="li-about" style="white-space:pre-wrap">${escapeHtml(data.about_summary || '')}</div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="navigator.clipboard.writeText(document.getElementById('li-about').innerText)">Copy About</button>
                </div>
                <div class="mb-2"><strong>Skills audit</strong></div>
                <ul class="mb-3">${audit || '<li>No audit items</li>'}</ul>
                <div class="mb-2"><strong>Suggested Top Skills order</strong></div>
                <div class="border rounded p-2 bg-white mb-3">${escapeHtml((data.suggested_skills_order||[]).join(', '))}</div>
                <div class="mb-2"><strong>How to apply on LinkedIn</strong></div>
                <ul>${tips}</ul>
            `;
        })
        .catch(err => {
            finishProgress('LinkedIn optimize failed', false);
            alert('❌ ' + err.message);
        });
    }

    function selectForReview(jobId) {
        document.getElementById('review-job-select').value = jobId;
        loadJobForReview(jobId);
        switchTab('review-tab');
    }

    function loadJobForReview(jobId) {
        if (!jobId) {
            document.getElementById('resume-review-details').style.display = 'none';
            return;
        }
        currentReviewJobId = jobId;
        document.getElementById('resume-review-details').style.display = 'block';

        fetch(`/api/draft/get?job_id=${jobId}`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('rev-master-path').innerText = data.master_resume_path || 'Set in config.yaml';
                document.getElementById('rev-draft-path').innerText = data.draft_resume_path || 'No draft generated yet';
                document.getElementById('rev-final-path').innerText = data.final_resume_path || 'Not finalized yet';
                document.getElementById('rev-approval-badge').innerText = data.approval_status || 'Awaiting Review';
                document.getElementById('rev-diff-summary').innerText = data.diff_summary || 'No diff summary available. Click "Generate New Draft" above.';
                if (data.optimize) {
                    renderOptimizeBundle(data.optimize);
                } else {
                    resetOptimizePanel();
                }
            })
            .catch(err => alert('❌ Failed loading draft review: ' + err));
    }

    function resetOptimizePanel() {
        currentOptimizeBundle = null;
        const row = document.getElementById('optimize-score-row');
        if (row) row.style.display = 'none';
        const list = document.getElementById('optimize-suggestions-list');
        if (list) list.innerHTML = 'Generate a draft first, then run AI Optimize to see editable suggestions.';
        const applyBtn = document.getElementById('btn-apply-optimize');
        if (applyBtn) applyBtn.disabled = true;
    }

    function renderOptimizeBundle(bundle) {
        currentOptimizeBundle = bundle || null;
        const row = document.getElementById('optimize-score-row');
        const list = document.getElementById('optimize-suggestions-list');
        const applyBtn = document.getElementById('btn-apply-optimize');
        if (!bundle) {
            resetOptimizePanel();
            return;
        }
        if (row) row.style.display = '';
        document.getElementById('opt-readiness').innerText = `${bundle.readiness_score ?? '-'}%`;
        document.getElementById('opt-matched').innerText = (bundle.matched_keywords || []).join(', ') || '—';
        document.getElementById('opt-gaps').innerText = (bundle.keyword_gaps || []).join(', ') || '—';
        const suggestions = bundle.suggestions || [];
        if (!suggestions.length) {
            list.innerHTML = '<span class="text-muted">No suggestions returned.</span>';
            applyBtn.disabled = true;
            return;
        }
        list.innerHTML = suggestions.map(s => {
            const statusClass = s.status === 'accepted' ? 'accepted' : (s.status === 'rejected' ? 'rejected' : (s.status === 'edited' ? 'edited' : ''));
            return `
            <div class="suggestion-card ${statusClass}" data-sid="${escapeHtml(s.id)}">
                <div class="d-flex justify-content-between align-items-start gap-2 mb-2">
                    <div>
                        <span class="badge bg-secondary me-1">${escapeHtml(s.kind)}</span>
                        <span class="badge bg-light text-dark border">${escapeHtml(s.status)}</span>
                        ${s.keyword ? `<span class="badge bg-info-subtle text-dark ms-1">${escapeHtml(s.keyword)}</span>` : ''}
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-success" onclick="updateOptimizeSuggestion('${s.id}', 'accept')">Accept</button>
                        <button type="button" class="btn btn-outline-danger" onclick="updateOptimizeSuggestion('${s.id}', 'reject')">Reject</button>
                        <button type="button" class="btn btn-outline-primary" onclick="editOptimizeSuggestion('${s.id}')">Edit</button>
                    </div>
                </div>
                ${s.original_text ? `<div class="small text-muted mb-1"><strong>Original:</strong> ${escapeHtml(s.original_text)}</div>` : ''}
                <div class="small mb-1"><strong>Suggested:</strong> ${escapeHtml(s.suggested_text)}</div>
                <div class="small text-muted">${escapeHtml(s.rationale || '')}</div>
            </div>`;
        }).join('');
        const hasAccepted = suggestions.some(s => s.status === 'accepted' || s.status === 'edited');
        applyBtn.disabled = !hasAccepted;
    }

    function runAiOptimize() {
        if (!currentReviewJobId) return;
        showProgress(`Running AI Optimize for Job #${currentReviewJobId}...`, 18);
        fetch('/api/draft/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ job_id: parseInt(currentReviewJobId) })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || data.message || 'Optimize failed');
            return data;
        })
        .then(data => {
            finishProgress('AI Optimize suggestions ready', true);
            renderOptimizeBundle(data.optimize || data);
        })
        .catch(err => {
            finishProgress('AI Optimize failed', false);
            alert('❌ AI Optimize failed: ' + err.message);
        });
    }

    function updateOptimizeSuggestion(suggestionId, action, editedText) {
        if (!currentReviewJobId) return;
        const payload = {
            job_id: parseInt(currentReviewJobId),
            suggestion_id: suggestionId,
            action: action
        };
        if (editedText !== undefined) payload.edited_text = editedText;
        fetch('/api/draft/suggestion', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Update failed');
            return data;
        })
        .then(data => renderOptimizeBundle(data.optimize || data))
        .catch(err => alert('❌ Could not update suggestion: ' + err.message));
    }

    function editOptimizeSuggestion(suggestionId) {
        const current = (currentOptimizeBundle?.suggestions || []).find(s => s.id === suggestionId);
        const next = prompt('Edit suggested text:', current?.suggested_text || '');
        if (next === null) return;
        updateOptimizeSuggestion(suggestionId, 'edit', next);
    }

    function applyAcceptedOptimize() {
        if (!currentReviewJobId) return;
        if (!confirm('Apply all accepted/edited suggestions into the draft DOCX? Master resume stays unchanged.')) return;
        showProgress('Applying accepted AI Optimize suggestions...', 25);
        fetch('/api/draft/optimize/apply', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ job_id: parseInt(currentReviewJobId) })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Apply failed');
            return data;
        })
        .then(data => {
            finishProgress('Suggestions applied to draft', true);
            alert('✅ Applied to draft:\\n' + (data.draft_resume_path || ''));
            loadJobForReview(currentReviewJobId);
        })
        .catch(err => {
            finishProgress('Apply failed', false);
            alert('❌ ' + err.message);
        });
    }

    function runProfileOptimize() {
        const jd = (document.getElementById('prof-opt-jd')?.value || '').trim();
        showProgress('Analyzing profile readiness & keyword gaps...', 20);
        fetch('/api/profile/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ job_description: jd, industry_role: jd })
        })
        .then(async res => {
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Profile optimize failed');
            return data;
        })
        .then(data => {
            finishProgress('Profile analysis ready', true);
            const el = document.getElementById('profile-optimize-results');
            const audit = (data.skills_audit || []).map(a =>
                `<li><strong>${escapeHtml(a.skill)}</strong> — <em>${escapeHtml(a.action)}</em>: ${escapeHtml(a.reason)}</li>`
            ).join('');
            el.innerHTML = `
                <div class="row g-3 mb-3">
                    <div class="col-md-3"><div class="stat-card py-2"><div class="text-muted small">Readiness</div><div class="stat-value text-primary fs-3">${data.readiness_score}%</div></div></div>
                    <div class="col-md-9">
                        <div class="mb-2"><strong>Matched:</strong> ${escapeHtml((data.matched_keywords||[]).join(', ') || '—')}</div>
                        <div><strong>Gaps:</strong> ${escapeHtml((data.keyword_gaps||[]).join(', ') || '—')}</div>
                    </div>
                </div>
                <div class="mb-3">
                    <div class="fw-semibold mb-1">Draft headline (≤220 chars)</div>
                    <div class="border rounded p-2 bg-white mb-2" id="prof-opt-headline">${escapeHtml(data.headline || '')}</div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="navigator.clipboard.writeText(document.getElementById('prof-opt-headline').innerText)">Copy headline</button>
                </div>
                <div class="mb-3">
                    <div class="fw-semibold mb-1">Draft About / summary</div>
                    <div class="border rounded p-2 bg-white mb-2" id="prof-opt-about">${escapeHtml(data.about_summary || '')}</div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="navigator.clipboard.writeText(document.getElementById('prof-opt-about').innerText)">Copy summary</button>
                </div>
                <div class="mb-2"><strong>Skills audit</strong></div>
                <ul class="mb-3">${audit || '<li>No audit items</li>'}</ul>
                <div class="mb-2"><strong>Suggested skills order</strong></div>
                <div class="border rounded p-2 bg-white mb-2">${escapeHtml((data.suggested_skills_order||[]).join(', '))}</div>
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="applySuggestedSkillsOrder()">Apply suggested order to Required Skills field</button>
                <div class="text-muted mt-2">${(data.notes||[]).map(escapeHtml).join(' · ')}</div>
            `;
            window.__lastProfileOptimize = data;
        })
        .catch(err => {
            finishProgress('Profile analysis failed', false);
            alert('❌ ' + err.message);
        });
    }

    function applySuggestedSkillsOrder() {
        const data = window.__lastProfileOptimize;
        if (!data || !data.suggested_skills_order) return;
        const field = document.getElementById('prof-req-skills');
        if (!field) {
            alert('Could not find required skills field');
            return;
        }
        field.value = data.suggested_skills_order.join(', ');
        alert('Updated Required Skills field with suggested order. Click Save to persist to config.yaml.');
    }

    function createDraftForJob(jobId) {
        showProgress(`Generating ATS Tailored Resume Draft for Job #${jobId}...`, 15);
        fetch('/api/draft/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(jobId)})
        })
        .then(res => res.json())
        .then(data => {
            finishProgress('Resume Draft Created Successfully!', true);
            alert('✅ Resume Draft Created! Opening Review screen...');
            selectForReview(jobId);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Failed creating resume draft', false);
            alert('❌ Failed creating resume draft: ' + err);
        });
    }

    function generateDraftForSelectedJob() {
        if (currentReviewJobId) createDraftForJob(currentReviewJobId);
    }

    function promptApproveDraftModal() {
        if (!currentReviewJobId) return;
        const modal = new bootstrap.Modal(document.getElementById('approveDraftModal'));
        modal.show();
    }

    function executeApproveDraft() {
        if (!currentReviewJobId) return;
        showProgress(`Approving & Finalizing Resume for Job #${currentReviewJobId}...`, 20);
        fetch('/api/draft/approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(currentReviewJobId)})
        })
        .then(res => res.json())
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('approveDraftModal'))?.hide();
            finishProgress('Resume Approved & Promoted to Jobs Applied folder!', true);
            alert('✅ Resume Approved & Finalized! Saved to jobapplied folder:\n\n' + data.final_resume_path);
            loadJobForReview(currentReviewJobId);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Failed approving draft', false);
            alert('❌ Failed approving draft: ' + err);
        });
    }

    function rejectDraftForSelectedJob() {
        if (!currentReviewJobId) return;
        if (!confirm('Reject draft and revert job status?')) return;
        showProgress(`Rejecting Draft for Job #${currentReviewJobId}...`, 25);
        fetch('/api/draft/reject', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(currentReviewJobId)})
        })
        .then(res => res.json())
        .then(data => {
            finishProgress('Draft Rejected', true);
            alert('Draft rejected.');
            loadJobForReview(currentReviewJobId);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Failed rejecting draft', false);
            alert('❌ Failed rejecting draft: ' + err);
        });
    }

    function runTop10JobSearch() {
        const selectedPlatforms = getSelectedPlatforms();
        if (selectedPlatforms.length === 0) {
            alert('Please select at least one job platform using the checkboxes above.');
            return;
        }

        const btn = document.getElementById('btn-find-jobs-now');
        const platformSummary = selectedPlatforms.map(formatPlatformLabel).join(', ');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Searching...';
        showProgress(`Searching ${selectedPlatforms.length} selected platform(s) for up to ${SEARCH_LIMIT_PER_PLATFORM} jobs each...`, 10);

        fetchWithTimeout('/api/jobs/find', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({platforms: selectedPlatforms, limit: SEARCH_LIMIT_PER_PLATFORM})
        }, 300000)
        .then(res => {
            if (!res.ok) throw new Error('HTTP error ' + res.status);
            return res.json();
        })
        .then(data => {
            renderPlatformSearchResults(data.platform_reports || []);
            const afterSearch = () => {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-search"></i> Find Jobs Now';
                const count = data.jobs_recorded != null ? data.jobs_recorded : 0;
                const searched = (data.platforms_searched || selectedPlatforms).map(formatPlatformLabel).join(', ');
                finishProgress(`Search complete! Discovered ${count} jobs.`, true);
                if (count === 0) {
                    alert(`No jobs imported from selected platforms.\n\nSee "Last Platform Search Results" for per-site status.\n\nTip: Use Dice, ZipRecruiter, Indeed (recommended), Load Demo Jobs, or Import URL.`);
                } else {
                    alert(`✅ Platform Search Complete!\n\nDiscovered ${count} jobs from:\n${searched}\n\nRunning score analyzer next...`);
                }
                loadAllData();
            };
            if ((data.jobs_recorded || 0) > 0) {
                showProgress('Running score analyzer on discovered jobs...', 70);
                return runAnalyzeJobs().finally(afterSearch);
            }
            afterSearch();
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-search"></i> Find Jobs Now';
            finishProgress('Search encountered an error', false);
            alert('Search encountered an error: ' + err);
            loadAllData();
        });
    }

    function openImportUrlModal() {
        const modal = new bootstrap.Modal(document.getElementById('importUrlModal'));
        modal.show();
    }

    function runAutomatedUrlImport() {
        const url = document.getElementById('import-url-input').value;
        if (!url) return;

        showProgress('Extracting job listing details from URL...', 20);

        fetch('/api/jobs/import-url', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        })
        .then(res => res.json())
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('importUrlModal'))?.hide();
            finishProgress(`Job Imported! ID: #${data.job_id} (${data.company})`, true);
            alert(`✅ Job Imported Successfully!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nMatch Score: ${data.score}/100`);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Failed importing job from URL', false);
            alert('❌ Failed importing job from URL: ' + err);
        });
    }

    function moveJobStatus(jobId, newStatus) {
        showProgress(`Updating Job #${jobId} status to '${newStatus}'...`, 30);
        fetch('/api/jobs/update-status', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(jobId), status: newStatus})
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                finishProgress(`Status updated to '${newStatus}'`, true);
                loadAllData();
            }
        })
        .catch(err => {
            finishProgress('Failed updating status', false);
            alert('❌ Failed updating status: ' + err);
        });
    }

    function loadDbExplorer() {
        const sel = document.getElementById('db-table-selector');
        loadTableData(sel.value || 'jobs');
    }

    function loadTableData(tableName) {
        showProgress(`Loading '${tableName}' table records...`, 25);
        fetch(`/api/db/table-data?table=${tableName}`)
            .then(res => res.json())
            .then(data => {
                const tableEl = document.getElementById('db-browser-table');
                if (!data.rows || data.rows.length === 0) {
                    tableEl.innerHTML = '<thead><tr><th>Table Empty</th></tr></thead><tbody><tr><td class="text-center py-3 text-muted">No records in this table.</td></tr></tbody>';
                    finishProgress(`Table '${tableName}' loaded (0 records)`, true);
                    return;
                }
                const cols = data.columns || [];
                let thead = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '<th>Action</th></tr>';
                let tbody = '';
                data.rows.forEach(row => {
                    let tr = '<tr>';
                    cols.forEach(c => {
                        let val = row[c];
                        if (val === null || val === undefined) val = '<span class="text-muted">-</span>';
                        else val = escapeHtml(String(val)).slice(0, 80);
                        tr += `<td>${val}</td>`;
                    });
                    tr += `<td><button class="btn btn-xs btn-outline-danger py-0 px-1" onclick="deleteDbRow('${tableName}', '${row.id}')">Delete</button></td></tr>`;
                    tbody += tr;
                });
                tableEl.innerHTML = `<thead class="table-light">${thead}</thead><tbody>${tbody}</tbody>`;
                finishProgress(`Loaded ${data.rows.length} rows from '${tableName}'`, true);
            })
            .catch(err => finishProgress('Failed loading table data', false));
    }

    function deleteDbRow(tableName, rowId) {
        if (!confirm(`Delete row #${rowId} from ${tableName}?`)) return;
        showProgress(`Deleting row #${rowId} from '${tableName}'...`, 30);
        fetch('/api/db/delete-row', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({table: tableName, id: parseInt(rowId)})
        })
        .then(res => res.json())
        .then(data => {
            finishProgress(`Row #${rowId} deleted`, true);
            alert(data.message);
            loadTableData(tableName);
            loadAllData();
        })
        .catch(err => {
            finishProgress('Failed deleting row', false);
            alert('❌ Failed deleting row: ' + err);
        });
    }

    function triggerQuickCleanup(action) {
        if (action === 'all' && !confirm('⚠️ Are you sure you want to PURGE ALL database records? This resets your local database completely.')) return;
        showProgress(`Executing cleanup action '${action}'...`, 20);
        fetch('/api/db/cleanup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: action})
        })
        .then(res => res.json())
        .then(data => {
            finishProgress('Database cleanup complete', true);
            alert('✅ Cleanup complete: ' + data.message);
            loadAllData();
            loadDbExplorer();
        })
        .catch(err => {
            finishProgress('Cleanup failed', false);
            alert('❌ Failed running cleanup: ' + err);
        });
    }

    function addKeyword(targetInputId, keyword) {
        if (!keyword || !keyword.trim()) return;
        const input = document.getElementById(targetInputId);
        if (!input) return;
        const cleanKw = keyword.trim();
        const existing = input.value.split(',').map(s => s.trim()).filter(Boolean);
        if (!existing.some(k => k.toLowerCase() === cleanKw.toLowerCase())) {
            existing.push(cleanKw);
            input.value = existing.join(', ');
        }
    }

    function addKeywordFromInput(targetInputId, sourceInputId) {
        const srcInput = document.getElementById(sourceInputId);
        if (!srcInput) return;
        const val = srcInput.value;
        if (val && val.trim()) {
            addKeyword(targetInputId, val);
            srcInput.value = '';
        }
    }

    function setSalaryValue(targetInputId, amount) {
        const input = document.getElementById(targetInputId);
        if (input) {
            input.value = amount;
        }
    }

    function setPreviewText(elementId, val) {
        const el = document.getElementById(elementId);
        if (!el) return;
        let formatted = 'None set';
        if (Array.isArray(val)) {
            formatted = val.length > 0 ? val.join(', ') : 'None set';
        } else if (val !== null && val !== undefined && val !== '') {
            formatted = String(val);
        }
        el.innerHTML = 'Config.yaml current: ' + escapeHtml(formatted);
    }

    function fetchProfile() {
        fetch('/api/profile')
            .then(res => res.json())
            .then(p => {
                if (document.getElementById('prof-titles')) document.getElementById('prof-titles').value = (p.target_titles || []).join(', ');
                if (document.getElementById('prof-exp')) document.getElementById('prof-exp').value = (p.years_experience !== undefined && p.years_experience !== null) ? p.years_experience : 0;
                if (document.getElementById('prof-req-skills')) document.getElementById('prof-req-skills').value = (p.required_skills || []).join(', ');
                if (document.getElementById('prof-pref-skills')) document.getElementById('prof-pref-skills').value = (p.preferred_skills || []).join(', ');
                if (document.getElementById('prof-locations')) document.getElementById('prof-locations').value = (p.locations || []).join(', ');
                if (document.getElementById('prof-salary')) document.getElementById('prof-salary').value = (p.salary_min !== null && p.salary_min !== undefined) ? p.salary_min : '';
                if (document.getElementById('prof-salary-max')) document.getElementById('prof-salary-max').value = (p.salary_max !== null && p.salary_max !== undefined) ? p.salary_max : '';
                if (document.getElementById('prof-industries')) document.getElementById('prof-industries').value = (p.industries || []).join(', ');
                if (document.getElementById('prof-work-modes')) document.getElementById('prof-work-modes').value = (p.work_modes || []).join(', ');
                if (document.getElementById('prof-excluded-companies')) document.getElementById('prof-excluded-companies').value = (p.excluded_companies || []).join(', ');
                if (document.getElementById('prof-excluded-titles')) document.getElementById('prof-excluded-titles').value = (p.excluded_titles || []).join(', ');
                if (document.getElementById('prof-excluded-skills')) document.getElementById('prof-excluded-skills').value = (p.excluded_skills || []).join(', ');

                setPreviewText('preview-titles', p.target_titles);
                setPreviewText('preview-exp', p.years_experience !== undefined && p.years_experience !== null ? p.years_experience + ' years' : null);
                setPreviewText('preview-req-skills', p.required_skills);
                setPreviewText('preview-pref-skills', p.preferred_skills);
                setPreviewText('preview-locations', p.locations);
                setPreviewText('preview-salary', p.salary_min ? '$' + Number(p.salary_min).toLocaleString() : null);
                setPreviewText('preview-salary-max', p.salary_max ? '$' + Number(p.salary_max).toLocaleString() : null);
                setPreviewText('preview-industries', p.industries);
                setPreviewText('preview-work-modes', p.work_modes);
                setPreviewText('preview-excluded-companies', p.excluded_companies);
                setPreviewText('preview-excluded-titles', p.excluded_titles);
                setPreviewText('preview-excluded-skills', p.excluded_skills);
            });
    }

    function saveProfileForm(e) {
        e.preventDefault();
        showProgress('Saving Candidate Profile to config.yaml...', 25);
        const getInputValue = id => document.getElementById(id) ? document.getElementById(id).value : '';
        const getListValue = id => getInputValue(id).split(',').map(s => s.trim()).filter(Boolean);
        const getIntVal = id => {
            const v = getInputValue(id);
            return v !== '' && !isNaN(parseInt(v)) ? parseInt(v) : null;
        };

        const payload = {
            target_titles: getListValue('prof-titles'),
            years_experience: getIntVal('prof-exp') || 0,
            required_skills: getListValue('prof-req-skills'),
            preferred_skills: getListValue('prof-pref-skills'),
            locations: getListValue('prof-locations'),
            salary_min: getIntVal('prof-salary'),
            salary_max: getIntVal('prof-salary-max'),
            industries: getListValue('prof-industries'),
            work_modes: getListValue('prof-work-modes'),
            excluded_companies: getListValue('prof-excluded-companies'),
            excluded_titles: getListValue('prof-excluded-titles'),
            excluded_skills: getListValue('prof-excluded-skills'),
        };

        fetch('/api/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            finishProgress('Candidate Profile Saved to config.yaml!', true);
            alert('✅ Profile saved to config.yaml!');
            fetchProfile();
            if (typeof loadAllData === 'function') loadAllData();
        })
        .catch(err => {
            finishProgress('Failed saving profile', false);
            alert('❌ Failed saving profile: ' + err);
        });
    }

    function loadCommandsMetadata() {
        fetch('/api/commands')
            .then(res => res.json())
            .then(categories => {
                metadataCommands = categories;
                renderCommands(categories);
            });
    }

    function renderCommands(categories) {
        const accordion = document.getElementById('commands-accordion');
        accordion.innerHTML = '';

        categories.forEach((cat, idx) => {
            const catId = `cat-${idx}`;
            let cmdCards = '';

            cat.commands.forEach(cmd => {
                let paramsHtml = '';
                cmd.params.forEach(p => {
                    if (p.type === 'bool') {
                        paramsHtml += `
                            <div class="form-check form-switch col-md-6 mb-2">
                                <input class="form-check-input" type="checkbox" id="param-${cmd.id}-${p.name}" ${p.default ? 'checked' : ''}>
                                <label class="form-check-label small" for="param-${cmd.id}-${p.name}">${p.label}</label>
                            </div>`;
                    } else if (p.type === 'select') {
                        const opts = (p.options || []).map(o => `<option value="${o}" ${o === p.default ? 'selected' : ''}>${o}</option>`).join('');
                        paramsHtml += `
                            <div class="col-md-6 mb-2">
                                <label class="form-label small mb-1">${p.label}</label>
                                <select class="form-select form-select-sm" id="param-${cmd.id}-${p.name}">${opts}</select>
                            </div>`;
                    } else {
                        paramsHtml += `
                            <div class="col-md-6 mb-2">
                                <label class="form-label small mb-1">${p.label}</label>
                                <input type="${p.type === 'number' ? 'number' : 'text'}" class="form-control form-control-sm" id="param-${cmd.id}-${p.name}" value="${p.default}" placeholder="${p.label}">
                            </div>`;
                    }
                });

                cmdCards += `
                    <div class="command-card p-3 mb-3" id="cmd-card-${cmd.id}">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h6 class="fw-bold mb-1 text-primary"><code>python -m job_agent ${cmd.cmd}</code></h6>
                                <small class="text-muted">${cmd.description}</small>
                            </div>
                            <button class="btn btn-sm btn-primary" onclick="runCommandFromCard('${cmd.id}')"><i class="bi bi-play-fill"></i> Run Command</button>
                        </div>
                        ${paramsHtml ? `<div class="row g-2 mt-1 pt-2 border-top">${paramsHtml}</div>` : ''}
                    </div>`;
            });

            accordion.innerHTML += `
                <div class="accordion-item border-0 mb-3 shadow-sm rounded">
                    <h2 class="accordion-header">
                        <button class="accordion-button ${idx === 0 ? '' : 'collapsed'} fw-bold" type="button" data-bs-toggle="collapse" data-bs-target="#${catId}">
                            ${cat.category}
                        </button>
                    </h2>
                    <div id="${catId}" class="accordion-collapse collapse ${idx === 0 ? 'show' : ''}">
                        <div class="accordion-body bg-light p-3">
                            ${cmdCards}
                        </div>
                    </div>
                </div>`;
        });
    }

    function runCommandFromCard(cmdId) {
        let matchedCmd = null;
        for (const cat of metadataCommands) {
            for (const c of cat.commands) {
                if (c.id === cmdId) {
                    matchedCmd = c;
                    break;
                }
            }
        }
        if (!matchedCmd) return;

        const args = [];
        for (const p of matchedCmd.params) {
            const el = document.getElementById(`param-${cmdId}-${p.name}`);
            if (!el) continue;

            if (p.flag === 'positional') {
                const val = el.value ? el.value.trim() : '';
                if (val) args.push(val);
            } else if (p.type === 'bool') {
                if (p.flag.includes('/')) {
                    const [pos, neg] = p.flag.split('/');
                    if (el.checked) args.push(pos);
                    else args.push(neg);
                } else if (el.checked) {
                    args.push(p.flag);
                }
            } else {
                const val = el.value ? el.value.trim() : '';
                if (val) {
                    args.push(p.flag);
                    args.push(val);
                }
            }
        }

        executeCommandOnServer(matchedCmd.cmd, args);
    }

    function triggerQuickCommand(cmd, args) {
        if (document.body.classList.contains('console-mode-user')) {
            navigateTo('cls-tab');
            runClsTask(cmd, args || []);
            return;
        }
        navigateTo('cheatsheet-tab');
        executeCommandOnServer(cmd, args);
    }

    function executeCommandOnServer(cmd, args) {
        const term = document.getElementById('terminal-output');
        term.innerText = `[Executing] python -m job_agent ${cmd} ${(args || []).join(' ')}...\n\nRunning... Please wait.`;
        showProgress(`Executing CLI command 'python -m job_agent ${cmd}'...`, 15);

        fetch('/api/run-command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: cmd, args: args || []})
        })
        .then(res => res.json())
        .then(data => {
            term.innerText = `$ ${data.command}\n\n${data.output}`;
            finishProgress(`CLI command '${cmd}' executed successfully (exit code ${data.exit_code})`, data.success);
            loadAllData();
        })
        .catch(err => {
            term.innerText = `Error executing command: ${err}`;
            finishProgress(`CLI command '${cmd}' failed`, false);
        });
    }

    function clearTerminal() {
        document.getElementById('terminal-output').innerText = 'Terminal cleared.';
    }

    function filterCommands() {
        const query = document.getElementById('cmd-search-input').value.toLowerCase();
        const cards = document.querySelectorAll('.command-card');
        cards.forEach(card => {
            const text = card.innerText.toLowerCase();
            card.style.display = text.includes(query) ? 'block' : 'none';
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
</script>
</body>
</html>
"""

HTML_CAPTURE_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>1-Click Bookmarklet Endpoint — Job Search Agent</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body { background-color: #f8f9fa; font-family: system-ui, -apple-system, sans-serif; }
        .hero-box { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 2rem; border-radius: 12px; }
        .code-box { background-color: #0f172a; color: #38bdf8; font-family: monospace; font-size: 0.85rem; padding: 1rem; border-radius: 8px; word-break: break-all; }
    </style>
</head>
<body>
<div class="container py-5" style="max-width: 800px;">
    <div class="hero-box shadow-sm mb-4">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h3 class="fw-bold mb-0"><i class="bi bi-bookmark-star-fill text-warning"></i> Bookmarklet Endpoint</h3>
            <span class="badge bg-success fs-6"><i class="bi bi-check-circle-fill"></i> Endpoint Active</span>
        </div>
        <p class="text-light-50 mb-0">Local HTTP server listening on <code>http://localhost:8000/capture</code>. Save job listings from Indeed, LinkedIn, Dice, ZipRecruiter, or Glassdoor directly into SQLite with 1 click while browsing!</p>
    </div>

    <div class="card border-0 shadow-sm mb-4">
        <div class="card-header bg-white fw-bold py-3"><i class="bi bi-gear-fill text-primary"></i> 1-Click Bookmarklet Installer</div>
        <div class="card-body">
            <ol class="mb-4">
                <li class="mb-2">Show Chrome Bookmarks Bar: press <code>Ctrl + Shift + B</code> (or <code>Cmd + Shift + B</code> on Mac).</li>
                <li class="mb-2">Right-click Bookmarks Bar &rarr; <strong>Add page...</strong></li>
                <li class="mb-2">Name it <strong>"Capture Job"</strong> and paste the javascript snippet below in the URL field.</li>
            </ol>

            <div class="code-box mb-3" id="bm-code">javascript:(function(){const title=document.querySelector('h1')?.innerText||document.title;const company=document.querySelector('[data-testid="inlineHeader-companyName"], .companyName, .company-name, [data-cy="search-result-company-name"]')?.innerText||"Unknown";const url=window.location.href;const description=document.querySelector('#jobDescriptionText, .job-description, .description, #job-description')?.innerText||document.body.innerText.slice(0,3000);fetch('http://localhost:8000/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,company,url,description})}).then(res=>res.json()).then(data=>alert(`✅ Job Saved!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nScore: ${data.score}/100`)).catch(err=>alert('❌ Error: Make sure "python -m job_agent web" is running.'));})();</div>

            <div class="d-flex gap-2 flex-wrap">
                <button class="btn btn-outline-primary" onclick="copyBookmarkletCode()"><i class="bi bi-clipboard"></i> Copy Bookmarklet Code</button>
                <button class="btn btn-outline-success" onclick="testCaptureEndpoint()"><i class="bi bi-play-circle-fill"></i> Send Test Capture Payload</button>
                <button class="btn btn-success" onclick="markBookmarkletInstalledOnCapturePage()"><i class="bi bi-check2-circle"></i> Mark as Installed</button>
                <a href="/" class="btn btn-primary ms-auto"><i class="bi bi-speedometer2"></i> Open Web Dashboard</a>
            </div>
            <div class="mt-3 small text-muted" id="capture-install-status"></div>
        </div>
    </div>
</div>
<script>
const BOOKMARKLET_INSTALLED_KEY = 'job_agent_bookmarklet_installed';

function updateCaptureInstallStatus() {
    const el = document.getElementById('capture-install-status');
    if (!el) return;
    if (localStorage.getItem(BOOKMARKLET_INSTALLED_KEY) === 'true') {
        el.innerHTML = '<span class="badge bg-success"><i class="bi bi-check-circle-fill"></i> This browser is marked as having the bookmarklet installed.</span>';
    } else {
        el.innerHTML = 'After adding the bookmark to Chrome, click <strong>Mark as Installed</strong> so the dashboard remembers your setup.';
    }
}

function markBookmarkletInstalledOnCapturePage() {
    localStorage.setItem(BOOKMARKLET_INSTALLED_KEY, 'true');
    updateCaptureInstallStatus();
    alert('✅ Bookmarklet marked as installed in this browser. You can revisit this page anytime from the dashboard Install Bookmarklet link.');
}

document.addEventListener('DOMContentLoaded', updateCaptureInstallStatus);

function copyBookmarkletCode() {
    const code = document.getElementById('bm-code').innerText;
    navigator.clipboard.writeText(code);
    alert('✅ Bookmarklet snippet copied to clipboard! Paste it into Chrome Bookmark URL field.');
}
function testCaptureEndpoint() {
    fetch('/capture', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            title: 'Sample Test Developer Position',
            company: 'Test Employer Corp',
            url: 'http://localhost:8000/capture-test',
            description: 'Sample description for testing capture endpoint functionality.'
        })
    })
    .then(res => res.json())
    .then(data => alert(`✅ Test Capture Successful!\n\nJob ID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nScore: ${data.score}/100`))
    .catch(err => alert('Error testing capture endpoint: ' + err));
}
</script>
</body>
</html>
"""


class WebConsoleRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving Web Console dashboard, JSON APIs, and command runner."""

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self) -> None:
        try:
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            pass

    def do_GET(self) -> None:
        url_path = urllib.parse.urlparse(self.path).path
        query_params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        try:
            if url_path in ("/", "/dashboard", "/cheat-sheet", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(HTML_APP_TEMPLATE.encode("utf-8"))

            elif url_path == "/capture":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(HTML_CAPTURE_PAGE.encode("utf-8"))

            elif url_path == "/api/calendar.ics":
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    ics_content = generate_ics_calendar(session)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/calendar; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="job_search_schedule.ics"')
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(ics_content.encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/stats":
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    summary = generate_pipeline_summary(session)
                    high_scores = [
                        {"id": j.id, "title": j.title, "company": j.company, "match_score": j.match_score, "source_platform": j.source_platform}
                        for j in summary["high_score_jobs"]
                    ]
                    recent = list_jobs(session, limit=8)
                    recent_jobs = [
                        {
                            "id": j.id,
                            "title": j.title,
                            "company": j.company,
                            "match_score": j.match_score,
                            "source_platform": j.source_platform,
                        }
                        for j in recent
                    ]
                    payload = {
                        "total_jobs": summary["total_jobs"],
                        "status_counts": summary["status_counts"],
                        "high_score_jobs": high_scores,
                        "recent_jobs": recent_jobs,
                        "health": get_system_health(settings, session),
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/activities":
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    stmt = select(ActivityLogRecord).order_by(ActivityLogRecord.id.desc()).limit(20)
                    acts = session.scalars(stmt).all()
                    act_list = [
                        {
                            "id": a.id,
                            "event_type": a.event_type,
                            "title": a.title,
                            "description": a.description,
                            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                        }
                        for a in acts
                    ]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(act_list).encode("utf-8"))
                finally:
                    session.close()

            elif url_path.startswith("/api/jobs/") and url_path.count("/") == 3:
                job_id_str = url_path.rsplit("/", 1)[-1]
                if job_id_str.isdigit():
                    job_id = int(job_id_str)
                    settings = get_settings()
                    SessionLocal = init_db(settings.database_path)
                    session = SessionLocal()
                    try:
                        j = get_job(session, job_id)
                        if not j:
                            self.send_error(404, "Job not found")
                            return
                        payload = {
                            "id": j.id,
                            "title": j.title,
                            "company": j.company,
                            "location": j.location,
                            "description": j.description,
                            "status": j.status,
                            "match_score": j.match_score,
                            "source_platform": j.source_platform,
                            "job_url": j.job_url,
                        }
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps(payload).encode("utf-8"))
                    finally:
                        session.close()
                else:
                    self.send_error(404, "Page not found")

            elif url_path == "/api/jobs":
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    jobs = list_jobs(session, limit=200)
                    job_list = [
                        {
                            "id": j.id,
                            "title": j.title,
                            "company": j.company,
                            "status": j.status,
                            "match_score": j.match_score,
                            "source_platform": j.source_platform,
                            "is_duplicate": j.is_duplicate,
                            "job_url": j.job_url,
                        }
                        for j in jobs
                    ]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(job_list).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/get":
                job_id = int((query_params.get("job_id") or ["0"])[0])
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    j = get_job(session, job_id)
                    if not j:
                        self.send_error(404, "Job not found")
                        return

                    master_path = profile.get_master_resume_path(j.title) or str(settings.master_resume_path or "Not configured")

                    optimize = None
                    if j.draft_resume_path:
                        bundle = load_optimize_bundle(j.draft_resume_path)
                        if bundle:
                            optimize = bundle.to_dict()

                    payload = {
                        "job_id": j.id,
                        "title": j.title,
                        "company": j.company,
                        "master_resume_path": master_path,
                        "draft_resume_path": j.draft_resume_path or "",
                        "final_resume_path": j.final_resume_path or j.tailored_resume_path or "",
                        "approval_status": j.approval_status or "Not created",
                        "diff_summary": j.diff_summary or "No draft generated yet.",
                        "optimize": optimize,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/auto-apply/eligibility":
                job_id = int((query_params.get("job_id") or ["0"])[0])
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    j = get_job(session, job_id)
                    if not j:
                        self.send_error(404, "Job not found")
                        return
                    payload = evaluate_auto_apply_eligibility(j).to_dict()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/email/providers":
                settings = get_settings()
                payload = email_provider_status(settings)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/tables":
                payload = {"tables": ["jobs", "activity_logs", "contacts", "interviews", "application_answers", "processed_emails"]}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/table-data":
                table_name = (query_params.get("table") or ["jobs"])[0]
                valid_tables = {"jobs", "activity_logs", "contacts", "interviews", "application_answers", "processed_emails"}
                if table_name not in valid_tables:
                    self.send_error(400, "Invalid table name")
                    return
                settings = get_settings()
                engine = create_db_engine(settings.database_path)
                with engine.connect() as conn:
                    res = conn.execute(text(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 100"))
                    cols = list(res.keys())
                    raw_rows = res.fetchall()
                    rows = []
                    for row in raw_rows:
                        row_dict = {}
                        for idx, col in enumerate(cols):
                            val = row[idx]
                            if isinstance(val, (datetime, date)):
                                val = val.isoformat()
                            row_dict[col] = val
                        rows.append(row_dict)
                    payload = {"table": table_name, "columns": cols, "rows": rows}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/profile":
                profile = load_candidate_profile()
                payload = profile.to_dict()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/commands":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(CLI_COMMANDS_METADATA).encode("utf-8"))

            elif url_path == "/api/console-settings":
                settings = get_settings()
                payload = get_web_console_settings(settings.config_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            else:
                self.send_error(404, "Page not found")

        except Exception as exc:
            logger.error("Error handling GET %s: %s", self.path, exc)
            try:
                self.send_error(500, f"Internal Server Error: {exc}")
            except Exception:
                pass

    def do_POST(self) -> None:
        url_path = urllib.parse.urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace") if content_length > 0 else "{}"

        try:
            if url_path == "/api/run-command":
                data = json.loads(body)
                cmd_name = data.get("command") or "help"
                args = data.get("args") or []
                res = execute_cli_command(cmd_name, [str(a) for a in args])

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))

            elif url_path == "/api/jobs/import-url":
                data = json.loads(body)
                url = data.get("url") or ""
                if not url:
                    self.send_error(400, "URL required")
                    return

                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    parsed = import_job_from_url(url)
                    record, match, dupe = record_parsed_job(session, parsed, profile)
                    log_activity(
                        session,
                        event_type="import",
                        title=f"Imported Job #{record.id} via URL",
                        description=f"{record.title} at {record.company} ({record.source_platform})",
                        job_id=record.id,
                    )
                    payload = {
                        "status": "success",
                        "job_id": record.id,
                        "title": record.title,
                        "company": record.company,
                        "score": match.score,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/jobs/find":
                data = json.loads(body)
                platforms = data.get("platforms") or list(TOP_10_PLATFORMS)
                limit = int(data.get("limit") or 3)
                limit = min(max(limit, 1), 9)

                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    import_result = search_and_import_jobs(
                        session, profile, platforms=platforms, limit_per_platform=limit
                    )
                    platform_reports = [
                        {
                            "platform": r.platform,
                            "fetched": r.fetched,
                            "imported": r.imported,
                            "status": r.status,
                            "message": r.message,
                            "tier": r.tier,
                        }
                        for r in import_result.platform_reports
                    ]
                    payload = {
                        "status": "success",
                        "jobs_recorded": import_result.jobs_recorded,
                        "platforms_searched": list(platforms),
                        "limit_per_platform": limit,
                        "platform_reports": platform_reports,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/jobs/analyze":
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    updated = reanalyze_all_jobs(session, profile)
                    payload = {"status": "success", "jobs_updated": updated}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/jobs/seed-demo":
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job_ids = seed_demo_jobs(session, profile)
                    reanalyze_all_jobs(session, profile)
                    payload = {"status": "success", "jobs_seeded": len(job_ids), "job_ids": job_ids}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/jobs/update":
                data = json.loads(body)
                job_id = int(data.get("job_id") or 0)
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job = update_job_details(
                        session,
                        job_id,
                        title=data.get("title"),
                        company=data.get("company"),
                        description=data.get("description"),
                        location=data.get("location"),
                        salary=data.get("salary"),
                        user_notes=data.get("user_notes"),
                    )
                    parsed = ParsedJob(
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        source_platform=job.source_platform,
                        salary=job.salary,
                        employment_type=job.employment_type,
                        job_url=job.job_url,
                        description=job.description or "",
                    )
                    match = score_job(parsed, profile)
                    job.match_score = match.score
                    job.recommendation = match.recommendation.value
                    job.match_summary = match.summary
                    job.matched_skills = ", ".join(match.matched_skills)
                    job.missing_skills = ", ".join(match.missing_skills)
                    job.concerns = "; ".join(match.concerns)
                    session.commit()
                    payload = {"status": "success", "job_id": job.id, "match_score": job.match_score}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/create":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))

                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job, draft_path, summary_path, diff_summary = create_resume_draft_for_job(
                        session=session,
                        job_id=job_id,
                        profile=profile,
                        settings=settings,
                    )
                    payload = {
                        "status": "success",
                        "job_id": job.id,
                        "draft_path": str(draft_path),
                        "diff_summary": diff_summary,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/approve":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))

                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job, final_path = approve_resume_draft_for_job(
                        session=session,
                        job_id=job_id,
                        settings=settings,
                    )
                    payload = {
                        "status": "success",
                        "job_id": job.id,
                        "final_resume_path": str(final_path),
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/reject":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))

                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job = reject_resume_draft_for_job(session=session, job_id=job_id)
                    payload = {"status": "success", "job_id": job.id}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/optimize":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job = get_job(session, job_id)
                    if not job:
                        self.send_error(404, "Job not found")
                        return
                    if not job.draft_resume_path:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Create a resume draft before running AI Optimize."}).encode("utf-8"))
                        return
                    parsed = ParsedJob(
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        source_platform=job.source_platform,
                        salary=job.salary,
                        employment_type=job.employment_type,
                        job_url=job.job_url or "",
                        description=job.description or "",
                    )
                    match = score_job(parsed, profile)
                    master_path = Path(profile.get_master_resume_path(job.title) or settings.master_resume_path or "")
                    bundle = generate_optimize_suggestions(
                        job=parsed,
                        match=match,
                        master_resume_path=master_path,
                        draft_resume_path=job.draft_resume_path,
                        job_id=job.id,
                        settings=settings,
                    )
                    log_activity(
                        session,
                        event_type="optimize",
                        title=f"AI Optimize for #{job.id}",
                        description=f"Generated {len(bundle.suggestions)} suggestions (source={bundle.source}).",
                        job_id=job.id,
                    )
                    payload = {"status": "success", "optimize": bundle.to_dict()}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/suggestion":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))
                suggestion_id = str(data.get("suggestion_id") or "")
                action = str(data.get("action") or "")
                edited_text = data.get("edited_text")
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job = get_job(session, job_id)
                    if not job or not job.draft_resume_path:
                        self.send_response(404)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Draft not found for job."}).encode("utf-8"))
                        return
                    try:
                        bundle = update_suggestion(
                            job.draft_resume_path,
                            suggestion_id,
                            action,
                            edited_text=edited_text,
                        )
                    except (LookupError, ValueError) as exc:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
                        return
                    payload = {"status": "success", "optimize": bundle.to_dict()}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/draft/optimize/apply":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))
                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    job = get_job(session, job_id)
                    if not job or not job.draft_resume_path:
                        self.send_response(404)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Draft not found for job."}).encode("utf-8"))
                        return
                    master_path = profile.get_master_resume_path(job.title) or settings.master_resume_path
                    try:
                        draft_path = apply_accepted_suggestions_to_draft(
                            job.draft_resume_path,
                            master_resume_path=master_path,
                        )
                    except (LookupError, ValueError, FileNotFoundError) as exc:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
                        return
                    note = "AI Optimize suggestions applied to draft (awaiting final approval)."
                    job.diff_summary = (job.diff_summary or "") + f"\n\n{note}"
                    session.commit()
                    log_activity(
                        session,
                        event_type="optimize",
                        title=f"Applied AI Optimize for #{job.id}",
                        description=note,
                        job_id=job.id,
                    )
                    payload = {
                        "status": "success",
                        "job_id": job.id,
                        "draft_resume_path": str(draft_path),
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/profile/optimize":
                data = json.loads(body) if body else {}
                settings = get_settings()
                profile = load_candidate_profile()
                jd = str(data.get("job_description") or "")
                industry = str(data.get("industry_role") or "")
                resume_path = profile.get_master_resume_path() or settings.master_resume_path
                resume_text = extract_resume_text(resume_path) if resume_path else ""
                result = analyze_profile_against_target(
                    profile,
                    job_description=jd,
                    resume_text=resume_text,
                    industry_role=industry,
                )
                payload = result.to_dict()
                payload["status"] = "success"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/email/sync":
                data = json.loads(body) if body else {}
                provider = str(data.get("provider") or "gmail")
                max_results = int(data.get("max_results") or 25)
                dry_run = bool(data.get("dry_run", False))
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                try:
                    summary = sync_email_alerts(
                        settings,
                        SessionLocal,
                        provider=provider,
                        max_results=max_results,
                        dry_run=dry_run,
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(summary).encode("utf-8"))
                except Exception as exc:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))

            elif url_path == "/api/linkedin/optimize":
                data = json.loads(body) if body else {}
                try:
                    payload = optimize_linkedin_profile(
                        target_role=str(data.get("target_role") or ""),
                        about_context=str(data.get("about_context") or ""),
                        job_description=str(data.get("job_description") or ""),
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                except Exception as exc:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))

            elif url_path == "/api/auto-apply/launch":
                data = json.loads(body) if body else {}
                job_id = int(data.get("job_id", 0))
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    result = launch_auto_apply(
                        session,
                        job_id,
                        settings,
                        open_browser=bool(data.get("open_browser", True)),
                        open_resume_folder=bool(data.get("open_resume_folder", True)),
                        mark_as_applied=bool(data.get("mark_as_applied", False)),
                        confirm=bool(data.get("confirm", False)),
                    )
                    payload = result.to_dict()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                except (LookupError, PermissionError, ValueError) as exc:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/jobs/update-status":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))
                new_status = str(data.get("status") or "Saved")

                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    update_status(session, job_id, new_status, confirm_applied=True)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "job_id": job_id, "new_status": new_status}).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/db/query":
                data = json.loads(body)
                sql_query = data.get("query") or "SELECT 1;"
                settings = get_settings()
                engine = create_db_engine(settings.database_path)
                with engine.connect() as conn:
                    res = conn.execute(text(sql_query))
                    if res.returns_rows:
                        cols = list(res.keys())
                        raw_rows = res.fetchall()
                        rows = [dict(zip(cols, [str(v) if isinstance(v, (datetime, date)) else v for v in r])) for r in raw_rows]
                        payload = {"success": True, "columns": cols, "rows": rows}
                    else:
                        payload = {"success": True, "message": "Query executed successfully."}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/delete-row":
                data = json.loads(body)
                table_name = data.get("table") or "jobs"
                row_id = int(data.get("id") or 0)
                valid_tables = {"jobs", "activity_logs", "contacts", "interviews", "application_answers", "processed_emails"}
                if table_name not in valid_tables or not row_id:
                    self.send_error(400, "Invalid parameters")
                    return
                settings = get_settings()
                engine = create_db_engine(settings.database_path)
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {table_name} WHERE id = :id"), {"id": row_id})
                payload = {"status": "success", "message": f"Row #{row_id} deleted from table {table_name}"}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/cleanup":
                data = json.loads(body)
                action = data.get("action") or "duplicates"
                target_status = data.get("status") or ""

                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    if action == "duplicates":
                        cnt = clean_duplicate_jobs(session)
                        msg = f"Cleaned {cnt} duplicate job records."
                    elif action in ("stale", "excluded"):
                        cnt = clean_stale_or_excluded_jobs(session)
                        msg = f"Cleaned {cnt} stale/excluded job records."
                    elif action == "status":
                        cnt = clean_jobs_by_status(session, target_status)
                        msg = f"Cleaned {cnt} jobs with status '{target_status}'."
                    elif action == "all":
                        res_dict = purge_all_database_data(session)
                        msg = f"Purged test data across all tables: {res_dict}"
                    else:
                        msg = f"Unknown action: {action}"

                    payload = {"status": "success", "message": msg}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/console-settings":
                data = json.loads(body)
                settings = get_settings()
                saved = save_web_console_settings(
                    default_mode=data.get("default_mode"),
                    guided_flow_pause_seconds=data.get("guided_flow_pause_seconds"),
                    setup_locked=data.get("setup_locked"),
                    config_path=settings.config_path,
                )
                payload = {"status": "success", **saved}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/profile":
                data = json.loads(body)
                current_p = load_candidate_profile()

                def _get_list(key: str, default: list[str]) -> list[str]:
                    if key in data and isinstance(data[key], list):
                        return [str(x).strip() for x in data[key] if str(x).strip()]
                    return default

                def _get_int(key: str, default: int | None) -> int | None:
                    if key in data:
                        val = data[key]
                        if val is None or val == "":
                            return None
                        try:
                            return int(val)
                        except (ValueError, TypeError):
                            return default
                    return default

                updated_p = CandidateProfile(
                    target_titles=_get_list("target_titles", current_p.target_titles),
                    industries=_get_list("industries", current_p.industries),
                    required_skills=_get_list("required_skills", current_p.required_skills),
                    preferred_skills=_get_list("preferred_skills", current_p.preferred_skills),
                    years_experience=_get_int("years_experience", current_p.years_experience) or 0,
                    locations=_get_list("locations", current_p.locations),
                    work_modes=_get_list("work_modes", current_p.work_modes),
                    salary_min=_get_int("salary_min", current_p.salary_min),
                    salary_max=_get_int("salary_max", current_p.salary_max),
                    salary_currency=str(data.get("salary_currency", current_p.salary_currency)),
                    employment_types=_get_list("employment_types", current_p.employment_types),
                    work_authorization=data.get("work_authorization", current_p.work_authorization),
                    excluded_companies=_get_list("excluded_companies", current_p.excluded_companies),
                    excluded_titles=_get_list("excluded_titles", current_p.excluded_titles),
                    excluded_skills=_get_list("excluded_skills", current_p.excluded_skills),
                    excluded_locations=_get_list("excluded_locations", current_p.excluded_locations),
                    master_resume_path=current_p.master_resume_path,
                    master_resumes=current_p.master_resumes,
                    cover_letter_template_path=current_p.cover_letter_template_path,
                )
                save_candidate_profile(updated_p)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Profile updated"}).encode("utf-8"))

            elif url_path == "/capture":
                data = json.loads(body)
                title = data.get("title") or "Captured Job"
                company = data.get("company") or "Unknown"
                url = data.get("url") or ""
                description = data.get("description") or ""

                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                profile = load_candidate_profile()

                session = SessionLocal()
                try:
                    parsed = ParsedJob(
                        title=title,
                        company=company,
                        job_url=url,
                        description=description,
                        source_platform="browser_capture",
                    )
                    record, match, dupe = record_parsed_job(session, parsed, profile)
                    log_activity(
                        session,
                        event_type="import",
                        title=f"Captured Job #{record.id} via Chrome Bookmarklet",
                        description=f"{record.title} at {record.company}",
                        job_id=record.id,
                    )
                    response_payload = {
                        "status": "success",
                        "job_id": record.id,
                        "title": record.title,
                        "company": record.company,
                        "score": match.score,
                        "recommendation": match.recommendation.value,
                        "is_duplicate": dupe.is_duplicate,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(response_payload).encode("utf-8"))
                finally:
                    session.close()

            else:
                self.send_error(404, "Endpoint not found")

        except Exception as exc:
            logger.error("Error handling POST %s: %s", self.path, exc)
            try:
                self.send_error(400, f"Error processing request: {exc}")
            except Exception:
                pass

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            err_payload = json.dumps({"error": message or "Error", "code": code})
            self.wfile.write(err_payload.encode("utf-8"))
        except Exception:
            super().send_error(code, message, explain)

    def log_message(self, format: str, *args: Any) -> None:
        try:
            msg = format % args if args else format
            logger.info("%s - %s", self.address_string(), msg)
        except Exception:
            logger.info("%s - %s", self.address_string(), format)


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def start_web_dashboard_server(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    """Start local web console and HTTP capture server on localhost."""
    server = _ThreadingHTTPServer((host, port), WebConsoleRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Local Web Console running on http://%s:%d/", host, port)
    return server
