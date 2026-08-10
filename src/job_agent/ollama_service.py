"""Local offline LLM service integration using Ollama (http://localhost:11434)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from job_agent.config import Settings, get_settings
from job_agent.logging_config import get_logger

logger = get_logger(__name__)


def generate_ollama_completion(prompt: str, settings: Settings | None = None) -> str | None:
    """
    Send prompt to local Ollama API (http://localhost:11434/api/generate).
    Returns generated text if Ollama is active, or None if Ollama is offline/disabled.
    """
    st = settings or get_settings()
    if st.llm_provider != "ollama":
        return None

    url = f"{st.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": st.ollama_model,
        "prompt": prompt,
        "stream": False,
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                res_data: dict[str, Any] = json.loads(resp.read().decode("utf-8", errors="replace"))
                response_text = res_data.get("response") or ""
                return response_text.strip()
    except Exception as exc:
        logger.debug("Local Ollama API unavailable (%s): %s", url, exc)

    return None
