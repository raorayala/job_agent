# CLI Command Cheat Sheet — Job Search Agent

A comprehensive reference guide for all CLI commands, maintenance procedures, and security safeguards in the **Job Search Agent** local-first personal career assistant.

---

## ⚡ Daily Workflow Quick Start

```powershell
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
| Command | Description | Default / Options |
| :--- | :--- | :--- |
| `python -m job_agent setup` | Initialize local runtime folders, SQLite DB schema, verify config and OAuth credentials | `--no-copy-env` |
| `python -m job_agent profile` | Display loaded candidate profile, target titles, skills, and multi-resumes | None |
| `python -m job_agent statuses` | List supported application lifecycle statuses | None |

---

### 2. Job Discovery & Ingestion
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent serve` | Start local HTTP server (`http://127.0.0.1:8000`) for 1-click Chrome bookmarklet capture | `--port 8000` |
| `python -m job_agent search-links` | Generate search URLs for Indeed, Dice, ZipRecruiter, LinkedIn & Glassdoor (jobs posted in last 1-2 weeks) | `--open`, `--browser chrome` |
| `python -m job_agent fetch-jobs` | Directly search job platforms without browser (<10 jobs, <1-2 weeks old) | `--platforms dice,ziprecruiter`, `--limit 9` |
| `python -m job_agent sync-gmail` | Fetch and parse job alert emails from Gmail using OAuth 2.0 | `--max-results 25`, `--dry-run` |
| `python -m job_agent add-job` | Manually capture a job listing via URL or custom details | `--url`, `--title`, `--company`, `--description`, `--salary` |

---

### 3. Analysis & Document Tailoring
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent analyze` | Re-score all stored jobs using 0–100 weighted matcher against DOCX resume text | `--min-score 70` |
| `python -m job_agent tailor <job_id>` | Generate tailored ATS resume DOCX & cover letter in `~/Desktop/Jobs Applied/` | `--dry-run`, `--no-cover-letter` |

---

### 4. Application Tracking & Workflow
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent jobs` | List tracked jobs with status, match score, company, and platform | `--min-score N`, `--status STATUS`, `--limit 50` |
| `python -m job_agent mark-applied <job_id>` | Mark a job as Applied with timestamp (explicit approval required) | `--confirm` |
| `python -m job_agent dashboard` | View high-score jobs, follow-ups due, upcoming interviews, and application metrics | None |
| `python -m job_agent follow-ups` | List follow-up actions due or overdue for applied jobs | None |
| `python -m job_agent report` | Generate local pipeline metrics, interview rates, and status summaries | `--period weekly` / `--period monthly` |

---

### 5. Contacts & Networking
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent add-contact "Name"` | Add recruiter, referral, or hiring manager contact | `--email`, `--role`, `--company`, `--job-id ID`, `--notes` |
| `python -m job_agent contacts` | List all local networking contacts and linked jobs | None |

---

### 6. Interview Tracking & Preparation
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent add-interview <job_id> "Date"` | Record upcoming interview details and preparation tasks | `--type "Technical"`, `--interviewer "Name"`, `--notes` |
| `python -m job_agent prepare-interview <job_id>` | Generate factual interview prep document based on JD, resume, and profile | `--dry-run` |

---

### 7. Application Answer Library
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent answers` | List saved application answers in local reusable library | `--tag TAG` |
| `python -m job_agent add-answer` | Save an approved question/answer pair to local library | `--question "..."`, `--answer "..."`, `--tags "..."` |
| `python -m job_agent suggest-answer <job_id> "Q"` | Draft answer suggestion using local resume and profile context (draft only) | `--question "..."` |

---

### 8. Maintenance, Backup & Data Management
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent backup [PATH]` | Create full local timestamped ZIP backup of SQLite DB, settings, `.env`, and documents | Optional output ZIP path |
| `python -m job_agent restore <backup_zip>` | Restore SQLite database and settings from a previously created ZIP backup archive | Required: ZIP file path |
| `python -m job_agent delete-job <job_id>` | Safely delete a single job record from SQLite along with its generated output files | `--confirm` |
| `python -m job_agent purge-data` | Complete wipe/purge of all database records (jobs, contacts, interviews, answers) | `--confirm` |
| `powershell -ExecutionPolicy Bypass -File scripts/schedule_daily_sync.ps1` | Configure Windows Task Scheduler for daily background syncs (`sync-gmail` & `analyze`) | None |

