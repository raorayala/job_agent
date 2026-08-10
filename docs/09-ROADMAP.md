# 09 — Product & Engineering Roadmap

## 1. Vision

A trustworthy personal agent that turns noisy job-alert email and platform listings into an explainable shortlist, truthful tailored resumes, and a clean application history — without auto-applying anywhere.

## 2. Milestone plan (completed)

| # | Milestone | Deliverables | Status |
|---|-----------|--------------|--------|
| 1 | Foundation | `pyproject`, config/profile, SQLite, CLI, tests, docs | **Done** |
| 2 | Resume + profile | Master resume DOCX ingestion, validation, profile CLI | **Done** |
| 3 | Gmail sync | OAuth readonly, incremental `processed_emails`, dry-run | **Done** |
| 4 | Parsing | Platform parsers, multi-job emails, graceful missing fields | **Done** |
| 5 | Dedup + tracking | URL / company-title-location / similarity | **Done** |
| 6 | Matching | Weighted explainable scores + recommendations | **Done** |
| 7 | Tailoring + export | Review-first DOCX drafts; Desktop folder convention | **Done** |
| 8 | Web console & adapters | Top 10 platform adapters, bookmarklet, Kanban, DB explorer, progress bar, health panel | **Done** |

## 3. Recent UX improvements (post-Milestone 8)

| Feature | Description |
|---------|-------------|
| Platform checkboxes | Select which job sites to search (recommended vs experimental) |
| 3 jobs per platform default | Faster, targeted discovery (max 9 via CLI) |
| Per-platform search reports | Success/empty/error status per site in web UI |
| System health panel | DB path, Gmail/resume status, onboarding checklist |
| Demo seed | `seed-demo` CLI + **Load Demo Jobs** dashboard button |
| Recent jobs widget | All discovered jobs on dashboard (not only score ≥ 65) |
| Auto-analyze after search | Score analyzer runs after successful platform import |
| Job edit modal | Fix incomplete imports; re-score on save |
| Threading HTTP server | Dashboard stays responsive during long searches |
| Full DB purge script | `scripts/purge_database.py --confirm` |

## 4. Near-term user setup

1. Edit `.env` and `config.yaml`  
2. Place master resume DOCX  
3. Create Google OAuth Desktop credentials (optional, for Gmail)  
4. Run `python -m job_agent web` and use **Load Demo Jobs** to validate the pipeline  

See [Testing Playbook](11-TESTING-PLAYBOOK.md).

## 5. Future enhancements

| Priority | Enhancement |
|----------|-------------|
| High | Per-platform live progress during search (streaming status) |
| High | Gmail OAuth setup wizard in web UI |
| Medium | Job duplicate merge UI with explanation |
| Medium | Export CSV of Jobs Applied |
| Medium | Optional PDF via `docx2pdf` extra |
| Low | Local embedding search over saved job descriptions |
| Low | Multi-resume profile picker in web UI |

## 6. Explicitly deferred

- Auto-submit applications  
- CAPTCHA solving  
- Aggressive scraping of bot-protected sites (prefer bookmarklet + Gmail + URL import)  
- Hosted multi-user SaaS  

## 7. Success metrics (personal)

| Metric | Target |
|--------|--------|
| Time from install to visible dashboard data | &lt; 2 min with demo seed |
| Duplicate applications | Near zero |
| Resume fabrication incidents | Zero |
| Cost to run | $0 with rule-based + free Gmail API quotas |
| User confirmations for Applied | 100% explicit |

## 8. Documentation maintenance

When shipping features:

1. Update status tables in `README.md`, `docs/01`, `docs/04`, `docs/09`  
2. Add tests; update `docs/07` and `docs/11`  
3. Update [Web Console API](12-WEB-CONSOLE-API.md) for new endpoints  
