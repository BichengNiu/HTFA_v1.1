from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from htfa.monitoring.uae.jobs import (
    source_baker_hughes,
    source_dubai_customs_air,
)


def test_baker_discovery_finds_the_current_worldwide_report(monkeypatch):
    html = b'''
    <a href="/static-files/report-2026-08.xlsx">
      Worldwide Rig Count Report - New Report
    </a>
    '''
    monkeypatch.setattr(source_baker_hughes, "fetch_bytes", lambda *_a, **_k: html)

    url, target = source_baker_hughes._discover_latest_worldwide_report()

    assert url.endswith("/static-files/report-2026-08.xlsx")
    assert target.name == "auto_worldwide_report-2026-08.xlsx"


def test_dubai_shards_follow_the_latest_manifest(tmp_path, monkeypatch):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    current = csv_dir / "current.csv.gz"
    stale = csv_dir / "stale.csv.gz"
    current.write_bytes(b"current")
    stale.write_bytes(b"stale")
    (csv_dir / "manifest.json").write_text(
        json.dumps([{"file_extension": "csv", "file_name": current.name}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(source_dubai_customs_air, "CSV_DIR", csv_dir)

    assert source_dubai_customs_air._current_shards() == [current]




def test_customs_downloader_creates_clean_runner_working_directory(monkeypatch, tmp_path):
    source = source_dubai_customs_air
    raw = tmp_path / "new/raw/customs"
    csv_dir = raw / "csv"
    monkeypatch.setattr(source, "RAW_DIR", raw)
    monkeypatch.setattr(source, "CSV_DIR", csv_dir)
    monkeypatch.setattr(source, "_current_shards", lambda: [csv_dir / "part.csv.gz"])
    def fake_run(command, **kwargs):
        assert kwargs["cwd"].is_dir()
        csv_dir.mkdir()
        (csv_dir / "download_report.json").write_text(json.dumps({
            "files": [{"file": "part.csv.gz", "status": "ok"}],
        }))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(source.subprocess, "run", fake_run)
    assert "1" in source._download_official_shards(force=True)




def test_t100_downloader_uses_repository_relative_output():
    script = (
        Path(__file__).parents[1]
        / "htfa" / "monitoring" / "uae" / "jobs" / "download_t100.py"
    ).read_text(encoding="utf-8")
    assert "def download_recent(directory" in script
    assert "C:/Users/NIU/Desktop/HTFA_v1.1/htfa/monitoring/uae/assets/raw/t100/csv" not in script
