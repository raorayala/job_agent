# 08 — Operations & Local Production Deployment

> **Note:** This product is **local-first**. “Production” means a reliable personal install on your workstation, not a cloud multi-tenant deployment.

## 1. System requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Windows 10/11 (primary); macOS/Linux should work via pathlib |
| Python | 3.11+ (developed with 3.14 available via `py -3`) |
| Disk | Small app + space for resumes/DB |
| Network | Required for Gmail OAuth/API and platform search; optional for LLM |
| Google account | Access to job-alert emails (optional) |
| Browser | Chrome recommended for bookmarklet capture |

## 2. Fresh install (production-on-desktop)

```powershell
cd C:\Users\Admin\Projects\job-search-agent
git checkout cursor/initial-gmail-job-agent-scaffold   # or main when merged
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
# edit .env and config.yaml
python -m job_agent setup
python -m job_agent profile
```

Dev tools (tests):

```powershell
pip install -e ".[dev]"
pytest -q -m "not e2e"    # expect 81+ passed
```

Helper scripts: `scripts\dev_setup.ps1`, `scripts\purge_database.py`

## 3. Configuration hardening checklist

1. `.env` exists and is gitignored  
2. `MASTER_RESUME_PATH` points to a real DOCX  
3. `JOBS_APPLIED_FOLDER` exists or can be created  
4. `LLM_PROVIDER=none` unless intentionally enabled  
5. `credentials.json` present for Gmail OAuth  
6. `config.yaml` profile matches your real targets  
7. Confirm `DATABASE_PATH` is on a private disk location  

## 4. Gmail API production setup

1. Google Cloud Console → project  
2. Enable **Gmail API**  
3. OAuth consent screen → add yourself as test user  
4. Credentials → OAuth client ID → **Desktop app**  
5. Download JSON → `credentials.json` in project root  
6. First sync opens browser; stores `token.json`  
7. Scope used: `gmail.readonly` only  

If auth breaks: delete `token.json` and re-run sync to re-consent.

## 5. Day-2 operations

| Task | Command / action |
|------|------------------|
| Launch Web Console | `python -m job_agent web` → `http://localhost:8000/` |
| Smoke test (no network) | `python -m job_agent seed-demo` or Dashboard **Load Demo Jobs** |
| Sync alerts | `python -m job_agent sync-gmail` |
| Platform search | `python -m job_agent fetch-jobs --platforms dice,ziprecruiter,indeed --limit 3` |
| Score jobs | `python -m job_agent analyze` (also auto-runs after web platform search) |
| Review | `python -m job_agent jobs --min-score 65` or Dashboard High-Match widget |
| Tailor | `python -m job_agent tailor <id>` |
| Approve draft | `python -m job_agent approve-draft <id>` |
| Record apply | `python -m job_agent mark-applied <id> --confirm` |
| Backup DB | `python -m job_agent backup` |
| Purge all data | `python -m job_agent purge-data --confirm` or `python scripts/purge_database.py --confirm` |

## 6. Scheduling (optional)

Use **Windows Task Scheduler** for automated sync:

- Trigger: daily morning  
- Action: run `.venv\Scripts\python.exe -m job_agent sync-gmail` then `analyze`  
- Start in: project directory  
- Prefer non-interactive token refresh (requires prior successful OAuth)

Helper: `scripts\schedule_daily_sync.ps1`, `scripts\daily_sync_job_agent.bat`

Do **not** schedule `mark-applied` or automatic submissions.

## 7. Logging

- Controlled by `LOG_LEVEL` (`INFO` default)
- Logs go to stderr via standard logging
- Web Console HTTP requests logged to stdout
- Increase to `DEBUG` when diagnosing parse/sync issues

## 8. Upgrades

```powershell
git pull
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
python -m job_agent setup
```

SQLite schema changes should be additive; if migrations are introduced later, document them in this file.

## 9. Cloud deployment (not recommended for v1)

If you later host this:

- Do **not** expose OAuth tokens or resumes on a public server without encryption and access control
- Prefer keeping Gmail tokens on the user’s machine
- Multi-user hosting is out of scope for current design

## 10. GitHub repository operations

| Item | Value |
|------|-------|
| Remote | `https://github.com/raorayala/job_agent.git` |
| Feature branch | `cursor/initial-gmail-job-agent-scaffold` |
| Suggested PR | Merge Milestone work into `main`/`master` when ready |

```powershell
git push -u origin HEAD
# then open PR on GitHub
```

## 11. Incident quick reference

| Symptom | Action |
|---------|--------|
| `origin` missing | `git remote add origin <url>` |
| Unicode console errors | Use ASCII-safe output; set `PYTHONUTF8=1` |
| Missing resume | Fix `MASTER_RESUME_PATH` in `.env` or `config.yaml` |
| Gmail 403/auth | Re-download credentials; delete token; re-auth; verify test user |
| Empty platform search | Use recommended platforms (dice, ziprecruiter, indeed); try bookmarklet or URL import |
| Web Console won't start | Check port 8000 not in use; try `--port 8001` |
| Need clean slate | `python -m job_agent purge-data --confirm` |

See [11 — Testing Playbook](11-TESTING-PLAYBOOK.md) for smoke test procedures.
