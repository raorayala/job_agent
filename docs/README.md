# Job Search Agent — Documentation Index

This folder is the project document set for **job-agent**: a local-first Python application that monitors Gmail job alerts, scores opportunities against a candidate profile, helps tailor truthful ATS resumes, and tracks applications in SQLite — without submitting applications automatically.

| Document | Contents |
|----------|----------|
| [CLI Cheat Sheet](../CLI_CHEAT_SHEET.md) | Complete CLI command reference and cheat sheet |
| [Usage Guide](../USER_USAGE_GUIDE.md) | Quick reference workflow & 1-click Chrome bookmarklet |
| [01 — Requirements](01-REQUIREMENTS.md) | Goals, scope, functional/non-functional requirements, constraints, out of scope |
| [02 — Design Specification](02-DESIGN-SPECIFICATION.md) | Product design, UX flows, CLI contracts, safeguards |
| [03 — Architecture](03-ARCHITECTURE.md) | System context, components, data flow, package layout |
| [04 — Implementation](04-IMPLEMENTATION.md) | Module responsibilities, milestone status, coding standards |
| [05 — Data Model](05-DATA-MODEL.md) | SQLite schema, statuses, config/profile fields |
| [06 — Security & Privacy](06-SECURITY-PRIVACY.md) | OAuth, secrets, PII handling, threat notes |
| [07 — Testing](07-TESTING.md) | Test strategy, how to run, coverage targets |
| [08 — Operations & Deployment](08-OPERATIONS-DEPLOYMENT.md) | Local “production” install, Gmail setup, scheduling, backups |
| [09 — Roadmap](09-ROADMAP.md) | Milestones, remaining work, future enhancements |
| [10 — User Guide](10-USER-GUIDE.md) | Day-to-day usage for the job seeker |

**Repository:** https://github.com/raorayala/job_agent  
**Current branch (as of docs):** `cursor/initial-gmail-job-agent-scaffold`  
**Package version:** `0.1.0` (All Milestones 1–8 complete)

Start with [Requirements](01-REQUIREMENTS.md), then [Architecture](03-ARCHITECTURE.md) and the [User Guide](10-USER-GUIDE.md).
