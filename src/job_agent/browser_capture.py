"""Lightweight local HTTP capture server on localhost for receiving job page data from browser bookmarklet/extension."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from job_agent.application_tracker import record_parsed_job
from job_agent.config import get_settings, load_candidate_profile
from job_agent.database import init_db
from job_agent.logging_config import get_logger
from job_agent.models import ParsedJob

logger = get_logger(__name__)


class CaptureRequestHandler(BaseHTTPRequestHandler):
    """Local-only HTTP handler on localhost for captured job page payloads."""

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self) -> None:
        try:
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            pass

    def do_GET(self) -> None:
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            msg = json.dumps({"status": "active", "server": "Job Search Agent Local Capture Server"}).encode("utf-8")
            self.wfile.write(msg)
        except Exception:
            pass

    def do_POST(self) -> None:
        if self.path != "/capture":
            try:
                self.send_error(404, "Endpoint not found")
            except Exception:
                pass
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data: dict[str, Any] = json.loads(body)
            title = data.get("title") or "Captured Job"
            company = data.get("company") or "Unknown"
            url = data.get("url") or ""
            description = data.get("description") or ""

            settings = get_settings()
            SessionLocal = init_db(settings.database_path)
            profile = load_candidate_profile()

            session = SessionLocal()
            try:
                parsed = ParsedJob(
                    title=title,
                    company=company,
                    job_url=url,
                    description=description,
                    source_platform="browser_capture",
                )
                record, match, dupe = record_parsed_job(session, parsed, profile)
                response_payload = {
                    "status": "success",
                    "job_id": record.id,
                    "title": record.title,
                    "company": record.company,
                    "score": match.score,
                    "recommendation": match.recommendation.value,
                    "is_duplicate": dupe.is_duplicate,
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(response_payload).encode("utf-8"))
                logger.info("Local browser capture recorded job #%d: %s @ %s", record.id, title, company)
            finally:
                session.close()

        except Exception as exc:
            logger.error("Failed to process local browser capture: %s", exc)
            try:
                self.send_error(400, f"Error processing capture: {exc}")
            except Exception:
                pass

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default HTTP logging to stdout


def start_capture_server(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    """Start local HTTP capture server on localhost."""
    server = HTTPServer((host, port), CaptureRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Local browser capture server running on http://%s:%d/capture", host, port)
    return server
