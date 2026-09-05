"""Tests for data/source_gfs.py: PDF/XLSX 解析、记录拆分、入库往返。

全部使用 tmp_path 构造的最小样例（含手工构造的合规单页 PDF），
不碰网络、不碰真实工作簿。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from htfa.jobs.uae_data import source_gfs as sg
from htfa.jobs.uae_data import db

# 每个科目的 PDF/XLSX 行标签（与 source_gfs 内置正则一一对应）
PDF_LABELS = {
    "1": "Revenue", "11": "Taxes", "12": "Social contributions", "13": "Grants",
    "14": "Other revenue", "2": "Expense", "21": "Compensation of employees",
    "22": "Use of goods and services", "23": "Consumption of fixed capital",
    "24": "Interest", "25": "Subsidies", "26": "Grants", "27": "Social benefits",
    "28": "Other expense", "GOB": "Gross operating balance",
    "NOB": "Net operating balance",
    "31": "Net/gross investment in nonfinancial assets", "311": "Fixed assets",
    "312": "Change in inventories", "313": "Valuables", "314": "Nonproduced assets",
    "2M": "Expenditure", "NLB": "Net lending / borrowing",
    "32": "Net acquisition of financial assets", "321": "Domestic debtors",
    "322": "External debtors", "33": "Net incurrence of liabilities",
    "331": "Domestic creditors", "332": "External creditors",
}


def _row_values(index: int) -> tuple[str, str, str, str, str]:
    """每个科目一行 5 个值（Q1-Q4 + 年度），全部整数便于精确比对。"""

    return tuple(str(100 + index + offset * 100) for offset in range(5))


def _build_pdf(path: Path, year: int = 2024, *, missing_2m: bool = False) -> Path:
    """手工构造一个合规的单页 GFS PDF（Helvetica 文本流）。"""

    codes = [
        code for code in sg.INDICATOR_BY_CODE
        if not (missing_2m and code == "2M")
    ]
    lines = [
        f"{code} {PDF_LABELS[code]} " + " ".join(_row_values(i))
        for i, code in enumerate(codes)
    ]
    content = (
        "BT /F1 10 Tf 72 720 Td 14 TL\n"
        + "T* ".join(f'({" " if n else ""}{line}) Tj\n' for n, line in enumerate(lines))
        + "T* ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content.encode('utf-8'))} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = ["%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len("".join(out)))
        out.append(f"{index} 0 obj\n{obj}\nendobj\n")
    xref_pos = len("".join(out))
    out.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.append(f"{offset:010d} 00000 n \n")
    out.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    )
    path.write_bytes("".join(out).encode("ascii"))
    return path


def _build_workbook(path: Path, year: int, *, na_quarters: tuple = ()) -> Path:
    """构造现代 GFS 工作簿：Meta Data + 唯一数据 sheet。"""

    from openpyxl import Workbook

    wb = Workbook()
    meta = wb.active
    meta.title = "Meta Data "
    meta.append([None, "United Arab Emirates Government Finance Statistics"])
    ws = wb.create_sheet("GFS data")
    has_annual = year != 2026  # 2026 文件只有季度列
    header = ["Code", " (Numbers in Millions UAE Dirhams)", "Q1", "Q2", "Q3", "Q4"]
    if has_annual:
        header.append(str(year))
    ws.append(header)
    for index, code in enumerate(sg.INDICATOR_BY_CODE):
        values = _row_values(index)
        row = [code, PDF_LABELS[code]]  # 列A=科目码，列B=英文名（与真实文件一致）
        for position in range(4):
            row.append("NA" if position in na_quarters else int(values[position]))
        if has_annual:
            row.append(int(values[4]))
        ws.append(row)
    wb.save(path)
    return path


def test_extract_pdf_minimal_fixture(tmp_path) -> None:
    """手工 PDF 能解析出全部 29 个科目与 5 个值。"""

    pdf = _build_pdf(tmp_path / "GFS-2024.pdf")
    rows = sg.extract_pdf(pdf)
    assert set(rows) == set(sg.INDICATOR_BY_CODE)
    assert rows["1"] == (Decimal(100), Decimal(200), Decimal(300), Decimal(400), Decimal(500))
    assert rows["NOB"] == (Decimal(115), Decimal(215), Decimal(315), Decimal(415), Decimal(515))


def test_extract_pdf_optional_2m(tmp_path) -> None:
    """缺少 2M 的 2012 文件不报错，2M 行缺位。"""

    pdf = _build_pdf(tmp_path / "GFS-2012.pdf", year=2012, missing_2m=True)
    rows = sg.extract_pdf(pdf)
    assert "2M" not in rows
    assert "1" in rows


def test_extract_excel_na_and_annual(tmp_path) -> None:
    """XLSX 提取：NA 转 None、无年度列的 2026 文件年度为 None。"""

    wb2025 = _build_workbook(tmp_path / "GFS-2025.xlsx", 2025)
    rows = sg.extract_excel(wb2025)
    assert len(rows) == 29
    assert rows["1"] == (Decimal(100), Decimal(200), Decimal(300), Decimal(400), Decimal(500))

    wb2026 = _build_workbook(tmp_path / "GFS-2026.xlsx", 2026, na_quarters=(1, 2, 3))
    rows26 = sg.extract_excel(wb2026)
    assert rows26["1"] == (Decimal(100), None, None, None, None)


def test_records_split_and_db_roundtrip(tmp_path) -> None:
    """解析结果 → 入库（内存库）→ _query_records 回读一致；无值单元格不入库。"""

    pdf_2024 = _build_pdf(tmp_path / "GFS-2024.pdf", year=2024)
    pdf_2012 = _build_pdf(tmp_path / "GFS-2012.pdf", year=2012, missing_2m=True)
    releases = {2024: sg.extract_pdf(pdf_2024), 2012: sg.extract_pdf(pdf_2012)}

    quarterly_rows, annual_rows = sg._records_to_db_rows(releases)
    # 2012 缺 2M → 季度/年度均少 2M 行
    assert sum(1 for r in quarterly_rows if r["year"] == 2012 and r["indicator"] == "2M") == 0
    assert sum(1 for r in quarterly_rows if r["year"] == 2024 and r["indicator"] == "2M") == 4
    assert sum(1 for r in annual_rows if r["year"] == 2024 and r["indicator"] == "2M") == 1

    con = db.connect(":memory:")
    db.init_schema(con)
    with sg._transaction(con):
        db.replace(con, "gfs_quarterly", quarterly_rows)
        db.replace(con, "gfs_annual", annual_rows)

    quarterly_records, annual_records = sg._query_records(con)
    assert len(quarterly_records) == 8  # 2012 Q1-Q4 + 2024 Q1-Q4
    assert len(annual_records) == 2
    by_period = {record["period"]: record["values"] for record in quarterly_records}
    assert by_period["2024-03-31"][0] == Decimal(100)
    assert by_period["2012-03-31"][21] is None  # 2M 缺失语义保留
    assert by_period["2024-03-31"][21] == Decimal(121)
    assert annual_records[0]["period"] == "2024-12-31"
    assert annual_records[0]["values"][0] == Decimal(500)
    con.close()


def test_dictionary_rows_cover_both_frequencies() -> None:
    """29 科目×季度/年度两个频率 = 58 行字典。"""

    rows = sg._dictionary_rows()
    assert len(rows) == len(sg.INDICATORS) * 2
    frequencies = {row["frequency"] for row in rows}
    assert frequencies == {"季", "年"}
    names = [row["indicator_name"] for row in rows]
    assert "阿联酋:GFS:季度:收入" in names
    assert "阿联酋:GFS:年度:收入:税收" in names
    assert all(row["unit"] == "百万阿联酋迪拉姆" for row in rows)
    assert all(row["source"] == "UAE Ministry of Finance (MOF GFS)" for row in rows)


def test_update_locks_data_into_database(tmp_path, monkeypatch) -> None:
    """update() 全流程：解析→入库→报告（extract_sources 与原始目录被替换）。"""

    fake_releases = {
        2024: {code: (Decimal(1), Decimal(2), Decimal(3), Decimal(4), Decimal(5)) for code in sg.INDICATOR_BY_CODE}
    }
    monkeypatch.setattr(sg, "RAW_GFS", tmp_path)
    monkeypatch.setattr(sg, "extract_sources", lambda source_dir: fake_releases)

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = sg.update(con)
    quarterly_count = con.execute("SELECT count(*) FROM gfs_quarterly").fetchone()[0]
    annual_count = con.execute("SELECT count(*) FROM gfs_annual").fetchone()[0]
    dictionary_count = con.execute("SELECT count(*) FROM meta_indicator_dictionary").fetchone()[0]
    con.close()

    assert outcome["status"] == "ok"
    assert quarterly_count == 4 * len(sg.INDICATORS)
    assert annual_count == len(sg.INDICATORS)
    assert dictionary_count == len(sg.INDICATORS) * 2
    assert (tmp_path / "validation_report.json").exists()


def test_build_payload_shape() -> None:
    """payload 结构：两个 sheet、58 个字典指标、remove 列表。"""

    quarterly = [
        {"period": "2024-03-31", "source_file": "GFS-2024",
         "values": [Decimal(100) if i % 3 else None for i in range(29)]}
    ]
    annual = [
        {"period": "2024-12-31", "source_file": "GFS-2024",
         "values": [Decimal(500) for _ in range(29)]}
    ]
    payload = sg.build_payload(quarterly, annual)
    assert [sheet["name"] for sheet in payload["sheets"]] == ["季度_GFS", "年度_GFS"]
    assert len(payload["indicators"]) == len(sg.INDICATORS) * 2
    assert payload["remove_dictionary_indicators"] == [i.name for i in sg.INDICATORS]
    assert payload["sheets"][0]["records"][0]["values"][0] is None
    assert payload["sheets"][0]["records"][0]["values"][1] == "100"
    assert payload["unit"] == "百万阿联酋迪拉姆"


def test_period_records_keeps_annual_not_summed() -> None:
    """年度值只取原件年度列（绝不由季度加总）。"""

    releases = {
        2024: {code: (Decimal(1), Decimal(2), Decimal(3), Decimal(4), Decimal(999)) for code in sg.INDICATOR_BY_CODE}
    }
    quarterly, annual = sg._period_records(releases)
    assert len(quarterly) == 4
    assert len(annual) == 1
    assert annual[0]["values"][0] == Decimal(999)
    assert sum(record["values"][0] for record in quarterly) == 10
