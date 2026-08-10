# User Usage Guide — Local AI Job Search Agent

A private, local-first personal career assistant with an interactive review-first web application, real-time progress bar, and CLI command suite.

---

## Interactive Web Console & Quick Reference Workflow

Launch the Web Console in your browser to discover jobs across the top 10 USA platforms, review ATS resume drafts, manage Kanban cards, and execute commands with 1 click:

```powershell
python -m job_agent web
```

Or run setup and CLI commands in your terminal:

```powershell
# 0. First-time setup (optionally opens 1-click Chrome bookmarklet page)
python -m job_agent setup --open-bookmarklet

# 1. Start Web Console on http://localhost:8000/
python -m job_agent web

# 2. (Optional) Load demo jobs for smoke testing without network
python -m job_agent seed-demo

# 3. Open automated search query links for top 10 USA platforms (posted in last 14 days)
python -m job_agent search-links --open --browser system

# 4. Direct search and fetch from platforms (default 3 jobs per platform, max 9 via --limit)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed --limit 3

# 5. Automated job import from URL
python -m job_agent add-job --url "https://www.linkedin.com/jobs/view/123456"

# 6. Sync job alert emails from Gmail (received in last 14 days)
python -m job_agent sync-gmail

# 7. Re-score all jobs against your master resume text and profile
python -m job_agent analyze

# 8. List high-matching opportunities
python -m job_agent jobs --min-score 65

# 9. Generate ATS tailored DOCX resume draft into _drafts/ folder
python -m job_agent tailor <job_id>

# 10. Explicitly approve and promote draft into finalized jobapplied folder
python -m job_agent approve-draft <job_id>

# 11. Mark as applied after manual submission
python -m job_agent mark-applied <job_id> --confirm

# 12. View search pipeline dashboard & follow-ups
python -m job_agent dashboard
python -m job_agent follow-ups
```

---

## How to Use the Web Application Console

The Web Application Console (`http://localhost:8000/`) runs on a local ThreadingHTTPServer (not Streamlit) and gives you complete, 100% private visual control over your job search pipeline.

### Key Interactive Features

1. **Global Event Progress Bar**
   - Every user click and background operation (platform search, URL import, draft generation, approval, profile saving, database cleanup, CLI execution) triggers a top-level animated progress bar (`#global-progress-wrapper`) displaying real-time status messages and completion percentage.

2. **Dashboard Tab (System Health, Metrics & Live Activity Feed)**
   - **System Health panel**: Database path, Gmail OAuth status, master resume status, and onboarding checklist (`system_health.py`).
   - **Load Demo Jobs** button: Inserts sample jobs via `demo_data.py` for smoke testing without network.
   - Metric cards: **Total Discovered Jobs**, **Jobs Requiring Review**, **Drafts Awaiting Approval**, and **Applications In Progress**.
   - **High-Match widget**: Jobs with score ≥65 AND status Saved or Reviewing.
   - **Recently Discovered Jobs** table: Shows all imported jobs with scores (not filtered to ≥65).
   - **Install Bookmarklet** card with link to `/capture` and browser-local install status.
   - Live Activity Feed tracking discovery, import, analysis, draft generation, and approval events.

3. **Job Discovery Tab (Top 10 USA Platforms)**
   - Platform checkboxes with **recommended** (dice, ziprecruiter, indeed) and **experimental** tier badges.
   - Filter jobs by Title, Location, Work Mode (`remote` / `hybrid` / `on-site`), Posting Age (within 14 days), and Salary.
   - Click **Find Jobs Now** to run automated discovery (default **3 jobs per platform**, max 9).
   - **Last Platform Search Results** table shows per-platform success/empty/error status after each search.
   - Auto-analyze runs after a successful platform search (`job_analysis.py`).

4. **Automated URL Job Import Modal**
   - Click **Import URL** in the header or Dashboard to open the URL import modal.
   - Paste any job page URL to automatically fetch and parse title, company, location, and description.

5. **Job Edit Modal**
   - Edit job title, company, location, description, and notes from the web UI.
   - Changes persist via `/api/jobs/update` and trigger automatic re-scoring.

6. **Resume Review & Approval Screen (3-Way Version View)**
   - Clearly distinguishes:
     1. **Master Resume**: Source of truth (`master_resume.docx`)
     2. **Draft Resume**: ATS tailored version in `_drafts/` awaiting review
     3. **Finalized Resume**: Promoted upon explicit approval into `~/Desktop/Jobs Applied/<Company>/<Job Title>/`
   - Inspect ATS Keyword Alignment & Change Summary / Diff view.
   - Click **Approve & Finalize Resume** to trigger confirmation modal and promote draft to `jobapplied` folder.

