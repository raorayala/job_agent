# CLI Command Cheat Sheet — Job Search Agent

A comprehensive reference guide for all CLI commands, maintenance procedures, web application controls, and security safeguards in the **Job Search Agent** local-first personal career assistant.

---

## 🌐 Interactive Web Application Dashboard & CLI Runner

Instead of running commands manually in your terminal, launch the local **Web Application Console**:

```powershell
python -m job_agent web
# or
python -m job_agent serve --open
```

This opens `http://localhost:8000/` in Chrome with:
- **Interactive CLI Cheat Sheet**: Form controls and **"▶ Run Command"** buttons for all 27 CLI commands.
- **Live Terminal Console**: Streams command stdout/stderr directly onto the web page in real-time.
- **Pipeline Dashboard**: Live metrics for total jobs, high match scores, follow-ups due, and interviews.
- **Tracked Jobs Explorer**: 1-Click action buttons to tailor resumes, mark applied, and draft answers.
- **1-Click Chrome Bookmarklet**: Embedded snippet installer and capture endpoint.

---

## ⚡ Daily Workflow Quick Start

```powershell
# 0. Launch Interactive Web Console & CLI Cheat Sheet (Recommended)
python -m job_agent web

# 1. Start local capture server (for 1-click Chrome Bookmarklet)
python -m job_agent serve

# 2. Open tailored search query links in Chrome (filtered for jobs posted in last 1-2 weeks)
python -m job_agent search-links --open --browser chrome

# 3. Fetch jobs directly from platforms (<10 jobs per platform, posted in last 1-2 weeks)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter --limit 9

# 4. Sync job alert emails from Gmail (posted in last 14 days)
python -m job_agent sync-gmail

# 5. Re-score all saved jobs against your master resume text and candidate profile
python -m job_agent analyze

# 6. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 7. Tailor ATS resume & cover letter (saved to ~/Desktop/Jobs Applied/<Company>/<Job Title>/)
python -m job_agent tailor <job_id>

# 8. Mark as applied after manual submission on job platform
python -m job_agent mark-applied <job_id> --confirm

# 9. View search pipeline dashboard & follow-ups
python -m job_agent dashboard
python -m job_agent follow-ups
```

---

## 📋 Categorized Command Reference

### 1. Setup & Environment
| Command | Web Console Link | Description | Default / Options |
| :--- | :--- | :--- | :--- |
| `python -m job_agent setup` | `▶ Run` | Initialize local runtime folders, SQLite DB schema, verify config and OAuth credentials | `--no-copy-env` |
| `python -m job_agent profile` | `▶ Run` | Display loaded candidate profile, target titles, skills, and multi-resumes | None |
| `python -m job_agent statuses` | `▶ Run` | List supported application lifecycle statuses | None |

---

### 2. Job Discovery & Ingestion
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent web` | `http://localhost:8000/` | Launch Interactive Web Application Console & CLI Cheat Sheet | `--port 8000`, `--open` |
| `python -m job_agent serve` | `▶ Run` | Start local HTTP server for 1-click Chrome bookmarklet capture & Web Console | `--port 8000`, `--open` |
| `python -m job_agent search-links` | `▶ Run` | Generate search URLs for Indeed, Dice, ZipRecruiter, LinkedIn & Glassdoor (jobs posted in last 1-2 weeks) | `--open`, `--browser chrome` |
| `python -m job_agent fetch-jobs` | `▶ Run` | Directly search job platforms without browser (<10 jobs, <1-2 weeks old) | `--platforms dice,ziprecruiter`, `--limit 9` |
| `python -m job_agent sync-gmail` | `▶ Run` | Fetch and parse job alert emails from Gmail using OAuth 2.0 | `--max-results 25`, `--dry-run` |
| `python -m job_agent add-job` | `▶ Run` | Manually capture a job listing via URL or custom details | `--url`, `--title`, `--company`, `--description`, `--salary` |

---

