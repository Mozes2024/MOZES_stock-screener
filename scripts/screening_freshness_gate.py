"""Decide whether the canonical daily screening job should run."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JERUSALEM = ZoneInfo("Asia/Jerusalem")


def should_run_screening(event_name: str, repository: Path, now: datetime | None = None) -> tuple[bool, str]:
    """Allow explicit runs and deduplicate only GitHub's native schedule."""
    if event_name != "schedule":
        return True, f"{event_name}_always_allowed"

    current = now or datetime.now(JERUSALEM)
    if current.tzinfo is None:
        current = current.replace(tzinfo=JERUSALEM)
    today = current.astimezone(JERUSALEM).date().isoformat()
    scan_dir = repository / "data" / "daily_scans"
    summary_path = scan_dir / "latest_structured_scan.json"
    pickle_path = scan_dir / "latest_structured_scan.pkl"

    if not summary_path.is_file() or not pickle_path.is_file() or pickle_path.stat().st_size == 0:
        return True, "structured_output_missing"

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True, "structured_summary_invalid"

    if not isinstance(summary, dict) or summary.get("scan_date") != today:
        return True, "structured_output_not_today"
    if not isinstance(summary.get("total_processed"), int) or summary["total_processed"] <= 0:
        return True, "structured_summary_invalid"
    return False, "today_valid_structured_output_exists"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    should_run, reason = should_run_screening(args.event_name, args.repository)
    result = f"should_run={'true' if should_run else 'false'}\nreason={reason}\n"
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(result)
    print(result, end="")


if __name__ == "__main__":
    main()
