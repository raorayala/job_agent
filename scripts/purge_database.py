"""Purge every record from all Job Search Agent SQLite tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as: python scripts/purge_database.py --confirm
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from job_agent.cleanup_service import purge_all_database_data
from job_agent.config import get_settings
from job_agent.database import init_db


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete all records from every Job Search Agent database table.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required flag to confirm full database purge.",
    )
    args = parser.parse_args()

    if not args.confirm:
        print("Refusing to purge without --confirm.")
        print("Example: python scripts/purge_database.py --confirm")
        print("Or:      python -m job_agent purge-data --confirm")
        return 1

    settings = get_settings()
    SessionLocal = init_db(settings.database_path)
    session = SessionLocal()
    try:
        counts = purge_all_database_data(session)
        total = sum(counts.values())
        print(f"Database: {settings.database_path}")
        for table_name, deleted in counts.items():
            print(f"  {table_name}: {deleted} deleted")
        print(f"Total: {total} records purged. Database is empty.")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
