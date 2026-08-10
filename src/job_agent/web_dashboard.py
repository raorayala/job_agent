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
    update_status,
)
from job_agent.backup_service import create_backup
from job_agent.cleanup_service import (
    clean_duplicate_jobs,
    clean_jobs_by_status,
    clean_old_jobs,
    clean_stale_or_excluded_jobs,
    purge_all_database_data,
)
from job_agent.config import get_settings, load_candidate_profile, save_candidate_profile
from job_agent.database import ActivityLogRecord, JobRecord, create_db_engine, get_job, init_db, list_jobs, log_activity
from job_agent.document_exporter import application_folder
from job_agent.gmail_client import sync_job_emails
from job_agent.logging_config import get_logger
from job_agent.matcher import score_job
from job_agent.models import CandidateProfile, ParsedJob
from job_agent.platform_fetcher import (
    TOP_10_PLATFORMS,
    generate_platform_search_urls,
    import_job_from_url,
    search_and_import_jobs,
)
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
                "id": "add-job",
                "name": "add-job",
                "cmd": "add-job",
                "description": "Automated job import from a URL (extracts title, company, location, and description).",
                "params": [
                    {"name": "url", "flag": "--url", "type": "text", "default": "", "label": "Job URL (required)", "required": True},
                    {"name": "title", "flag": "--title", "type": "text", "default": "", "label": "Fallback Title"},
                    {"name": "company", "flag": "--company", "type": "text", "default": "", "label": "Fallback Company"}
                ]
            }
        ]
    },
    {
        "category": "Analysis & Review-First Resume Tailoring",
        "commands": [
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
    <title>Job Search Agent Web Console — CLI Command Cheat Sheet & Review-First Web Application</title>
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
        .platform-card {
            border: 1px solid var(--card-border);
            border-radius: 10px;
            background: #ffffff;
            padding: 1rem;
            text-align: center;
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
        <h4 class="mb-0 fw-bold"><i class="bi bi-robot"></i> Job Search Agent</h4>
        <small class="text-light-50">Automated Review-First Personal Career Assistant (100% Private)</small>
    </div>
    <div class="d-flex align-items-center gap-2">
        <button class="btn btn-sm btn-outline-light" onclick="openImportUrlModal()"><i class="bi bi-link-45deg"></i> Import URL</button>
        <a href="/api/calendar.ics" class="btn btn-sm btn-outline-light"><i class="bi bi-calendar-event"></i> .ics Calendar</a>
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
            <button class="nav-link" id="discovery-tab" data-bs-toggle="tab" data-bs-target="#discovery-pane"><i class="bi bi-compass"></i> Job Discovery (Top 10 Platforms)</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="review-tab" data-bs-toggle="tab" data-bs-target="#review-pane"><i class="bi bi-file-earmark-check"></i> Resume Review & Approvals</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="kanban-tab" data-bs-toggle="tab" data-bs-target="#kanban-pane"><i class="bi bi-kanban"></i> Application Board</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="db-tab" data-bs-toggle="tab" data-bs-target="#db-pane" onclick="loadDbExplorer()"><i class="bi bi-database-gear"></i> Database Explorer</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="profile-tab" data-bs-toggle="tab" data-bs-target="#profile-pane"><i class="bi bi-person-gear"></i> Profile & Skills Editor</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="cheatsheet-tab" data-bs-toggle="tab" data-bs-target="#cheatsheet-pane"><i class="bi bi-terminal"></i> CLI Runner</button>
        </li>
    </ul>

    <div class="tab-content" id="mainTabsContent">
        
        <!-- DASHBOARD PANE -->
        <div class="tab-pane fade show active" id="dashboard-pane">
            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">New Discovered Jobs</div>
                        <div class="stat-value text-primary" id="stat-total-jobs">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Jobs Requiring Review</div>
                        <div class="stat-value text-warning" id="stat-review-count">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Draft Resumes Awaiting Approval</div>
                        <div class="stat-value text-danger" id="stat-drafts-count">-</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card">
                        <div class="text-muted small">Applications In Progress</div>
                        <div class="stat-value text-success" id="stat-applied-count">-</div>
                    </div>
                </div>
            </div>

            <!-- Primary Action Bar -->
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-body d-flex flex-wrap gap-2 align-items-center justify-content-between py-3">
                    <span class="fw-bold"><i class="bi bi-lightning-charge-fill text-warning"></i> Primary Actions:</span>
                    <div class="d-flex gap-2">
                        <button class="btn btn-primary" onclick="switchTab('discovery-tab')"><i class="bi bi-search"></i> Find Jobs Now (Top 10 Platforms)</button>
                        <button class="btn btn-outline-primary" onclick="triggerQuickCommand('sync-gmail', [])"><i class="bi bi-envelope-at"></i> Sync Gmail Alerts</button>
                        <button class="btn btn-outline-success" onclick="openImportUrlModal()"><i class="bi bi-link-45deg"></i> Import Job URL</button>
                        <button class="btn btn-warning text-dark" onclick="switchTab('review-tab')"><i class="bi bi-file-earmark-check"></i> Review Resume Drafts</button>
                    </div>
                </div>
            </div>

            <div class="row g-3">
                <div class="col-md-8">
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center py-3">
                            <span><i class="bi bi-star-fill text-warning"></i> High-Match Opportunities</span>
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
                </div>

                <div class="col-md-4">
                    <!-- Activity Feed Card -->
                    <div class="card border-0 shadow-sm mb-4">
                        <div class="card-header bg-white fw-bold py-3">
                            <i class="bi bi-activity text-primary"></i> Recent Activity Feed
                        </div>
                        <div class="card-body p-0" style="max-height: 380px; overflow-y: auto;">
                            <ul class="list-group list-group-flush fs-8" id="activity-feed-list">
                                <li class="list-group-item text-muted text-center py-3">Loading recent events...</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- JOB DISCOVERY PANE (TOP 10 USA PLATFORMS) -->
        <div class="tab-pane fade" id="discovery-pane">
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-white fw-bold py-3">
                    <i class="bi bi-globe-americas text-primary"></i> Top 10 USA Job Platforms Adapter Suite
                </div>
                <div class="card-body">
                    <p class="text-muted small mb-3">Search across Indeed, LinkedIn, Glassdoor, Monster, ZipRecruiter, CareerBuilder, SimplyHired, Dice, Wellfound, and Google Jobs (< 10 jobs per platform, posted in last 14 days).</p>
                    <div class="row row-cols-2 row-cols-md-5 g-2 mb-3" id="top-10-platforms-grid">
                        <!-- Top 10 cards generated dynamically -->
                    </div>
                    <div class="d-flex justify-content-between align-items-center border-top pt-3">
                        <div class="d-flex gap-2 align-items-center">
                            <span class="small fw-bold">Platforms:</span>
                            <span class="badge bg-secondary">Top 10 USA Supported</span>
                        </div>
                        <button class="btn btn-primary" id="btn-find-jobs-now" onclick="runTop10JobSearch()"><i class="bi bi-search"></i> Find Jobs Now</button>
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
                        <table class="table table-hover align-middle mb-0" id="all-jobs-table">
                            <thead class="table-light">
                                <tr>
                                    <th>ID</th>
                                    <th>Status</th>
                                    <th>Score</th>
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

        <!-- RESUME REVIEW & APPROVALS PANE -->
        <div class="tab-pane fade" id="review-pane">
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

        <!-- KANBAN BOARD PANE -->
        <div class="tab-pane fade" id="kanban-pane">
            <div class="row g-3" id="kanban-board-container">
                <!-- Columns loaded dynamically -->
            </div>
        </div>

        <!-- DATABASE EXPLORER PANE -->
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

    const KANBAN_STATUSES = ["Imported", "Analyzed", "Resume draft ready", "Awaiting review", "Approved", "Applied", "Interviewing", "Offer", "Rejected"];
    const TOP_10 = ["indeed", "linkedin", "glassdoor", "monster", "ziprecruiter", "careerbuilder", "simplyhired", "dice", "wellfound", "google_jobs"];

    document.addEventListener("DOMContentLoaded", function() {
        renderTop10PlatformsGrid();
        loadAllData();
        loadCommandsMetadata();
        fetchProfile();
    });

    function renderTop10PlatformsGrid() {
        const grid = document.getElementById('top-10-platforms-grid');
        grid.innerHTML = '';
        TOP_10.forEach(p => {
            grid.innerHTML += `
                <div class="col">
                    <div class="platform-card shadow-sm">
                        <i class="bi bi-check-circle-fill text-success"></i>
                        <div class="fw-bold text-dark fs-8 text-capitalize mt-1">${p.replace('_', ' ')}</div>
                    </div>
                </div>`;
        });
    }

    function loadAllData() {
        fetchStats();
        fetchJobs();
        fetchActivityFeed();
    }

    function switchTab(tabId) {
        const el = document.getElementById(tabId);
        bootstrap.Tab.getInstance(el)?.show() || new bootstrap.Tab(el).show();
    }

    function fetchStats() {
        fetch('/api/stats')
            .then(res => res.json())
            .then(data => {
                document.getElementById('stat-total-jobs').innerText = data.total_jobs || 0;
                document.getElementById('stat-review-count').innerText = data.status_counts['Awaiting review'] || data.status_counts['Imported'] || 0;
                document.getElementById('stat-drafts-count').innerText = data.status_counts['Resume draft ready'] || 0;
                document.getElementById('stat-applied-count').innerText = data.status_counts['Applied'] || data.status_counts['Approved'] || 0;

                // High score table
                const hsBody = document.querySelector('#high-score-table tbody');
                hsBody.innerHTML = '';
                if (!data.high_score_jobs || data.high_score_jobs.length === 0) {
                    hsBody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">No high-score jobs. Click "Find Jobs Now".</td></tr>';
                } else {
                    data.high_score_jobs.slice(0, 8).forEach(j => {
                        hsBody.innerHTML += `
                            <tr>
                                <td><strong>#${j.id}</strong></td>
                                <td><span class="badge bg-success badge-score">${Math.round(j.match_score)}</span></td>
                                <td><strong class="text-primary">${escapeHtml(j.title)}</strong></td>
                                <td>${escapeHtml(j.company)}</td>
                                <td><small class="text-muted">${j.source_platform}</small></td>
                                <td>
                                    <button class="btn btn-xs btn-outline-primary py-0 px-2" onclick="createDraftForJob('${j.id}')">Tailor Draft</button>
                                </td>
                            </tr>`;
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
                populateReviewJobSelect(jobs);
            });
    }

    function renderAllJobsTable(jobs) {
        const tbody = document.querySelector('#all-jobs-table tbody');
        tbody.innerHTML = '';
        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No jobs tracked. Click "Find Jobs Now" or "Import URL".</td></tr>';
            return;
        }
        jobs.forEach(j => {
            const scoreBadge = j.match_score ? `<span class="badge bg-success badge-score">${Math.round(j.match_score)}</span>` : '<span class="badge bg-secondary">-</span>';
            tbody.innerHTML += `
                <tr>
                    <td><strong>#${j.id}</strong></td>
                    <td><span class="badge bg-info text-dark">${j.status}</span></td>
                    <td>${scoreBadge}</td>
                    <td><strong class="text-primary">${escapeHtml(j.title)}</strong></td>
                    <td>${escapeHtml(j.company)}</td>
                    <td><small class="text-muted">${j.source_platform}</small></td>
                    <td>
                        <div class="btn-group btn-group-sm">
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
                const scoreBadge = j.match_score ? `<span class="badge bg-success ms-auto">${Math.round(j.match_score)}</span>` : '';
                cardsHtml += `
                    <div class="kanban-card" onclick="selectForReview('${j.id}')">
                        <div class="d-flex align-items-center mb-1">
                            <strong class="text-dark fs-7">#${j.id}</strong>
                            ${scoreBadge}
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
        fetch('/api/activities')
            .then(res => res.json())
            .then(acts => {
                const list = document.getElementById('activity-feed-list');
                list.innerHTML = '';
                if (!acts || acts.length === 0) {
                    list.innerHTML = '<li class="list-group-item text-muted text-center py-3">No activity logged yet.</li>';
                    return;
                }
                acts.forEach(a => {
                    list.innerHTML += `
                        <li class="list-group-item py-2">
                            <div class="d-flex justify-content-between">
                                <strong class="text-dark">${escapeHtml(a.title)}</strong>
                                <small class="text-muted fs-8">${a.created_at || ''}</small>
                            </div>
                            <small class="text-muted">${escapeHtml(a.description || '')}</small>
                        </li>`;
                });
            });
    }

    function populateReviewJobSelect(jobs) {
        const sel = document.getElementById('review-job-select');
        sel.innerHTML = '<option value="">Select a job from list...</option>';
        (jobs || []).forEach(j => {
            sel.innerHTML += `<option value="${j.id}">#${j.id}: ${escapeHtml(j.title)} at ${escapeHtml(j.company)} (${j.status})</option>`;
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
            });
    }

    function createDraftForJob(jobId) {
        fetch('/api/draft/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(jobId)})
        })
        .then(res => res.json())
        .then(data => {
            alert('✅ Resume Draft Created! Opening Review screen...');
            selectForReview(jobId);
            loadAllData();
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
        fetch('/api/draft/approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(currentReviewJobId)})
        })
        .then(res => res.json())
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('approveDraftModal'))?.hide();
            alert('✅ Resume Approved & Finalized! Saved to jobapplied folder:\n\n' + data.final_resume_path);
            loadJobForReview(currentReviewJobId);
            loadAllData();
        });
    }

    function rejectDraftForSelectedJob() {
        if (!currentReviewJobId) return;
        if (!confirm('Reject draft and revert job status?')) return;
        fetch('/api/draft/reject', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({job_id: parseInt(currentReviewJobId)})
        })
        .then(res => res.json())
        .then(data => {
            alert('Draft rejected.');
            loadJobForReview(currentReviewJobId);
            loadAllData();
        });
    }

    function runTop10JobSearch() {
        const btn = document.getElementById('btn-find-jobs-now');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Searching Top 10 Platforms...';

        fetch('/api/jobs/find', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({platforms: TOP_10})
        })
        .then(res => res.json())
        .then(data => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-search"></i> Find Jobs Now';
            alert(`✅ Platform Search Complete!\n\nDiscovered ${data.jobs_recorded} jobs across platforms.`);
            loadAllData();
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-search"></i> Find Jobs Now';
            alert('Search encountered an error: ' + err);
        });
    }

    function openImportUrlModal() {
        const modal = new bootstrap.Modal(document.getElementById('importUrlModal'));
        modal.show();
    }

    function runAutomatedUrlImport() {
        const url = document.getElementById('import-url-input').value;
        if (!url) return;

        fetch('/api/jobs/import-url', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        })
        .then(res => res.json())
        .then(data => {
            bootstrap.Modal.getInstance(document.getElementById('importUrlModal'))?.hide();
            alert(`✅ Job Imported Successfully!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nMatch Score: ${data.score}/100`);
            loadAllData();
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
            if (data.status === 'success') loadAllData();
        });
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
        };

        fetch('/api/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            alert('✅ Profile saved to config.yaml!');
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
        switchTab('cheatsheet-tab');
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
                    payload = {
                        "total_jobs": summary["total_jobs"],
                        "status_counts": summary["status_counts"],
                        "high_score_jobs": high_scores,
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

                    payload = {
                        "job_id": j.id,
                        "title": j.title,
                        "company": j.company,
                        "master_resume_path": master_path,
                        "draft_resume_path": j.draft_resume_path or "",
                        "final_resume_path": j.final_resume_path or j.tailored_resume_path or "",
                        "approval_status": j.approval_status or "Not created",
                        "diff_summary": j.diff_summary or "No draft generated yet.",
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))
                finally:
                    session.close()

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
                payload = {
                    "target_titles": profile.target_titles,
                    "required_skills": profile.required_skills,
                    "preferred_skills": profile.preferred_skills,
                    "years_experience": profile.years_experience,
                    "locations": profile.locations,
                    "salary_min": profile.salary_min,
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
                platforms = data.get("platforms") or TOP_10_PLATFORMS

                settings = get_settings()
                profile = load_candidate_profile()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    results = search_and_import_jobs(session, profile, platforms=platforms, limit_per_platform=9)
                    payload = {"status": "success", "jobs_recorded": len(results)}
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
                    excluded_companies=current_p.excluded_companies,
                    excluded_titles=current_p.excluded_titles,
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

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default HTTP logging noise


def start_web_dashboard_server(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    """Start local web console and HTTP capture server on localhost."""
    server = HTTPServer((host, port), WebConsoleRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Local Web Console running on http://%s:%d/", host, port)
    return server
