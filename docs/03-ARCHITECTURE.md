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
│  CLI / optional │                         └──────────────────────┘
│  Streamlit      │
└────────┬────────┘
         │ optional
         ▼
   Local Ollama / LLM API
```

The agent is a **single-user desktop tool**. There is no application server and no multi-tenant backend in v1.

## 2. Logical pipeline

```text
Gmail messages
    → gmail_client (auth, list, fetch, incremental IDs)
    → email_parser (platform-aware extraction)
    → job_normalizer (URL/text normalize + dedupe signals)
    → matcher (explainable score vs CandidateProfile + resume facts)
    → application_tracker / database (persist Jobs Applied)
    → resume_tailor + document_exporter (truthful DOCX under Desktop)
    → CLI (human review, mark-applied --confirm)
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
│   ├── document_exporter.py
│   ├── application_tracker.py
│   └── services/               # higher-level orchestration (future)
├── tests/
├── data/                       # local DB (gitignored contents)
├── templates/                  # optional templates
└── scripts/                    # e.g. dev_setup.ps1
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
| `web_dashboard` | Web Application Console, Kanban board, Database Explorer, progress bar, CLI runner |
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
| UI | Embedded Web Console | Private local HTTP server on `localhost:8000` |
| Optional LLM | Ollama / local models | Local-first cost control |

## 6. Software Design Patterns Implemented

1. **Flyweight Pattern**:
   - `functools.lru_cache` memoizes compiled regular expressions (`_compile_word_pattern`, `_get_skill_regex`) and string distance ratios (`calculate_similarity`).
2. **Strategy & Adapter Pattern**:
   - Modular platform search adapters (`fetch_dice_jobs`, `fetch_ziprecruiter_jobs`, `import_job_from_url`) behind uniform interface.
3. **Repository & Data Mapper Pattern**:
   - Abracts database queries and utilizes composite B-Tree indexes (`ix_jobs_company_title_norm`, `ix_jobs_status_score`, `ix_jobs_date_discovered`, `ix_jobs_gmail_msg_id`).
4. **Lazy Loading / Deferred Execution**:
   - Deferred master resume DOCX text extraction and draft document creation.
5. **Factory & Singleton Connection**:
   - Centralized database engine and settings initialization.

## 6. Configuration layers

1. **Committed defaults:** `config.yaml` (platforms, profile template, weights)
2. **Local secrets/paths:** `.env` (resume path, OAuth paths, DB path, LLM)
3. **Runtime OAuth artifacts:** `credentials.json`, `token.json`
4. **Derived state:** `data/jobs.db`, Desktop exports

## 7. Trust boundaries

| Boundary | Rule |
|----------|------|
| Network → Gmail | Only via official API with user consent |
| Network → LLM | Optional; disabled by default |
| Disk → git | Secrets, DB, tokens, personal resumes ignored |
| CLI → Applied status | Requires explicit `--confirm` |

## 8. Extensibility points

- Add platforms in `config.yaml` (`sender_domains`, `link_patterns`)
- Swap matcher backend (rule → hybrid LLM) behind `score_job()`
- Add exporters (PDF) via optional `pdf` extra
- Add orchestration in `services/` without changing CLI surface

## 9. Deployment topology (v1)

Single machine:

- Developer / job-seeker workstation (Windows supported; POSIX-compatible paths via `pathlib`)
- No containers required for v1 (optional later)
- Optional Windows Task Scheduler for periodic `sync-gmail` + `analyze`
