# 06 — Security & Privacy

## 1. Sensitivity classification

| Data | Sensitivity | Storage |
|------|-------------|---------|
| OAuth client secrets (`credentials.json`) | High | Local, gitignored |
| OAuth access/refresh token (`token.json`) | High | Local, gitignored |
| `.env` paths and optional API keys | High | Local, gitignored |
| Master / tailored resumes | High (PII) | Local Desktop / paths; not committed |
| Job email bodies / descriptions | Medium–High | SQLite `data/jobs.db` (gitignored) |
| Application history | Medium–High | SQLite |
| `config.yaml` profile template | Low–Medium | May be committed if non-sensitive |

## 2. Gmail OAuth

- Scope: `https://www.googleapis.com/auth/gmail.readonly` only
- Client type: Desktop app
- Token refresh handled by google-auth libraries
- Do not request send/modify/delete scopes
- Add only the user’s Google account as OAuth test user while app is in testing

### Setup checklist

1. Enable Gmail API in Google Cloud project  
2. Configure OAuth consent screen  
3. Create Desktop OAuth client  
4. Save JSON as `credentials.json` (never commit)  
5. First interactive auth writes `token.json`  

## 3. Secrets handling

**Never commit:**

- `.env`, `.env.local`
- `credentials.json`, `client_secret*.json`
- `token.json`, `token.pickle`
- `data/*.db`
- Personal resumes under templates or Desktop exports

`.gitignore` is configured for these paths. Review `git status` before every commit.

## 4. Application submission policy

- The agent **must not** automate form submission on job boards
- The agent **must not** solve CAPTCHAs
- Marking `Applied` requires explicit user confirmation (`--confirm`)
- Resume generation and Gmail sync support dry-run modes

## 5. Resume truthfulness policy

- Tailoring may emphasize existing content and keywords present in the master resume/profile
- Forbidden: inventing employers, dates, degrees, certifications, metrics, or skills the candidate does not have
- Generated ATS sections that are advisory must be clearly marked for human review when used

## 6. LLM / third-party data sharing

| Provider mode | Risk |
|---------------|------|
| `LLM_PROVIDER=none` | No job text leaves the machine for LLM inference |
| Ollama local | Stays on machine if Ollama is local-only |
| Cloud LLM APIs | Job descriptions / resume excerpts may leave the machine — **opt-in only** |

Recommendation: keep `LLM_PROVIDER=none` unless you accept third-party processing of personal/job data.

## 7. Threat notes (lightweight)

| Threat | Mitigation |
|--------|------------|
| Credential leak via git | gitignore + review before push |
| Token theft from disk | File system permissions; don’t sync token to cloud folders |
| Over-broad Gmail scope | Readonly only |
| Accidental “Applied” marking | `--confirm` gate |
| Fabricated resume harming trust | Truthfulness rules in tailor module |
| Malicious email HTML | Parse with BS4; no arbitrary code execution from email |

## 8. Backup & deletion

- Backup `data/jobs.db` and `Desktop/Jobs Applied` if you need history retention
- To revoke Gmail access: Google Account → Security → Third-party access → remove the app; delete local `token.json`
- To wipe local app data: `python -m job_agent purge-data --confirm` (all six SQLite tables) or delete `data/jobs.db`, `token.json`, and generated resume folders manually (keep master resume if desired)

## 9. Web Console (local HTTP)

- Binds to `127.0.0.1` only (`http://localhost:8000/`) — not exposed to the network
- Bookmarklet install status (`Mark as Installed`) is stored in browser `localStorage` only; the server cannot verify Chrome bookmark bar state
- **Local API token**: privileged routes (`/api/db/*`, `/api/run-command`, `/api/console-settings`) require header `X-Console-Token`. Set `WEB_CONSOLE_TOKEN` in `.env`, or let the server auto-create `data/web_console_token` (gitignored). The dashboard injects the token into same-origin page fetches.
- **Role gate**: DB explorer requires `X-Console-Role: admin`. Writing `/api/console-settings` also requires admin. Destructive CLI commands (`cleanup`, `backup`, `setup`, `seed-demo`, `test`, `purge-data`) are blocked in User module.
- **Command allowlist**: `/api/run-command` only runs known `python -m job_agent` subcommands — not arbitrary shell.
- **SQL console**: `/api/db/query` is read-only (`SELECT` / `WITH` only); stacked statements and write keywords are rejected.
- **CORS**: never `*`. Loopback origins (`http://127.0.0.1`, `http://localhost`) may be reflected; other origins get no ACAO header.
- User vs Admin module switch remains a UX partition; the token + role + allowlists are the security boundary for powerful APIs.
- Marking Kanban status `Applied` requires explicit `confirm_applied=true` (browser confirm dialog), matching CLI `--confirm` friction.

## 10. Compliance notes

This is a personal productivity tool. Users are responsible for complying with:

- Gmail / Google API Terms of Service  
- Job platform Terms of Service (no automated apply)  
- Accuracy of resume representations to employers  
