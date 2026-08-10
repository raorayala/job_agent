# 01 — Requirements Specification

## 1. Purpose

Build a **secure, budget-friendly, local-first** Python AI Job Search Agent that:

1. Reads job-alert emails from Gmail (ZipRecruiter, Lensa, Indeed, Glassdoor, Dice).
2. Extracts listings and evaluates them against the user’s career profile, skills, preferences, and resume.
3. Identifies best matches, explains why they match, and flags missing qualifications.
4. Creates a tailored, ATS-friendly resume version for each selected job.
5. Prevents duplicate applications and tracks every application in a “Jobs Applied” record.
6. Saves tailored resumes and application data under `Desktop/Jobs Applied`.
7. **Never** submits applications automatically; requires explicit user approval before any external action that changes application status.

## 2. Goals

| Goal | Description |
|------|-------------|
| Local-first | Default storage and processing on the user’s machine |
| Budget-friendly | Free/open-source tools; paid LLM APIs optional |
| Explainable | Match scores with clear factor breakdowns |
| Truthful resumes | Never invent employers, dates, skills, or achievements |
| Human-in-the-loop | User confirms before marking Applied |
| Traceable | Preserve Gmail message IDs and source URLs |

## 3. Non-goals (explicitly out of scope)

- Automatic job application submission
- CAPTCHA solving
- Browser automation against job platforms
- Scraping employer sites unless legally permitted (prefer email content + user-opened links)
- Cloud-hosted multi-tenant SaaS (v1 is single-user local)

## 4. Actors

| Actor | Role |
|-------|------|
| Job seeker (primary user) | Configures profile, syncs Gmail, reviews matches, applies manually, confirms Applied |
| Google OAuth / Gmail API | Provides read-only access to job-alert emails |
| Optional LLM provider | Enhances analysis/tailoring when configured; must have rule-based fallback |

## 5. Functional requirements

### 5.1 Candidate profile

Configurable fields:

- Target job titles and industries
- Required and preferred skills
- Years of experience
- Location preferences; remote / hybrid / on-site
- Salary range
- Employment type
- Work authorization requirements
- Excluded companies, titles, skills, or locations
- Master resume path
- Optional cover-letter template path

### 5.2 Discovery & Ingestion

- **Gmail OAuth 2.0**: Least-privilege read-only access (`gmail.readonly`) to sync job alert emails (filtered to last 14 days).
- **Direct Platform Search (`fetch-jobs`)**: Query ingestion from selectable USA platforms via web UI checkboxes or CLI.
  - **Default limit**: **3 jobs per platform** (max 9 via `--limit`).
  - **Recommended platforms**: Dice, ZipRecruiter, Indeed (most reliable automated fetch).
  - **Experimental platforms**: LinkedIn, Glassdoor, Monster, etc. (may return zero when sites block bots).
  - **Freshness filter**: Jobs posted within the **last 14 days**.
  - **Per-platform reports**: Web UI shows success/empty/error for each selected site.
- **Demo seed (`seed-demo`)**: Insert sample jobs for smoke testing without network.
- **1-Click Chrome Bookmarklet (`web` / `/capture`)**: Local HTTP endpoint for saving listings from Chrome while browsing.
- **Search Query URLs (`search-links`)**: Pre-formatted search URLs with freshness parameters; opens in browser.
- **URL import (`add-job`, web Import URL modal)**: Single-job import with optional manual field overrides.
- **Web Console health panel**: Shows DB path, Gmail OAuth status, master resume status, onboarding checklist.

### 5.3 Job analysis and ranking

- Normalize and deduplicate (URL, company/title/location, content similarity)
- Score 0–100 with weighted factors:
  - Required-skill overlap
  - Preferred-skill overlap
  - Job title similarity
  - Experience-level alignment
  - Location / work-mode compatibility
  - Salary compatibility
  - Exclusion rules
- Output: matched skills, missing skills, concerns, recommendation:
  - Strong match / Worth reviewing / Low match / Excluded

