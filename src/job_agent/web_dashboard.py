"""Web application dashboard and interactive CLI command execution server for Job Search Agent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from job_agent.application_tracker import list_tracked_jobs, mark_applied, record_parsed_job
from job_agent.backup_service import create_backup
from job_agent.config import get_settings, load_candidate_profile
from job_agent.database import JobRecord, get_job, init_db, list_jobs
from job_agent.logging_config import get_logger
from job_agent.models import ParsedJob
from job_agent.report_service import generate_pipeline_summary, generate_report

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
        "category": "Contacts & Networking",
        "commands": [
            {
                "id": "add-contact",
                "name": "add-contact",
                "cmd": "add-contact",
                "description": "Store recruiter, referral, or hiring manager contact locally.",
                "params": [
                    {"name": "name", "flag": "positional", "type": "text", "default": "", "label": "Contact Name (required)", "required": True},
                    {"name": "email", "flag": "--email", "type": "text", "default": "", "label": "Email Address"},
                    {"name": "role", "flag": "--role", "type": "text", "default": "", "label": "Role / Title"},
                    {"name": "company", "flag": "--company", "type": "text", "default": "", "label": "Company"},
                    {"name": "job_id", "flag": "--job-id", "type": "number", "default": "", "label": "Linked Job ID"}
                ]
            },
            {
                "id": "contacts",
                "name": "contacts",
                "cmd": "contacts",
                "description": "List all locally stored networking contacts.",
                "params": []
            }
        ]
    },
    {
        "category": "Interview Tracking & Prep",
        "commands": [
            {
                "id": "add-interview",
                "name": "add-interview",
                "cmd": "add-interview",
                "description": "Record an upcoming interview schedule and participants.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "interview_date", "flag": "positional", "type": "text", "default": "", "label": "Date (YYYY-MM-DD HH:MM)", "required": True},
                    {"name": "type", "flag": "--type", "type": "text", "default": "Technical", "label": "Interview Type"},
                    {"name": "interviewer", "flag": "--interviewer", "type": "text", "default": "", "label": "Interviewer / Participants"},
                    {"name": "notes", "flag": "--notes", "type": "text", "default": "", "label": "Notes"}
                ]
            },
            {
                "id": "prepare-interview",
                "name": "prepare-interview",
                "cmd": "prepare-interview",
                "description": "Generate local truthful interview preparation DOCX guide.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "dry_run", "flag": "--dry-run", "type": "bool", "default": False, "label": "Dry Run mode"}
                ]
            }
        ]
    },
    {
        "category": "Application Answer Library",
        "commands": [
            {
                "id": "answers",
                "name": "answers",
                "cmd": "answers",
                "description": "List saved reusable application question & answer pairs.",
                "params": [
                    {"name": "tag", "flag": "--tag", "type": "text", "default": "", "label": "Filter by Tag"}
                ]
            },
            {
                "id": "add-answer",
                "name": "add-answer",
                "cmd": "add-answer",
                "description": "Save an approved application answer to local library.",
                "params": [
                    {"name": "question", "flag": "--question", "type": "text", "default": "", "label": "Question (required)", "required": True},
                    {"name": "answer", "flag": "--answer", "type": "text", "default": "", "label": "Answer (required)", "required": True},
                    {"name": "tags", "flag": "--tags", "type": "text", "default": "", "label": "Tags (comma separated)"}
                ]
            },
            {
                "id": "suggest-answer",
                "name": "suggest-answer",
                "cmd": "suggest-answer",
                "description": "Draft answer suggestion for a job question using local resume & profile.",
                "params": [
                    {"name": "job_id", "flag": "positional", "type": "number", "default": "", "label": "Job ID (required)", "required": True},
                    {"name": "question", "flag": "positional", "type": "text", "default": "", "label": "Question text (required)", "required": True}
                ]
            }
        ]
    },
    {
        "category": "Maintenance & Data Security",
        "commands": [
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

    cmd = [sys.executable, "-m", "job_agent", cmd_name] + raw_args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
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
    <title>Job Search Agent — Web Console & CLI Cheat Sheet</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        :root {
            --bg-main: #f8f9fa;
            --sidebar-bg: #1e293b;
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
        .command-card {
            border: 1px solid var(--card-border);
            border-radius: 10px;
            background: #ffffff;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .command-card:hover {
            box-shadow: 0 6px 12px -2px rgba(0, 0, 0, 0.08);
        }
        .terminal-box {
            background-color: #0f172a;
            color: #38bdf8;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.9rem;
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
        <small class="text-light-50">Local-first Private Assistant & Interactive CLI Executor</small>
    </div>
    <div>
        <span class="badge bg-success me-2"><i class="bi bi-shield-check"></i> Local-First (100% Private)</span>
        <button class="btn btn-sm btn-outline-light" onclick="loadAllData()"><i class="bi bi-arrow-clockwise"></i> Refresh</button>
    </div>
</header>

<div class="container-fluid px-4 py-3">
    <!-- Navigation Tabs -->
    <ul class="nav nav-tabs mb-4" id="mainTabs" role="tablist">
        <li class="nav-item">
            <button class="nav-link active" id="dashboard-tab" data-bs-toggle="tab" data-bs-target="#dashboard-pane"><i class="bi bi-speedometer2"></i> Dashboard</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="cheatsheet-tab" data-bs-toggle="tab" data-bs-target="#cheatsheet-pane"><i class="bi bi-terminal"></i> CLI Command Cheat Sheet & Runner</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="jobs-tab" data-bs-toggle="tab" data-bs-target="#jobs-pane"><i class="bi bi-briefcase"></i> Tracked Jobs Explorer</button>
        </li>
        <li class="nav-item">
            <button class="nav-link" id="bookmarklet-tab" data-bs-toggle="tab" data-bs-target="#bookmarklet-pane"><i class="bi bi-bookmark-star"></i> 1-Click Bookmarklet</button>
        </li>
    </ul>

    <div class="tab-content" id="mainTabsContent">
        
        <!-- DASHBOARD PANE -->
        <div class="tab-pane fade show active" id="dashboard-pane">
            <div class="row g-3 mb-4" id="stats-cards-container">
                <!-- Stats loaded dynamically -->
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
                        <div class="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
                            <span><i class="bi bi-star-fill text-warning"></i> High-Score Saved Opportunities</span>
                            <button class="btn btn-sm btn-outline-primary" onclick="triggerQuickCommand('analyze', [])">Run Match Analyzer</button>
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
                        <div class="card-header bg-white fw-bold">
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

        <!-- BOOKMARKLET PANE -->
        <div class="tab-pane fade" id="bookmarklet-pane">
            <div class="card border-0 shadow-sm max-w-700 mx-auto">
                <div class="card-header bg-white fw-bold">
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

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    let metadataCommands = [];

    document.addEventListener("DOMContentLoaded", function() {
        loadAllData();
        loadCommandsMetadata();
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
                                <td>${escapeHtml(j.title)}</td>
                                <td>${escapeHtml(j.company)}</td>
                                <td><small class="text-muted">${j.source_platform}</small></td>
                                <td>
                                    <button class="btn btn-xs btn-outline-primary py-0 px-2" onclick="triggerQuickCommand('tailor', ['${j.id}'])">Tailor DOCX</button>
                                </td>
                            </tr>
                        `;
                    });
                }
            })
            .catch(err => console.error("Error fetching stats:", err));
    }

    function fetchJobs() {
        fetch('/api/jobs')
            .then(res => res.json())
            .then(jobs => {
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
                            <td>${escapeHtml(j.title)}</td>
                            <td>${escapeHtml(j.company)}</td>
                            <td><small class="text-muted">${j.source_platform}</small></td>
                            <td>${j.is_duplicate ? '<span class="text-danger">Yes</span>' : ''}</td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-primary" title="Tailor Resume & Cover Letter" onclick="triggerQuickCommand('tailor', ['${j.id}'])"><i class="bi bi-file-earmark-word"></i> Tailor</button>
                                    <button class="btn btn-outline-success" title="Mark Applied" onclick="triggerQuickCommand('mark-applied', ['${j.id}', '--confirm'])"><i class="bi bi-check-circle"></i> Applied</button>
                                    <button class="btn btn-outline-secondary" title="Suggest Answer" onclick="promptSuggestAnswer('${j.id}')"><i class="bi bi-chat-quote"></i> Q&A</button>
                                </div>
                            </td>
                        </tr>
                    `;
                });
            })
            .catch(err => console.error("Error fetching jobs:", err));
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
        // Switch to cheatsheet tab to view terminal
        const tabEl = document.getElementById('cheatsheet-tab');
        bootstrap.Tab.getInstance(tabEl)?.show() || new bootstrap.Tab(tabEl).show();
        executeCommandOnServer(cmd, args);
    }

    function promptSuggestAnswer(jobId) {
        const q = prompt("Enter the application question to draft an answer for:");
        if (q && q.trim()) {
            triggerQuickCommand('suggest-answer', [jobId, q.trim()]);
        }
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
            loadAllData(); // Refresh UI metrics and job rows
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
        try:
            if url_path in ("/", "/dashboard", "/cheat-sheet", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(HTML_APP_TEMPLATE.encode("utf-8"))

            elif url_path == "/api/stats":
                settings = get_settings()
                SessionLocal = init_db(settings.database_path)
                session = SessionLocal()
                try:
                    summary = generate_pipeline_summary(session)
                    # Convert objects to lightweight dicts
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
                    jobs = list_jobs(session, limit=100)
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
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

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
