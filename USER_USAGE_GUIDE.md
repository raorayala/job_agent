# User Usage Guide — Local AI Job Search Agent

A private, local-first personal career assistant.

---

## Interactive Web Console & Quick Reference Workflow

Launch the Web Console in your browser to view results, manage Kanban cards, edit your candidate profile, and execute commands with 1 click:

```powershell
python -m job_agent web
```

Or run individual commands in your terminal:

```powershell
# 1. Start Web Console & 1-click Chrome bookmarklet server
python -m job_agent serve

# 2. Open automated search query links tailored to your config.yaml skills (posted in last 1-2 weeks)
python -m job_agent search-links --open --browser chrome

# 3. Direct search and fetch from job platforms (<10 jobs per platform, posted in last 1-2 weeks)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter --limit 9

# 4. Sync job alert emails from Gmail (received in last 14 days)
python -m job_agent sync-gmail

# 5. Re-score all jobs against your master resume text and profile
python -m job_agent analyze

# 6. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 7. Generate ATS tailored DOCX resume & cover letter
python -m job_agent tailor <job_id>

# 8. Mark as applied after manual submission
python -m job_agent mark-applied <job_id> --confirm

# 9. View search pipeline dashboard & follow-ups
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
   This automatically opens `http://localhost:8000/` in Google Chrome.

2. **Dashboard Tab (Pipeline Metrics & High Matches)**:
   - View top cards for **Total Tracked Jobs**, **High Match Opportunities**, **Follow-ups Due**, and **Upcoming Interviews**.
   - Review high-score opportunities with color-coded score badges. Click **Tailor DOCX** to generate resume files immediately.

3. **Kanban Application Board Tab (Visual Status Tracker)**:
   - View jobs organized by columns: `Saved`, `Reviewing`, `Ready to apply`, `Applied`, `Interviewing`, `Offer`, `Rejected`.
   - **Move Cards**: Change a job's application status with 1 click using the status dropdown on any card.
   - **Inspect Details**: Click any card to open the Slide-Over Job Details Modal.

4. **Slide-Over Job Details Modal**:
   - Displays full job description, matched skills badges (green), and missing keywords (red).
   - **📁 Open Desktop Folder**: Click to open `~/Desktop/Jobs Applied/<Company>/<Job Title>/` directly in **Windows File Explorer**!
   - **📄 Tailor Resume & Cover Letter**: Generates ATS tailored DOCX files.
   - **🌐 Open Link**: Opens job listing in Google Chrome.

5. **Profile & Skills Editor Tab (`config.yaml`)**:
   - Edit target job titles, required skills, preferred skills, experience years, salary range, locations, and excluded companies/titles directly in browser.
   - Click **Save Profile Configuration** to save changes to `config.yaml` and re-score jobs in real time.

6. **CLI Command Runner Tab**:
   - Access form controls and **"▶ Run Command"** buttons for all 27 CLI commands.
   - Click **Run Command** to execute any command in a subprocess and view output live in the **Terminal Output Console**.

7. **Export `.ics` Calendar Events**:
   - Click **Export .ics Calendar** in the top header to download a standard `.ics` file containing all upcoming follow-ups (automatically set for 7 days after application) and scheduled interviews. Import this file directly into Outlook, Google Calendar, or Apple Calendar.

8. **Windows Desktop Toast Notifications**:
   - Whenever you run `fetch-jobs` or `sync-gmail`, if a new job scoring **≥ 70/100** is discovered, a native Windows Toast popup alerts you immediately!

---

## 1-Click Chrome Bookmarklet Setup

1. Run `python -m job_agent serve` or `python -m job_agent web` in terminal.
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
  .catch(err => alert('❌ Error: Make sure "python -m job_agent serve" is running in terminal.'));
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

- **Automated Daily Sync (Task Scheduler)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/schedule_daily_sync.ps1
  ```

---

## 🔐 Security & Privacy Safeguards

1. **Air-Gapped Local Storage**: All databases, tokens, resumes, cover letters, contacts, and logs remain 100% on your computer.
2. **Gmail Read-Only Scope**: Uses `gmail.readonly` OAuth 2.0 scope only; cannot send or modify emails.
3. **Localhost Endpoint Binding**: Capture server (`serve`) binds strictly to `127.0.0.1:8000`.
4. **Git Exclusion (`.gitignore`)**: Prevents accidental commits of `.env`, `credentials.json`, `token.json`, `jobs.db`, and generated DOCX resumes.
5. **Truthfulness Guarantee**: Resumes and cover letters use only verified experience from your master DOCX resume. Zero hallucinated jobs, titles, or dates.
6. **Zero Auto-Apply**: Human-in-the-loop required for all application submissions.

---

## 📖 Complete Command Reference

For a complete reference of all available CLI commands, options, and flags, see the **[CLI Command Cheat Sheet](CLI_CHEAT_SHEET.md)**.
