# User Usage Guide — Job Search Agent

Local-first, private personal AI job search assistant.

---

## 1. Executive Overview

The **Job Search Agent** is a private, local-first personal career assistant designed to help you manage your targeted job applications. All data, database records, resumes, cover letters, application answers, and notes remain **100% local on your computer**.

### Key Capabilities
- **Job Discovery (4 Methods)**:
  1. Direct Platform Search (`fetch-jobs` for Dice & ZipRecruiter)
  2. 1-Click Chrome Bookmarklet (`web` on `localhost:8000/capture`)
  3. Pre-formatted Browser Query Links (`search-links --open`)
  4. Gmail Alert Sync (`sync-gmail` via OAuth 2.0)
- **Explainable Match Engine**: 0–100 weighted scoring comparing job details against your candidate profile AND master DOCX resume text.
- **Truthful Document Tailoring**: Creates ATS-optimized DOCX resumes, cover letters, and summary text files in `~/Desktop/Jobs Applied/<Company>/<Job Title>/`.
- **Application Tracking & Answer Library**: Track application statuses, networking contacts, interview prep sheets, and reusable application answers.
- **Privacy & Safety**: Zero auto-submission. Requires explicit user confirmation for all application updates and data deletion.

---

## 2. Environment & Initial Setup

### 2.1 Installation
```powershell
cd C:\Users\Admin\Projects\job-search-agent
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
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
   ```yaml
   profile:
     target_titles:
       - Senior Backend Engineer
       - Java Developer
     required_skills:
       - Java
       - SpringBoot
       - Python
     master_resumes:
       java: C:/Users/Admin/Desktop/Java_Resume.docx
       python: C:/Users/Admin/Desktop/Python_Resume.docx
   ```

### 2.3 Run Setup Check
```powershell
python -m job_agent setup
python -m job_agent profile
```

---

## 3. How to Discover & Import Jobs (No Gmail Required)

### Method A: Interactive Web Console & 1-Click Chrome Bookmarklet (Recommended)
1. Initialize local setup (optional — can also open bookmarklet page during setup):
   ```powershell
   python -m job_agent setup --open-bookmarklet
   ```
2. Start the interactive Web Console server:
   ```powershell
   python -m job_agent web
   ```
3. Open `http://localhost:8000/` in Google Chrome to manage your job search pipeline:
   - **Global Event Progress Bar**: Real-time visual progress feedback (`#global-progress-wrapper`) for all web console actions.
   - **Install Bookmarklet**: Header button or Dashboard card opens `/capture` anytime (copy snippet, test endpoint, mark install status in this browser).
   - **Top 10 USA Platform Search**: Search Indeed, LinkedIn, Glassdoor, Monster, ZipRecruiter, CareerBuilder, SimplyHired, Dice, Wellfound, and Google Jobs.
   - **URL Job Import Modal**: Paste any job URL to extract details and score alignment automatically.
   - **Resume Review & Approval Page**: Compare Master Resume vs Tailored Draft (`_drafts/`) vs Finalized Resume (`jobapplied`). Click *"Approve & Finalize Resume"* to promote the approved draft to your `Jobs Applied` folder.
   - **Profile & Skills Editor**: Field-by-field helper text showing live `config.yaml` values, with quick keyword addition controls.
4. On `http://localhost:8000/capture`: show Chrome Bookmarks Bar (`Ctrl + Shift + B`), add bookmark **Capture Job** with the JavaScript snippet, run **Send Test Capture Payload**, then **Mark as Installed**.
5. When viewing any job on **Indeed, Dice, ZipRecruiter, Glassdoor, or LinkedIn**, click **`Capture Job`** on your Chrome bar to save it instantly (keep `python -m job_agent web` running).

### Method B: Direct Platform Search (`fetch-jobs`)
Fetch jobs directly from platforms without opening a browser:
```powershell
python -m job_agent fetch-jobs --platforms dice
```

### Method C: Launch Automated Browser Searches (`search-links`)
Open search result tabs tailored to your `config.yaml` skills in Chrome:
```powershell
python -m job_agent search-links --open
```

### Method D: Direct URL Import (`add-job`)
```powershell
python -m job_agent add-job --url "https://www.dice.com/job-detail/sample-123" --title "Senior Backend Java Engineer" --company "Acme Corp" --description "Looking for Java, Spring Boot, and SQL..."
```

### Method E: Gmail Alert Sync (`sync-gmail`)
If you have set up Google OAuth `credentials.json`:
```powershell
python -m job_agent sync-gmail
```

---

## 4. Analysis, Tailoring & Application Workflow

### Step 1: Re-Score All Jobs Against Profile & Resume
```powershell
python -m job_agent analyze
```

### Step 2: List Top-Matching Opportunities
```powershell
python -m job_agent jobs --min-score 60
```

### Step 3: Generate ATS Tailored Resume & Cover Letter
```powershell
python -m job_agent tailor <job_id>
```
*Creates documents in `~/Desktop/Jobs Applied/<Company>/<Job Title>/`:*
- `Company_JobTitle_Resume.docx`
- `Company_JobTitle_Cover_Letter.docx`
- `Application_Summary.txt`

### Step 4: Apply Manually & Confirm Status
After submitting your application on the employer site:
```powershell
python -m job_agent mark-applied <job_id> --confirm
```

---

## 5. Personal Assistant Features

