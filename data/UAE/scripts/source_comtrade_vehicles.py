"""UN Comtrade —— 阿联酋 HS 87 车辆进口（月度）入库。

数据口径与 `source_comtrade.py`（资本品设备）一致，但只针对车辆章：
- HS 87 总量 + 四个 HS4 细分子目：8702（客车/巴士）、8703（乘用车）、
  8704（货车）、8708（车辆零件）。
- **直报**（uae_reported，reporterCode=784 flow=M）仅 2017–2019 有值，阿联酋
  2020 起未持续直报月度；**镜像**（all_mirror，partnerCode=784 flow=X，即各国对
  阿出口）全年份连续（2015 → 2026-06），故**以镜像为主口径、直报为辅**，与
  source_comtrade.py 的「直报优先→镜像兜底」不同（镜像本身已完整覆盖，避免把
  直报的 CIF 与镜像 FOB 混在同一条长期序列导致口径断点）。

- 原始 JSON：`raw/comtrade/hs87/{uae_reported,all_mirror}/hs87_*.json`（由
  `raw/comtrade/hs87/download_hs87.py` 下载）。
- 入库长表 `comtrade_vehicles_monthly`：(period, code, value_usd, units, source)。
- ⚠️ 用户指示该源走 UN Comtrade API 核实更新；**暂不进入 Excel**（merge 占位跳过，
  与 Salik 一致），待需要时补充写表助手与 sheet。

台数：与 source_comtrade.py 同规则，取 qtyUnitCode=5（number of items）且仅
is*Estimated 一致的记录；金额取 primaryValue USD。
"""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
from _excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "comtrade" / "hs87"
TABLE = "comtrade_vehicles_monthly"
SOURCE_NAME = "UN Comtrade (HS87 镜像口径)"
UNIT = "台"
FREQUENCY = "月"
INDUSTRY = "交通"

ITEM_UNIT_CODE = 5

# 87 章总量与四个细分子目；(代码, 中文名, 指标类型)
SERIES = (
    ("87", "车辆(HS87)总量", "金额"),
    ("8702", "客车及巴士", "金额"),
    ("8703", "乘用车", "金额"),
    ("8704", "货车", "金额"),
    ("8708", "车辆零件", "金额"),
)
CODE_ORDER = {code: i for i, (code, _name, _t) in enumerate(SERIES)}

# Excel 汇总只出两大整车分类的**进口量（台）**：
#   乘用车 = 8703（passenger motor cars）
#   商用车 = 8702（bus）+ 8704（goods vehicles）
TARGET_SHEET = "月度_汽车进口"
TWO_CATEGORIES = (
    ("乘用车进口量", ("8703",)),
    ("商用车进口量", ("8702", "8704")),
)
CATEGORY_ORDER = {name: i for i, (name, _codes) in enumerate(TWO_CATEGORIES)}
LEGACY_SHEETS: tuple[str, ...] = ()
DICTIONARY_SHEET = "指标字典"

