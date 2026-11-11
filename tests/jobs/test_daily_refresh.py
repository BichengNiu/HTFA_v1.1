"""Scheduled source rollback, finalization and Linux writer contracts."""

from contextlib import nullcontext
from datetime import datetime
import json

from openpyxl import Workbook, load_workbook
import pytest

from htfa.jobs.uae_data import daily_refresh, portable_sheet_writer


def payload():
    return {
        "dictionary_sheet_name": "指标字典",
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月", "source": "官方", "source_label": "来源",
        "updated_at": "2026-11-10", "number_format": "#,##0.000",
        "column_width": 34, "period_format": "month",
        "indicators": [
            {"name": "数量", "unit": "次", "type": "观测", "industry": "交通"},
            {"name": "金额", "unit": "AED", "type": "观测", "industry": "交通"},
        ],
        "records": [{"period": "2024-02", "values": [0, None]}],
    }


def workbook(tmp_path):
    path = tmp_path / "test.xlsx"
    book = Workbook()
    book.active.title = "指标字典"
    book.active.append(["指标", "类型", "行业", "来源"])
    book.create_sheet("保留").cell(1, 1, "=1+2")
    book.create_sheet("目标").cell(15, 1, "stale")
    book.save(path)
    book.close()
    return path


@pytest.mark.parametrize("helper", ["write_indicator_sheet.ps1", "write_cbuae_sheet.ps1", "write_baker_hughes_sheet.ps1"])
def test_linux_writer_preserves_zeros_missing_values_units_other_sheets(tmp_path, helper):
    path = workbook(tmp_path)
    spec = payload()
    spec["unit"] = "次"
    data = tmp_path / "payload.json"
    data.write_text(json.dumps(spec), encoding="utf-8")
    portable_sheet_writer.write_payload_sheet(helper, path, data, "目标")
    with_book = load_workbook(path)
    try:
        assert with_book.sheetnames == ["指标字典", "保留", "目标"]
        sheet = with_book["目标"]
        assert sheet.cell(7, 1).value == datetime(2024, 2, 29)
        assert sheet.cell(7, 2).value == 0
        assert sheet.cell(7, 3).value is None
        assert sheet.max_row == 7
        assert sheet.cell(4, 3).value == "AED"
        assert with_book["保留"].cell(1, 1).value == "=1+2"
        assert with_book["指标字典"].max_row == 3
    finally:
        with_book.close()


