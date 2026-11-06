from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from htfa.jobs.uae_data import (
    source_baker_hughes,
    source_comtrade_vehicles,
    source_dubai_customs_air,
    source_salik,
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


def test_comtrade_adapter_calls_the_official_downloader(monkeypatch, tmp_path):
    calls = []
    helper = tmp_path / "download_hs87.py"
    helper.write_text("# subprocess fixture\n")
    monkeypatch.setattr(source_comtrade_vehicles, "DOWNLOAD_SCRIPT", helper)

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="summary", stderr="")

    monkeypatch.setattr(source_comtrade_vehicles.subprocess, "run", fake_run)
    note = source_comtrade_vehicles._download_official_data(force=False)

    assert "summary" in note
    assert calls[0][0][0] == source_comtrade_vehicles.sys.executable
    assert "--start" in calls[0][0]


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


def test_salik_extracts_absolute_value_but_not_yoy_percentage(monkeypatch):
    class FakePage:
        def __init__(self, text: str):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self, _path: str):
            self.pages = [
                FakePage(
                    "# OF REGISTERED ACTIVE VEHICLES as of Jun 30, 2026 c. 4.88 MN"
                )
            ]

    monkeypatch.setattr(source_salik, "PdfReader", FakeReader)
    assert source_salik._period_from_filename("Salik-Investor-Presentation-H1_2026.pdf")
    assert source_salik._extract_absolute_value(Path("fake.pdf")) == 4.88


def test_t100_downloader_uses_repository_relative_output():
    script = (
        Path(__file__).parents[1]
        / "htfa" / "jobs" / "uae_data" / "download_t100.py"
    ).read_text(encoding="utf-8")
    assert "def download_recent(directory" in script
    assert "C:/Users/NIU/Desktop/HTFA_v1.1/data/UAE/raw/t100/csv" not in script
