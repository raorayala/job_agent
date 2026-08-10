# 07 — Testing Strategy

## 1. Goals

- Keep core config, DB, web API, and status gates reliable as features grow  
- Prefer fast unit tests with temp SQLite files  
- Mock Gmail/LLM network boundaries where needed  
- Never require real credentials in CI/tests  

## 2. Tooling

| Tool | Role |
|------|------|
| pytest | Test runner |
| pytest-cov | Optional coverage |
| pytest-playwright | Browser E2E tests in **visible Google Chrome** (default) |
| tmp_path | Isolated DB/filesystem fixtures |

Install and run:

```powershell
pip install -e ".[dev]"
python -m job_agent test --install-browsers   # one-time Chrome/Playwright setup
python -m job_agent test                        # unit + API + E2E in visible Google Chrome
python -m job_agent test --headless               # headless Chromium (CI/automation)
python -m job_agent test --no-e2e                 # skip browser tests (fast console-only)
python -m job_agent test --cov                    # with coverage
```

**Web Console E2E tests** open a real **Google Chrome** window, navigate to `http://127.0.0.1:<port>/`, and interact with the UI (clicks, tabs, modals) exactly as an end user would. Unit and HTTP API tests still run in the terminal first; only the `@pytest.mark.e2e` tests use Chrome.

Requirements for browser E2E:

1. [Google Chrome](https://www.google.com/chrome/) installed on your machine  
2. `python -m job_agent test --install-browsers` run once  
3. Run `python -m job_agent test` (Chrome opens automatically — do not use `--headless` unless automating CI)

Direct pytest (equivalent):

```powershell
pytest -q
pytest -m "not e2e" -q
pytest --cov=job_agent --cov-report=term-missing
```

## 3. Test layers

| Layer | Location | What it covers |
|-------|----------|----------------|
| Unit / integration | `tests/test_*.py` | Config, DB, matcher, Gmail parse, platform fetcher, services |
| HTTP API | `tests/test_web_dashboard.py` | REST endpoints without a browser |
| Browser E2E | `tests/e2e/` | Playwright in **visible Google Chrome**: tabs, demo seed, discovery, capture, CLI runner |

## 4. Current test map (63 tests)

| File | Covers |
|------|--------|
| `tests/test_config.py` | Profile mapping, YAML load, Settings paths |
| `tests/test_database.py` | Schema create, job CRUD, processed emails |
| `tests/test_application_tracker.py` | Applied confirmation gate; status updates |
| `tests/test_job_normalizer.py` | URL/company/text normalization |
| `tests/test_document_exporter.py` | Filename + folder conventions |
| `tests/test_matcher.py` | Scoring, exclusions, recommendations |
| `tests/test_email_parser.py` | HTML parsing, skill extraction |
| `tests/test_platform_fetcher.py` | Platform search, `SearchImportResult` |
| `tests/test_web_dashboard.py` | HTTP API, stats/health, seed-demo, capture, DB explorer |
| `tests/test_demo_health.py` | Demo seed + system health |
| `tests/test_cleanup_service.py` | Full purge including `activity_logs` |
| `tests/test_backup_service.py` | Backup, restore, purge |
| `tests/test_review_first_workflow.py` | Browser launcher, config validation |
| `tests/e2e/test_web_console_ui.py` | Playwright browser E2E: dashboard, tabs, demo seed, capture |

## 5. Manual smoke test

See **[11 — Testing Playbook](11-TESTING-PLAYBOOK.md)** for the recommended fast path:

```powershell
python -m job_agent seed-demo
python -m job_agent web   # verify dashboard in browser
python -m job_agent test
```

## 6. Test data policy

- Use synthetic companies/titles only  
- Do not commit real resumes, tokens, or email corpora with PII  
- HTML fixtures under `tests/fixtures/` when added must be anonymized  

## 7. Definition of done for a feature

- Unit/integration tests for new logic  
- Web API test if adding endpoints  
- Browser E2E test if changing primary UI flows  
- `python -m job_agent test` green on Windows  
- Update `docs/11` or `docs/12` if user-facing behavior changes  

## 8. Manual checklist (pre-release local)

1. `python -m job_agent setup` succeeds  
2. `python -m job_agent seed-demo` → 3 jobs in DB  
3. `python -m job_agent web` → dashboard shows health + recent jobs  
4. `mark-applied` without `--confirm` refuses  
5. `sync-gmail --dry-run` lists query without writing (if Gmail configured)  
6. `scripts/purge_database.py --confirm` empties all tables  
