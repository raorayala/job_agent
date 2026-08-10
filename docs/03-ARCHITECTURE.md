# 03 — Architecture

## 1. System context

```text
┌─────────────────┐     OAuth readonly      ┌──────────────┐
│  Job seeker PC  │ ◄─────────────────────► │  Gmail API   │
│  (job-agent)    │                         └──────────────┘
│                 │
│  config.yaml    │
│  .env           │     write artifacts     ┌──────────────────────┐
│  SQLite DB      │ ──────────────────────► │ Desktop/Jobs Applied │
│  CLI + Web      │                         └──────────────────────┘
│  Console :8000  │
└────────┬────────┘
         │ optional
         ▼
   Local Ollama / LLM API
```

The agent is a **single-user desktop tool**. The Web Console is an embedded local HTTP server (`ThreadingHTTPServer` on `127.0.0.1:8000`) — not Streamlit, not a cloud multi-tenant backend.

## 2. Logical pipeline

```text
Discovery (platform fetch / Gmail / URL import / bookmarklet)
    → job_normalizer (URL/text normalize + dedupe signals)
    → matcher (explainable score vs CandidateProfile + resume facts)
    → job_analysis (batch re-score after platform search)
    → application_tracker / database (persist Jobs Applied)
    → resume_tailor + document_exporter (truthful DOCX under Desktop)
    → Web Console or CLI (human review, mark-applied --confirm)
```

Gmail-specific path:

```text
Gmail messages
    → gmail_client (auth, list, fetch, incremental IDs)
    → email_parser (platform-aware extraction)
    → (joins main pipeline at job_normalizer)
```

## 3. Package layout

```text
job-search-agent/
├── pyproject.toml              # packaging, deps, entry point
├── config.yaml                 # platforms + candidate profile
├── .env.example                # documented env vars
├── docs/                       # this documentation set
├── src/job_agent/
│   ├── __main__.py             # python -m job_agent
│   ├── cli.py                  # Typer commands
│   ├── config.py               # Settings + profile loading
│   ├── models.py               # Domain dataclasses / enums
│   ├── database.py             # SQLAlchemy models + session
│   ├── logging_config.py
│   ├── gmail_client.py
│   ├── email_parser.py
│   ├── job_normalizer.py
│   ├── matcher.py
│   ├── resume_tailor.py
│   ├── resume_parser.py        # Master-resume DOCX text extraction
│   ├── document_exporter.py
│   ├── application_tracker.py
│   ├── platform_fetcher.py     # Top 10 platform adapters + URL import
│   ├── browser_capture.py      # HTTP server + bookmarklet endpoint
│   ├── web_dashboard.py        # Web Console UI + API handlers
│   ├── system_health.py        # Dashboard health panel + onboarding
│   ├── demo_data.py            # seed-demo sample jobs
│   ├── job_analysis.py         # Batch re-analyze after search
│   ├── backup_service.py       # Backup/restore/purge
│   ├── cleanup_service.py      # Duplicate/stale cleanup + full purge
│   ├── contact_service.py
│   ├── interview_service.py
│   ├── answer_service.py
│   ├── report_service.py
│   ├── notification_service.py
│   └── services/               # higher-level orchestration (future)
├── tests/
├── data/                       # local DB (gitignored contents)
├── templates/                  # optional templates
└── scripts/                    # dev_setup.ps1, purge_database.py, etc.
```

## 4. Component responsibilities

| Component | Responsibility |
|-----------|----------------|
| `config` | Load `.env`, YAML, resolve paths, build `CandidateProfile` / `Settings` |
| `database` | SQLite engine, `JobRecord` with B-Tree indexes, `ProcessedEmail`, `ActivityLogRecord`, queries |
| `gmail_client` | OAuth token lifecycle, message list/get, body extraction |
| `email_parser` | HTML/text → `ParsedJob` list (multi-job digests) |
| `job_normalizer` | Canonical URL/company/title/location helpers, LRU cached similarity |
| `matcher` | Weighted scoring + `MatchExplanation`, Flyweight compiled regex caching |
| `resume_tailor` | Fact-preserving ATS DOCX draft & cover letter generation |
| `document_exporter` | Folder/filename conventions |
| `application_tracker` | Status transitions, explicit approval gate |
| `platform_fetcher` | Direct search adapters for top 10 USA platforms; URL auto-import; per-platform reports |
| `browser_capture` | ThreadingHTTPServer on `:8000`, CORS, bookmarklet POST `/capture` |
| `web_dashboard` | Web Console HTML/JS, Kanban, Database Explorer, progress bar, CLI runner, REST API |
| `system_health` | DB/Gmail/resume readiness, onboarding checklist for dashboard |
| `demo_data` | Insert sample jobs for smoke testing (`seed-demo`) |
| `job_analysis` | Batch re-score all jobs; auto-triggered after platform search |
| `cli` | User-facing commands and Rich output |

## 5. Technology choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python 3.11+ | Typing, ecosystem, user constraint |
| CLI | Typer + Rich | Fast UX, typed options |
| DB | SQLite + SQLAlchemy 2 | Local, zero ops, B-Tree indexes |
| Email | Gmail API + google-auth-oauthlib | Official, readonly scope |
| HTML | BeautifulSoup + lxml | Robust malformed HTML handling |
| Resume | python-docx | DOCX read/write without Office COM |
| Config | YAML + python-dotenv | Human-editable profile + secrets split |
| UI | Embedded Web Console (ThreadingHTTPServer) | Private local HTTP on `localhost:8000` |
| Optional LLM | Ollama / local models | Local-first cost control |

## 6. Software Design Patterns Implemented

1. **Flyweight Pattern**:
   - `functools.lru_cache` memoizes compiled regular expressions and string distance ratios.
2. **Strategy & Adapter Pattern**:
   - Modular platform search adapters behind uniform interface in `platform_fetcher.py`.
3. **Repository & Data Mapper Pattern**:
   - Abstracts database queries and utilizes composite B-Tree indexes.
4. **Lazy Loading / Deferred Execution**:
   - Deferred master resume DOCX text extraction and draft document creation.
5. **Factory & Singleton Connection**:
   - Centralized database engine and settings initialization.

## 7. Configuration layers

1. **Committed defaults:** `config.yaml` (platforms, profile template, weights)
2. **Local secrets/paths:** `.env` (resume path, OAuth paths, DB path, LLM)
3. **Runtime OAuth artifacts:** `credentials.json`, `token.json`
4. **Derived state:** `data/jobs.db`, Desktop exports

## 8. Trust boundaries

| Boundary | Rule |
|----------|------|
| Network → Gmail | Only via official API with user consent |
| Network → job platforms | Read-only HTML fetch for recommended platforms; experimental may fail |
| Network → LLM | Optional; disabled by default |
| Disk → git | Secrets, DB, tokens, personal resumes ignored |
| CLI → Applied status | Requires explicit `--confirm` |
| Web Console | Binds to `127.0.0.1` only |

## 9. Extensibility points

- Add platforms in `config.yaml` (`sender_domains`, `link_patterns`) and `platform_fetcher.py`
- Swap matcher backend (rule → hybrid LLM) behind `score_job()`
- Add exporters (PDF) via optional `pdf` extra
- Add orchestration in `services/` without changing CLI surface

## 10. Deployment topology (v1)

Single machine:

- Developer / job-seeker workstation (Windows supported; POSIX-compatible paths via `pathlib`)
- No containers required for v1 (optional later)
- Optional Windows Task Scheduler for periodic `sync-gmail` + `analyze`

See [12 — Web Console API](12-WEB-CONSOLE-API.md) for HTTP endpoints.
