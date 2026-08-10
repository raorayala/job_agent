"""Tests for web_dashboard server, API endpoints, database explorer, and command runner."""

import json
import urllib.request
import pytest

from job_agent.web_dashboard import start_web_dashboard_server, CLI_COMMANDS_METADATA


@pytest.fixture(scope="module")
def web_server(tmp_path_factory):
    port = 8899
    server = start_web_dashboard_server(host="127.0.0.1", port=port)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_get_index_html(web_server):
    req = urllib.request.Request(f"{web_server}/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Job Search Agent Web Console" in html
        assert "CLI Command Cheat Sheet" in html
        assert 'id="global-progress-wrapper"' in html
        assert 'id="global-progress-bar"' in html
        assert "function showProgress" in html
        assert "function finishProgress" in html
        assert "Profile &amp; Skills Editor" in html or "Profile & Skills Editor" in html
        assert "Optional &amp; Synced with <code>config.yaml</code>" in html or "Optional & Synced with" in html
        assert 'id="preview-titles"' in html
        assert 'id="preview-req-skills"' in html
        assert 'id="preview-pref-skills"' in html
        assert 'id="preview-locations"' in html
        assert 'id="preview-salary"' in html
        assert 'id="preview-salary-max"' in html
        assert 'href="/capture"' in html
        assert "Install Bookmarklet" in html
        assert 'id="bookmarklet-install-card"' in html
        assert "function goFindJobsNow" in html
        assert 'class="form-check-input platform-checkbox"' in html
        assert "selectRecommendedPlatforms" in html
        assert "Top 3 Recommended" in html
        assert 'id="system-health-card"' in html
        assert 'id="recent-jobs-table"' in html


def test_get_api_commands(web_server):
    req = urllib.request.Request(f"{web_server}/api/commands")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0
        categories = [c["category"] for c in data]
        assert "Setup & Environment" in categories
        assert "Job Discovery & Ingestion" in categories


def test_get_api_stats(web_server):
    req = urllib.request.Request(f"{web_server}/api/stats")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "total_jobs" in data
        assert "status_counts" in data
        assert "high_score_jobs" in data
        assert isinstance(data["high_score_jobs"], list)


def test_get_api_jobs(web_server):
    req = urllib.request.Request(f"{web_server}/api/jobs")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, list)


def test_get_calendar_ics(web_server):
    req = urllib.request.Request(f"{web_server}/api/calendar.ics")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "BEGIN:VCALENDAR" in content
        assert "END:VCALENDAR" in content


def test_db_explorer_endpoints(web_server):
    # 1. Get Tables
    req_tables = urllib.request.Request(f"{web_server}/api/db/tables")
    with urllib.request.urlopen(req_tables, timeout=5) as resp:
        assert resp.status == 200
        tables_data = json.loads(resp.read().decode("utf-8"))
        assert "jobs" in tables_data["tables"]

    # 2. Get Table Data
    req_data = urllib.request.Request(f"{web_server}/api/db/table-data?table=jobs")
    with urllib.request.urlopen(req_data, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["table"] == "jobs"
        assert isinstance(data["rows"], list)

    # 3. SQL Query Console
    payload_query = json.dumps({"query": "SELECT count(*) FROM jobs;"}).encode("utf-8")
    req_query = urllib.request.Request(
        f"{web_server}/api/db/query",
        data=payload_query,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_query, timeout=5) as resp:
        assert resp.status == 200
        res_query = json.loads(resp.read().decode("utf-8"))
        assert res_query["success"] is True

    # 4. Cleanup Endpoint
    payload_cleanup = json.dumps({"action": "duplicates"}).encode("utf-8")
    req_cleanup = urllib.request.Request(
        f"{web_server}/api/db/cleanup",
        data=payload_cleanup,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_cleanup, timeout=5) as resp:
        assert resp.status == 200
        res_cleanup = json.loads(resp.read().decode("utf-8"))
        assert res_cleanup["status"] == "success"


def test_get_and_post_profile(web_server):
    req_get = urllib.request.Request(f"{web_server}/api/profile")
    with urllib.request.urlopen(req_get, timeout=5) as resp:
        assert resp.status == 200
        p = json.loads(resp.read().decode("utf-8"))
        assert "target_titles" in p
        assert "required_skills" in p
        assert "preferred_skills" in p
        assert "locations" in p
        assert "salary_min" in p
        assert "salary_max" in p

    payload = json.dumps({
        "target_titles": ["Staff Software Engineer", "Tech Lead"],
        "required_skills": ["Python", "Docker", "SQL"],
        "preferred_skills": ["Kubernetes", "Kafka"],
        "locations": ["Remote", "San Francisco, CA"],
        "salary_min": 140000,
        "salary_max": 200000,
        "years_experience": 8,
    }).encode("utf-8")
    req_post = urllib.request.Request(
        f"{web_server}/api/profile",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_post, timeout=5) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "success"

    # Verify updated values persist via GET
    with urllib.request.urlopen(req_get, timeout=5) as resp:
        p_updated = json.loads(resp.read().decode("utf-8"))
        assert "Staff Software Engineer" in p_updated["target_titles"]
        assert "Tech Lead" in p_updated["target_titles"]
        assert p_updated["salary_min"] == 140000
        assert p_updated["salary_max"] == 200000


def test_post_run_command_statuses(web_server):
    payload = json.dumps({"command": "statuses", "args": []}).encode("utf-8")
    req = urllib.request.Request(
        f"{web_server}/api/run-command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["success"] is True
        assert res["exit_code"] == 0
        assert "Saved" in res["output"] or "Applied" in res["output"]


def test_post_capture_job(web_server):
    payload = json.dumps({
        "title": "Senior Web Architect",
        "company": "WebCorp Local",
        "url": "https://example.com/job/web123",
        "description": "Python, JavaScript, HTML5, Web Services"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{web_server}/capture",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "success"
        assert res["title"] == "Senior Web Architect"
        assert res["company"] == "WebCorp Local"


def test_get_capture_page(web_server):
    req = urllib.request.Request(f"{web_server}/capture")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "1-Click Bookmarklet Installer" in html
        assert "Mark as Installed" in html
        assert "javascript:(function()" in html


def test_post_jobs_find_selected_platforms(web_server):
    payload = json.dumps({"platforms": ["dice"], "limit": 3}).encode("utf-8")
    req = urllib.request.Request(
        f"{web_server}/api/jobs/find",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "success"
        assert res["platforms_searched"] == ["dice"]
        assert res["limit_per_platform"] == 3
        assert "jobs_recorded" in res
        assert "platform_reports" in res


def test_get_api_stats_includes_health(web_server):
    req = urllib.request.Request(f"{web_server}/api/stats")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert "health" in data
        assert "recent_jobs" in data
        assert "database_path" in data["health"]


def test_post_seed_demo(web_server):
    payload = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(
        f"{web_server}/api/jobs/seed-demo",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "success"
        assert data["jobs_seeded"] == 3