### Networking Contacts
```powershell
# Add contact
python -m job_agent add-contact "Sarah Jenkins" --role "Technical Recruiter" --company "Acme Corp" --email "s.jenkins@acme.com" --job-id 25

# List contacts
python -m job_agent contacts
```

### Interview Tracking & Preparation
```powershell
# Schedule interview
python -m job_agent add-interview 25 "2026-08-15 10:00" --type "Technical" --participants "Lead Architect"

# Generate local interview prep sheet
python -m job_agent prepare-interview 25
```

### Application Answer Library
```powershell
# List answers
python -m job_agent answers

# Save approved answer
python -m job_agent add-answer "Notice Period" "2 weeks notice"

# Suggest draft answer for application question
python -m job_agent suggest-answer 25 "Why are you interested in this role?"
```

### Search Dashboard & Pipeline Reports
```powershell
# View pipeline dashboard
python -m job_agent dashboard

# View weekly or monthly search report
python -m job_agent report --period weekly
```

### Local Backup & Data Management
```powershell
# Create ZIP backup
python -m job_agent backup

# Restore from backup archive
python -m job_agent restore backups/job_agent_backup_20260808_180000.zip

# Delete a single job
python -m job_agent delete-job 25

# Purge all local data (requires confirmation)
python -m job_agent purge-data
```

---

## 5. Interactive Web Application Console

The **Web Application Console** provides a modern, 100% private visual interface to manage your job search pipeline.

### 5.1 Launching the Console
```powershell
python -m job_agent web
```
This starts a local HTTP server on `http://localhost:8000/` and opens Google Chrome automatically.

### 5.2 Key Web Features
- **Visual Kanban Application Board**:
  - Drag-and-drop or 1-click status transitions across `Saved`, `Reviewing`, `Ready to apply`, `Applied`, `Interviewing`, `Offer`, and `Rejected`.
- **Slide-Over Job Details Modal**:
  - Full Job Description text, matched skills badges (green), and missing keywords (red).
  - **📁 Open Desktop Folder**: Click to launch `~/Desktop/Jobs Applied/<Company>/<Job Title>/` directly in **Windows File Explorer**!
  - **📄 Tailor DOCX**: Generate ATS tailored DOCX resumes and cover letters.
- **Profile & Skills Web Editor**:
  - View and edit `config.yaml` target titles, required/preferred skills, salary, locations, and exclusions directly in browser with 1-click saving.
- **Interactive CLI Cheat Sheet Runner**:
  - Access form controls and **"▶ Run Command"** buttons for all 27 CLI commands with live terminal output.
- **`.ics` iCalendar Exporter**:
  - Download standard `.ics` files containing all upcoming follow-ups and scheduled interviews for Outlook/Google Calendar.
- **Windows Desktop Toast Notifications**:
  - Real-time native Windows Toast notifications whenever a new job scoring **≥ 70/100** is discovered.

---

## 6. Complete CLI Command Reference

| Command | Usage | Description |
| :--- | :--- | :--- |
| **`setup`** | `python -m job_agent setup` | Verify DB, folders, and configuration |
| **`profile`** | `python -m job_agent profile` | Display current candidate profile & resume paths |
| **`serve`** | `python -m job_agent serve` | Start local HTTP capture server for 1-click Chrome bookmarklet |
| **`search-links`** | `python -m job_agent search-links [--open]` | Generate platform query links from `config.yaml` |
| **`fetch-jobs`** | `python -m job_agent fetch-jobs [--platforms dice]` | Search and import jobs directly from job sites |
| **`add-job`** | `python -m job_agent add-job --url URL --title T --company C` | Manually import job listing details |
| **`sync-gmail`** | `python -m job_agent sync-gmail [--dry-run]` | Sync job alerts from Gmail |
| **`analyze`** | `python -m job_agent analyze` | Re-score all database records against profile and resume |
| **`jobs`** | `python -m job_agent jobs [--min-score 60]` | List saved jobs and match scores |
| **`tailor`** | `python -m job_agent tailor <job_id>` | Generate ATS tailored resume & cover letter |
| **`mark-applied`** | `python -m job_agent mark-applied <job_id> --confirm` | Mark job as applied |
| **`add-contact`** | `python -m job_agent add-contact "Name" --job-id ID` | Store networking contact locally |
| **`contacts`** | `python -m job_agent contacts` | List saved networking contacts |
| **`add-interview`** | `python -m job_agent add-interview ID "YYYY-MM-DD HH:MM"` | Record an upcoming interview |
| **`prepare-interview`** | `python -m job_agent prepare-interview ID` | Generate interview preparation DOCX sheet |
| **`answers`** | `python -m job_agent answers` | List application answer library |
| **`add-answer`** | `python -m job_agent add-answer "Question" "Answer"` | Save reusable question answer |
| **`suggest-answer`** | `python -m job_agent suggest-answer ID "Question"` | Generate factual draft answer for application |
| **`dashboard`** | `python -m job_agent dashboard` | Show pipeline status and upcoming interviews |
| **`report`** | `python -m job_agent report [--period weekly]` | Generate analytical search report |
| **`backup`** | `python -m job_agent backup [PATH]` | Create local ZIP backup archive |
| **`restore`** | `python -m job_agent restore PATH` | Restore local database and config from backup |
| **`delete-job`** | `python -m job_agent delete-job ID` | Delete job record with confirmation |
| **`purge-data`** | `python -m job_agent purge-data` | Purge local database records with confirmation |
