# Job Search Agent

Local-first Python agent that monitors Gmail job alerts, scores opportunities against your career profile, helps tailor truthful ATS resumes, and tracks applications in SQLite — without ever submitting applications for you.

## Full documentation

See the **[docs/](docs/README.md)** folder for the complete project document set:

| Doc | Topic |
|-----|-------|
| [Requirements](docs/01-REQUIREMENTS.md) | Goals, scope, functional requirements |
| [Design](docs/02-DESIGN-SPECIFICATION.md) | UX flows, CLI contracts, safeguards |
| [Architecture](docs/03-ARCHITECTURE.md) | Components and data flow |
| [Implementation](docs/04-IMPLEMENTATION.md) | Module status and coding details |
| [Data model](docs/05-DATA-MODEL.md) | SQLite schema and config fields |
| [Security](docs/06-SECURITY-PRIVACY.md) | OAuth, secrets, privacy |
| [Testing](docs/07-TESTING.md) | Test strategy |
| [Operations](docs/08-OPERATIONS-DEPLOYMENT.md) | Local production install & ops |
| [Roadmap](docs/09-ROADMAP.md) | Milestones and future work |
| [User guide](docs/10-USER-GUIDE.md) | Day-to-day usage |

## MVP architecture

```
Gmail (OAuth readonly) → email parser → normalizer/dedupe
        ↓
 rule-based matcher (+ optional LLM later)
        ↓
 SQLite tracker ← CLI (approval required for Applied)
        ↓
 Desktop/Jobs Applied/<Company>/<Job Title>/
```

| Layer | Responsibility |
|-------|----------------|
| `config.yaml` + `.env` | Candidate profile, platforms, secrets |
| `database.py` | SQLite jobs + processed Gmail IDs |
| `gmail_client.py` | Read-only OAuth sync (incremental) |
| `matcher.py` | Explainable 0–100 scoring |
| `resume_tailor.py` | Factual keyword emphasis only |
| `cli.py` | Human-in-the-loop commands |

**Design rules:** data stays local; LLM is optional; Applied status needs `--confirm`; no auto-submit / CAPTCHA / browser automation on job sites.

## Milestone status

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Project setup, config, SQLite schema, CLI | ✅ Done |
| 2 | Candidate profile + master-resume ingestion | Next |
| 3 | Gmail OAuth + incremental sync | Planned |
| 4 | Email/job extraction | Planned |
| 5 | Duplicate detection + tracking | Planned |
| 6 | Rule-based explainable matching | Planned |
| 7 | Truthful resume tailoring + Desktop export | Planned |
| 8 | Tests polish + optional Streamlit dashboard | Planned |

## Quick start (Windows)

```powershell
cd C:\Users\Admin\Projects\job-search-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
python -m job_agent setup
python -m job_agent profile
```

Or run `scripts\dev_setup.ps1`.

### Working commands (Milestone 1)

```powershell
python -m job_agent setup
python -m job_agent profile
python -m job_agent jobs
python -m job_agent statuses
python -m job_agent mark-applied <job_id> --confirm   # only after you apply manually
```

Commands reserved for later milestones exit with a clear message:

`sync-gmail`, `analyze`, `tailor`, `dashboard`.

## Configure your profile

Edit `config.yaml` → `profile`:

- Target titles / industries
- Required & preferred skills
- Years of experience
- Locations & work modes (`remote` / `hybrid` / `on-site`)
- Salary range & employment type
- Work authorization
- Exclusions (companies, titles, skills, locations)
- Optional cover-letter template path

Set `MASTER_RESUME_PATH` and `JOBS_APPLIED_FOLDER` in `.env`.

## Gmail OAuth setup (free, read-only)

1. [Google Cloud Console](https://console.cloud.google.com/) → create/select a project
2. **APIs & Services** → enable **Gmail API**
3. **OAuth consent screen** → add yourself as a test user
4. **Credentials** → **OAuth client ID** → application type **Desktop app**
5. Download JSON → save as `credentials.json` in the project root (gitignored)
6. First real sync will open a browser; token is stored in `token.json` (gitignored)
7. Scope used: `https://www.googleapis.com/auth/gmail.readonly` only

Redirect URIs for Desktop clients are handled by the local loopback server (`google-auth-oauthlib`). Do not commit `credentials.json` or `token.json`.

## Project layout

```
job-search-agent/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config.yaml
├── src/job_agent/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── gmail_client.py
│   ├── email_parser.py
│   ├── job_normalizer.py
│   ├── matcher.py
│   ├── resume_tailor.py
│   ├── document_exporter.py
│   ├── application_tracker.py
│   └── services/
├── tests/
├── data/                 # SQLite DB (gitignored)
├── templates/
└── scripts/
```

## Tests

```powershell
pytest -q
```

## Security & privacy

- Credentials, OAuth tokens, `.env`, databases, and generated resumes are gitignored
- Treat resume content, email bodies, and application history as sensitive personal data
- Prefer rule-based matching (`LLM_PROVIDER=none`) to avoid sending job text to third parties
- Never invent qualifications in tailored resumes
- Never mark Applied without explicit `--confirm`

## License

MIT — personal use
