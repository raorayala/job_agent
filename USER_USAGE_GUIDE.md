# User Usage Guide — Local AI Job Search Agent

A private, local-first personal career assistant with a review-first web application.

---

## Interactive Web Console & Quick Reference Workflow

Launch the Web Console in your browser to discover jobs across the top 10 USA platforms, review ATS resume drafts, manage Kanban cards, and execute commands with 1 click:

```powershell
python -m job_agent web
```

Or run individual commands in your terminal:

```powershell
# 1. Start Web Console & 1-click Chrome bookmarklet server
python -m job_agent web

# 2. Open automated search query links for top 10 USA platforms (posted in last 1-2 weeks)
python -m job_agent search-links --open --browser system

# 3. Direct search and fetch from top 10 platforms (<10 jobs per platform, posted in last 1-2 weeks)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed,linkedin,glassdoor --limit 9

# 4. Automated job import from URL
python -m job_agent add-job --url "https://www.linkedin.com/jobs/view/123456"

# 5. Sync job alert emails from Gmail (received in last 14 days)
python -m job_agent sync-gmail

# 6. Re-score all jobs against your master resume text and profile
python -m job_agent analyze

# 7. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 8. Generate ATS tailored DOCX resume draft into _drafts/ folder
python -m job_agent tailor <job_id>

# 9. Explicitly approve and promote draft into finalized jobapplied folder
python -m job_agent approve-draft <job_id>

# 10. Mark as applied after manual submission
python -m job_agent mark-applied <job_id> --confirm

# 11. View search pipeline dashboard & follow-ups
python -m job_agent dashboard
python -m job_agent follow-ups
```

---

## 🖥️ How to Use and Manage the Web Application Console

The Web Application Console (`http://localhost:8000/`) gives you complete, 100% private visual control over your job search pipeline.

### Step-by-Step Usage Guide:

1. **Launching the Web Application**:
   Open PowerShell and start the Web Console:
   ```powershell
   python -m job_agent web
   ```
   This automatically opens `http://localhost:8000/` in your system default browser.

2. **Dashboard Tab (Pipeline Metrics & Live Activity Feed)**:
   - View metric cards: **Total Discovered Jobs**, **Jobs Requiring Review**, **Drafts Awaiting Approval**, and **Applications In Progress**.
   - Primary Action buttons: **Find Jobs Now**, **Sync Gmail Alerts**, **Import Job URL**, and **Review Resume Drafts**.
   - Live Activity Feed tracking discovery, import, analysis, draft generation, and approval events.

3. **Job Discovery Tab (Top 10 USA Platforms)**:
   - Platform cards for Indeed, LinkedIn, Glassdoor, Monster, ZipRecruiter, CareerBuilder, SimplyHired, Dice, Wellfound, and Google Jobs.
   - Filter jobs by Title, Location, Work Mode (`remote` / `hybrid` / `on-site`), Posting Age (within 14 days), and Salary.
   - Click **"Find Jobs Now"** to run automated discovery across top platforms (<10 jobs per platform).

4. **Automated URL Job Import Modal**:
   - Click **Import URL** in the header or Dashboard to open the URL import modal.
   - Paste any job page URL (from LinkedIn, Indeed, Glassdoor, Monster, Dice, etc.) to automatically fetch and parse title, company, location, and description.

5. **Resume Review & Approval Screen (3-Way Version View)**:
   - Clearly distinguishes:
     1. **Master Resume**: Source of truth (`master_resume.docx`)
     2. **Draft Resume**: ATS tailored version in `_drafts/` awaiting review
     3. **Finalized Resume**: Promoted upon explicit approval into `~/Desktop/Jobs Applied/<Company>/<Job Title>/`
   - Inspect ATS Keyword Alignment & Change Summary / Diff view.
   - Click **"Approve & Finalize Resume"** to trigger confirmation modal and promote draft to `jobapplied` folder.

6. **Kanban Application Board Tab**:
   - View jobs organized by lifecycle columns: `Imported`, `Analyzed`, `Resume draft ready`, `Awaiting review`, `Approved`, `Applied`, `Interviewing`, `Offer`, `Rejected`.
   - Change a job's status with 1 click using the status dropdown.

7. **Database Explorer & Cleanup Tab**:
   - Browse SQLite tables (`jobs`, `activity_logs`, `contacts`, `interviews`, `application_answers`, `processed_emails`).
   - Execute SQL queries directly or run automated cleanup routines (duplicates, stale jobs, purge test data).

8. **Profile & Skills Editor Tab (`config.yaml`)**:
   - Edit target job titles, required skills, preferred skills, experience years, salary range, and locations directly in browser.
   - Click **Save Profile Configuration** to save changes to `config.yaml`.

---

## 1-Click Chrome Bookmarklet Setup

1. Run `python -m job_agent web` in terminal.
2. In Google Chrome, press `Ctrl + Shift + B` to show Bookmarks Bar.
3. Right-click Bookmarks Bar -> **Add page...**
   - **Name**: `Capture Job`
   - **URL**:
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
4. Click **`Capture Job`** on Chrome's bar while viewing any job on Indeed, Dice, ZipRecruiter, Glassdoor, or LinkedIn!

---

## 🛠️ Maintenance & Backup Procedures

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

- **Purge All Database Records**:
  ```powershell
  python -m job_agent purge-data --confirm
  ```

---

## 🔐 Security & Privacy Safeguards

1. **Air-Gapped Local Storage**: All databases, tokens, resumes, cover letters, contacts, and logs remain 100% on your computer.
2. **Gmail Read-Only Scope**: Uses `gmail.readonly` OAuth 2.0 scope only; cannot send or modify emails.
3. **Localhost Endpoint Binding**: Web Console binds strictly to `127.0.0.1:8000`.
4. **Git Exclusion (`.gitignore`)**: Prevents accidental commits of `.env`, `credentials.json`, `token.json`, `jobs.db`, and generated DOCX resumes.
5. **Truthfulness Guarantee**: Resumes and cover letters use only verified experience from your master DOCX resume. Zero hallucinated jobs, titles, or dates.
6. **Zero Auto-Apply**: Human-in-the-loop required for all application submissions and resume draft approvals.

---

## 📖 Complete Command Reference

For a complete reference of all available CLI commands, options, and flags, see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)**.
