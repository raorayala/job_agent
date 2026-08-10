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

    payload = json.dumps({
        "target_titles": ["Staff Software Engineer"],
        "required_skills": ["Python", "Docker"],
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
