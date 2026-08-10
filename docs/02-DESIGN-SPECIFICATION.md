# 02 — Design Specification

## 1. Product principles

1. **Local-first** — processing and storage on the user’s machine by default.
2. **Human approval** — no automatic applications; Applied is an explicit confirmation after the user applies elsewhere.
3. **Truthfulness** — resume output may reorder/emphasize facts, never fabricate them.
4. **Explainability** — scores must show why a job matched or was excluded.
5. **Least privilege** — Gmail access is read-only.
6. **Graceful degradation** — works without LLM or paid APIs.

## 2. Primary user journeys

### Journey A — First-time setup

1. Install Python 3.11+, create venv, `pip install -e ".[dev]"`.
2. Copy `.env.example` → `.env`; set resume and Jobs Applied paths.
3. Edit `config.yaml` profile.
4. Place master resume DOCX.
5. Create Google OAuth Desktop credentials → `credentials.json`.
6. Run `python -m job_agent setup` and `profile`.

### Journey B — Daily scan and review (CLI or Web)

**Web (recommended):**
1. `python -m job_agent web`
2. Dashboard → review **System Health** checklist
3. **Load Demo Jobs** (first time) or **Job Discovery** → select platforms → **Find Jobs Now**
4. Review **Last Platform Search Results** and **Recently Discovered Jobs**
5. **Re-Score Jobs** if profile changed
6. **Resume Review** tab → tailor → approve/reject

**CLI:**
1. `sync-gmail` (optionally `--dry-run`) or `fetch-jobs --platforms dice,ziprecruiter,indeed --limit 3`
2. `analyze` to score jobs
3. `jobs --min-score 70` to review shortlist
4. Apply manually on employer site
5. `tailor <job_id>` → `approve-draft <job_id>` → `mark-applied <job_id> --confirm`

### Journey C — Duplicate / conflict handling

1. Sync finds a listing similar to an existing record.
2. System flags duplicate with reason (URL / company-title-location / similarity).
3. User is warned before a new record is created.
4. Existing application history is preserved.

## 3. CLI contract

| Command | Side effects | Confirmation |
|---------|--------------|--------------|
| `setup` | Creates DB/dirs; may copy `.env` | None |
| `profile` | Read-only display | None |
| `sync-gmail` | Writes jobs + processed email IDs (unless dry-run) | None for read; dry-run available |
| `analyze` | Updates scores on job rows | None |
| `jobs` | Read-only | None |
| `tailor` | Writes DOCX (+ optional notes) unless dry-run | None; dry-run available |
| `mark-applied` | Sets status Applied + date_applied | **Requires `--confirm`** |
| `web` / `serve` | Starts threaded local Web Console on `:8000` | None |
| `seed-demo` | Inserts 3 sample jobs; optional analyze | None |
| `fetch-jobs` | Writes jobs from selected platforms (default 3 each) | None |
| `dashboard` | CLI pipeline summary (mirrors web stats) | None |
| `statuses` | Read-only | None |

## 4. Recommendation labels

| Label | Typical score band | Meaning |
|-------|--------------------|---------|
| Strong match | ≥ 80 | High overlap; prioritize |
| Worth reviewing | 65–79 | Partial fit; human review |
| Low match | < 65 | Weak fit |
| Excluded | N/A | Hit exclusion rule (company/title/skill/location) |

Thresholds are configurable via `MIN_MATCH_SCORE` and matcher logic.

## 5. File and folder design

```
~/Desktop/Jobs Applied/
  master_resume.docx          # user-managed (path via .env)
  <Company>/
    <Job Title>/
      Company_JobTitle_YYYY-MM-DD_Resume.docx
      (optional notes / summary files)

./data/jobs.db                # local SQLite (gitignored)
./credentials.json            # OAuth client secrets (gitignored)
./token.json                  # OAuth user token (gitignored)
./.env                        # secrets/paths (gitignored)
./config.yaml                 # non-secret profile + platforms (committed template)
```

## 6. UX guidelines

- Show actionable tables (score, title, company, platform, status), not raw JSON by default.
- Fail with clear setup guidance when credentials/resume are missing.
- Prefer Rich console formatting that is Windows-safe (avoid unsupported Unicode in legacy consoles).
- Dry-run must describe intended actions without writing resumes or (where applicable) DB mutations.

## 7. LLM design (optional)

| Mode | Behavior |
|------|----------|
| `LLM_PROVIDER=none` | Rule-based matcher/tailor only (default) |
| `ollama` | Local model via Ollama HTTP API |
| Future cloud keys | Explicit opt-in via env; never required |

LLM may refine summaries or keyword emphasis but **must not** invent resume facts. Rule-based path remains the source of truth for hard exclusions and skill presence checks.

## 8. Error handling design

| Condition | Behavior |
|-----------|----------|
| Missing `.env` / config | Setup command creates/guides |
| Missing credentials.json | Clear OAuth setup instructions |
| Missing master resume | FileNotFoundError with path hint |
| Malformed email HTML | Parse what is possible; skip or partial job with warnings |
| Duplicate job | Warn; set duplicate flags; do not silently overwrite Applied history |
| mark-applied without `--confirm` | Exit non-zero with refusal message |

## 9. Web Console design (v1 UI)

- **Primary UI:** Embedded Web Console at `http://localhost:8000/` (not Streamlit)
- **Dashboard:** Health panel, onboarding checklist, stat cards, high-match (≥65 + Saved/Reviewing), recently discovered jobs (all scores)
- **Discovery:** Platform checkboxes (recommended/experimental tier badges), Find Jobs Now (default 3 per platform), per-platform results table, auto-analyze after search
- **Job edit:** Modal + `/api/jobs/update` with re-scoring
- **Demo seed:** Load Demo Jobs button + `seed-demo` CLI command
- **Review-first:** Draft approve/reject before promoting to Jobs Applied folder
- **Fallback capture:** Bookmarklet + URL import when automated platform fetch returns zero

See [12 — Web Console API](12-WEB-CONSOLE-API.md).
