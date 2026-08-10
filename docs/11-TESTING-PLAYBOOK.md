# 11 — Testing Playbook (Smoke Test)

Quick end-to-end validation after install, upgrade, or purge. **No network required** for the fast path.

## Prerequisites

```powershell
cd C:\Users\Admin\Projects\job-search-agent
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Fast path (~2 minutes, no platform scraping)

**Terminal 1 — web server:**
```powershell
python -m job_agent web
```

**Terminal 2 — seed & verify:**
```powershell
python -m job_agent seed-demo
python -m job_agent dashboard
python -m job_agent jobs
```

**Browser:** Hard refresh `http://localhost:8000/`

| Check | Expected |
|-------|----------|
| User Mode banner | Daily workflow focus visible; admin tools hidden |
| Stat cards | Total jobs ≥ 3 (after seed) |
| Recently Discovered Jobs | 3 demo rows with scores |
| High-Match Opportunities | May show jobs if score ≥ 65, or helpful empty message |

**Admin setup:** Click **Admin Setup** in the header to open System Health, Load Demo Jobs, Profile editor, CLI runner, and DB explorer.

Alternative: click **Load Demo Jobs** on the dashboard (same as `seed-demo`). A confirmation modal appears before inserting sample data.

## Guided Chrome walkthrough (~4 minutes)

Learn every major UI flow with **15-second pauses** between steps (configurable):

```powershell
python -m job_agent test --guided
python -m job_agent test --guided --flow-pause 20   # custom pause (seconds)
```

Chrome opens visibly. A step guide overlay appears in the bottom-right corner. The walkthrough starts in **User Mode** (daily workflow: dashboard, discovery, review, Kanban), then switches to **Admin Setup** (profile, health checklist, demo seed, CLI runner, database explorer, bookmarklet).

**Admin vs User Mode:** The Web Console defaults to **User Mode** for day-to-day job search. Click **Admin Setup** in the header (or the banner link) to configure profile, load demo data, run CLI commands, and inspect the database. Mode is saved in `config.yaml` (`web_console.default_mode`) and your browser.

## Platform search path (~5+ minutes)

1. **Job Discovery** tab → keep **Dice, ZipRecruiter, Indeed** checked (recommended).
2. Click **Find Jobs Now**.
3. Review **Last Platform Search Results** (per-platform success/empty/error).
4. Analyzer runs automatically if jobs were imported.
5. Click **Refresh** on Dashboard.

**CLI equivalent:**
```powershell
python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed --limit 3
python -m job_agent analyze
python -m job_agent jobs
```

## Reset between test runs

```powershell
python scripts/purge_database.py --confirm
# or
python -m job_agent purge-data --confirm
```

## Full automated test suite

```powershell
pytest -q
```

Current suite: **65 tests** (config, DB, matcher, platform fetcher, web dashboard API, demo seed, health, backup/purge, browser E2E).

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Stuck on "Loading high score jobs..." | Restart `python -m job_agent web`; hard refresh browser |
| 0 jobs from platform search | Check **Last Platform Search Results**; use recommended platforms or demo seed |
| Empty dashboard after CLI import | Click **Refresh**; verify same DB path in System Health card |
| Gmail errors | Configure `credentials.json`; run `sync-gmail` once for OAuth token |

See also [Web Console API](12-WEB-CONSOLE-API.md) and [CLI Cheat Sheet](../CLI_CHEAT_SHEET.md).