_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    period    DATE    NOT NULL,
    code      VARCHAR NOT NULL,
    value_usd DOUBLE,
    units     DOUBLE,
    source    VARCHAR,
    PRIMARY KEY (period, code)
)
"""


def _period_end(period: str) -> date:
    year, month = int(period[:4]), int(period[4:])
    return date(year, month, monthrange(year, month)[1])


def _item_units(row: dict) -> float | None:
    """与 source_comtrade.py 相同：只取 number of items (qtyUnitCode=5) 且
    isEstimated 标记一致的台数，避免 qty/altQty 双计。"""
    candidates = [
        ("altQty", "altQtyUnitCode", "isAltQtyEstimated", False),
        ("qty", "qtyUnitCode", "isQtyEstimated", False),
        ("altQty", "altQtyUnitCode", "isAltQtyEstimated", True),
        ("qty", "qtyUnitCode", "isQtyEstimated", True),
    ]
    for value_field, unit_field, estimate_field, estimated in candidates:
        if row.get(unit_field) != ITEM_UNIT_CODE:
            continue
        v = row.get(value_field)
        if v is None or float(v) <= 0:
            continue
        row_est = bool(row.get(estimate_field))
        if row_est != estimated:
            continue
        return float(v)
    return None


def _iter_rows(source: str):
    folder = RAW_DIR / source
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.json")):
        if ".part" in path.name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("data", []):
            yield row


def _collect() -> dict[tuple[date, str], dict]:
    """按 (period, code) 聚合，镜像优先、直报复用。

    同 (period, code) 的**所有申报国行求和**（镜像 = 各国对阿出口之和；直报 =
    阿联酋对各国进口重报默认 partnerCode=0 已是合计，但保险起见同样累加）。
    """
    out: dict[tuple[date, str], dict] = {}

    def normalize(code: str) -> str | None:
        code = code.zfill(4)
        if code == "0087":
            code = "87"
        return code if code in CODE_ORDER else None

    def accumulate(period: str, code: str, value: float | None,
                   units: float | None, source: str) -> None:
        key = (_period_end(period), code)
        rec = out.setdefault(
            key,
            {"value_usd": None, "units": None, "source": None},
        )
        # 已有镜像用户时不被直报复盖（镜像为主）
        if rec["source"] == "all_mirror" and source != "all_mirror":
            return
        if value is not None:
            rec["value_usd"] = (rec["value_usd"] or 0.0) + value
        if units is not None:
            rec["units"] = (rec["units"] or 0.0) + units
        if rec["source"] is None:
            rec["source"] = source

    for row in _iter_rows("all_mirror"):
        period = str(row.get("period", ""))
        code = normalize(str(row.get("cmdCode", "")))
        if len(period) != 6 or code is None:
            continue
        v = row.get("primaryValue")
        accumulate(period, code, float(v) if v is not None else None,
                   _item_units(row), "all_mirror")

    for row in _iter_rows("uae_reported"):
        period = str(row.get("period", ""))
        code = normalize(str(row.get("cmdCode", "")))
        if len(period) != 6 or code is None:
            continue
        # 直报只在镜像缺失的 (period, code) 生效
        key = (_period_end(period), code)
        if out.get(key, {}).get("source") == "all_mirror":
            continue
        v = row.get("primaryValue")
        accumulate(period, code, float(v) if v is not None else None,
                   _item_units(row), "uae_reported")

    for rec in out.values():
        if rec["value_usd"] is not None:
            rec["value_usd"] = round(rec["value_usd"], 3)
        if rec["units"] is not None:
            rec["units"] = round(rec["units"], 3)
    return out


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": f"阿联酋:{name}:当月值",
            "frequency": FREQUENCY,
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": "数量",
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, _codes in TWO_CATEGORIES
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """从 raw/comtrade/hs87/ JSON 聚合 → 整表替换入库。

    下载由 `raw/comtrade/hs87/download_hs87.py` 负责（本模块不联网）。
    """
    if skip_download:
        missing = [
            folder
            for folder in (RAW_DIR / "all_mirror", RAW_DIR / "uae_reported")
            if not folder.exists() or not any(folder.glob("*.json"))
        ]
        if missing:
            raise FileNotFoundError(
                "--skip-download 但缺少 HS87 输入: "
                + ", ".join(str(p) for p in missing)
            )

    collected = _collect()
    if not collected:
        raise ValueError("comtrade HS87 无任何观测，拒绝入库")

    rows = [
        {
            "period": period,
            "code": code,
            "value_usd": rec["value_usd"],
            "units": rec["units"],
            "source": rec["source"],
        }
        for (period, code), rec in sorted(collected.items())
    ]

    con.begin()
    try:
        db.ensure(con, TABLE, _TABLE_DDL)
        db.replace(con, TABLE, rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())
        con.commit()
    except Exception:
        con.rollback()
        raise

    periods = sorted({row["period"] for row in rows})
    source_counts: dict[str, int] = {}
    for row in rows:
        source_counts[row["source"]] = source_counts.get(row["source"], 0) + 1
    note = (
        f"{len(rows)} 行（{periods[0]} 至 {periods[-1]}），"
        f"来源分布 {source_counts}；Excel 只出两大整车类台数"
    )
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """从 comtrade_vehicles_monthly 聚合两大整车类**进口量（台）**写 月度_汽车进口。

    - 乘用车 = 8703；商用车 = 8702（bus）+ 8704（goods vehicles）。
    - 只取台数（units，qtyUnitCode=5），不写金额；最新在前；缺失留空。
    """
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_comtrade_vehicles_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, code, units FROM comtrade_vehicles_monthly "
            "WHERE code IN ('8702','8703','8704') ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    if not db_rows:
        raise ValueError("comtrade_vehicles_monthly 无整车台数，无法合并")

    # 按 period 聚合两大整车类台数
    by_period: dict[str, list] = {}
    for period, code, units in db_rows:
        if units is None:
            continue
        key = period.strftime("%Y-%m")
        item = by_period.setdefault(key, [None] * len(TWO_CATEGORIES))
        for name, codes in TWO_CATEGORIES:
            if code in codes:
                idx = CATEGORY_ORDER[name]
                item[idx] = (item[idx] or 0.0) + float(units)

    if not by_period:
        raise ValueError("无有效整车台数观测，无法合并")

    observations = [
        type(
            "Observation",
            (),
            {
                "period": period,
                "values": tuple(item),
                "source_file": SOURCE_NAME,
            },
        )()
        for period, item in sorted(by_period.items())
    ]

    payload = {
        "source_label": SOURCE_NAME,
        "legacy_sheet_names": list(LEGACY_SHEETS),
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": FREQUENCY,
        "unit": UNIT,
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": "数量", "industry": INDUSTRY, "unit": UNIT}
            for name, _codes in TWO_CATEGORIES
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload,
        prefix=".comtrade-vehicles-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写 {TARGET_SHEET}（乘用车+商用车台数）",
    }


if __name__ == "__main__":
    print("source_comtrade_vehicles.py 自检：")
    print("  update(con, ...) 聚合 raw/comtrade/hs87/ JSON → comtrade_vehicles_monthly")
    print("     （镜像口径为主，金额 USD + 台数）")
    print("  merge() 聚合乘用车(8703)+商用车(8702+8704) 台数 → 月度_汽车进口")
    print("  Excel 只写两大整车类的进口量（台），不含金额与零件。")
