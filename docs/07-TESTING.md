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
| tmp_path | Isolated DB/filesystem fixtures |

Install and run:

```powershell
pip install -e ".[dev]"
pytest -q
pytest --cov=job_agent --cov-report=term-missing
```

## 3. Current test map (53 tests)

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

## 4. Manual smoke test

See **[11 — Testing Playbook](11-TESTING-PLAYBOOK.md)** for the recommended fast path:

```powershell
python -m job_agent seed-demo
python -m job_agent web   # verify dashboard in browser
pytest -q
```

## 5. Test data policy

- Use synthetic companies/titles only  
- Do not commit real resumes, tokens, or email corpora with PII  
- HTML fixtures under `tests/fixtures/` when added must be anonymized  

## 6. Definition of done for a feature

- Unit/integration tests for new logic  
- Web API test if adding endpoints  
- `pytest -q` green on Windows  
- Update `docs/11` or `docs/12` if user-facing behavior changes  

## 7. Manual checklist (pre-release local)

1. `python -m job_agent setup` succeeds  
2. `python -m job_agent seed-demo` → 3 jobs in DB  
3. `python -m job_agent web` → dashboard shows health + recent jobs  
4. `mark-applied` without `--confirm` refuses  
5. `sync-gmail --dry-run` lists query without writing (if Gmail configured)  
6. `scripts/purge_database.py --confirm` empties all tables  
