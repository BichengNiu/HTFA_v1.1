"""Salik（迪拜收费公路运营商）「Registered Active Vehicles」季度入库。

数据来源：Salik Company PJSC 投资者关系（https://www.salik.ae/Investors）季度财报 /
投资者演示 PDF 中的官方 KPI「Registered active vehicles (mn)」。Salik 只按季度披露该
绝对数（无月度序列）。

- 原始件：`data/UAE/raw/salik/*.pdf`（季度演示/财报，人工下载）。
- 编译序列：`data/UAE/raw/salik/registered_active_vehicles_quarterly.csv`
  （period_end, vehicles_mn, source, note；各数值注明出处文件，横图读数可能取整）。
- 入库表：`salik_active_vehicles_quarterly`（period 季末日, value 百万辆, source, note）。

⚠️ 用户指示：**本数据暂不进入 Excel**。因此本模块只实现 ``update()``（入库 duckdb）；
``merge()`` 按协议返回「已跳过」占位（不写任何 sheet），且不注册到
`merge_workbook.py` 的 SOURCES。待用户决定接入 Excel 时再补充写表助手。

单位：百万辆（mn）。
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_CSV = DATA_DIR / "raw" / "salik" / "registered_active_vehicles_quarterly.csv"
TABLE = "salik_active_vehicles_quarterly"
SOURCE_NAME = "Salik (salik.ae IR)"
UNIT = "百万辆"
FREQUENCY = "季"
INDUSTRY = "交通"
INDICATOR_NAME = "阿联酋:Salik注册活跃车辆:季末值"

_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    period DATE           NOT NULL PRIMARY KEY,
    value  DECIMAL(28, 3),
    source VARCHAR,
    note   VARCHAR
)
"""


# ---------------------------------------------------------------------------
# 解析 / 入库
# ---------------------------------------------------------------------------


def _read_rows() -> list[dict]:
    """读编译 CSV；vehicles_mn 为空（如某期未给绝对数）则跳过该行。"""
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"Salik 编译序列缺失: {RAW_CSV}")
    rows: list[dict] = []
    with RAW_CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            period_end = record.get("period_end", "").strip()
            value_text = (record.get("vehicles_mn") or "").strip()
            if not period_end or not value_text:
                continue
            try:
                value = float(value_text)
            except ValueError:
                continue
            rows.append(
                {
                    "period": date.fromisoformat(period_end),
                    "value": value,
                    "source": record.get("source", "").strip(),
                    "note": record.get("note", "").strip(),
                }
            )
    rows.sort(key=lambda r: r["period"])
    return rows


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """把编译 CSV 整表替换进 duckdb（本数据源无网络下载环节）。"""
    rows = _read_rows()
    if not rows:
        raise ValueError("salik_active_vehicles_quarterly 输入为空，拒绝入库")

    con.begin()
    try:
        db.ensure(con, TABLE, _TABLE_DDL)
        db.replace(con, TABLE, rows)
        db.upsert_dictionary_rows(
            con,
            [
                {
                    "indicator_name": INDICATOR_NAME,
                    "frequency": FREQUENCY,
                    "unit": UNIT,
                    "source": SOURCE_NAME,
                    "type": "存量",
                    "industry": INDUSTRY,
                    "updated_at": date.today(),
                }
            ],
        )
        con.commit()
    except Exception:
        con.rollback()
        raise

    periods = [row["period"].isoformat() for row in rows]
    note = (
        f"{len(rows)} 个季末观测（{periods[0]} 至 {periods[-1]}），"
        "暂不进入 Excel"
    )
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """按用户指示暂不进入 Excel：返回占位，不写任何 sheet。"""
    return {
        "status": "skipped",
        "note": "Salik 按用户指示暂不进入 Excel（source_salik.merge 为占位）",
    }


if __name__ == "__main__":
    print("source_salik.py 自检：")
    print("  update(con, ...) 读取 raw/salik/registered_active_vehicles_quarterly.csv")
    print("    → 入长表 salik_active_vehicles_quarterly（季末日, 百万辆）")
    print("  merge() 为占位：用户指示暂不进入 Excel。")