### 5.4 Resume tailoring

- Use only factual content from master resume + profile
- Emphasize relevant existing experience and keywords
- Preserve truthful chronology; ATS-friendly format
- Export DOCX (optional PDF)
- Naming: `Company_JobTitle_YYYY-MM-DD_Resume.docx`
- Path: `~/Desktop/Jobs Applied/<Company>/<Job Title>/`

### 5.5 Application tracker

SQLite “Jobs Applied” view fields:

- Job title, company, source platform, job URL
- Date discovered, date applied
- Application status, match score
- Tailored resume path, notes, follow-up date
- Gmail message ID, duplicate status

Statuses:

`Saved` · `Reviewing` · `Ready to apply` · `Applied` · `Interviewing` · `Rejected` · `Offer` · `Withdrawn` · `Archived`

Duplicate prevention:

1. Exact job URLs  
2. Normalized company / title / location  
3. Similarity for near-duplicates  
4. Warn before creating a duplicate record  
5. Never mark Applied without explicit confirmation  

### 5.6 User experience

CLI commands:

| Command | Purpose |
|---------|---------|
| `python -m job_agent setup` | Initialize local env / DB / checklist |
| `python -m job_agent sync-gmail [--dry-run]` | Sync job alerts |
| `python -m job_agent analyze` | Score jobs |
| `python -m job_agent jobs [--min-score N]` | List tracked jobs |
| `python -m job_agent tailor <job_id>` | Tailor resume |
| `python -m job_agent mark-applied <job_id> --confirm` | Record Applied |
| `python -m job_agent web` | Launch Web Console on `http://localhost:8000/` |
| `python -m job_agent seed-demo` | Insert sample jobs for testing |
| `python -m job_agent fetch-jobs` | Search selected platforms (default 3 jobs each) |
| `python -m job_agent purge-data --confirm` | Wipe all DB tables |
| `python -m job_agent test` | Run full suite (unit + API + browser E2E) | `--no-e2e`, `--cov`, `--install-browsers` |

Dry-run mode required for Gmail sync and resume generation.

## 6. Non-functional requirements

| Area | Requirement |
|------|-------------|
| Language | Python 3.11+ |
| Storage | SQLite for history/jobs |
| Secrets | Env vars / ignored local files; never commit credentials, tokens, `.env`, sensitive resumes |
| Architecture | Modular, testable; type hints; logging; error handling; unit tests |
| LLM | Optional and configurable; local/rule-based fallback when no API key |
| Privacy | Treat resumes, email, tokens, history as sensitive personal data |
| Cost | Runnable without paid APIs |

## 7. Supported platforms (email sources)

ZipRecruiter, Indeed, Glassdoor, Dice, Lensa — configured in `config.yaml` via sender domains and link patterns.

## 8. Acceptance criteria (product-level)

- [x] User can configure profile without code changes
- [x] Gmail sync works with readonly OAuth and does not reprocess known message IDs
- [x] Jobs are scored with explainable output
- [x] Tailored resumes do not invent facts
- [x] Duplicates are detected / warned
- [x] Applied requires `--confirm`
- [x] Artifacts land under Desktop/Jobs Applied
- [x] System runs with `LLM_PROVIDER=none`
- [x] Web Console provides platform search, health panel, demo seed, and job edit
- [x] 63 automated tests pass (unit, API, Playwright E2E)

## 9. Current fulfillment status (v0.1.0)

| Area | Status |
|------|--------|
| Project packaging, config, SQLite schema, CLI | **Done** |
| Profile loading from YAML + web Profile Editor | **Done** |
| Master-resume DOCX ingestion | **Done** |
| Gmail OAuth sync | **Done** |
| Email parsing, matching, tailoring | **Done** |
| Web Application Console (not Streamlit) | **Done** |
| Top 10 platform adapters with selectable checkboxes | **Done** |
| System health, demo seed, job edit, auto-analyze | **Done** |
| 63 automated tests (unit, API, browser E2E) | **Done** |
