"""Web application dashboard, Kanban board, database explorer, data cleanup, and CLI execution server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from sqlalchemy import text

from job_agent.application_tracker import list_tracked_jobs, mark_applied, record_parsed_job, update_status
from job_agent.backup_service import create_backup
from job_agent.cleanup_service import (
    clean_duplicate_jobs,
    clean_jobs_by_status,
    clean_old_jobs,
    clean_stale_or_excluded_jobs,
    purge_all_database_data,
)
from job_agent.config import get_settings, load_candidate_profile, save_candidate_profile
from job_agent.database import JobRecord, create_db_engine, get_job, init_db, list_jobs
from job_agent.document_exporter import application_folder
from job_agent.logging_config import get_logger
from job_agent.models import CandidateProfile, ParsedJob
from job_agent.report_service import generate_ics_calendar, generate_pipeline_summary, generate_report

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
                "description": "Search job platforms (Dice, ZipRecruiter) directly (<10 jobs per platform, <1-2 weeks old).",
                "params": [
                    {"name": "platforms", "flag": "--platforms", "type": "text", "default": "dice,ziprecruiter", "label": "Platforms (dice,ziprecruiter)"},
                    {"name": "limit", "flag": "--limit", "type": "number", "default": 9, "label": "Max jobs per platform (<10 default)"}
                ]
            },
            {
                "id": "search-links",
                "name": "search-links",
                "cmd": "search-links",
                "description": "Generate platform search URLs filtered for jobs posted in the last 1-2 weeks.",
                "params": [
                    {"name": "open", "flag": "--open", "type": "bool", "default": False, "label": "Open links in browser"},
                    {"name": "browser", "flag": "--browser", "type": "text", "default": "chrome", "label": "Browser (chrome/edge/default)"}
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
                "id": "add-job",
                "name": "add-job",
                "cmd": "add-job",
                "description": "Manually import a job listing via URL, title, company, and description.",
                "params": [
                    {"name": "url", "flag": "--url", "type": "text", "default": "", "label": "Job URL"},
                    {"name": "title", "flag": "--title", "type": "text", "default": "", "label": "Job Title"},
                    {"name": "company", "flag": "--company", "type": "text", "default": "", "label": "Company Name"},
                    {"name": "description", "flag": "--description", "type": "text", "default": "", "label": "Job Description"},
                    {"name": "salary", "flag": "--salary", "type": "text", "default": "", "label": "Salary Range"}
                ]
            }
        ]
    },
    {
        "category": "Analysis & Document Tailoring",
        "commands": [
            {
                "id": "analyze",
                "name": "analyze",
                "cmd": "analyze",
                "description": "Re-score all saved jobs against candidate profile and master DOCX resume text.",
                "params": [
                    {"name": "min_score", "flag": "--min-score", "type": "number", "default": "", "label": "Minimum score filter"}
                ]
            },
            {
                "id": "tailor",
                "name": "tailor",
                "cmd": "tailor",
                "description": "Generate ATS tailored DOCX resume and cover letter in ~/Desktop/Jobs Applied/.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "dry_run", "flag": "--dry-run", "type": "bool", "default": False, "label": "Dry Run mode"},
                    {"name": "cover_letter", "flag": "--cover-letter/--no-cover-letter", "type": "bool", "default": True, "label": "Generate cover letter"}
                ]
            }
        ]
    },
    {
        "category": "Application Tracking & Pipeline",
        "commands": [
            {
                "id": "jobs",
                "name": "jobs",
                "cmd": "jobs",
                "description": "List tracked jobs with status, score, company, and source platform.",
                "params": [
                    {"name": "min_score", "flag": "--min-score", "type": "number", "default": "", "label": "Min Score Filter"},
                    {"name": "status", "flag": "--status", "type": "text", "default": "", "label": "Status Filter"},
                    {"name": "limit", "flag": "--limit", "type": "number", "default": 50, "label": "Max rows"}
                ]
            },
            {
                "id": "mark-applied",
                "name": "mark-applied",
                "cmd": "mark-applied",
                "description": "Mark job as Applied after manual submission on employer platform.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "confirm", "flag": "--confirm", "type": "bool", "default": True, "label": "Confirm status change"}
                ]
            },
            {
                "id": "dashboard",
                "name": "dashboard",
                "cmd": "dashboard",
                "description": "View job search pipeline summary, high score opportunities, and interviews.",
                "params": []
            },
            {
                "id": "follow-ups",
                "name": "follow-ups",
                "cmd": "follow-ups",
                "description": "List follow-up actions due or overdue.",
                "params": []
            },
            {
                "id": "report",
                "name": "report",
                "cmd": "report",
                "description": "Generate local analytics report on applications, response rates, and platforms.",
                "params": [
                    {"name": "period", "flag": "--period", "type": "select", "default": "weekly", "options": ["weekly", "monthly"], "label": "Report Period"}
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
                    {"name": "days", "flag": "--days", "type": "number", "default": 30, "label": "Days threshold (if action=old)"},
                    {"name": "confirm", "flag": "--confirm", "type": "bool", "default": True, "label": "Confirm deletion"}
                ]
            },
            {
                "id": "backup",
                "name": "backup",
                "cmd": "backup",
                "description": "Create local ZIP backup archive of SQLite DB, settings, and documents.",
                "params": [
                    {"name": "backup_path", "flag": "positional", "type": "text", "default": "", "label": "Backup Output Path (optional)"}
                ]
            },
            {
                "id": "restore",
                "name": "restore",
                "cmd": "restore",
                "description": "Restore SQLite database and configuration from a local backup archive.",
                "params": [
                    {"name": "backup_path", "flag": "positional", "type": "text", "default": "", "label": "Backup ZIP Path (required)", "required": True}
                ]
            },
            {
                "id": "delete-job",
                "name": "delete-job",
                "cmd": "delete-job",
                "description": "Delete a single job record and its generated output directory.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "confirm", "flag": "--confirm", "type": "bool", "default": True, "label": "Confirm deletion"}
                ]
            },
            {
                "id": "purge-data",
                "name": "purge-data",
                "cmd": "purge-data",
                "description": "Purge all local database records and reset SQLite schema.",
                "params": [
                    {"name": "confirm", "flag": "--confirm", "type": "bool", "default": True, "label": "Confirm purge"}
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


HTML_APP_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Search Agent — Web Console & Interactive Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        :root {
            --bg-main: #f8f9fa;
            --card-border: #e2e8f0;
            --brand-primary: #2563eb;
        }
        body {
            background-color: var(--bg-main);
            font-family: system-ui, -apple-system, sans-serif;
        }
        .app-header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: #ffffff;
            padding: 1.25rem 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
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
            border: 1px solid var(--card-border);
            border-radius: 12px;
            background: #ffffff;
            padding: 1.25rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        }
        .stat-value {
            font-size: 1.85rem;
            font-weight: 700;
        }
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
        .command-card {
            border: 1px solid var(--card-border);
            border-radius: 10px;
            background: #ffffff;
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
            font-size: 0.85rem;
            padding: 0.35em 0.65em;
        }
    </style>
</head>
<body>

<header class="app-header d-flex justify-content-between align-items-center">
    <div>
        <h4 class="mb-0 fw-bold"><i class="bi bi-robot"></i> Job Search Agent Web Console</h4>
        <small class="text-light-50">Local-first Private Assistant, Kanban Board & Database Explorer</small>
    </div>
    <div class="d-flex align-items-center gap-2">
        <a href="/api/calendar.ics" class="btn btn-sm btn-outline-light"><i class="bi bi-calendar-event"></i> Export .ics Calendar</a>
        <button class="btn btn-sm btn-danger" onclick="triggerQuickCleanup('all')"><i class="bi bi-trash3-fill"></i> Purge Test Data</button>
        <button class="btn btn-sm btn-primary" onclick="loadAllData()"><i class="bi bi-arrow-clockwise"></i> Refresh</button>
    </div>
</header>

<div class="container-fluid px-4 py-3">
    <!-- Navigation Tabs -->
    <ul class="nav nav-tabs mb-4" id="mainTabs" role="tablist">
        <li class="nav-item">
            <button class="nav-link active" id="dashboard-tab" data-bs-toggle="tab" data-bs-target="#dashboard-pane"><i class="bi bi-speedometer2"></i> Dashboard</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="kanban-tab" data-bs-toggle="tab" data-bs-target="#kanban-pane"><i class="bi bi-kanban"></i> Kanban Application Board</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="jobs-tab" data-bs-toggle="tab" data-bs-target="#jobs-pane"><i class="bi bi-briefcase"></i> Tracked Jobs Explorer</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="db-tab" data-bs-toggle="tab" data-bs-target="#db-pane" onclick="loadDbExplorer()"><i class="bi bi-database-gear"></i> Database Explorer & Cleanup</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="profile-tab" data-bs-toggle="tab" data-bs-target="#profile-pane"><i class="bi bi-person-gear"></i> Profile & Skills Editor</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="cheatsheet-tab" data-bs-toggle="tab" data-bs-target="#cheatsheet-pane"><i class="bi bi-terminal"></i> CLI Command Runner</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="bookmarklet-tab" data-bs-toggle="tab" data-bs-target="#bookmarklet-pane"><i class="bi bi-bookmark-star"></i> Bookmarklet</button>
        </li>
    </ul>

    <div class="tab-content" id="mainTabsContent">
        
        <!-- DASHBOARD PANE -->
        <div class="tab-pane fade show active" id="dashboard-pane">
            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Total Tracked Jobs</div>
                        <div class="stat-value text-primary" id="stat-total-jobs">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">High Match Opportunities</div>
                        <div class="stat-value text-success" id="stat-high-score">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Follow-ups Due</div>
                        <div class="stat-value text-warning" id="stat-followups">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Upcoming Interviews</div>
                        <div class="stat-value text-info" id="stat-interviews">-</div>
                    </div>
                </div>
            </div>

            <div class="row g-3">
                <div class="col-md-8">
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-3">
                            <span><i class="bi bi-star-fill text-warning"></i> High-Score Saved Opportunities</span>
                            <button class="btn btn-sm btn-outline-primary" onclick="triggerQuickCommand('analyze', [])"><i class="bi bi-cpu"></i> Re-Score Jobs</button>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive">
                                <table class="table table-hover align-middle mb-0" id="high-score-table">
                                    <thead class="table-light">
                                        <tr>
                                            <th>ID</th>
                                            <th>Score</th>
                                            <th>Job Title</th>
                                            <th>Company</th>
                                            <th>Platform</th>
                                            <th>Quick Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr><td colspan="6" class="text-center py-3 text-muted">Loading high score jobs...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-md-4">
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold py-3">
                            <i class="bi bi-pie-chart-fill text-primary"></i> Application Status Breakdown
                        </div>
                        <div class="card-body">
                            <ul class="list-group list-group-flush" id="status-counts-list">
                                <li class="list-group-item text-muted">Loading breakdown...</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- KANBAN BOARD PANE -->
        <div class="tab-pane fade" id="kanban-pane">
            <div class="row g-3" id="kanban-board-container">
                <!-- Columns loaded dynamically -->
            </div>
        </div>

        <!-- TRACKED JOBS EXPLORER PANE -->
        <div class="tab-pane fade" id="jobs-pane">
            <div class="card border-0 shadow-sm">
                <div class="card-header bg-white d-flex justify-content-between align-items-center py-3">
                    <h5 class="fw-bold mb-0"><i class="bi bi-card-checklist"></i> All Tracked Jobs Explorer</h5>
                    <div class="d-flex gap-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="triggerQuickCommand('fetch-jobs', ['--platforms', 'dice,ziprecruiter', '--limit', '9'])"><i class="bi bi-download"></i> Fetch Jobs (<10)</button>
                        <button class="btn btn-sm btn-primary" onclick="triggerQuickCommand('analyze', [])"><i class="bi bi-cpu"></i> Re-Score All Jobs</button>
                    </div>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover align-middle mb-0" id="all-jobs-table">
                            <thead class="table-light">
                                <tr>
                                    <th>ID</th>
                                    <th>Status</th>
                                    <th>Score</th>
                                    <th>Title</th>
                                    <th>Company</th>
                                    <th>Platform</th>
                                    <th>Dup?</th>
                                    <th>Interactive Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td colspan="8" class="text-center py-4 text-muted">Loading tracked jobs...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- DATABASE EXPLORER & CLEANUP PANE -->
        <div class="tab-pane fade" id="db-pane">
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
                                <div class="input-group">
                                    <select class="form-select form-select-sm" id="cleanup-status-select">
                                        <option value="Saved">Saved</option>
                                        <option value="Reviewing">Reviewing</option>
                                        <option value="Rejected">Rejected</option>
                                    </select>
                                    <button class="btn btn-sm btn-outline-secondary" onclick="triggerStatusCleanup()">Delete by Status</button>
                                </div>
                                <hr>
                                <button class="btn btn-danger text-start fw-bold" onclick="triggerQuickCleanup('all')"><i class="bi bi-exclamation-triangle-fill"></i> Purge All Database Test Data</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-md-8">
                    <div class="card border-0 shadow-sm h-100">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-2">
                            <span><i class="bi bi-table text-primary"></i> SQLite Table Browser</span>
                            <div class="d-flex align-items-center gap-2">
                                <label class="small text-muted mb-0">Table:</label>
                                <select class="form-select form-select-sm" id="db-table-selector" style="width: auto;" onchange="loadTableData(this.value)">
                                    <option value="jobs">jobs</option>
                                    <option value="contacts">contacts</option>
                                    <option value="interviews">interviews</option>
                                    <option value="application_answers">application_answers</option>
                                    <option value="processed_emails">processed_emails</option>
                                </select>
                            </div>
                        </div>
                        <div class="card-body p-0">
                            <div class="table-responsive" style="max-height: 380px; overflow-y: auto;">
                                <table class="table table-sm table-hover align-middle mb-0 fs-8" id="db-browser-table">
                                    <thead class="table-light">
                                        <tr><th>Select a table above...</th></tr>
                                    </thead>
                                    <tbody>
                                        <tr><td class="text-center py-4 text-muted">Loading table data...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SQL Query Console -->
            <div class="card border-0 shadow-sm">
                <div class="card-header bg-dark text-white fw-bold d-flex justify-content-between align-items-center py-2">
                    <span><i class="bi bi-terminal text-success"></i> Interactive SQL Query Console (SQLite)</span>
                    <button class="btn btn-sm btn-success" onclick="runCustomSqlQuery()"><i class="bi bi-play-fill"></i> Execute SQL</button>
                </div>
                <div class="card-body bg-dark text-white p-3">
                    <textarea class="form-control font-monospace bg-dark text-light border-secondary mb-3" id="sql-query-input" rows="3" placeholder="Type raw SQL query (e.g., SELECT id, title, company, match_score, status FROM jobs WHERE match_score > 70 ORDER BY match_score DESC;)">SELECT id, title, company, status, match_score, source_platform FROM jobs ORDER BY id DESC LIMIT 20;</textarea>
                    <div class="table-responsive" style="max-height: 250px; overflow-y: auto;">
                        <table class="table table-dark table-sm table-striped font-monospace fs-8" id="sql-query-result-table">
                            <thead><tr><th>Result will display here after execution...</th></tr></thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- PROFILE & SKILLS EDITOR PANE -->
        <div class="tab-pane fade" id="profile-pane">
            <div class="card border-0 shadow-sm max-w-800 mx-auto">
                <div class="card-header bg-white fw-bold py-3">
                    <i class="bi bi-person-gear text-primary"></i> Edit Candidate Profile & Target Skills (config.yaml)
                </div>
                <div class="card-body">
                    <form id="profile-editor-form" onsubmit="saveProfileForm(event)">
                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Target Job Titles (comma separated)</label>
                                <input type="text" class="form-control" id="prof-titles">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Years of Experience</label>
                                <input type="number" class="form-control" id="prof-exp">
                            </div>
                        </div>

                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Required Skills (comma separated)</label>
                                <textarea class="form-control" id="prof-req-skills" rows="3"></textarea>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Preferred Skills (comma separated)</label>
                                <textarea class="form-control" id="prof-pref-skills" rows="3"></textarea>
                            </div>
                        </div>

                        <div class="row g-3 mb-3">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Target Locations (comma separated)</label>
                                <input type="text" class="form-control" id="prof-locations">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Target Minimum Salary (USD)</label>
                                <input type="number" class="form-control" id="prof-salary">
                            </div>
                        </div>

                        <div class="row g-3 mb-4">
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Excluded Companies (comma separated)</label>
                                <input type="text" class="form-control" id="prof-ex-companies">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label fw-semibold">Excluded Job Titles (comma separated)</label>
                                <input type="text" class="form-control" id="prof-ex-titles">
                            </div>
                        </div>

                        <button type="submit" class="btn btn-primary"><i class="bi bi-save-fill"></i> Save Profile Configuration</button>
                    </form>
                </div>
            </div>
        </div>

        <!-- CHEAT SHEET & COMMAND EXECUTOR PANE -->
        <div class="tab-pane fade" id="cheatsheet-pane">
            <div class="row">
                <div class="col-md-7">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="fw-bold mb-0"><i class="bi bi-journal-code"></i> CLI Command Cheat Sheet</h5>
                        <input type="text" id="cmd-search-input" class="form-control form-control-sm w-50" placeholder="🔍 Search commands (e.g., fetch, tailor, backup)..." onkeyup="filterCommands()">
                    </div>

                    <div id="commands-accordion">
                        <!-- Command categories loaded dynamically -->
                    </div>
                </div>

                <!-- Live Command Output Terminal -->
                <div class="col-md-5">
                    <div class="card border-0 shadow-sm sticky-top" style="top: 1rem;">
                        <div class="card-header bg-dark text-white fw-bold d-flex justify-content-between align-items-center">
                            <span><i class="bi bi-terminal-fill text-success"></i> Terminal Output Console</span>
                            <button class="btn btn-sm btn-outline-secondary text-white" onclick="clearTerminal()">Clear</button>
                        </div>
                        <div class="card-body p-2 bg-dark">
                            <div class="terminal-box" id="terminal-output">
Ready. Select a CLI command on the left and click "Run Command" to view direct output here.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- BOOKMARKLET PANE -->
        <div class="tab-pane fade" id="bookmarklet-pane">
            <div class="card border-0 shadow-sm max-w-700 mx-auto">
                <div class="card-header bg-white fw-bold py-3">
                    <i class="bi bi-bookmark-star-fill text-warning"></i> 1-Click Chrome Bookmarklet Setup
                </div>
                <div class="card-body">
                    <p class="text-muted">Save any job listing from Indeed, Dice, ZipRecruiter, Glassdoor, or LinkedIn directly into your local database while browsing in Chrome!</p>

                    <ol class="ps-3 mb-4">
                        <li class="mb-2">In Google Chrome, press <kbd>Ctrl + Shift + B</kbd> to show your Bookmarks Bar.</li>
                        <li class="mb-2">Right-click the Bookmarks Bar -> Click <strong>Add page...</strong></li>
                        <li class="mb-2">Set <strong>Name</strong> to: <code>Capture Job</code></li>
                        <li class="mb-2">Set <strong>URL</strong> to the JavaScript snippet below:</li>
                    </ol>

                    <div class="mb-3">
                        <textarea class="form-control font-monospace fs-7" id="bookmarklet-code" rows="8" readonly>javascript:(function(){
  const title = document.querySelector('h1')?.innerText || document.title;
  const company = document.querySelector('[data-testid="inlineHeader-companyName"], .companyName, .company-name, [data-cy="search-result-company-name"]')?.innerText || "Unknown";
  const url = window.location.href;
  const description = document.querySelector('#jobDescriptionText, .job-description, .description, #job-description')?.innerText || document.body.innerText.slice(0, 3000);

  fetch('http://localhost:8000/capture', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, company, url, description})
  })
  .then(res => res.json())
  .then(data => alert(`✅ Job Saved to Job Agent!\\n\\nID: #${data.job_id}\\nTitle: ${data.title}\\nCompany: ${data.company}\\nMatch Score: ${data.score}/100`))
  .catch(err => alert('❌ Error: Make sure "python -m job_agent serve" is running in terminal.'));
})();</textarea>
                    </div>
                    <button class="btn btn-outline-primary btn-sm" onclick="copyBookmarkletCode()"><i class="bi bi-clipboard"></i> Copy Bookmarklet Snippet</button>
                </div>
            </div>
        </div>

    </div>
</div>

<!-- JOB DETAILS MODAL -->
<div class="modal fade" id="jobDetailsModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content">
            <div class="modal-header bg-light">
                <h5 class="modal-title fw-bold" id="modal-job-title">Job Details</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body" id="modal-job-body">
                Loading details...
            </div>
            <div class="modal-footer bg-light d-flex justify-content-between">
                <div>
                    <button class="btn btn-sm btn-outline-secondary" onclick="openJobFolderInExplorer()"><i class="bi bi-folder2-open"></i> Open Desktop Folder</button>
                    <button class="btn btn-sm btn-outline-primary" id="modal-job-url-btn" onclick="openJobUrlExternal()"><i class="bi bi-box-arrow-up-right"></i> Open Link</button>
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-primary" onclick="triggerModalAction('tailor')"><i class="bi bi-file-word"></i> Tailor DOCX</button>
                    <button class="btn btn-sm btn-success" onclick="triggerModalAction('mark-applied')"><i class="bi bi-check-circle"></i> Mark Applied</button>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    let metadataCommands = [];
    let currentModalJobId = null;
    let currentModalJobUrl = null;

    const KANBAN_STATUSES = ["Saved", "Reviewing", "Ready to apply", "Applied", "Interviewing", "Offer", "Rejected"];

    document.addEventListener("DOMContentLoaded", function() {
        loadAllData();
        loadCommandsMetadata();
        fetchProfile();
    });

    function loadAllData() {
        fetchStats();
        fetchJobs();
    }

    function fetchStats() {
        fetch('/api/stats')
            .then(res => res.json())
            .then(data => {
                document.getElementById('stat-total-jobs').innerText = data.total_jobs || 0;
                document.getElementById('stat-high-score').innerText = (data.high_score_jobs || []).length;
                document.getElementById('stat-followups').innerText = (data.followups_due || []).length;
                document.getElementById('stat-interviews').innerText = (data.upcoming_interviews || []).length;

                // Render status counts
                const statusList = document.getElementById('status-counts-list');
                statusList.innerHTML = '';
                for (const [st, cnt] of Object.entries(data.status_counts || {})) {
                    statusList.innerHTML += `<li class="list-group-item d-flex justify-content-between align-items-center fw-medium">${st} <span class="badge bg-primary rounded-pill">${cnt}</span></li>`;
                }

                // Render high score table
                const hsBody = document.querySelector('#high-score-table tbody');
                hsBody.innerHTML = '';
                if (!data.high_score_jobs || data.high_score_jobs.length === 0) {
                    hsBody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">No high-score saved opportunities yet. Run "analyze" or "fetch-jobs".</td></tr>';
                } else {
                    data.high_score_jobs.slice(0, 10).forEach(j => {
                        hsBody.innerHTML += `
                            <tr>
                                <td><strong>#${j.id}</strong></td>
                                <td><span class="badge bg-success badge-score">${Math.round(j.match_score)}</span></td>
                                <td><a href="#" class="text-decoration-none fw-bold" onclick="showJobDetails('${j.id}')">${escapeHtml(j.title)}</a></td>
                                <td>${escapeHtml(j.company)}</td>
                                <td><small class="text-muted">${j.source_platform}</small></td>
                                <td>
                                    <button class="btn btn-xs btn-outline-primary py-0 px-2" onclick="triggerQuickCommand('tailor', ['${j.id}'])">Tailor DOCX</button>
                                </td>
                            </tr>
                        `;
                    });
                }
            });
    }

    function fetchJobs() {
        fetch('/api/jobs')
            .then(res => res.json())
            .then(jobs => {
                renderAllJobsTable(jobs);
                renderKanbanBoard(jobs);
            });
    }

    function renderAllJobsTable(jobs) {
        const tbody = document.querySelector('#all-jobs-table tbody');
        tbody.innerHTML = '';
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No jobs tracked yet. Run "fetch-jobs" or use the 1-click Chrome bookmarklet!</td></tr>';
            return;
        }
        jobs.forEach(j => {
            const scoreBadge = j.match_score ? `<span class="badge bg-success badge-score">${Math.round(j.match_score)}</span>` : '<span class="badge bg-secondary">-</span>';
            tbody.innerHTML += `
                <tr>
                    <td><strong>#${j.id}</strong></td>
                    <td><span class="badge bg-info text-dark">${j.status}</span></td>
                    <td>${scoreBadge}</td>
                    <td><a href="#" class="text-decoration-none fw-semibold" onclick="showJobDetails('${j.id}')">${escapeHtml(j.title)}</a></td>
                    <td>${escapeHtml(j.company)}</td>
                    <td><small class="text-muted">${j.source_platform}</small></td>
                    <td>${j.is_duplicate ? '<span class="text-danger">Yes</span>' : ''}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-secondary" onclick="showJobDetails('${j.id}')"><i class="bi bi-eye"></i> Details</button>
                            <button class="btn btn-outline-primary" onclick="triggerQuickCommand('tailor', ['${j.id}'])"><i class="bi bi-file-word"></i> Tailor</button>
                            <button class="btn btn-outline-success" onclick="triggerQuickCommand('mark-applied', ['${j.id}', '--confirm'])"><i class="bi bi-check-circle"></i> Applied</button>
                        </div>
                    </td>
                </tr>
            `;
        });
    }

    function renderKanbanBoard(jobs) {
        const container = document.getElementById('kanban-board-container');
        container.innerHTML = '';

        KANBAN_STATUSES.forEach(status => {
            const statusJobs = (jobs || []).filter(j => j.status === status);
            let cardsHtml = '';

            statusJobs.forEach(j => {
                const scoreBadge = j.match_score ? `<span class="badge bg-success ms-auto">${Math.round(j.match_score)}</span>` : '';
                cardsHtml += `
                    <div class="kanban-card" onclick="showJobDetails('${j.id}')">
                        <div class="d-flex align-items-center mb-1">
                            <strong class="text-dark fs-7">#${j.id}</strong>
                            ${scoreBadge}
                        </div>
                        <div class="fw-bold text-primary text-truncate mb-1" style="font-size:0.9rem;">${escapeHtml(j.title)}</div>
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
                            <h6 class="fw-bold mb-0 text-dark">${status}</h6>
                            <span class="badge bg-white text-dark border">${statusJobs.length}</span>
                        </div>
                        ${cardsHtml || '<div class="text-muted fs-8 text-center py-4">No jobs</div>'}
                    </div>
                </div>`;
        });
    }

    function moveJobStatus(jobId, newStatus) {
        fetch('/api/jobs/update-status', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(jobId), status: newStatus})
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                loadAllData();
            }
        });
    }

    function showJobDetails(jobId) {
        currentModalJobId = jobId;
        const modal = new bootstrap.Modal(document.getElementById('jobDetailsModal'));
        document.getElementById('modal-job-title').innerText = `Loading Job #${jobId}...`;
        document.getElementById('modal-job-body').innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
        modal.show();

        fetch(`/api/job-details?id=${jobId}`)
            .then(res => res.json())
            .then(j => {
                currentModalJobUrl = j.job_url;
                document.getElementById('modal-job-title').innerText = `Job #${j.id}: ${j.title} at ${j.company}`;
                
                const matchedBadges = (j.matched_skills || []).map(s => `<span class="badge bg-success-subtle text-success border border-success me-1 mb-1">${escapeHtml(s)}</span>`).join('');
                const missingBadges = (j.missing_skills || []).map(s => `<span class="badge bg-danger-subtle text-danger border border-danger me-1 mb-1">${escapeHtml(s)}</span>`).join('');

                document.getElementById('modal-job-body').innerHTML = `
                    <div class="row g-3 mb-3">
                        <div class="col-md-4"><strong>Status:</strong> <span class="badge bg-info text-dark">${j.status}</span></div>
                        <div class="col-md-4"><strong>Match Score:</strong> <span class="badge bg-success">${j.match_score ? Math.round(j.match_score) + '/100' : 'N/A'}</span></div>
                        <div class="col-md-4"><strong>Platform:</strong> ${j.source_platform}</div>
                    </div>
                    <div class="mb-3">
                        <strong>Location:</strong> ${escapeHtml(j.location || 'Not specified')} | 
                        <strong>Salary:</strong> ${escapeHtml(j.salary || 'Not specified')}
                    </div>
                    <div class="mb-3">
                        <h6 class="fw-bold mb-1 text-success">Matched Skills</h6>
                        <div>${matchedBadges || '<span class="text-muted small">None listed</span>'}</div>
                    </div>
                    <div class="mb-3">
                        <h6 class="fw-bold mb-1 text-danger">Missing Skills / Keywords</h6>
                        <div>${missingBadges || '<span class="text-muted small">None missing</span>'}</div>
                    </div>
                    <div class="mb-3">
                        <h6 class="fw-bold mb-1">Job Description</h6>
                        <div class="p-3 bg-light rounded border text-muted fs-7" style="max-height: 250px; overflow-y: auto; white-space: pre-wrap;">${escapeHtml(j.description || 'No description provided.')}</div>
                    </div>
                `;
            });
    }

    function triggerModalAction(action) {
        if (!currentModalJobId) return;
        if (action === 'tailor') {
            triggerQuickCommand('tailor', [currentModalJobId]);
        } else if (action === 'mark-applied') {
            triggerQuickCommand('mark-applied', [currentModalJobId, '--confirm']);
        }
        bootstrap.Modal.getInstance(document.getElementById('jobDetailsModal'))?.hide();
    }

    function openJobFolderInExplorer() {
        if (!currentModalJobId) return;
        fetch('/api/open-folder', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(currentModalJobId)})
        });
    }

    function openJobUrlExternal() {
        if (currentModalJobUrl) {
            window.open(currentModalJobUrl, '_blank');
        }
    }

    function loadDbExplorer() {
        const sel = document.getElementById('db-table-selector');
        loadTableData(sel.value || 'jobs');
    }

    function loadTableData(tableName) {
        fetch(`/api/db/table-data?table=${tableName}`)
            .then(res => res.json())
            .then(data => {
                const tableEl = document.getElementById('db-browser-table');
                if (!data.rows || data.rows.length === 0) {
                    tableEl.innerHTML = '<thead><tr><th>Table Empty</th></tr></thead><tbody><tr><td class="text-center py-3 text-muted">No records in this table.</td></tr></tbody>';
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
            });
    }

    function deleteDbRow(tableName, rowId) {
        if (!confirm(`Delete row #${rowId} from ${tableName}?`)) return;
        fetch('/api/db/delete-row', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({table: tableName, id: parseInt(rowId)})
        })
        .then(res => res.json())
        .then(data => {
            alert(data.message);
            loadTableData(tableName);
            loadAllData();
        });
    }

    function triggerQuickCleanup(action) {
        if (action === 'all' && !confirm('⚠️ Are you sure you want to PURGE ALL database records? This resets your local database completely.')) return;
        fetch('/api/db/cleanup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: action})
        })
        .then(res => res.json())
        .then(data => {
            alert('✅ Cleanup complete: ' + data.message);
            loadAllData();
            loadDbExplorer();
        });
    }

    function triggerStatusCleanup() {
        const st = document.getElementById('cleanup-status-select').value;
        if (!confirm(`Delete all jobs with status '${st}'?`)) return;
        fetch('/api/db/cleanup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'status', status: st})
        })
        .then(res => res.json())
        .then(data => {
            alert('✅ Cleanup complete: ' + data.message);
            loadAllData();
            loadDbExplorer();
        });
    }

    function runCustomSqlQuery() {
        const q = document.getElementById('sql-query-input').value;
        if (!q) return;
        fetch('/api/db/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({query: q})
        })
        .then(res => res.json())
        .then(data => {
            const tableEl = document.getElementById('sql-query-result-table');
            if (!data.success) {
                tableEl.innerHTML = `<thead><tr><th class="text-danger">SQL Error</th></tr></thead><tbody><tr><td>${data.error || 'Execution failed.'}</td></tr></tbody>`;
                return;
            }
            if (!data.columns || data.columns.length === 0) {
                tableEl.innerHTML = `<thead><tr><th class="text-success">Query Executed</th></tr></thead><tbody><tr><td>${data.message || 'Done'}</td></tr></tbody>`;
                return;
            }
            let thead = '<tr>' + data.columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
            let tbody = '';
            data.rows.forEach(r => {
                tbody += '<tr>' + r.map(v => `<td>${escapeHtml(String(v ?? '-'))}</td>`).join('') + '</tr>';
            });
            tableEl.innerHTML = `<thead>${thead}</thead><tbody>${tbody}</tbody>`;
            loadAllData();
        });
    }

    function fetchProfile() {
        fetch('/api/profile')
            .then(res => res.json())
            .then(p => {
                document.getElementById('prof-titles').value = (p.target_titles || []).join(', ');
                document.getElementById('prof-exp').value = p.years_experience || 0;
                document.getElementById('prof-req-skills').value = (p.required_skills || []).join(', ');
                document.getElementById('prof-pref-skills').value = (p.preferred_skills || []).join(', ');
                document.getElementById('prof-locations').value = (p.locations || []).join(', ');
                document.getElementById('prof-salary').value = p.salary_min || 120000;
                document.getElementById('prof-ex-companies').value = (p.excluded_companies || []).join(', ');
                document.getElementById('prof-ex-titles').value = (p.excluded_titles || []).join(', ');
            });
    }

    function saveProfileForm(e) {
        e.preventDefault();
        const payload = {
            target_titles: document.getElementById('prof-titles').value.split(',').map(s => s.trim()).filter(Boolean),
            years_experience: parseInt(document.getElementById('prof-exp').value || 0),
            required_skills: document.getElementById('prof-req-skills').value.split(',').map(s => s.trim()).filter(Boolean),
            preferred_skills: document.getElementById('prof-pref-skills').value.split(',').map(s => s.trim()).filter(Boolean),
            locations: document.getElementById('prof-locations').value.split(',').map(s => s.trim()).filter(Boolean),
            salary_min: parseInt(document.getElementById('prof-salary').value || 0),
            excluded_companies: document.getElementById('prof-ex-companies').value.split(',').map(s => s.trim()).filter(Boolean),
            excluded_titles: document.getElementById('prof-ex-titles').value.split(',').map(s => s.trim()).filter(Boolean),
        };

        fetch('/api/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            alert('✅ Profile configuration saved to config.yaml!');
            loadAllData();
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
        const tabEl = document.getElementById('cheatsheet-tab');
        bootstrap.Tab.getInstance(tabEl)?.show() || new bootstrap.Tab(tabEl).show();
        executeCommandOnServer(cmd, args);
    }

    function executeCommandOnServer(cmd, args) {
        const term = document.getElementById('terminal-output');
        term.innerText = `[Executing] python -m job_agent ${cmd} ${(args || []).join(' ')}...\n\nRunning... Please wait.`;

        fetch('/api/run-command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: cmd, args: args || []})
        })
        .then(res => res.json())
        .then(data => {
            term.innerText = `$ ${data.command}\n\n${data.output}`;
            loadAllData();
        })
        .catch(err => {
            term.innerText = `Error executing command: ${err}`;
        });
    }

    function clearTerminal() {
        document.getElementById('terminal-output').innerText = 'Terminal cleared. Select a command to run.';
    }

    function filterCommands() {
        const query = document.getElementById('cmd-search-input').value.toLowerCase();
        const cards = document.querySelectorAll('.command-card');
        cards.forEach(card => {
            const text = card.innerText.toLowerCase();
            card.style.display = text.includes(query) ? 'block' : 'none';
        });
    }

    function copyBookmarkletCode() {
        const textarea = document.getElementById('bookmarklet-code');
        textarea.select();
        document.execCommand('copy');
        alert('✅ Bookmarklet code copied to clipboard!');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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
                    followups = [
                        {"id": f.id, "title": f.title, "company": f.company, "follow_up_date": f.follow_up_date.strftime("%Y-%m-%d")}
                        for f in summary["followups_due"] if f.follow_up_date
                    ]
                    interviews = [
                        {"job_id": iv.job_id, "interview_date": iv.interview_date.strftime("%Y-%m-%d %H:%M"), "interview_type": iv.interview_type}
                        for iv in summary["upcoming_interviews"] if iv.interview_date
                    ]
                    payload = {
                        "total_jobs": summary["total_jobs"],
                        "status_counts": summary["status_counts"],
                        "platform_counts": summary["platform_counts"],
                        "high_score_jobs": high_scores,
                        "stale_jobs_count": summary["stale_jobs_count"],
                        "upcoming_interviews": interviews,
                        "followups_due": followups,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

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

            elif url_path == "/api/job-details":
                job_id_str = (query_params.get("id") or ["0"])[0]
                job_id = int(job_id_str)
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    j = get_job(session, job_id)
                    if not j:
                        self.send_error(404, "Job not found")
                        return
                    matched_list = [s.strip() for s in (j.matched_skills or "").split(",") if s.strip()]
                    missing_list = [s.strip() for s in (j.missing_skills or "").split(",") if s.strip()]
                    payload = {
                        "id": j.id,
                        "title": j.title,
                        "company": j.company,
                        "status": j.status,
                        "match_score": j.match_score,
                        "location": j.location,
                        "salary": j.salary,
                        "source_platform": j.source_platform,
                        "job_url": j.job_url,
                        "description": j.description,
                        "matched_skills": matched_list,
                        "missing_skills": missing_list,
                        "notes": j.notes or j.user_notes,
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

            elif url_path == "/api/db/tables":
                payload = {"tables": ["jobs", "contacts", "interviews", "application_answers", "processed_emails"]}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/table-data":
                table_name = (query_params.get("table") or ["jobs"])[0]
                valid_tables = {"jobs", "contacts", "interviews", "application_answers", "processed_emails"}
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
                payload = {
                    "target_titles": profile.target_titles,
                    "required_skills": profile.required_skills,
                    "preferred_skills": profile.preferred_skills,
                    "years_experience": profile.years_experience,
                    "locations": profile.locations,
                    "salary_min": profile.salary_min,
                    "excluded_companies": profile.excluded_companies,
                    "excluded_titles": profile.excluded_titles,
                }
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

            elif url_path == "/api/db/query":
                data = json.loads(body)
                query_str = (data.get("query") or "").strip()
                if not query_str:
                    self.send_error(400, "Empty SQL query")
                    return
                settings = get_settings()
                engine = create_db_engine(settings.database_path)
                try:
                    with engine.begin() as conn:
                        res = conn.execute(text(query_str))
                        if res.returns_rows:
                            cols = list(res.keys())
                            raw_rows = res.fetchall()
                            rows = []
                            for row in raw_rows:
                                r_converted = []
                                for val in row:
                                    if isinstance(val, (datetime, date)):
                                        r_converted.append(val.isoformat())
                                    else:
                                        r_converted.append(val)
                                rows.append(r_converted)
                            payload = {"success": True, "columns": cols, "rows": rows, "row_count": len(rows)}
                        else:
                            payload = {"success": True, "columns": [], "rows": [], "row_count": res.rowcount or 0, "message": f"Query executed successfully ({res.rowcount or 0} rows affected)"}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                except Exception as q_err:
                    payload = {"success": False, "error": str(q_err)}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))

            elif url_path == "/api/db/delete-row":
                data = json.loads(body)
                table_name = data.get("table") or "jobs"
                row_id = int(data.get("id") or 0)
                valid_tables = {"jobs", "contacts", "interviews", "application_answers", "processed_emails"}
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

            elif url_path == "/api/open-folder":
                data = json.loads(body)
                job_id = int(data.get("job_id", 0))
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    j = get_job(session, job_id)
                    if j:
                        folder = application_folder(settings.jobs_applied_folder, j.company, j.title)
                        folder.mkdir(parents=True, exist_ok=True)
                        if sys.platform == "win32":
                            subprocess.Popen(["explorer", str(folder)])
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self._set_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "success", "folder": str(folder)}).encode("utf-8"))
                    else:
                        self.send_error(404, "Job not found")
                finally:
                    session.close()

            elif url_path == "/api/profile":
                data = json.loads(body)
                current_p = load_candidate_profile()
                updated_p = CandidateProfile(
                    target_titles=data.get("target_titles", current_p.target_titles),
                    industries=current_p.industries,
                    required_skills=data.get("required_skills", current_p.required_skills),
                    preferred_skills=data.get("preferred_skills", current_p.preferred_skills),
                    years_experience=int(data.get("years_experience", current_p.years_experience)),
                    locations=data.get("locations", current_p.locations),
                    work_modes=current_p.work_modes,
                    salary_min=data.get("salary_min", current_p.salary_min),
                    salary_max=current_p.salary_max,
                    salary_currency=current_p.salary_currency,
                    employment_types=current_p.employment_types,
                    work_authorization=current_p.work_authorization,
                    excluded_companies=data.get("excluded_companies", current_p.excluded_companies),
                    excluded_titles=data.get("excluded_titles", current_p.excluded_titles),
                    excluded_skills=current_p.excluded_skills,
                    excluded_locations=current_p.excluded_locations,
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
                    logger.info("Browser capture recorded job #%d: %s @ %s", record.id, title, company)
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

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default HTTP logging noise


def start_web_dashboard_server(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    """Start local web console and HTTP capture server on localhost."""
    server = HTTPServer((host, port), WebConsoleRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Local Web Console and Capture server running on http://%s:%d/", host, port)
    return server
