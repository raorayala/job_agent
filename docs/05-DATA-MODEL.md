# 05 — Data Model

## 1. Overview

Persistence uses **SQLite** (default `./data/jobs.db`) via SQLAlchemy 2.x.

Six primary tables:

- `jobs` — discovered / tracked opportunities (“Jobs Applied” view) with B-Tree indexes
- `processed_emails` — incremental Gmail sync cursor by message ID
- `activity_logs` — audit feed for discovery, import, analysis, draft generation, and approval events
- `contacts` — networking contacts linked to jobs
- `interviews` — interview dates, types, participants, and prep tasks
- `application_answers` — reusable Q&A answer library

## 2. Entity relationship

```text
processed_emails (gmail_message_id)
        │
        │ 1:N (logical; jobs also store gmail_message_id)
        ▼
      jobs ◄─── contacts (job_id)
        │  ◄─── interviews (job_id)
        │  ◄─── activity_logs (job_id)
```

## 3. Table: `jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `title` | VARCHAR(300) | Job title |
| `company` | VARCHAR(200) | Default `Unknown` |
| `location` | VARCHAR(200) NULL | |
| `source_platform` | VARCHAR(50) | indeed, linkedin, ziprecruiter, … |
| `job_url` | VARCHAR(1000) | Original URL |
| `job_url_normalized` | VARCHAR(1000) UNIQUE | Dedupe key |
| `salary` | VARCHAR(200) NULL | Raw salary string |
| `employment_type` | VARCHAR(100) NULL | |
| `description` | TEXT NULL | Job description extract |
| `date_discovered` | DATETIME TZ | Default UTC now (Indexed) |
| `date_applied` | DATETIME TZ NULL | Set on Applied |
| `follow_up_date` | DATETIME TZ NULL | Auto-set on Applied |
| `status` | VARCHAR(50) | See ApplicationStatus (Indexed) |
| `match_score` | FLOAT NULL | 0–100 (Indexed) |
| `recommendation` | VARCHAR(50) NULL | Strong match, Worth reviewing, Low match, Excluded |
| `match_summary` | TEXT NULL | Explainable summary |
| `matched_skills` | TEXT NULL | Serialized list |
| `missing_skills` | TEXT NULL | Serialized list |
| `concerns` | TEXT NULL | Serialized list |
| `tailored_resume_path` | VARCHAR(1000) NULL | |
| `draft_resume_path` | VARCHAR(1000) NULL | Path in `_drafts/` folder |
| `draft_summary_path` | VARCHAR(1000) NULL | Path to draft summary |
| `final_resume_path` | VARCHAR(1000) NULL | Path in `jobapplied` folder |
| `approval_status` | VARCHAR(50) NULL | Awaiting Review, Approved, Rejected |
| `diff_summary` | TEXT NULL | Keyword alignment diff |
| `notes` / `user_notes` | TEXT NULL | Notes and user overrides |
| `gmail_message_id` | VARCHAR(200) NULL | Gmail message ID (Indexed) |
| `is_duplicate` | BOOLEAN | Default false |
| `company_normalized` / `title_normalized` | VARCHAR NULL | Dedupe index (`ix_jobs_company_title_norm`) |
| `priority` | FLOAT | Default 50.0 |
| `is_stale` | BOOLEAN | Default false |
| `created_at` / `updated_at` | DATETIME TZ | Audit timestamps |

## 4. Table: `processed_emails`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `gmail_message_id` | VARCHAR(200) UNIQUE | Incremental sync key |
| `processed_at` | DATETIME TZ | |
| `subject` | VARCHAR(500) NULL | Debug aid |
| `jobs_extracted` | INTEGER | Count from that email |

## 5. Application statuses

Stored as display strings matching `ApplicationStatus`:

| Status | Meaning |
|--------|---------|
| Saved | Ingested / bookmarked |
| Reviewing | User inspecting |
| Ready to apply | Resume ready / approved to apply manually |
| Applied | User confirmed they applied |
| Interviewing | Interview stage |
| Rejected | Rejected by employer |
| Offer | Offer received |
| Withdrawn | User withdrew |
| Archived | Closed / ignored |

**Transition rule:** entering `Applied` requires explicit confirmation (`--confirm` / `confirm_applied=True`).

## 6. Config profile model (YAML → `CandidateProfile`)

| Field | YAML key | Type |
|-------|----------|------|
| Target titles | `profile.target_titles` | list[str] |
| Industries | `profile.industries` | list[str] |
| Required skills | `profile.required_skills` | list[str] |
| Preferred skills | `profile.preferred_skills` | list[str] |
| Years experience | `profile.years_experience` | int |
| Locations | `profile.locations` | list[str] |
| Work modes | `profile.work_modes` | list[str] (normalized lower) |
| Salary min/max | `profile.salary_min` / `salary_max` | int \| null |
| Currency | `profile.salary_currency` | str |
| Employment types | `profile.employment_types` | list[str] |
| Work authorization | `profile.work_authorization` | str \| null |
| Exclusions | `excluded_*` | lists |
| Master resume | `master_resume_path` or env | str \| null |
| Cover letter | `cover_letter_template_path` | str \| null |

## 7. Runtime settings (`.env` → `Settings`)

| Env var | Purpose |
|---------|---------|
| `MASTER_RESUME_PATH` | Master DOCX |
| `JOBS_APPLIED_FOLDER` | Export root |
| `GMAIL_CREDENTIALS_PATH` | OAuth client JSON |
| `GMAIL_TOKEN_PATH` | Cached user token |
| `GMAIL_SEARCH_QUERY` | Gmail search string |
| `GMAIL_LABEL` | Optional label filter |
| `MIN_MATCH_SCORE` | Default filter threshold |
| `LLM_PROVIDER` | `none` / `ollama` / … |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local LLM |
| `DATABASE_PATH` | SQLite file |
| `LOG_LEVEL` | Logging verbosity |
| `CONFIG_PATH` | Override config.yaml |

## 8. In-memory domain objects

- `ParsedJob` — parser output before persistence  
- `MatchExplanation` — score, recommendation, skills, concerns, factor_scores  
- `DuplicateCheckResult` — duplicate decision payload  

## 9. Future schema considerations

- Child table `job_extractions` if one email yields many jobs and unique `gmail_message_id` on `jobs` is too strict
- `application_events` append-only log for status transitions
- Full-text index on descriptions for local search
