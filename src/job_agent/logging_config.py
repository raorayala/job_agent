"""Central logging setup."""

from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: str | None = None) -> None:
    """Configure root logging once for CLI and library use."""
    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    numeric = getattr(logging, resolved, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(numeric)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
