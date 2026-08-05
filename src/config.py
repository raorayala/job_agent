"""Load environment variables and YAML configuration."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def get_jobs_applied_folder() -> Path:
    folder = Path(get_env("JOBS_APPLIED_FOLDER", str(Path.home() / "Desktop" / "Jobs Applied")))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tailored_resumes").mkdir(exist_ok=True)
    (folder / "exports").mkdir(exist_ok=True)
    return folder


def load_yaml_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
