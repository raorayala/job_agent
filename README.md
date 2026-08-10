# Job Search Agent

Local-first Python AI Job Search Agent that automates job discovery across the top 10 USA job search platforms, imports Gmail alerts, performs ATS keyword analysis, generates versioned resume drafts in a review-first workflow, and tracks applications in SQLite — without ever submitting applications or overwriting finalized resumes without your explicit approval.

## Full documentation

See the **[docs/](docs/README.md)** folder for the complete project document set:

| Doc | Topic |
|-----|-------|
| [Requirements](docs/01-REQUIREMENTS.md) | Goals, scope, functional requirements |
| [Design](docs/02-DESIGN-SPECIFICATION.md) | UX flows, CLI contracts, safeguards |
| [Architecture](docs/03-ARCHITECTURE.md) | Components, top 10 adapters, and data flow |
| [Implementation](docs/04-IMPLEMENTATION.md) | Module status, review-first engine details |
| [Data model](docs/05-DATA-MODEL.md) | SQLite schema, draft versioning, activity feed |
| [Security](docs/06-SECURITY-PRIVACY.md) | OAuth, secrets, privacy, local-first policy |
| [Testing](docs/07-TESTING.md) | Test strategy & 100% passing suite |
| [Operations](docs/08-OPERATIONS-DEPLOYMENT.md) | Local production install & ops |
| [Roadmap](docs/09-ROADMAP.md) | Milestones and future work |
| [User guide](docs/10-USER-GUIDE.md) | Day-to-day usage guide |
| [CLI Cheat Sheet](CLI_CHEAT_SHEET.md) | Quick CLI reference |

## Review-First Architecture & Safety Workflow

```
Job Discovery (Top 10 USA Platforms / Gmail / URL Import)
        ↓
   SQLite DB ← Matcher (0-100 Explainable ATS Score)
        ↓
  Generate ATS Resume Draft (Saved in _drafts/ folder)
        ↓
  Web Console Review (Preview Draft vs Master Resume & Diff Summary)
        ↓
  User Explicitly Clicks "Approve & Finalize"
        ↓
  Promote Approved Resume to ~/Desktop/Jobs Applied/<Company>/<Job Title>/
```

### Top 10 Supported USA Job Platforms

1. **Indeed**
2. **LinkedIn Jobs**
3. **Glassdoor**
4. **Monster**
5. **ZipRecruiter**
6. **CareerBuilder**
7. **SimplyHired**
8. **Dice**
9. **Wellfound (AngelList Talent)**
10. **Google Jobs**

**Key Safeguards:**
- **Strict Human Approval**: Resumes are generated into `_drafts/` first. Master resumes and finalized applied resumes are **never overwritten** until you explicitly approve the draft.
- **Top 10 Platform Batch Limits**: Direct platform searches limit results to **fewer than 10 jobs per platform per run** and filter for postings from the **last 1–2 weeks (14 days)**.
- **Terms of Service Compliance**: Uses public RSS/Atom feeds, JSON-LD schema, public search endpoints, and URL import fallbacks. Does not perform aggressive browser scraping violating platform TOS.
- **Browser Control**: Opens search links in your system default browser or configured `PREFERRED_BROWSER` (never forcing Microsoft Edge).

## Milestone Status

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Project setup, config validation, SQLite schema, CLI | ✅ Done |
| 2 | Candidate profile + master-resume DOCX text extraction | ✅ Done |
| 3 | Gmail OAuth + incremental sync (`gmail.readonly`) | ✅ Done |
| 4 | Email digest / multi-job extraction | ✅ Done |
| 5 | Multi-tier duplicate detection + application tracking | ✅ Done |
| 6 | Weighted explainable matching algorithm (0–100) | ✅ Done |
| 7 | Review-first ATS resume & cover letter tailoring + `_drafts/` folder | ✅ Done |
| 8 | Top 10 USA Platform Adapters, URL Auto-Importer, Web Application Console, Kanban Board, Database Explorer | ✅ Done |

## Quick Start (Windows / macOS / Linux)

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

### 🖥️ Interactive Web Application Console

Launch the Web Console to manage applications, search top platforms, review resume drafts, and view Kanban board:

```powershell
python -m job_agent web
```
This launches `http://localhost:8000/` featuring:
- **Dashboard**: Summary cards for New Jobs, Jobs Requiring Review, Drafts Awaiting Approval, Applications in Progress, plus live Activity Feed.
- **Top 10 Job Discovery Page**: Platform cards for all top 10 USA platforms, search query links (<14 days old), and "Find Jobs Now".
- **Automated URL Job Import**: Paste a job page URL to automatically extract title, company, location, and description.
- **Resume Review & Approval Page**: Compare Master Resume vs Tailored Draft vs Finalized Resume, inspect change summary, preview draft, and explicitly click "Approve & Finalize".
- **Visual Kanban Board**: Drag/drop and 1-click status transitions.
- **Database Explorer & Cleanup**: View SQLite tables, execute SQL queries, and trigger safe automated cleanup routines.

### Daily Usage Commands

For a full reference, see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)** or **[USER_USAGE_GUIDE.md](USER_USAGE_GUIDE.md)**.

```powershell
python -m job_agent web                                  # Launch Web Application Console
python -m job_agent search-links --open --browser system # Launch top 10 search URLs in default browser
python -m job_agent fetch-jobs --platforms dice,ziprecruiter # Search platforms (<10 jobs, <14 days old)
python -m job_agent add-job --url "https://..."          # Automated URL job import
python -m job_agent sync-gmail                          # Fetch job alert emails from Gmail
python -m job_agent analyze                             # Re-score stored jobs against profile & DOCX resume
python -m job_agent tailor <job_id>                     # Generate ATS resume draft into _drafts/
python -m job_agent approve-draft <job_id>               # Explicitly approve and finalize draft
python -m job_agent mark-applied <job_id> --confirm     # Mark as applied after manual submission
python -m job_agent backup                              # Create local ZIP backup archive
```

## Configure Your Profile

Edit `config.yaml` → `profile`:
- Target titles / industries
- Required & preferred skills
- Years of experience
- Locations & work modes (`remote` / `hybrid` / `on-site`)
- Salary range & employment type
- Work authorization
- Exclusions (companies, titles, skills, locations)
- `master_resume_path` and `master_resumes` mapping

Set environment variables in `.env`:
- `JOBS_APPLIED_FOLDER`: Finalized output directory (default: `~/Desktop/Jobs Applied`)
- `JOBS_DRAFT_FOLDER`: Draft output directory (default: `~/Desktop/Jobs Applied/_drafts`)
- `PREFERRED_BROWSER`: `system` (default), `chrome`, `firefox`, or `default`

## Gmail OAuth Setup (Read-Only)

1. [Google Cloud Console](https://console.cloud.google.com/) → create/select a project
2. **APIs & Services** → enable **Gmail API**
3. **OAuth consent screen** → add yourself as a test user
4. **Credentials** → **OAuth client ID** → application type **Desktop app**
5. Download JSON → save as `credentials.json` in the project root (gitignored)
6. First real sync will open a browser; token is stored in `token.json` (gitignored)
7. Scope used: strictly `https://www.googleapis.com/auth/gmail.readonly`

## Tests

Run the full test suite (46 passing tests):

```powershell
pytest
```

## License

MIT — 100% Private Personal Use
