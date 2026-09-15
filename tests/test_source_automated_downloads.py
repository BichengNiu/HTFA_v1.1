from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from htfa.jobs.uae_data import (
    source_baker_hughes,
    source_comtrade_vehicles,
    source_dubai_customs_air,
    source_salik,
    source_scad,
    source_uaewps,
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


def test_comtrade_adapter_calls_the_official_downloader(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="summary", stderr="")

    monkeypatch.setattr(source_comtrade_vehicles.subprocess, "run", fake_run)
    note = source_comtrade_vehicles._download_official_data(force=False)

    assert "summary" in note
    assert calls[0][0][0] == source_comtrade_vehicles.sys.executable
    assert "--start" in calls[0][0]


def test_scad_discovery_supports_current_liferay_cards(monkeypatch):
    html = b'''
    <div class="journal-content-article "
         data-analytics-asset-title="Hotel Statistics-Monthly March 2026">
      <a class="ml-2" href="/documents/report.xlsx/abc?t=1">Excel</a>
    </div>
    '''

    def fake_fetch(url: str, **_kwargs):
        return html if "start=1" in url else b""

    monkeypatch.setattr(source_scad, "fetch_bytes", fake_fetch)
    found = source_scad._discover_official_files()

    assert len(found) == 1
    assert found[0][0] == "HotelStats"
    assert found[0][2].name == "HotelStats_2026-03.xlsx"


def test_uaewps_accepts_a_new_report_period_without_disabling_historical_checks():
    verified = source_uaewps.validate_observations(
        {"2026Q2": ("2026-03", 11.7, 0.7, "")}
    )
    assert verified == [("2026Q2", "2026-03", 11.7, 0.7, "")]


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
        / "data"
        / "UAE"
        / "raw"
        / "t100"
        / "download_uae_years.mjs"
    ).read_text(encoding="utf-8")
    assert "T100_OUTPUT" in script
    assert "C:/Users/NIU/Desktop/HTFA_v1.1/data/UAE/raw/t100/csv" not in script
