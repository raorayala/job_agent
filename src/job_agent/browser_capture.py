"""Lightweight local HTTP capture server and web console on localhost."""

from __future__ import annotations

from http.server import HTTPServer
from job_agent.web_dashboard import WebConsoleRequestHandler, start_web_dashboard_server

# Maintain backward compatibility
CaptureRequestHandler = WebConsoleRequestHandler


def start_capture_server(host: str = "127.0.0.1", port: int = 8000) -> HTTPServer:
    """Start local web console and HTTP capture server on localhost."""
    return start_web_dashboard_server(host, port)