### 3. Analysis & Document Tailoring
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent analyze` | `▶ Run` | Re-score all stored jobs using 0–100 weighted matcher against DOCX resume text | `--min-score 70` |
| `python -m job_agent tailor <job_id>` | `▶ Run` | Generate tailored ATS resume DOCX & cover letter in `~/Desktop/Jobs Applied/` | `--dry-run`, `--no-cover-letter` |

---

### 4. Application Tracking & Workflow
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent jobs` | `▶ Run` | List tracked jobs with status, match score, company, and platform | `--min-score N`, `--status STATUS`, `--limit 50` |
| `python -m job_agent mark-applied <job_id>` | `▶ Run` | Mark a job as Applied with timestamp (explicit approval required) | `--confirm` |
| `python -m job_agent dashboard` | `▶ Run` | View job search pipeline summary, high score opportunities, and interviews | None |
| `python -m job_agent follow-ups` | `▶ Run` | List follow-up actions due or overdue for applied jobs | None |
| `python -m job_agent report` | `▶ Run` | Generate local pipeline metrics, interview rates, and status summaries | `--period weekly` / `--period monthly` |

---

### 5. Contacts & Networking
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent add-contact "Name"` | `▶ Run` | Add recruiter, referral, or hiring manager contact | `--email`, `--role`, `--company`, `--job-id ID`, `--notes` |
| `python -m job_agent contacts` | `▶ Run` | List all local networking contacts and linked jobs | None |

---

### 6. Interview Tracking & Preparation
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent add-interview <job_id> "Date"` | `▶ Run` | Record upcoming interview details and preparation tasks | `--type "Technical"`, `--interviewer "Name"`, `--notes` |
| `python -m job_agent prepare-interview <job_id>` | `▶ Run` | Generate factual interview prep document based on JD, resume, and profile | `--dry-run` |

---

### 7. Application Answer Library
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent answers` | `▶ Run` | List saved application answers in local reusable library | `--tag TAG` |
| `python -m job_agent add-answer` | `▶ Run` | Save an approved question/answer pair to local library | `--question "..."`, `--answer "..."`, `--tags "..."` |
| `python -m job_agent suggest-answer <job_id> "Q"` | `▶ Run` | Draft answer suggestion using local resume and profile context (draft only) | `--question "..."` |

---

### 8. Maintenance, Backup & Data Management
| Command | Web Console Link | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `python -m job_agent backup [PATH]` | `▶ Run` | Create full local timestamped ZIP backup of SQLite DB, settings, `.env`, and documents | Optional output ZIP path |
| `python -m job_agent restore <backup_zip>` | `▶ Run` | Restore SQLite database and settings from a previously created ZIP backup archive | Required: ZIP file path |
| `python -m job_agent delete-job <job_id>` | `▶ Run` | Safely delete a single job record from SQLite along with its generated output files | `--confirm` |
| `python -m job_agent purge-data` | `▶ Run` | Complete wipe/purge of all database records (jobs, contacts, interviews, answers) | `--confirm` |

---

## 🛠️ Command Details & Flags Reference

### `web` & `serve`
```powershell
# Start local Web Application Console and open in browser
python -m job_agent web

# Start local server on custom port 8000
python -m job_agent serve --port 8000 --open
```

---

### `backup` & `restore`
```powershell
# Create a full local timestamped ZIP backup archive
python -m job_agent backup

# Create a backup at a custom path
python -m job_agent backup C:\Backups\my_job_agent_backup.zip

# Restore database and configuration from backup
python -m job_agent restore C:\Backups\my_job_agent_backup.zip
```

---

### `delete-job` & `purge-data`
```powershell
# Delete a single job record and its generated output folder (requires confirmation)
python -m job_agent delete-job 28 --confirm

# Purge ALL local database records and reset SQLite schema (requires confirmation)
python -m job_agent purge-data --confirm
```

---

## 🔐 Security & Privacy Safeguards Reference

1. **Air-Gapped Local-First Data Storage**:
   - All job listings, SQLite database records (`data/jobs.db`), candidate profiles, master DOCX resumes, tailored applications, contacts, and logs remain stored strictly on your local machine.
   - Zero cloud sync, no user accounts, no telemetry, and no external data uploads.

2. **Google OAuth 2.0 Least Privilege**:
   - Uses `https://www.googleapis.com/auth/gmail.readonly` exclusively. Cannot send, edit, or delete emails.

3. **Localhost Capture Server Security (`serve` / `web`)**:
   - Binds strictly to `127.0.0.1` (`http://localhost:8000/`).
   - Only processes local requests from your own browser console and bookmarklet.

4. **Git Version Control Exclusion Guardrails (`.gitignore`)**:
   - Automatically excludes `.env`, `credentials.json`, `token.json`, `*.db`, `data/`, `backups/`, and generated output files.
