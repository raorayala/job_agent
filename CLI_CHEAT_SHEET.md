# CLI Command Cheat Sheet — Job Search Agent

A comprehensive reference guide for all CLI commands in the **Job Search Agent** local-first personal career assistant.

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

## 📋 Categorized Cheat Sheet

### 1. Setup & Environment
| Command | Description | Default / Options |
| :--- | :--- | :--- |
| `python -m job_agent setup` | Initialize local folders, SQLite DB, verify config and OAuth settings | `--no-copy-env` |
| `python -m job_agent profile` | Display loaded candidate profile, target titles, skills, and multi-resumes | None |
| `python -m job_agent statuses` | List supported application lifecycle statuses | None |

---

### 2. Job Discovery & Ingestion
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent serve` | Start local HTTP server (`http://localhost:8000`) for 1-click Chrome bookmarklet capture | `--port 8000` |
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

### 8. Data Maintenance & Backup
| Command | Description | Key Parameters |
| :--- | :--- | :--- |
| `python -m job_agent backup` | Create full local zip backup of SQLite DB, settings, and documents | None |
| `python -m job_agent restore <backup_zip>` | Restore database and settings from local backup archive | Required: ZIP file path |
| `python -m job_agent delete-job <job_id>` | Delete a job record and its generated output files | `--confirm` |
| `python -m job_agent purge-data` | Purge all local data and reset SQLite database | `--confirm` |

---

## 🛠️ Command Details & Flags Reference

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
*Note: Direct platform search automatically filters for jobs posted within the last 14 days and applies strict batch limits (< 10 items) for safe initial processing.*

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

## 🛡️ Safety & Safeguards Summary

1. **Zero Auto-Apply**: The agent **never** fills out forms or submits job applications automatically.
2. **Explicit Confirmation**: Action commands like `mark-applied`, `delete-job`, and `purge-data` require `--confirm`.
3. **Truthful Documents**: Tailored resumes and interview guides use **100% factual content** from your master DOCX resume; zero hallucinated experience or credentials.
4. **Local Data Only**: All databases, tokens, resumes, contacts, and logs remain strictly on your local filesystem.
