from pathlib import Path

import dashboard


def test_resolve_scan_path_accepts_only_txt_files_inside_scan_dir(tmp_path, monkeypatch):
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    scan_file = scan_dir / "optimized_scan_2026-08-03.txt"
    scan_file.write_text("Scan Date: 2026-08-03\n", encoding="utf-8")
    monkeypatch.setattr(dashboard, "SCAN_DIR", scan_dir)

    assert dashboard.resolve_scan_path(scan_file) == scan_file.resolve()
    assert dashboard.resolve_scan_path(scan_file.name) == scan_file.resolve()
    assert dashboard.resolve_scan_path(scan_dir / "payload.json") is None


def test_resolve_scan_path_rejects_files_outside_scan_dir(tmp_path, monkeypatch):
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("not scan data", encoding="utf-8")
    monkeypatch.setattr(dashboard, "SCAN_DIR", scan_dir)

    assert dashboard.resolve_scan_path(outside) is None
    assert dashboard.resolve_scan_path(Path("..") / "secret.txt") is None


def test_scan_api_rejects_path_traversal(tmp_path, monkeypatch):
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("not scan data", encoding="utf-8")
    monkeypatch.setattr(dashboard, "SCAN_DIR", scan_dir)

    response = dashboard.app.test_client().get("/api/scan", query_string={"path": str(outside)})

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid scan path"}
