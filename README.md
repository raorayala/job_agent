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
| 2 | Candidate profile + master-resume DOCX text extraction | ✅ Done |
| 3 | Gmail OAuth + incremental sync (`gmail.readonly`) | ✅ Done |
| 4 | Email digest / multi-job extraction | ✅ Done |
| 5 | Multi-tier duplicate detection + application tracking | ✅ Done |
| 6 | Weighted explainable matching algorithm (0–100) | ✅ Done |
| 7 | Truthful ATS resume & cover letter tailoring + Desktop export | ✅ Done |
| 8 | Direct platform fetch, local capture server, contacts, answers, backup, test suite | ✅ Done |

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

### 🌐 Web Console & Visual Application Board

Launch the local Web Application Console to manage applications, view Kanban cards, and execute CLI commands with 1 click:

```powershell
python -m job_agent web
```
This starts `http://localhost:8000/` featuring:
- **Visual Kanban Board**: Drag & drop / 1-click status transitions across application stages.
- **Slide-Over Job Details**: Full job description, matched/missing skills badges, and 1-click **Open Desktop Folder** in File Explorer (`~/Desktop/Jobs Applied/<Company>/<Job Title>/`).
- **Profile & Skills Web Editor**: Interactive form to edit `config.yaml` target titles, skills, salary, and exclusions directly in browser.
- **Calendar Exporter (`.ics`)**: Export follow-ups and scheduled interviews directly to Outlook / Google Calendar.
- **Desktop Toast Notifications**: Real-time Windows Toast popups when high-score jobs (≥ 70/100) are discovered.
- **1-Click Chrome Bookmarklet**: Save listings instantly while browsing Indeed, Dice, ZipRecruiter, Glassdoor, or LinkedIn.

### Daily Usage Commands

For a full reference, see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)** or **[USER_USAGE_GUIDE.md](USER_USAGE_GUIDE.md)**.

```powershell
python -m job_agent web                                 # Launch Web Console, Kanban Board & CLI Runner
python -m job_agent serve                              # Start 1-click Chrome bookmarklet capture server
python -m job_agent search-links --open --browser chrome  # Launch search URLs (<1-2 weeks old) in Chrome
python -m job_agent fetch-jobs --platforms dice --limit 9 # Direct search (<10 jobs per platform, <1-2 weeks old)
python -m job_agent sync-gmail                         # Fetch job alert emails from Gmail
python -m job_agent analyze                            # Re-score stored jobs against profile & DOCX resume
python -m job_agent jobs --min-score 60               # List tracked jobs
python -m job_agent tailor <job_id>                    # Generate tailored ATS DOCX resume & cover letter
python -m job_agent mark-applied <job_id> --confirm    # Mark as applied after manual submission
python -m job_agent dashboard                          # View search pipeline dashboard
python -m job_agent follow-ups                         # View follow-up actions due
```

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
