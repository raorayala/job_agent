# 07 — Testing Strategy

## 1. Goals

- Keep core config, DB, and status gates reliable as features grow
- Prefer fast unit tests with temp SQLite files
- Mock Gmail/LLM network boundaries in later milestones
- Never require real credentials in CI/tests

## 2. Tooling

| Tool | Role |
|------|------|
| pytest | Test runner |
| pytest-cov | Optional coverage |
| tmp_path | Isolated DB/filesystem fixtures |

Install:

```powershell
pip install -e ".[dev]"
```

Run:

```powershell
pytest -q
pytest --cov=job_agent --cov-report=term-missing
```

## 3. Current test map (Milestone 1)

| File | Covers |
|------|--------|
| `tests/test_config.py` | Profile mapping, YAML load, Settings path resolution |
| `tests/test_database.py` | Schema create, job CRUD helpers, processed email tracking |
| `tests/test_application_tracker.py` | Applied confirmation gate; status updates |
| `tests/test_job_normalizer.py` | URL/company/text normalization |
| `tests/test_document_exporter.py` | Filename + folder conventions |

## 4. Planned test areas

| Area | Examples |
|------|----------|
| Gmail client | Token refresh mocked; message decode fixtures |
| Email parser | Fixture HTML for each platform; missing fields |
| Matcher | Deterministic scores for known profile/job pairs; exclusions |
| Duplicates | URL vs near-duplicate title/company cases |
| Resume tailor | No invented skills; keyword emphasis only; dry-run path |
| CLI | Typer CliRunner for `--confirm` refusal / success |

## 5. Test data policy

- Use synthetic companies/titles only
- Do not commit real resumes, tokens, or email corpora with PII
- Large HTML fixtures may live under `tests/fixtures/` with anonymized content

## 6. Definition of done for a milestone

- Unit tests for new pure logic  
- CLI smoke path documented  
- No secrets in fixtures  
- `pytest -q` green on Windows (primary target)  

## 7. Manual test checklist (pre-production local)

1. `python -m job_agent setup` succeeds  
2. `profile` shows edited YAML values  
3. `jobs` on empty DB exits cleanly  
4. `mark-applied 1` without `--confirm` refuses  
5. After Gmail milestone: `sync-gmail --dry-run` lists query without writing  
6. After tailor milestone: `tailor <id> --dry-run` prints target path only  
