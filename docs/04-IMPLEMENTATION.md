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
| 2 | Master-resume ingestion + stronger profile validation | Planned |
| 3 | Gmail OAuth + incremental sync | Planned (module stubbed) |
| 4 | Email/job extraction | Planned (module stubbed) |
| 5 | Duplicate detection beyond URL normalize helpers | Planned (helpers started) |
| 6 | Rule-based explainable matching | Planned (module stubbed) |
| 7 | Resume tailoring + Desktop export paths | Planned (exporter helpers done) |
| 8 | Test polish + optional Streamlit dashboard | Planned |

## 3. What Milestone 1 delivers

### 3.1 Packaging

- `pyproject.toml` with setuptools `src/` layout
- Optional extras: `dev`, `dashboard`, `pdf`
- Editable install: `pip install -e ".[dev]"`

### 3.2 Configuration (`config.py`)

- `Settings` dataclass from environment
- `CandidateProfile` from `config.yaml` → `profile`
- `load_candidate_profile()`, `get_settings()`, `ensure_runtime_dirs()`
- Env overrides for `MASTER_RESUME_PATH`, DB path, Gmail paths, LLM, log level

### 3.3 Domain models (`models.py`)

- `ApplicationStatus` enum (full status set)
- `Recommendation` enum
- `CandidateProfile`, `ParsedJob`, `MatchExplanation`, `DuplicateCheckResult`

### 3.4 Database (`database.py`)

- SQLAlchemy models: `JobRecord`, `ProcessedEmail`
- `init_db()`, `list_jobs()`, `get_job()`, email processed helpers
- Unique constraints on normalized URL and Gmail message ID

### 3.5 Application tracker (`application_tracker.py`)

- `list_tracked_jobs()`
- `update_status()` / `mark_applied()` with **Applied confirmation gate**

### 3.6 Document path helpers (`document_exporter.py`)

- `safe_filename()`, `application_folder()`, `resume_filename()`

### 3.7 Normalizer helpers (`job_normalizer.py`)

- `normalize_url()`, `normalize_company()`, `normalize_text()`

### 3.8 CLI (`cli.py`)

Working: `setup`, `profile`, `jobs`, `statuses`, `mark-applied`  
Stubbed with clear exit: `sync-gmail`, `analyze`, `tailor`, `dashboard`

### 3.9 Tests

- `tests/test_config.py`
- `tests/test_database.py`
- `tests/test_application_tracker.py`
- `tests/test_job_normalizer.py`
- `tests/test_document_exporter.py`

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
