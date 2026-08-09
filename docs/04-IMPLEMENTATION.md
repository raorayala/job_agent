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
| 8 | Direct platform fetch, local capture server, contacts, answers, backup, test suite | **Complete** |

## 3. Implemented Modules Overview

### 3.1 Platform Fetcher (`platform_fetcher.py`)
- Direct search against Dice and ZipRecruiter via public HTML & JSON-LD schema parsing.
- Enforces batch limits (**< 10 jobs per run**, default: `limit=9`).
- Filters for postings within the **last 1 to 2 weeks** (`postedDate=14`, `days=14`).

### 3.2 Local Capture Server (`browser_capture.py`)
- Lightweight HTTP server running on `http://localhost:8000`.
- CORS preflight and JSON POST payload handling for 1-click Chrome bookmarklet capture.

### 3.3 CLI Enhancements (`cli.py`)
- **`search-links`**: Generates query links with 1-2 week freshness filters; `--open` flag explicitly launches Google Chrome on Windows (`_open_in_browser`).
- **`fetch-jobs`**: Fetches direct platform listings with `--limit 9` (<10 jobs) and 14-day freshness.
- Full suite of commands: `serve`, `search-links`, `fetch-jobs`, `sync-gmail`, `analyze`, `jobs`, `tailor`, `mark-applied`, `add-contact`, `contacts`, `add-interview`, `prepare-interview`, `answers`, `add-answer`, `suggest-answer`, `dashboard`, `follow-ups`, `report`, `backup`, `restore`, `delete-job`, `purge-data`.

## 4. Coding standards

| Practice | Convention |
|----------|------------|
| Types | Type hints on public functions |
| Style | Python 3.11+, dataclasses with `slots` where used |
| Logging | `logging_config.setup_logging()` + module loggers |
| Errors | Specific exceptions (`LookupError`, `PermissionError`, `NotImplementedError` for stubs) |
| Tests | pytest; temp DB paths via `tmp_path` |
| Secrets | Never hardcode; never commit `.env` / tokens |

## 5. Key algorithms (planned / partial)

### Duplicate detection (planned full; URL helpers exist)

1. Exact / normalized URL match  
2. Normalized `(company, title, location)` match  
3. Similarity threshold from `config.yaml` → `duplicate.*`  
4. Warn user; set `is_duplicate`, `duplicate_of_id`, `duplicate_reason`

### Match scoring (planned)

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

### Resume tailoring (planned)

1. Load master DOCX  
2. Identify overlapping keywords already present in resume/profile  
3. Emphasize existing bullets / summary language  
4. **Reject** invented employers, dates, certifications  
5. Write under Desktop path convention  

## 6. Dependencies (runtime)

See `pyproject.toml`:

- Google API client + oauthlib  
- python-dotenv, PyYAML  
- BeautifulSoup4, lxml  
- python-docx  
- SQLAlchemy  
- Typer, Rich  

## 7. How to extend a module

Example: implement matcher

1. Replace `NotImplementedError` in `matcher.score_job`
2. Return `MatchExplanation` with factor breakdown
3. Add unit tests with fixed `ParsedJob` + `CandidateProfile`
4. Wire CLI `analyze` to load jobs, score, persist fields
5. Keep LLM behind a provider interface; default to rules

## 8. Known implementation gaps

- Gmail client not yet ported from early scaffold into new package (intentionally stubbed for Milestone order)
- No resume text extraction yet
- No Streamlit app yet
- Unique constraint on `gmail_message_id` assumes one job record per message; multi-job emails may need a composite or child table in Milestone 4
