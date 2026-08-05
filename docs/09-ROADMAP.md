# 09 — Product & Engineering Roadmap

## 1. Vision

A trustworthy personal agent that turns noisy job-alert email into an explainable shortlist, truthful tailored resumes, and a clean application history — without auto-applying anywhere.

## 2. Milestone plan

| # | Milestone | Deliverables | Status |
|---|-----------|--------------|--------|
| 1 | Foundation | `pyproject`, config/profile, SQLite, CLI, tests, docs | **Done** |
| 2 | Resume + profile depth | Master resume text ingestion, validation, profile CLI checks | Next |
| 3 | Gmail sync | OAuth readonly, incremental `processed_emails`, dry-run | Planned |
| 4 | Parsing | Platform parsers, graceful missing fields, multi-job emails | Planned |
| 5 | Dedup + tracking | URL / company-title-location / similarity; warn on dupes | Planned |
| 6 | Matching | Weighted explainable scores + recommendations | Planned |
| 7 | Tailoring + export | Truthful DOCX; Desktop folder convention; dry-run | Planned |
| 8 | Polish | Broader tests; optional Streamlit dashboard | Planned |

## 3. Near-term user setup (parallel to engineering)

These do not require more code:

1. Edit `.env` and `config.yaml`  
2. Place master resume  
3. Create Google OAuth Desktop credentials  

## 4. Future enhancements (post-MVP)

- Cover letter drafting from template (truthful only)
- Follow-up reminders (`follow_up_date`)
- Export CSV of Jobs Applied
- Optional PDF via `docx2pdf` extra
- Local embedding search over saved jobs
- Calendar integration for interviews
- Multi-resume profiles (e.g., backend vs data)

## 5. Explicitly deferred

- Auto-submit applications
- CAPTCHA solving
- Aggressive third-party site scraping
- Hosted multi-user SaaS

## 6. Success metrics (personal)

| Metric | Target |
|--------|--------|
| Time from email to shortlist | Minutes, not hours |
| Duplicate applications | Near zero |
| Resume fabrication incidents | Zero |
| Cost to run | $0 with rule-based + free Gmail API quotas |
| User confirmations for Applied | 100% explicit |

## 7. Documentation maintenance

When a milestone lands:

1. Update status tables in `README.md`, `docs/01`, `docs/04`, `docs/09`  
2. Add tests to `docs/07`  
3. Update user guide commands that become available  
