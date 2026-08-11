# Job Search Agent — Documentation Index

This folder is the project document set for **job-agent**: a local-first Python application that discovers jobs across selectable USA platforms, syncs Gmail alerts, scores opportunities against a candidate profile, helps tailor truthful ATS resumes in a review-first workflow, and tracks applications in SQLite — without submitting applications automatically.

| Document | Contents |
|----------|----------|
| [CLI Cheat Sheet](../CLI_CHEAT_SHEET.md) | Complete CLI command reference |
| [Usage Guide](../USER_USAGE_GUIDE.md) | Quick workflow, web console, bookmarklet |
| [01 — Requirements](01-REQUIREMENTS.md) | Goals, scope, functional/non-functional requirements |
| [02 — Design Specification](02-DESIGN-SPECIFICATION.md) | UX flows, CLI contracts, web console design |
| [03 — Architecture](03-ARCHITECTURE.md) | System context, components, data flow, modules |
| [04 — Implementation](04-IMPLEMENTATION.md) | Module responsibilities, milestone status |
| [05 — Data Model](05-DATA-MODEL.md) | SQLite schema, statuses, config/profile fields |
| [06 — Security & Privacy](06-SECURITY-PRIVACY.md) | OAuth, secrets, PII handling |
| [07 — Testing](07-TESTING.md) | Test strategy, 81+ unit/API tests |
| [08 — Operations & Deployment](08-OPERATIONS-DEPLOYMENT.md) | Local install, Gmail setup, scheduling, backups |
| [09 — Roadmap](09-ROADMAP.md) | Completed milestones and future enhancements |
| [10 — User Guide](10-USER-GUIDE.md) | Day-to-day usage for the job seeker |
| [11 — Testing Playbook](11-TESTING-PLAYBOOK.md) | **Smoke test** — demo seed, platform search, troubleshooting |
| [12 — Web Console API](12-WEB-CONSOLE-API.md) | Local HTTP API reference for `python -m job_agent web` |

**Repository:** https://github.com/raorayala/job_agent  
**Current branch:** `cursor/initial-gmail-job-agent-scaffold`  
**Package version:** `0.1.0` (Milestones 1–8 complete)

**Recommended reading order:** [Requirements](01-REQUIREMENTS.md) → [Architecture](03-ARCHITECTURE.md) → [User Guide](10-USER-GUIDE.md) → [Testing Playbook](11-TESTING-PLAYBOOK.md)