def test_linux_writer_daily_dates_and_atomic_failure(tmp_path, monkeypatch):
    path = workbook(tmp_path)
    spec = payload()
    spec["period_format"] = "day"
    spec["records"][0]["period"] = "2026-11-09"
    data = tmp_path / "payload.json"
    data.write_text(json.dumps(spec), encoding="utf-8")
    before = path.read_bytes()
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(portable_sheet_writer.os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        portable_sheet_writer.write_payload_sheet("write_indicator_sheet.ps1", path, data, "目标")
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp.xlsx"))


def test_linux_pmi_writer_updates_dictionary_and_preserves_missing(tmp_path):
    path = workbook(tmp_path)
    spec = payload()
    spec["indicator"] = spec.pop("indicators")[0]
    spec["unit"] = "指数"
    spec["records"] = [{"period": "2026-10", "value": None}]
    data = tmp_path / "payload.json"
    data.write_text(json.dumps(spec), encoding="utf-8")
    portable_sheet_writer.write_payload_sheet("write_uae_pmi_sheet.ps1", path, data, "目标")
    book = load_workbook(path)
    try:
        assert book["目标"].cell(7, 1).value == datetime(2026, 10, 31)
        assert book["目标"].cell(7, 2).value is None
        assert book["指标字典"].cell(2, 4).value == "官方"
    finally:
        book.close()


@pytest.mark.parametrize("final_status", ["ok", "error"])
def test_daily_failed_source_rolls_back_pair_and_finalization_is_atomic(tmp_path, monkeypatch, final_status):
    from htfa.jobs.energy_supply import publish, snapshot_update
    data = tmp_path / "data"
    data.mkdir()
    database, excel = data / "uae.duckdb", data / "阿联酋.xlsx"
    database.write_bytes(b"original-db")
    excel.write_bytes(b"original-xlsx")
    monkeypatch.setattr(daily_refresh, "DATA_DIR", data)
    monkeypatch.setattr(daily_refresh, "DB_PATH", database)
    monkeypatch.setattr(daily_refresh, "WORKBOOK_PATH", excel)
    monkeypatch.setattr(publish, "publication_lock", lambda path: nullcontext())
    monkeypatch.setattr(snapshot_update, "inspect", lambda path: {})
    monkeypatch.setattr(snapshot_update, "validate_progress", lambda before, after: None)
    monkeypatch.setattr(daily_refresh, "validate_history", lambda *args, **kwargs: {"status": "ok"})
    def run(name, directory, results_dir):
        if name == "first":
            (directory / database.name).write_bytes(b"good-db")
            (directory / excel.name).write_bytes(b"good-xlsx")
            return {"status": "ok"}
        if name == "broken":
            (directory / database.name).write_bytes(b"corrupt")
            (directory / excel.name).write_bytes(b"corrupt")
            (directory / (database.name + ".wal")).write_bytes(b"stale WAL")
            return {"status": "error", "error": "upstream unavailable"}
        assert name == "finalize"
        assert (directory / database.name).read_bytes() == b"good-db"
        assert (directory / excel.name).read_bytes() == b"good-xlsx"
        assert not (directory / (database.name + ".wal")).exists()
        return {"status": final_status}
    monkeypatch.setattr(daily_refresh, "run_worker", run)
    result = daily_refresh.refresh(tmp_path / "results", sources=["first", "broken"], collect_energy=False)
    assert result["status"] == ("partial" if final_status == "ok" else "error")
    assert database.read_bytes() == (b"good-db" if final_status == "ok" else b"original-db")
    assert excel.read_bytes() == (b"good-xlsx" if final_status == "ok" else b"original-xlsx")


def test_daily_scope_contains_live_energy_worker_and_no_annual_quarterly_jobs():
    assert {"public_market", "cbuae", "portwatch", "oil"} <= set(daily_refresh.HIGH_FREQUENCY_SOURCES)
    assert not {"energy_supply", "fcsc_annual", "fcsc_gdp", "gfs", "salik"} & set(daily_refresh.HIGH_FREQUENCY_SOURCES)


def test_wam_cloud_uses_database_baseline_and_still_requires_online_scan(tmp_path, monkeypatch):
    from htfa.jobs.uae_data import db, source_wam
    monkeypatch.setattr(source_wam, "DAILY_PATH", tmp_path / "missing.csv")
    def missing_registry():
        raise FileNotFoundError("raw registry unavailable")
    monkeypatch.setattr(source_wam, "load_daily_observations", missing_registry)
    monkeypatch.setattr(source_wam.fetch_wam, "last_complete_uae_date", lambda: source_wam.START_DATE)
    calls = []
    monkeypatch.setattr(source_wam.fetch_wam, "refresh_source_manifest", lambda **kw: (
        calls.append("archive") or {"total": 0, "downloaded": 0, "reused": 0, "failed": 0}
    ))
    monkeypatch.setattr(source_wam.fetch_wam, "refresh_auto_articles", lambda **kw: (
        calls.append("online scan") or {"discovered": 0, "downloaded": 0, "reused": 0}
    ))
    monkeypatch.setattr(source_wam.fetch_wam, "load_auto_articles", lambda: [])
    with db.connect(":memory:") as con:
        db.init_schema(con)
        con.execute("INSERT INTO detail.wam_military_strike_daily "
                    "(date,ballistic_missiles,cruise_missiles,uavs,unclassified_missiles,"
                    "strike_intensity_log,attack_any,uae_asset_attack,observation_status,external_threat_alert) "
                    "VALUES (?,0,0,0,0,0,false,false,'reviewed',false)", [source_wam.START_DATE])
        assert source_wam.update(con)["status"] == "ok"
        assert calls == ["archive", "online scan"]
        assert con.execute("SELECT COUNT(*) FROM detail.wam_military_strike_daily").fetchone()[0] == 1
        con.execute("UPDATE detail.wam_military_strike_daily SET uavs=1")
        with pytest.raises(ValueError, match="inconsistent pressure"):
            source_wam.load_database_daily_observations(con)


@pytest.mark.parametrize("remote", [b"verified LFS data", b"truncated"])
def test_remote_verification_reads_exact_commit_and_rejects_corrupt_object(monkeypatch, remote):
    import hashlib
    from htfa.jobs.uae_data import verify_publication
    expected = b"verified LFS data"
    pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{hashlib.sha256(expected).hexdigest()}\nsize {len(expected)}\n"
    monkeypatch.setattr(verify_publication.subprocess, "check_output", lambda *a, **k: pointer)
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def raise_for_status(self):
            pass
        def iter_content(self, *args):
            yield remote
    def get(url, **kwargs):
        assert "/" + "a" * 40 + "/htfa/monitoring/uae/assets/uae.duckdb" in url
        assert kwargs["stream"]
        return Response()
    monkeypatch.setattr(verify_publication.requests, "get", get)
    if remote == expected:
        assert verify_publication.verify("a" * 40)["status"] == "verified"
    else:
        with pytest.raises(RuntimeError, match="size/SHA256"):
            verify_publication.verify("a" * 40)
