# User Usage Guide — Job Search Agent

Local-first, private personal AI job search assistant.

---

## 1. Executive Overview

The **Job Search Agent** is a private, local-first personal career assistant designed to help you manage your targeted job applications. All data, database records, resumes, cover letters, application answers, and notes remain **100% local on your computer**.

### Key Capabilities
- **Job Discovery (5 Methods)**:
  1. **Web Console Platform Search** — checkboxes with recommended/experimental tier badges; default 3 jobs per platform
  2. **Direct Platform Search (`fetch-jobs`)** — CLI search for dice, ziprecruiter, indeed (recommended)
  3. **1-Click Chrome Bookmarklet** (`web` → `/capture`)
  4. **Pre-formatted Browser Query Links** (`search-links --open`)
  5. **Gmail Alert Sync** (`sync-gmail` via OAuth 2.0)
  6. **URL Import** (`add-job` or web Import URL modal)
  7. **Demo Seed** (`seed-demo` or Dashboard **Load Demo Jobs**)
- **Explainable Match Engine**: 0–100 weighted scoring comparing job details against your candidate profile AND master DOCX resume text.
- **Auto-Analyze**: Platform search automatically re-scores imported jobs.
- **Truthful Document Tailoring**: Creates ATS-optimized DOCX resumes in `_drafts/` first; promotes to `~/Desktop/Jobs Applied/` only after explicit approval.
- **Application Tracking & Answer Library**: Track application statuses, networking contacts, interview prep sheets, and reusable application answers.
- **System Health Panel**: Onboarding checklist, Gmail OAuth status, master resume status.
- **Privacy & Safety**: Zero auto-submission. Requires explicit user confirmation for all application updates and data deletion.

---

## 2. Environment & Initial Setup

### 2.1 Installation
```powershell
cd C:\Users\Admin\Projects\job-search-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

### 2.2 Configuration Files
1. `.env`:
   ```ini
   MASTER_RESUME_PATH=C:/Users/Admin/Desktop/Jobs Applied/master_resume.docx
   JOBS_APPLIED_FOLDER=C:/Users/Admin/Desktop/Jobs Applied
   DATABASE_PATH=C:/Users/Admin/Projects/job-search-agent/data/jobs.db
   LLM_PROVIDER=none
   ```
2. `config.yaml`: Configure target job titles, required/preferred skills, years of experience, locations, work modes, salary range, and exclusion lists.

### 2.3 Run Setup Check
```powershell
python -m job_agent setup --open-bookmarklet
python -m job_agent profile
```

---

## 3. How to Discover & Import Jobs

### Method A: Interactive Web Console (Recommended)

1. Start the Web Console:
   ```powershell
   python -m job_agent web
   ```
2. Open `http://localhost:8000/` (ThreadingHTTPServer — not Streamlit).
3. **User Mode** (default) shows your daily workflow: Dashboard stats, Job Discovery, Resume Review, and Kanban. Admin-only setup tools are hidden.
4. **First-time admin setup:** Click **Admin Setup** in the header → review **System Health** and the onboarding checklist → configure profile under **Profile & Skills** → click **Load Demo Jobs** or run `python -m job_agent seed-demo`.
5. Return to **User Mode** (**Switch to User View**) for day-to-day job search.
6. Go to **Job Discovery** → select platforms (recommended: dice, ziprecruiter, indeed) → **Find Jobs Now**.
7. Review **Last Platform Search Results** (per-platform success/empty/error) and **Recently Discovered Jobs** (all scores).
8. Install the bookmarklet from **Install Bookmarklet** → `/capture` → **Mark as Installed** (Admin Setup tab or direct `/capture` URL).

### Method B: Direct Platform Search (`fetch-jobs`)
```powershell
# Default: 3 jobs per platform; recommended platforms
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed

# Max 9 jobs per platform
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed --limit 9
```

### Method C: Launch Automated Browser Searches (`search-links`)
```powershell
python -m job_agent search-links --open --browser system
```

### Method D: Direct URL Import (`add-job`)
```powershell
python -m job_agent add-job --url "https://www.dice.com/job-detail/sample-123"
```

### Method E: Gmail Alert Sync (`sync-gmail`)
```powershell
python -m job_agent sync-gmail
```

### Method F: Chrome Bookmarklet
See [USER_USAGE_GUIDE.md](../USER_USAGE_GUIDE.md) for full bookmarklet setup.

---

## 4. Analysis, Tailoring & Application Workflow

### Step 1: Re-Score All Jobs
```powershell
python -m job_agent analyze
```
Auto-runs after successful platform search from the Web Console.

### Step 2: Review Matches
- **Dashboard High-Match widget**: score ≥65 AND status Saved/Reviewing
- **Recently Discovered Jobs**: all imported jobs with scores
- CLI: `python -m job_agent jobs --min-score 65`

### Step 3: Edit Job Details (Optional)
Use the web **Job Edit Modal** or `/api/jobs/update` to edit fields; changes trigger automatic re-scoring.

### Step 4: Generate ATS Tailored Resume Draft
```powershell
python -m job_agent tailor <job_id>
```
Creates draft in `_drafts/` folder awaiting review.

### Step 5: Approve & Finalize
```powershell
python -m job_agent approve-draft <job_id>
```
Or use the Web Console **Resume Review** tab → **Approve & Finalize Resume**.

### Step 6: Apply Manually & Confirm Status
```powershell
python -m job_agent mark-applied <job_id> --confirm
```

---

## 5. Personal Assistant Features

### Networking Contacts
```powershell
python -m job_agent add-contact "Sarah Jenkins" --role "Technical Recruiter" --company "Acme Corp" --email "s.jenkins@acme.com" --job-id 25
python -m job_agent contacts
```

