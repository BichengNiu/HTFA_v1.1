"""Official BTS archive filtering, no-data proof and historical preservation."""

import csv
from datetime import date
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import duckdb
import pytest

from htfa.jobs.uae_data import db, download_t100 as downloader, source_dot_t100 as source


def archive(year=2026, months=(7,)):
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=source.FIELDS_REQUIRED)
    writer.writeheader()
    for month in months:
        for origin, destination in [("US", "AE"), ("AE", "US"), ("US", "CA")]:
            row = {name: "10" for name in source.FIELDS_REQUIRED}
            row.update(YEAR=str(year), MONTH=str(month), QUARTER=str((month - 1) // 3 + 1),
                       ORIGIN="JFK", DEST="DXB", ORIGIN_COUNTRY=origin, DEST_COUNTRY=destination)
            writer.writerow(row)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        zipped.writestr("lookup.csv", "code,name\nAE,UAE\n")
        zipped.writestr("segments.csv", text.getvalue())
    return output.getvalue()


def test_bts_selects_matching_data_table_and_filters_only_us_uae(tmp_path):
    path = tmp_path / "uae_2026.zip"
    assert downloader.filter_zip(archive(), path, 2026) == 2
    rows = source.collect_rows([path], today=date(2026, 10, 28))
    assert len(rows) == 10
    assert next(r["value"] for r in rows if r["indicator"] == source.INDICATOR_TPL["all", "passengers"]) == 20
    with pytest.raises(ValueError, match="different year"):
        downloader.filter_zip(archive(2025), tmp_path / "wrong.zip", 2026)


def test_no_data_marker_requires_official_message_and_echoed_filters(tmp_path):
    form = ''.join(f'<input type="checkbox" name="{field}">' for field in source.FIELDS_REQUIRED)
    def response(text):
        return SimpleNamespace(text=text, content=text.encode(), raise_for_status=lambda: None)
    empty = ('No data available for All Months 1990'
             '<select><option selected value="United Arab Emirates">AE</option>'
             '<option selected value="1990">1990</option><option selected value="All">All</option></select>')
    session = SimpleNamespace(get=lambda *a, **k: response(form), post=lambda *a, **k: response(empty))
    assert downloader.download_year(session, 1990, tmp_path) == 0
    assert (tmp_path / "uae_1990.nodata").is_file()
    session.post = lambda *a, **k: response("No data available for All Months 1991")
    with pytest.raises(ValueError, match="verified no-data"):
        downloader.download_year(session, 1991, tmp_path)
    assert not (tmp_path / "uae_1991.nodata").exists()


def test_recent_year_refresh_retains_old_database_history(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    csv_dir = raw / "csv"
    csv_dir.mkdir(parents=True)
    monkeypatch.setattr(source, "RAW_DIR", raw)
    monkeypatch.setattr(source, "CSV_DIR", csv_dir)
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 28)
    monkeypatch.setattr(source, "date", Today)
    (csv_dir / "uae_1990.nodata").write_text("Official no-data response")
    downloader.filter_zip(archive(months=range(1, 8)), csv_dir / "uae_2026.zip", 2026)
    old = []
    for year in range(2005, 2026):
        for month in range(1, 13):
            old.extend({"period": date(year, month, 1), "indicator": name, "value": 1, "source_file": "historical.zip"}
                       for name in source.INDICATOR_TPL.values())
    old.extend({"period": date(1991, 2, 1), "indicator": name, "value": 1, "source_file": "1991.zip"}
               for name in source.INDICATOR_TPL.values())
    with duckdb.connect() as con:
        db.init_schema(con)
        db.replace(con, "dot_t100_monthly", old)
        assert source.update(con, skip_download=True)["status"] == "ok"
        assert con.execute("SELECT min(period),max(period) FROM dot_t100_monthly").fetchone() == (date(1991, 2, 1), date(2026, 7, 1))
        assert con.execute("SELECT count(*) FROM dot_t100_monthly WHERE period < DATE '2026-01-01'").fetchone()[0] == len(old)
        con.execute("INSERT INTO dot_t100_monthly VALUES (DATE '2026-08-01',?,1,'old.zip')", [next(iter(source.INDICATOR_TPL.values()))])
        before = con.execute("SELECT count(*) FROM dot_t100_monthly").fetchone()[0]
        with pytest.raises(ValueError, match="remove existing observations"):
            source.update(con, skip_download=True)
        assert con.execute("SELECT count(*) FROM dot_t100_monthly").fetchone()[0] == before
