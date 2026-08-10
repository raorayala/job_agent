# CLI Command Cheat Sheet — Job Search Agent

A comprehensive reference guide for all CLI commands, review-first resume approvals, maintenance procedures, web application controls, progress bar events, and security safeguards in the **Job Search Agent** local-first personal career assistant.

---

## 🌐 Interactive Web Application Dashboard & CLI Runner

Instead of running commands manually in your terminal, launch the local **Web Application Console**:

```powershell
python -m job_agent web
```

This opens `http://localhost:8000/` in your browser featuring:
- **Global Event Progress Bar**: Real-time animated progress bar (`#global-progress-wrapper`) displaying event status messages and completion percentage for all web actions.
- **Interactive CLI Cheat Sheet**: Form controls and **"▶ Run Command"** buttons for all CLI commands.
- **Live Terminal Console**: Streams command output and server logs directly onto the web page.
- **Top 10 USA Job Discovery**: Platform cards for Indeed, LinkedIn, Glassdoor, Monster, ZipRecruiter, CareerBuilder, SimplyHired, Dice, Wellfound, and Google Jobs.
- **Automated URL Import Modal**: Paste a job page URL to extract details automatically.
- **Resume Review & Approval Screen**: 3-way view (Master Resume vs Draft Resume vs Finalized Resume) with explicit approval controls.
- **Visual Kanban Board**: 1-click status transitions across application stages.
- **Database Explorer & Cleanup**: Browse tables, execute SQL queries, and purge test data.
- **Profile & Skills Editor**: Field-by-field helper text showing live `config.yaml` values, with quick keyword addition controls.

---

## ⚡ Daily Workflow Quick Start

```powershell
# 0. Setup local DB and configuration (optionally opens 1-click Chrome bookmarklet setup page)
python -m job_agent setup --open-bookmarklet

# 1. Launch Interactive Web Console & CLI Cheat Sheet (Recommended)
python -m job_agent web

# 2. Open tailored search query links for top 10 USA platforms (posted in last 1-2 weeks)
python -m job_agent search-links --open --browser system

# 3. Fetch jobs directly from platforms (<10 jobs per platform, posted in last 1-2 weeks)
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed,linkedin,glassdoor --limit 9

# 4. Automated URL job import
python -m job_agent add-job --url "https://www.linkedin.com/jobs/view/123456"

# 5. Sync job alert emails from Gmail (received in last 14 days)
python -m job_agent sync-gmail

# 6. Re-score all saved jobs against your master resume text and candidate profile
python -m job_agent analyze

# 7. List high-matching opportunities
python -m job_agent jobs --min-score 60

# 8. Generate ATS tailored DOCX resume draft into _drafts/ folder
python -m job_agent tailor <job_id>

# 9. Explicitly approve and promote draft into finalized jobapplied folder
python -m job_agent approve-draft <job_id>

# 10. Mark as applied after manual submission on job platform
python -m job_agent mark-applied <job_id> --confirm

# 11. View search pipeline dashboard & follow-ups
python -m job_agent dashboard
python -m job_agent follow-ups
```

---

## 📋 Categorized Command Reference

### 1. Setup & Environment
| Command | Description | Default / Options |
| :--- | :--- | :--- |
| `python -m job_agent setup` | Initialize local runtime folders, SQLite DB schema, verify config and OAuth credentials | `--no-copy-env`, `--open-bookmarklet` |
| `python -m job_agent profile` | Display loaded candidate profile, target titles, skills, and multi-resumes | None |
| `python -m job_agent statuses` | List supported application lifecycle statuses | None |

---

### 2. Job Discovery & Ingestion
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent web` | Launch Interactive Web Application Console & CLI Cheat Sheet | `--port 8000`, `--open` |
| `python -m job_agent search-links` | Generate search URLs for top 10 USA platforms (jobs posted in last 1-2 weeks) | `--open`, `--browser system` |
| `python -m job_agent fetch-jobs` | Directly search job platforms without browser (<10 jobs, <1-2 weeks old) | `--platforms dice,ziprecruiter,indeed`, `--limit 9` |
| `python -m job_agent add-job` | Automated job import from a URL (extracts title, company, location, and description) | `--url`, `--title`, `--company`, `--description` |
| `python -m job_agent sync-gmail` | Fetch and parse job alert emails from Gmail using OAuth 2.0 | `--max-results 25`, `--dry-run` |

---

### 3. Review-First Resume Analysis & Tailoring
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent analyze` | Re-score all stored jobs using 0–100 weighted matcher against DOCX resume text | `--min-score 70` |
| `python -m job_agent tailor <job_id>` | Generate ATS tailored DOCX resume draft into `_drafts/` awaiting review | `--dry-run`, `--no-cover-letter` |
| `python -m job_agent approve-draft <job_id>` | Explicitly approve and promote resume draft into finalized `jobapplied` folder | None |
| `python -m job_agent reject-draft <job_id>` | Reject resume draft and revert job status | None |

---

### 4. Application Tracking & Workflow
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent jobs` | List tracked jobs with status, match score, company, and platform | `--min-score N`, `--status STATUS`, `--limit 50` |
| `python -m job_agent mark-applied <job_id>` | Mark a job as Applied with timestamp (explicit approval required) | `--confirm` |
| `python -m job_agent dashboard` | View job search pipeline summary, high score opportunities, and activity feed | None |
| `python -m job_agent follow-ups` | List follow-up actions due or overdue for applied jobs | None |
| `python -m job_agent report` | Generate local pipeline metrics, interview rates, and status summaries | `--period weekly` / `--period monthly` |

---

### 5. Maintenance, Cleanup & Backup
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent cleanup` | Clean up duplicate jobs, stale/excluded listings, or reset database | `--action duplicates|stale|status|all`, `--confirm` |
| `python -m job_agent backup [PATH]` | Create full local timestamped ZIP backup of SQLite DB, settings, `.env`, and documents | Optional output ZIP path |
| `python -m job_agent restore <backup_zip>` | Restore SQLite database and settings from a previously created ZIP backup archive | Required: ZIP file path |
| `python -m job_agent delete-job <job_id>` | Safely delete a single job record from SQLite along with its generated output files | `--confirm` |
| `python -m job_agent purge-data` | Complete wipe/purge of all database records (jobs, contacts, interviews, answers) | `--confirm` |

---

## 🔐 Security & Privacy Safeguards Reference

1. **Air-Gapped Local-First Data Storage**:
   - All job listings, SQLite database records (`data/jobs.db`), candidate profiles, master DOCX resumes, tailored applications, contacts, and logs remain stored strictly on your local machine.
   - Zero cloud sync, no user accounts, no telemetry, and no external data uploads.

2. **Review-First Approval Guarantee**:
   - Tailored resumes are generated into `_drafts/` first. Master resumes and finalized applied resumes are **never overwritten** until you explicitly approve the draft.

3. **Google OAuth 2.0 Least Privilege**:
   - Uses `https://www.googleapis.com/auth/gmail.readonly` exclusively. Cannot send, edit, or delete emails.

4. **Localhost Console Security (`web`)**:
   - Binds strictly to `127.0.0.1` (`http://localhost:8000/`).

5. **Git Version Control Exclusion Guardrails (`.gitignore`)**:
   - Automatically excludes `.env`, `credentials.json`, `token.json`, `*.db`, `data/`, `backups/`, and generated output files.
