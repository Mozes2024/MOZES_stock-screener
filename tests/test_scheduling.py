import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.screening_freshness_gate import should_run_screening

JERUSALEM = ZoneInfo("Asia/Jerusalem")
NOW = datetime(2026, 9, 23, 12, 50, tzinfo=JERUSALEM)


def write_output(root: Path, *, scan_date="2026-09-23", total_processed=3770, pickle=b"valid"):
    scan_dir = root / "data" / "daily_scans"
    scan_dir.mkdir(parents=True, exist_ok=True)
    (scan_dir / "latest_structured_scan.json").write_text(
        json.dumps({"scan_date": scan_date, "total_processed": total_processed}), encoding="utf-8"
    )
    (scan_dir / "latest_structured_scan.pkl").write_bytes(pickle)


def test_scheduled_fallback_skips_after_today_valid_scan(tmp_path):
    write_output(tmp_path)
    assert should_run_screening("schedule", tmp_path, NOW) == (
        False,
        "today_valid_structured_output_exists",
    )


def test_scheduled_fallback_runs_when_output_is_absent_or_invalid(tmp_path):
    assert should_run_screening("schedule", tmp_path, NOW)[0] is True
    write_output(tmp_path, total_processed=0)
    assert should_run_screening("schedule", tmp_path, NOW)[0] is True
    write_output(tmp_path, scan_date="2026-09-22")
    assert should_run_screening("schedule", tmp_path, NOW)[0] is True
    write_output(tmp_path, pickle=b"")
    assert should_run_screening("schedule", tmp_path, NOW)[0] is True


def test_manual_and_cloudflare_dispatches_are_never_deduplicated(tmp_path):
    write_output(tmp_path)
    assert should_run_screening("workflow_dispatch", tmp_path, NOW)[0] is True
    assert should_run_screening("repository_dispatch", tmp_path, NOW)[0] is True


def test_same_day_uses_jerusalem_not_utc(tmp_path):
    write_output(tmp_path, scan_date="2026-09-24")
    near_midnight = datetime(2026, 9, 23, 21, 30, tzinfo=ZoneInfo("UTC"))
    assert should_run_screening("schedule", tmp_path, near_midnight)[0] is False


def test_workflows_keep_dispatch_and_downstream_contracts():
    root = Path(__file__).resolve().parents[1]
    daily = (root / ".github/workflows/daily_screening_git_storage.yml").read_text(encoding="utf-8")
    downstream = (root / ".github/workflows/generate_breakout_signals.yml").read_text(encoding="utf-8")
    watchdog = (root / ".github/workflows/daily_screening_watchdog.yml").read_text(encoding="utf-8")

    assert "repository_dispatch:" in daily
    assert "types: [cloudflare_screener_schedule]" in daily
    assert "workflow_dispatch:" in daily and "schedule:" in daily
    assert 'workflows: ["Daily Stock Screening (Git-Based Storage)"]' in downstream
    assert "Canonical stock screening" in daily
    assert "Canonical stock screening" in downstream and "conclusion == 'success'" in downstream
    assert "screening_freshness_gate.py" in watchdog
