"""Tests for data/source_ded.py：快照聚合、审计文件、入库往返、月度_DED 行构建。

全部使用 tmp_path 构造的最小样例，不碰网络、不碰真实工作簿。
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from htfa.jobs.uae_data import source_ded as sd
from htfa.jobs.uae_data import db

HEADER = [
    "issue_date", "commerce_number", "main_license_number",
    "legal_type_desc_en", "cancel_date",
]

# 构造 6 行测试数据：
# 2024-01-31：企业 A（commerce_number=100）与执照 9001 各一条
# 2024-01-31：企业 A 的第二条记录（同企业号再次出现 → 企业计数只算 1 次）
# 2024-02-28：企业 A 的第三条记录（跨月再次出现 → 首现月份仍是 2024-01）
# 2024-02-28：企业 B（200，但 commerce_number='0' 占位 → 不入企业口径）
# 空日期一行（→ by_type 归入 unknown 月）
# 2024-03-31：企业 C（300，执照 9002）


def _write_fixture(path: Path) -> Path:
    rows = [
        ["2024-01-05", "100", "9001", "Sole Establishment", ""],
        ["2024-01-20", "100", "9001", "Sole Establishment", ""],
        ["2024-02-10", "100", "9001", "Sole Establishment", ""],
        ["2024-02-15", "0", "9003", "Limited Liability Company(LLC)", ""],
        ["", "0", "9004", "Sole Establishment", ""],
        ["2024-03-02", "300", "9002", "Civil Company", ""],
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def test_aggregate_snapshots_dedup_semantics(tmp_path) -> None:
    """首现筛重：企业/执照号只在最早发照月份计数，占位 '0' 与空日期不污染口径。"""

    snap = _write_fixture(tmp_path / "commerce_registry_sample.csv")
    result = sd.aggregate_snapshots([snap])
    stats = result["stats"]

    assert stats["total"] == 6
    assert stats["parsed"] == 5  # 空日期行
    assert stats["bad"] == 1
    assert result["date_col"] == "issue_date"
    assert result["type_col"] == "legal_type_desc_en"

    assert stats["monthly"] == {"2024-01": 2, "2024-02": 2, "2024-03": 1}
    # 企业：A 首现 2024-01 只计 1；占位 '0' 不计；C 首现 2024-03
    assert stats["monthly_enterprise"] == {"2024-01": 1, "2024-03": 1}
    assert stats["enterprise_total"] == 2
    # 执照：9001 首现 2024-01 只计 1；9003/9002 各一
    assert stats["monthly_licence"] == {"2024-01": 1, "2024-02": 1, "2024-03": 1}
    assert stats["licence_total"] == 3
    # by_type：空日期行（2024-02 行有日期）→ 未解析的仅 1 行入 unknown
    assert stats["by_type"][("unknown", "Sole Establishment")] == 1
    assert stats["by_type"][("2024-01", "Sole Establishment")] == 2
    assert stats["date_min"] == "2024-01"
    assert stats["date_max"] == "2024-03"


def test_db_roundtrip_with_unknown_excluded(tmp_path) -> None:
    """聚合结果入库：月末 DATE、四系列长表、unknown 月不进入 by_type 表。"""

    snap = _write_fixture(tmp_path / "commerce_registry_sample.csv")
    result = sd.aggregate_snapshots([snap])
    stats = result["stats"]
    official = {"2024-01": 12345}

    monthly_rows = sd._ded_monthly_rows(stats, official)
    by_type_rows = sd._ded_by_type_rows(stats)

    assert {"records", "enterprises", "licences", "official_new_licenses"} == {
        row["series"] for row in monthly_rows
    }

    con = db.connect(":memory:")
    db.init_schema(con)
    with sd._transaction(con):
        db.replace(con, "ded_monthly", monthly_rows)
        db.replace(con, "ded_monthly_by_type", by_type_rows)

    assert con.execute(
        "SELECT month, series, value FROM ded_monthly WHERE series='records' ORDER BY month"
    ).fetchall() == [
        (datetime(2024, 1, 31).date(), "records", 2.0),
        (datetime(2024, 2, 29).date(), "records", 2.0),
        (datetime(2024, 3, 31).date(), "records", 1.0),
    ]
    # 2024-01 官方数字
    assert con.execute(
        "SELECT month, value FROM ded_monthly WHERE series='official_new_licenses'"
    ).fetchone() == (datetime(2024, 1, 31).date(), 12345.0)
    # unknown 月（空日期行）只在 CSV 审计文件里，不在 DB
    assert "unknown" not in {row["month"] for row in by_type_rows}
    assert con.execute("SELECT count(*) FROM ded_monthly_by_type").fetchone()[0] == 4
    assert con.execute(
        "SELECT legal_form FROM ded_monthly_by_type WHERE month = ?",
        [datetime(2024, 1, 31).date()],
    ).fetchall() == [("Sole Establishment",)]
    con.close()


def test_audit_files_structure(tmp_path) -> None:
    """审计文件结构与旧脚本逐字节一致：列头、排序、编码。"""

    snap = _write_fixture(tmp_path / "commerce_registry_sample.csv")
    result = sd.aggregate_snapshots([snap])
    stats = result["stats"]
    out = tmp_path / "DED_data"
    out.mkdir()

    sd.write_monthly(out / "monthly_new_licenses.csv", stats["monthly"])
    sd.write_monthly_counts(
        out / "monthly_counts.csv",
        stats["monthly"],
        stats["monthly_enterprise"],
        stats["monthly_licence"],
    )
    sd.write_monthly_by_type(out / "monthly_by_type.csv", stats["by_type"])
    sd.write_schema_report(
        out / "schema_report.txt", result["columns"], stats,
        result["date_col"], result["type_col"], result["warnings"],
    )
    sd.build_manifest(out, dataset_id="460521", source_urls=["local"],
                      snapshot_files=["x.csv"], snapshot_sha256=["abc"],
                      snapshot_sizes=[1], row_count=6, parsed_dates=5,
                      unparsed_dates=1, enterprise_count=2, licence_count=3,
                      date_col_used="issue_date", type_col_used="legal_type_desc_en",
                      date_min="2024-01", date_max="2024-03", warnings=[])

    with open(out / "monthly_counts.csv", encoding="utf-8-sig") as source:
        rows = list(csv.reader(source))
    assert rows[0] == ["month", "records", "enterprises", "licences"]
    assert rows[1] == ["2024-01", "2", "1", "1"]
    assert rows[2] == ["2024-02", "2", "0", "1"]
    assert rows[3] == ["2024-03", "1", "1", "1"]

    with open(out / "monthly_by_type.csv", encoding="utf-8-sig") as source:
        type_rows = list(csv.reader(source))
    assert type_rows[0] == ["month", "license_type", "count"]
    assert ["unknown", "Sole Establishment", "1"] in type_rows

    manifest = sd.json.loads((out / "fetch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 6
    assert manifest["date_col_used"] == "issue_date"


def test_month_to_date_and_build_rows() -> None:
    """月末换算（含闰年）与 build_rows 的降序、缺报留空行为。"""

    counts = {"2024-01": {"enterprises": 10, "licences": 11}}
    official = {"2024-02": 99}
    rows = sd.build_rows(counts, official)
    assert [row["month"] for row in rows] == ["2024-02", "2024-01"]
    assert rows[0]["date"] == datetime(2024, 2, 29)  # 2024 闰年
    assert rows[0]["enterprises"] is None  # 官方有值但筛重无值 → 留空
    assert rows[1]["official"] is None
    assert sd._month_end_date("2023-02") == datetime(2023, 2, 28).date()


def test_update_writes_files_and_db(tmp_path, monkeypatch) -> None:
    """update() 全流程（skip_download=True，代理指向 tmp 目录）：审计文件 + 入库。"""

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_fixture(raw_dir / "commerce_registry_sample.csv")
    out_dir = tmp_path / "DED_data"
    official_path = tmp_path / "official_ded_monthly.csv"
    official_path.write_text(
        "month,official_new_licenses,note,source_url\n2024-01,12345,test,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sd, "RAW", raw_dir)
    monkeypatch.setattr(sd, "OUT", out_dir)
    monkeypatch.setattr(sd, "OFFICIAL_CSV", official_path)

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = sd.update(con, skip_download=True)
    assert outcome["status"] == "ok"
    assert (out_dir / "monthly_counts.csv").exists()
    assert (out_dir / "monthly_new_licenses.csv").exists()
    assert (out_dir / "monthly_by_type.csv").exists()
    assert (out_dir / "schema_report.txt").exists()
    assert (out_dir / "fetch_manifest.json").exists()
    assert con.execute(
        "SELECT count(*) FROM ded_monthly WHERE series='official_new_licenses'"
    ).fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM ded_monthly_by_type").fetchone()[0] == 4
    con.close()
