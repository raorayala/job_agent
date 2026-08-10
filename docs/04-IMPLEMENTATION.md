# 04 — Implementation Details

## 1. Version and branch

| Item | Value |
|------|-------|
| Package | `job-agent` `0.1.0` |
| Entry points | `python -m job_agent`, console script `job-agent` |
| Remote | https://github.com/raorayala/job_agent.git |
| Feature branch | `cursor/initial-gmail-job-agent-scaffold` |

## 2. Milestone implementation status

| Milestone | Scope | Status |
|-----------|-------|--------|
| 1 | Packaging, config, SQLite schema, CLI | **Complete** |
| 2 | Master-resume DOCX text extraction (`resume_parser.py`) | **Complete** |
| 3 | Gmail OAuth + incremental sync (`gmail_client.py`) | **Complete** |
| 4 | Email digest / multi-job extraction (`email_parser.py`) | **Complete** |
| 5 | Multi-tier duplicate detection + schema migration (`job_normalizer.py`, `database.py`) | **Complete** |
| 6 | Weighted 0–100 explainable matching algorithm (`matcher.py`) | **Complete** |
| 7 | Truthful ATS resume & cover letter tailoring + Desktop export (`resume_tailor.py`) | **Complete** |
| 8 | Platform fetch, Web Console, bookmarklet, contacts, answers, backup, test suite | **Complete** |

All Milestones 1–8 are **complete**. No remaining "Planned" or "Streamlit" work items.

## 3. Implemented Modules Overview

### 3.1 Platform Fetcher (`platform_fetcher.py`)
- Direct search against top 10 USA platforms via public HTML & JSON-LD schema parsing.
- **Default limit**: 3 jobs per platform (`DEFAULT_LIMIT_PER_PLATFORM`); max 9 via `--limit`.
- **Recommended platforms**: dice, ziprecruiter, indeed (most reliable).
- **Experimental platforms**: linkedin, glassdoor, monster, etc. (may return 0 when sites block bots).
- Filters for postings within the **last 14 days**.
- Returns per-platform search reports (success/empty/error) consumed by CLI and Web Console.

### 3.2 Local Capture Server & Web Console (`browser_capture.py`, `web_dashboard.py`)
- `ThreadingHTTPServer` on `http://localhost:8000/` (not Streamlit).
- CORS preflight and JSON POST payload handling for 1-click Chrome bookmarklet capture (`/capture`).
- Full Web Console: Dashboard, Job Discovery, Resume Review, Kanban, Database Explorer, Profile Editor, CLI runner.
- REST API endpoints documented in [12 — Web Console API](12-WEB-CONSOLE-API.md).

### 3.3 System Health (`system_health.py`)
- Dashboard health panel: database path, Gmail OAuth status, master resume status.
- Onboarding checklist (profile, resume, Gmail, bookmarklet, first search).

### 3.4 Demo Data (`demo_data.py`)
- `seed-demo` CLI command and **Load Demo Jobs** web button.
- Inserts 3 sample jobs for smoke testing without network.

### 3.5 Job Analysis (`job_analysis.py`)
- Batch re-score all stored jobs against profile and master resume.
- Auto-triggered after successful platform search from Web Console.

### 3.6 CLI & Web Application Console (`cli.py`, `web_dashboard.py`)
- **`web`**: Launches Web Application Console at `http://localhost:8000/`.
- **`search-links`**: Generates query links for top 10 USA platforms with 14-day freshness filters.
- **`fetch-jobs`**: Directly fetches platform listings (default 3 per platform, max 9).
- **`seed-demo`**: Insert sample jobs for testing.
- Full suite of commands: `serve`, `web`, `search-links`, `fetch-jobs`, `seed-demo`, `sync-gmail`, `analyze`, `jobs`, `tailor`, `approve-draft`, `reject-draft`, `mark-applied`, `add-contact`, `contacts`, `add-interview`, `prepare-interview`, `answers`, `add-answer`, `suggest-answer`, `dashboard`, `follow-ups`, `report`, `backup`, `restore`, `delete-job`, `purge-data`, `cleanup`.

## 4. Coding standards & SOLID Principles

| Practice | Convention |
|----------|------------|
| Types | 100% Type hints on public functions and domain dataclasses |
| Style | Python 3.11+, Google/Sphinx-style docstrings on public modules and functions |
| Logging | `logging_config.setup_logging()` + structured Python `logger.info` for HTTP requests |
| SOLID | Single Responsibility, Open/Closed adapters, Interface Segregation, Dependency Inversion |
| Optimization | Flyweight LRU caching for regex and similarity; B-Tree SQLite indexes |
| Tests | pytest (**53 passing** unit/integration tests) |
| Secrets | Never hardcode; never commit `.env`, `credentials.json`, or `token.json` |

## 5. Key algorithms (implemented)

### Duplicate detection

1. Exact / normalized URL match  
2. Normalized `(company, title, location)` match  
3. Similarity threshold from `config.yaml` → `duplicate.*`  
4. Warn user; set `is_duplicate`, `duplicate_of_id`, `duplicate_reason`

### Match scoring

Weighted sum (defaults in `config.yaml` → `match_weights`):

| Factor | Default weight |
|--------|----------------|
| Required skills | 30 |
| Preferred skills | 15 |
| Title similarity | 20 |
| Experience alignment | 10 |
| Location / work mode | 15 |
| Salary compatibility | 10 |

Exclusions force recommendation `Excluded` regardless of partial score.

Recommendation bands: Strong match (≥80), Worth reviewing (65–79), Low match (<65), Excluded.

### Resume tailoring

1. Load master DOCX  
2. Identify overlapping keywords already present in resume/profile  
3. Emphasize existing bullets / summary language  
4. **Reject** invented employers, dates, certifications  
5. Write draft to `_drafts/`; promote to Desktop path only after explicit approval  

## 6. Dependencies (runtime)

See `pyproject.toml`:

- Google API client + oauthlib  
- python-dotenv, PyYAML  
- BeautifulSoup4, lxml  
- python-docx  
- SQLAlchemy  
- Typer, Rich  

## 7. How to extend a module

Example: add a new platform adapter

1. Add fetch function in `platform_fetcher.py` behind the uniform adapter interface
2. Register platform name in `TOP_10_PLATFORMS` and tier (recommended/experimental)
3. Add unit tests with mocked HTML responses
4. Wire into `search_and_import_jobs()` and Web Console platform checkboxes
5. Document in [12 — Web Console API](12-WEB-CONSOLE-API.md)

## 8. Maintenance scripts

| Script | Purpose |
|--------|---------|
| `scripts/purge_database.py --confirm` | Wipe all 6 SQLite tables (alternative to `purge-data --confirm`) |
| `scripts/dev_setup.ps1` | Fresh venv install helper |
| `scripts/daily_sync_job_agent.bat` | Scheduled Gmail sync + analyze |
