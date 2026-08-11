# 12 — Web Console HTTP API

Local-only REST-style endpoints served by `python -m job_agent web` on `http://127.0.0.1:8000/`. **Not intended for external exposure.**

Server uses `ThreadingHTTPServer` so long platform searches do not block stats/refresh requests.

### Auth headers (privileged routes)

| Header | Required for | Notes |
|--------|--------------|-------|
| `X-Console-Token` | `/api/db/*`, `/api/run-command`, `/api/console-settings` | From `WEB_CONSOLE_TOKEN` or `data/web_console_token` |
| `X-Console-Role: admin` | `/api/db/*`, POST `/api/console-settings`, destructive CLI via `/api/run-command` | Dashboard sets this in Admin module |

`/api/db/query` accepts **read-only** SQL only. `/api/run-command` is allowlisted to known CLI commands.

## Pages

| Path | Description |
|------|-------------|
| `/` | Main Web Console dashboard |
| `/capture` | Bookmarklet installer page |
| `/api/calendar.ics` | iCalendar export for follow-ups/interviews |

## Read APIs (GET)

| Path | Returns |
|------|---------|
| `/api/stats` | `total_jobs`, `status_counts`, `high_score_jobs`, `recent_jobs`, `health` (DB path, Gmail/resume status, onboarding checklist) |
| `/api/jobs` | All tracked jobs (up to 200) |
| `/api/jobs/{id}` | Single job details for edit modal |
| `/api/activities` | Recent activity feed (20 events) |
| `/api/profile` | Candidate profile JSON |
| `/api/commands` | CLI command metadata for runner tab |
| `/api/email/providers` | Gmail + Outlook/Hotmail configuration readiness |
| `/api/email/sync` | POST `{ "provider": "gmail\|outlook\|hotmail", "max_results?", "dry_run?" }` sync job-alert emails |
| `/api/draft/get?job_id=` | Draft paths, approval status, diff summary, optional `optimize` bundle |
| `/api/db/tables` | Database table list |
| `/api/db/table-data?table=jobs` | Paginated table rows |

## Write APIs (POST)

| Path | Body | Description |
|------|------|-------------|
| `/api/jobs/find` | `{ "platforms": ["dice","indeed"], "limit": 3 }` | Platform search + import; returns `platform_reports[]` per site |
| `/api/jobs/analyze` | `{}` | Re-score all jobs against profile |
| `/api/jobs/seed-demo` | `{}` | Insert 3 demo jobs + analyze |
| `/api/jobs/update` | `{ "job_id": 1, "title", "company", "description", "location" }` | Edit job + re-score |
| `/api/jobs/import-url` | `{ "url": "https://..." }` | URL import |
| `/api/jobs/update-status` | `{ "job_id", "status", "confirm_applied?" }` | Kanban status change; `Applied` requires `confirm_applied: true` |
| `/api/draft/create` | `{ "job_id" }` | Generate resume draft |
| `/api/draft/approve` | `{ "job_id" }` | Approve draft |
| `/api/draft/reject` | `{ "job_id" }` | Reject draft |
| `/api/draft/optimize` | `{ "job_id" }` | AI Optimize: keyword gaps + editable rewrite suggestions |
| `/api/draft/suggestion` | `{ "job_id", "suggestion_id", "action": "accept\|reject\|edit", "edited_text?" }` | Update one optimize suggestion |
| `/api/draft/optimize/apply` | `{ "job_id" }` | Apply accepted/edited suggestions into draft DOCX |
| `/api/auto-apply/eligibility` | GET `?job_id=` | Check review-gated Auto Apply readiness |
| `/api/auto-apply/launch` | `{ "job_id", "confirm?", "mark_as_applied?", "open_browser?", "open_resume_folder?" }` | Assisted Auto Apply (open job URL + resume folder; optional mark Applied) |
| `/api/linkedin/optimize` | `{ "target_role?", "job_description?", "about_context?" }` | Dedicated LinkedIn headline/About/skills optimization drafts |
| `/api/profile/optimize` | `{ "job_description?", "industry_role?" }` | Profile readiness, keyword gaps, skills audit, headline/About drafts |
| `/api/run-command` | `{ "command", "args" }` | Execute CLI from web runner |
| `/api/console-settings` | `{ "default_mode": "user\|admin", "guided_flow_pause_seconds": 15, "setup_locked": false }` | Persist console mode and guided-flow timing to `config.yaml` |
| `/api/db/cleanup` | `{ "action" }` | duplicates / stale / all purge |
| `/capture` | `{ title, company, url, description }` | Bookmarklet job capture |

## Platform search response example

```json
{
  "status": "success",
  "jobs_recorded": 2,
  "platforms_searched": ["dice", "indeed"],
  "limit_per_platform": 3,
  "platform_reports": [
    {
      "platform": "dice",
      "fetched": 2,
      "imported": 2,
      "status": "success",
      "message": "Imported 2 job(s)",
      "tier": "recommended"
    },
    {
      "platform": "linkedin",
      "fetched": 0,
      "imported": 0,
      "status": "empty",
      "message": "No listings returned...",
      "tier": "experimental"
    }
  ]
}
```

## Health object (in `/api/stats`)

```json
{
  "database_path": "C:/.../data/jobs.db",
  "total_jobs": 3,
  "gmail": { "status": "not_configured|needs_auth|token_present", "message": "..." },
  "master_resume": { "status": "ready|missing_file|not_configured", "path": "..." },
  "onboarding_steps": [ { "id": "profile", "label": "...", "done": true } ],
  "onboarding_complete": false
}
```

## Recommended vs experimental platforms

| Tier | Platforms |
|------|-----------|
| **Recommended** | Dice, ZipRecruiter, Indeed |
| **Experimental** | LinkedIn, Glassdoor, Monster, CareerBuilder, SimplyHired, Wellfound, Google Jobs |

Experimental adapters may return zero results when sites block automated fetch. Use bookmarklet, URL import, or Gmail sync as fallbacks.