### Interview Tracking & Preparation
```powershell
python -m job_agent add-interview 25 "2026-08-15 10:00" --type "Technical" --participants "Lead Architect"
python -m job_agent prepare-interview 25
```

### Application Answer Library
```powershell
python -m job_agent answers
python -m job_agent add-answer "Notice Period" "2 weeks notice"
python -m job_agent suggest-answer 25 "Why are you interested in this role?"
```

### Search Dashboard & Pipeline Reports
```powershell
python -m job_agent dashboard
python -m job_agent report --period weekly
```

### Local Backup & Data Management
```powershell
python -m job_agent backup
python -m job_agent restore backups/job_agent_backup_20260808_180000.zip
python -m job_agent delete-job 25
python -m job_agent purge-data --confirm   # wipes all 6 tables
```

Alternative purge: `python scripts/purge_database.py --confirm`

---

## 6. Web Application Console Reference

### 6.1 Launching
```powershell
python -m job_agent web
```
Starts ThreadingHTTPServer on `http://localhost:8000/` and opens Chrome automatically.

### 6.2 Dashboard
- System health panel + onboarding checklist
- **Load Demo Jobs** button
- Stat cards: Total Jobs, Requiring Review, Drafts Awaiting Approval, In Progress
- **High-Match** widget (≥65, Saved/Reviewing)
- **Recently Discovered Jobs** (all scores)
- Live Activity Feed
- Install Bookmarklet card

### 6.3 Job Discovery
- Platform checkboxes with recommended/experimental tier badges
- **Find Jobs Now** (default 3 jobs per platform, max 9)
- **Last Platform Search Results** table
- Auto-analyze after search

### 6.4 Resume Review
- 3-way view: Master → Draft (`_drafts/`) → Finalized (`Jobs Applied/`)
- Diff summary and keyword alignment
- Approve/Reject controls

### 6.5 Kanban Board
Status columns: Saved, Reviewing, Ready to apply, Applied, Interviewing, Offer, Rejected.

### 6.6 Database Explorer
Browse all 6 tables; run SQL; cleanup routines.

### 6.7 Profile Editor
Edit `config.yaml` fields with live helper text; save from browser.

### 6.8 CLI Runner
Form controls and **Run Command** buttons with live terminal output.

See [12 — Web Console API](12-WEB-CONSOLE-API.md) for HTTP endpoints.

---

## 7. Complete CLI Command Reference

| Command | Usage | Description |
| :--- | :--- | :--- |
| **`setup`** | `python -m job_agent setup` | Verify DB, folders, and configuration |
| **`profile`** | `python -m job_agent profile` | Display current candidate profile & resume paths |
| **`web`** | `python -m job_agent web` | Launch Web Console on `http://localhost:8000/` |
| **`seed-demo`** | `python -m job_agent seed-demo` | Insert sample jobs for smoke testing |
| **`search-links`** | `python -m job_agent search-links [--open]` | Generate platform query links |
| **`fetch-jobs`** | `python -m job_agent fetch-jobs [--platforms dice,ziprecruiter,indeed]` | Search platforms (default 3 each) |
| **`add-job`** | `python -m job_agent add-job --url URL` | Import job from URL |
| **`sync-gmail`** | `python -m job_agent sync-gmail [--dry-run]` | Sync job alerts from Gmail |
| **`analyze`** | `python -m job_agent analyze` | Re-score all jobs |
| **`jobs`** | `python -m job_agent jobs [--min-score 65]` | List saved jobs and match scores |
| **`tailor`** | `python -m job_agent tailor <job_id>` | Generate ATS tailored resume draft |
| **`approve-draft`** | `python -m job_agent approve-draft <job_id>` | Approve and promote draft |
| **`reject-draft`** | `python -m job_agent reject-draft <job_id>` | Reject draft |
| **`mark-applied`** | `python -m job_agent mark-applied <job_id> --confirm` | Mark job as applied |
| **`add-contact`** | `python -m job_agent add-contact "Name" --job-id ID` | Store networking contact |
| **`contacts`** | `python -m job_agent contacts` | List contacts |
| **`add-interview`** | `python -m job_agent add-interview ID "YYYY-MM-DD HH:MM"` | Record interview |
| **`prepare-interview`** | `python -m job_agent prepare-interview ID` | Generate prep sheet |
| **`answers`** | `python -m job_agent answers` | List answer library |
| **`add-answer`** | `python -m job_agent add-answer "Q" "A"` | Save reusable answer |
| **`suggest-answer`** | `python -m job_agent suggest-answer ID "Question"` | Draft answer |
| **`dashboard`** | `python -m job_agent dashboard` | Pipeline summary |
| **`report`** | `python -m job_agent report [--period weekly]` | Analytical report |
| **`backup`** | `python -m job_agent backup [PATH]` | Create ZIP backup |
| **`restore`** | `python -m job_agent restore PATH` | Restore from backup |
| **`delete-job`** | `python -m job_agent delete-job ID` | Delete single job |
| **`purge-data`** | `python -m job_agent purge-data --confirm` | Wipe all 6 DB tables |
| **`cleanup`** | `python -m job_agent cleanup --action duplicates --confirm` | Targeted cleanup |

Full details: [CLI_CHEAT_SHEET.md](../CLI_CHEAT_SHEET.md)

---

## 8. Related Documentation

| Doc | Purpose |
|-----|---------|
| [CLI Cheat Sheet](../CLI_CHEAT_SHEET.md) | Complete CLI reference |
| [Testing Playbook](11-TESTING-PLAYBOOK.md) | Smoke tests and troubleshooting |
| [Web Console API](12-WEB-CONSOLE-API.md) | HTTP API reference |
| [Operations](08-OPERATIONS-DEPLOYMENT.md) | Install, scheduling, backups |
