# Job Search Agent

A Python agent that monitors your Gmail for job alerts from major platforms, analyzes listing relevance, tailors your resume for ATS compatibility, and tracks applications to prevent duplicates.

## Features (roadmap)

| Phase | Capability | Status |
|-------|------------|--------|
| 1 | Gmail fetch + platform parsing | ✅ Scaffolded |
| 1 | Duplicate detection + SQLite tracking | ✅ Scaffolded |
| 1 | Rule-based match scoring | ✅ Scaffolded |
| 1 | ATS keyword resume tailoring | ✅ Basic |
| 2 | LLM-powered job analysis (Ollama / free tier) | 🔜 Planned |
| 2 | Scheduled proactive monitoring | 🔜 Planned |
| 3 | Application submission helpers | 🔜 Planned |

## Supported platforms

ZipRecruiter, Indeed, Glassdoor, Dice, Lensa — extensible via `config.yaml`.

## Quick start

```powershell
cd C:\Users\Admin\Projects\job-search-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py setup
```

### Gmail API setup (free)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → **APIs & Services** → enable **Gmail API**
3. **Credentials** → Create **OAuth client ID** → Desktop app
4. Download JSON → save as `credentials.json` in this folder
5. First `scan` run opens a browser for one-time authorization

### Run a scan

```powershell
python main.py scan
python main.py history
```

Tailored resumes and exports land in `Desktop\Jobs Applied\`.

## Project structure

```
job-search-agent/
├── config.yaml          # Platforms, target roles/skills
├── credentials.json     # You add this (not committed)
├── data/jobs.db         # SQLite application tracker
├── main.py              # CLI
└── src/
    ├── agent.py         # Orchestration
    ├── gmail_client.py  # Gmail API
    ├── job_parser.py    # Email → structured job
    ├── job_analyzer.py  # Relevance scoring
    ├── resume_tailor.py # DOCX tailoring
    └── application_tracker.py
```

## Customize your profile

Edit `config.yaml`:

- `target_roles` — job titles you want
- `target_skills` — skills to match and inject into resumes
- `platforms` — sender domains and URL patterns

## Important notes

- **Human in the loop**: Review every tailored resume before applying.
- **No auto-submit**: Deliberately omitted to avoid ToS violations and bad applications.
- **Privacy**: Credentials and job data stay local on your machine.

## License

MIT — personal use