---

## 🛠️ Command Details & Flags Reference

### `backup` & `restore`
```powershell
# Create a full local timestamped ZIP backup archive
python -m job_agent backup

# Create a backup at a custom path
python -m job_agent backup C:\Backups\my_job_agent_backup.zip

# Restore database and configuration from backup
python -m job_agent restore C:\Backups\my_job_agent_backup.zip
```
*Note: Backups archive your SQLite database (`data/jobs.db`), `.env` file, `config.yaml`, and tailored document outputs into a single encrypted-capable ZIP file.*

---

### `delete-job` & `purge-data`
```powershell
# Delete a single job record and its generated output folder (requires confirmation)
python -m job_agent delete-job 28 --confirm

# Purge ALL local database records and reset SQLite schema (requires confirmation)
python -m job_agent purge-data --confirm
```

---

### `search-links`
```powershell
python -m job_agent search-links [OPTIONS]

Options:
  --open / --no-open      Automatically launch search links in your browser [default: --no-open]
  --browser TEXT          Browser to use when opening links: 'chrome', 'edge', or 'default' [default: chrome]
  --help                  Show help message
```
*Note: Generated query URLs include date filters ensuring search results are posted within the last 1–2 weeks (14 days max).*

---

### `fetch-jobs`
```powershell
python -m job_agent fetch-jobs [OPTIONS]

Options:
  --platforms TEXT        Comma-separated platforms to search: 'dice', 'ziprecruiter' [default: dice,ziprecruiter]
  --limit INTEGER         Max jobs per platform (enforces <10 jobs per run) [default: 9]
  --help                  Show help message
```

---

### `mark-applied`
```powershell
python -m job_agent mark-applied JOB_ID [OPTIONS]

Arguments:
  JOB_ID                  Database integer ID of the job [required]

Options:
  --confirm / --no-confirm  Explicitly confirm marking job as Applied [default: --no-confirm]
  --help                    Show help message
```

---

## 🔐 Security & Privacy Safeguards Reference

### 1. Air-Gapped Local-First Data Storage
- **100% Local Filesystem**: All job listings, SQLite database records (`data/jobs.db`), candidate profiles, master DOCX resumes, tailored applications, contacts, and logs remain stored strictly on your local machine.
- **Zero Cloud Sync & Telemetry**: No user accounts, sign-in, remote databases, analytics tracking, advertising, or external data uploads.

### 2. Google OAuth 2.0 Least Privilege
- **Read-Only Scope**: Uses `https://www.googleapis.com/auth/gmail.readonly` exclusively.
- **No Email Sending or Modifying**: The agent cannot send, edit, or delete emails in your Gmail account.
- **Local Credentials**: OAuth client secrets (`credentials.json`) and token cache (`token.json`) are stored locally and ignored by Git.

### 3. Localhost Capture Server Security (`serve`)
- **Strict Local Binding**: The capture endpoint binds exclusively to `127.0.0.1` (`localhost:8000`).
- **User Review Guard**: Captured listings require user confirmation before saving and are never auto-submitted.

### 4. Git Version Control Exclusion Guardrails (`.gitignore`)
- Automatically excludes sensitive assets from version control:
  - Secrets & Credentials: `.env`, `credentials.json`, `token.json`
  - Local Databases & Backups: `*.db`, `*.sqlite`, `data/`, `backups/`
  - Personal Output Files: `~/Desktop/Jobs Applied/`, generated DOCX/PDF resumes, log files

### 5. Truthfulness Safeguards
- **Zero Hallucination Policy**: Tailored resumes and cover letters reorder and emphasize only verified experience from your master DOCX resume. Never invents employers, titles, dates, or skills.
- **Draft Application Answers**: Suggested answers (`suggest-answer`) are explicitly tagged as `[DRAFT]` for user review before submission.

### 6. Human-In-The-Loop Approval Gates
- **Zero Auto-Apply**: The agent **never** auto-fills forms or auto-submits job applications.
- **Confirmation Flags**: Destructive and status-changing actions require explicit `--confirm` parameters.