7. **Kanban Application Board Tab**
   - View jobs organized by lifecycle columns: `Saved`, `Reviewing`, `Ready to apply`, `Applied`, `Interviewing`, `Offer`, `Rejected`.
   - Change a job's status with 1 click using the status dropdown.

8. **Database Explorer & Cleanup Tab**
   - Browse SQLite tables (`jobs`, `activity_logs`, `contacts`, `interviews`, `application_answers`, `processed_emails`).
   - Execute SQL queries directly or run automated cleanup routines (duplicates, stale jobs, purge test data).

9. **Profile & Skills Editor Tab (`config.yaml`)**
   - Optional profile configuration with field-by-field helper labels displaying live `Config.yaml current: ...` text underneath every input element.
   - Quick Add input fields and preset buttons for salary range and work modes.
   - Click **Save Profile Configuration** to persist changes directly to `config.yaml`.

---

## 1-Click Chrome Bookmarklet Setup

Install anytime from the Web Dashboard — click **Install Bookmarklet** in the header or on the Dashboard card (opens `http://localhost:8000/capture`). You do not need to re-run `setup --open-bookmarklet` unless you want the setup wizard to open that page automatically.

1. Run `python -m job_agent web` in terminal.
2. In the dashboard, click **Install Bookmarklet** (header or Dashboard card).
3. On the `/capture` page: show Chrome Bookmarks Bar (`Ctrl + Shift + B`), add a bookmark named **Capture Job**, and paste the snippet (or click **Copy Bookmarklet Code**).
4. Click **Send Test Capture Payload** to confirm the server endpoint works.
5. Click **Mark as Installed** so the dashboard remembers setup in this browser (localStorage — Chrome cannot expose bookmark bar state to web apps).
6. While browsing job sites, click **Capture Job** on Chrome's bar (server must be running).

Alternative during first-time setup:

```powershell
python -m job_agent setup --open-bookmarklet
```

Bookmarklet JavaScript (also shown on `/capture`):

```javascript
javascript:(function(){
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
  .then(data => alert(`✅ Job Saved to Job Agent!\n\nID: #${data.job_id}\nTitle: ${data.title}\nCompany: ${data.company}\nMatch Score: ${data.score}/100`))
  .catch(err => alert('❌ Error: Make sure "python -m job_agent web" is running in terminal.'));
})();
```

---

## Maintenance & Backup Procedures

- **Local Backup Archive**:
  ```powershell
  python -m job_agent backup [OPTIONAL_OUTPUT_PATH.zip]
  ```
  Creates a timestamped local ZIP backup of `data/jobs.db`, `.env`, `config.yaml`, and output documents.

- **Restore from Backup**:
  ```powershell
  python -m job_agent restore path/to/backup.zip
  ```

- **Delete Job & Output Artifacts**:
  ```powershell
  python -m job_agent delete-job <job_id> --confirm
  ```

- **Purge All Database Records** (all 6 tables: jobs, activity_logs, contacts, interviews, application_answers, processed_emails):
  ```powershell
  python -m job_agent purge-data --confirm
  ```
  Alternative: `python scripts/purge_database.py --confirm`

---

## Security & Privacy Safeguards

1. **Air-Gapped Local Storage**: All databases, tokens, resumes, cover letters, contacts, and logs remain 100% on your computer.
2. **Gmail Read-Only Scope**: Uses `gmail.readonly` OAuth 2.0 scope only; cannot send or modify emails.
3. **Localhost Endpoint Binding**: Web Console binds strictly to `127.0.0.1:8000`.
4. **Git Exclusion (`.gitignore`)**: Prevents accidental commits of `.env`, `credentials.json`, `token.json`, `jobs.db`, and generated DOCX resumes.
5. **Truthfulness Guarantee**: Resumes and cover letters use only verified experience from your master DOCX resume. Zero hallucinated jobs, titles, or dates.
6. **Zero Auto-Apply**: Human-in-the-loop required for all application submissions and resume draft approvals.

---

## Complete Command Reference

For a complete reference of all available CLI commands, options, and flags, see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)**.

For smoke testing and troubleshooting, see **[docs/11-TESTING-PLAYBOOK.md](docs/11-TESTING-PLAYBOOK.md)**.

For Web Console HTTP API endpoints, see **[docs/12-WEB-CONSOLE-API.md](docs/12-WEB-CONSOLE-API.md)**.
