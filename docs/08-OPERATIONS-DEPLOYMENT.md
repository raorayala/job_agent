# 08 — Operations & Local Production Deployment

> **Note:** This product is **local-first**. “Production” means a reliable personal install on your workstation, not a cloud multi-tenant deployment.

## 1. System requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Windows 10/11 (primary); macOS/Linux should work via pathlib |
| Python | 3.11+ (developed with 3.14 available via `py -3`) |
| Disk | Small app + space for resumes/DB |
| Network | Required for Gmail OAuth/API; optional for LLM |
| Google account | Access to job-alert emails |

## 2. Fresh install (production-on-desktop)

```powershell
cd C:\Users\Admin\Projects\job-search-agent
git checkout cursor/initial-gmail-job-agent-scaffold   # or main when merged
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
copy .env.example .env
# edit .env and config.yaml
python -m job_agent setup
python -m job_agent profile
```

Dev tools (tests):

```powershell
pip install -e ".[dev]"
pytest -q
```

Helper script: `scripts\dev_setup.ps1`

## 3. Configuration hardening checklist

1. `.env` exists and is gitignored  
2. `MASTER_RESUME_PATH` points to a real DOCX  
3. `JOBS_APPLIED_FOLDER` exists or can be created  
4. `LLM_PROVIDER=none` unless intentionally enabled  
5. `credentials.json` present for Gmail (after Milestone 3)  
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
| Sync alerts | `python -m job_agent sync-gmail` (Milestone 3+) |
| Score jobs | `python -m job_agent analyze` |
| Review | `python -m job_agent jobs --min-score 70` |
| Tailor | `python -m job_agent tailor <id>` |
| Record apply | `python -m job_agent mark-applied <id> --confirm` |
| Backup DB | Copy `data\jobs.db` to a secure backup location |
| Backup resumes | Copy `Desktop\Jobs Applied` |

## 6. Scheduling (optional)

Use **Windows Task Scheduler** after sync/analyze exist:

- Trigger: daily morning  
- Action: run `.venv\Scripts\python.exe -m job_agent sync-gmail` then `analyze`  
- Start in: project directory  
- Prefer non-interactive token refresh (requires prior successful OAuth)

Do **not** schedule `mark-applied` or automatic submissions.

## 7. Logging

- Controlled by `LOG_LEVEL` (`INFO` default)
- Logs go to stderr via standard logging
- Increase to `DEBUG` when diagnosing parse/sync issues

## 8. Upgrades

```powershell
git pull
.\.venv\Scripts\Activate.ps1
pip install -e .
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
| Missing resume | Fix `MASTER_RESUME_PATH` |
| Gmail 403/auth | Re-download credentials; delete token; re-auth; verify test user |
| Empty jobs list | Expected until sync milestone; then check search query |
