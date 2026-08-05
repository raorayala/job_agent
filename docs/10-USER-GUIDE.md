# 10 — User Guide

## 1. What this tool does

Helps you:

- Pull job alerts from Gmail (when sync is enabled)
- Score them against your profile
- Create tailored resume drafts from your **real** experience
- Track applications locally

It does **not** apply to jobs for you.

## 2. One-time setup

### 2.1 Install

```powershell
cd C:\Users\Admin\Projects\job-search-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2.2 Environment

```powershell
copy .env.example .env
```

Edit `.env`:

- `MASTER_RESUME_PATH` — your master DOCX  
- `JOBS_APPLIED_FOLDER` — e.g. `C:\Users\Admin\Desktop\Jobs Applied`  
- `LLM_PROVIDER=none`  

### 2.3 Profile

Edit `config.yaml` → `profile` section (titles, skills, locations, salary, exclusions).

### 2.4 Master resume

Save your master resume DOCX where `.env` points. Keep a clean, complete version — tailoring will only emphasize what is already true.

### 2.5 Gmail (needed for sync)

1. Google Cloud Console → enable Gmail API  
2. OAuth Desktop client → download JSON as `credentials.json` in the project folder  
3. Run setup:

```powershell
python -m job_agent setup
python -m job_agent profile
```

## 3. Commands available now (Milestone 1)

| Command | What it does |
|---------|----------------|
| `python -m job_agent setup` | Creates DB/folders; prints OAuth checklist |
| `python -m job_agent profile` | Shows loaded profile |
| `python -m job_agent jobs` | Lists tracked jobs |
| `python -m job_agent statuses` | Lists allowed statuses |
| `python -m job_agent mark-applied <id> --confirm` | Records that **you** applied |

Coming soon (will say “not ready yet”):

- `sync-gmail`
- `analyze`
- `tailor`
- `dashboard`

## 4. Recommended daily workflow (after full MVP)

```powershell
python -m job_agent sync-gmail
python -m job_agent analyze
python -m job_agent jobs --min-score 70
python -m job_agent tailor 123
# apply manually on the job site
python -m job_agent mark-applied 123 --confirm
```

Dry runs:

```powershell
python -m job_agent sync-gmail --dry-run
python -m job_agent tailor 123 --dry-run
```

## 5. Understanding scores

| Recommendation | Meaning |
|----------------|---------|
| Strong match | High overlap — prioritize |
| Worth reviewing | Partial fit |
| Low match | Weak fit |
| Excluded | Hits an exclusion rule |

Always read missing skills and concerns before applying.

## 6. Where files go

```text
Desktop\Jobs Applied\
  <Company>\
    <Job Title>\
      Company_JobTitle_YYYY-MM-DD_Resume.docx
```

Database: `data\jobs.db` (local).

## 7. Safety reminders

- Never share `credentials.json`, `token.json`, or `.env`
- Review every tailored resume before uploading to employers
- Only use `--confirm` after you have actually applied
- Prefer `LLM_PROVIDER=none` to keep data on your machine

## 8. Getting help

- Project docs index: [docs/README.md](README.md)
- Requirements: [01-REQUIREMENTS.md](01-REQUIREMENTS.md)
- Security: [06-SECURITY-PRIVACY.md](06-SECURITY-PRIVACY.md)
- Repo: https://github.com/raorayala/job_agent
