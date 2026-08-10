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
| System Health card | DB path shown; onboarding checklist visible |
| Stat cards | Total jobs ≥ 3 |
| Recently Discovered Jobs | 3 demo rows with scores |
| High-Match Opportunities | May show jobs if score ≥ 65, or helpful empty message |

Alternative: click **Load Demo Jobs** on the dashboard (same as `seed-demo`). A confirmation modal appears before inserting sample data.

## Guided Chrome walkthrough (~6 minutes)

Learn every major UI flow with **30-second pauses** between steps:

```powershell
python -m job_agent test --guided
```

Chrome opens visibly. A step guide overlay appears in the bottom-right corner. The walkthrough covers: dashboard health, demo seed, re-score, job edit, platform search, resume review, Kanban, profile editor, CLI runner, database explorer, and bookmarklet install.

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

Current suite: **53 tests** (config, DB, matcher, platform fetcher, web dashboard API, demo seed, health, backup/purge).

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Stuck on "Loading high score jobs..." | Restart `python -m job_agent web`; hard refresh browser |
| 0 jobs from platform search | Check **Last Platform Search Results**; use recommended platforms or demo seed |
| Empty dashboard after CLI import | Click **Refresh**; verify same DB path in System Health card |
| Gmail errors | Configure `credentials.json`; run `sync-gmail` once for OAuth token |

See also [Web Console API](12-WEB-CONSOLE-API.md) and [CLI Cheat Sheet](../CLI_CHEAT_SHEET.md).
