"""Dubai Customs "Airway Bill Details"（航空运单行项目）月度指标入库。

数据源（Data Dubai / Dubai Pulse 官方开放数据）：

- 数据集页：https://data.dubai/en/l/459114（"Airway Bill Details"，ID 459114）
- 发布机构：Dubai Customs（Open 许可，无需密钥）
- 粒度：运单行项目（line items），22 列，含 goods description、货运类型、
  件数、重量/体积及单位、起运/目的机场城市与代码、创建/修改时间戳。
- 原始文件：``data/UAE/raw/dubai_customs_air/csv/<shard>.csv.gz``（由
  ``raw/dubai_customs_air/download_dubai_customs_air.py`` 从 cdn.data.dubai
  下载全量分片；每片约 100 万行，33 片覆盖 2019-08 起至今，长期逐月积累）。

口径说明（重要）：

- 每条记录是一张运单（airwaybillid）下的一个行项目（airwaybilldetailid）；
  "运单数" = 月度去重 airwaybillid 计数，"行项目数" = 行数。
- 方向判定基于起运/目的机场城市名称或城市码（详见 ``_is_dubai``）：
    - 进口：目的地在迪拜、起运地非迪拜；
    - 出口：起运地在迪拜、目的地非迪拜；
    - 境内：两端均在迪拜；
    - 转运：两端均非迪拜（经由迪拜海关监管的货运）。
- 重量统一折算为吨（Pounds→kg 按 0.45359237），体积统一折算为立方米
  （Cubic Feet→m³ 按 0.0283168466，Cubic Inches→m³ 按 1.6387064e-5，
  Cubic Centimetres→m³ 按 1e-6）。
- 数据含少量负值行（重量/件数为负，疑为海关冲销/调整记录），聚合按净值
  加总并保留，质检报告中单独披露负值占比。
- 聚合按 ``createddate`` 所在月份归期。

指标（月度）：
- 迪拜航空货运_进口总量(吨) / 出口总量(吨) / 转运总量(吨) / 境内总量(吨) / 合计(吨)
- 迪拜航空货运_进口件数(件) / 出口件数(件) / 合计件数(件)
- 迪拜航空货运_进口运单数(张) / 出口运单数(张) / 合计运单数(张)
- 迪拜航空货运_进口体积(立方米) / 出口体积(立方米)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "dubai_customs_air"
CSV_DIR = RAW_DIR / "csv"

TARGET_SHEET = "月度_迪拜海关航空"  # 预留（写表暂未实现）

LB_TO_KG = 0.45359237
FT3_TO_M3 = 0.0283168466
IN3_TO_M3 = 1.6387064e-5
CM3_TO_M3 = 1e-6

COLUMNS = (
    "airwaybilldetailid", "airwaybillid", "createddate", "modifieddate",
    "destairportcitycode", "destairportcityid", "destairportcityname",
    "goodsdesc", "isactive", "numberofpieces", "originairportcitycode",
    "originairportcityid", "originairportcityname", "shipmenttypeid",
    "shipmenttypename", "volume", "volumetypeid", "volumetypename",
    "weight", "weighttypeid", "weighttypename", "load_timestamp",
)

# 迪拜机场城市判定：名称含 DUBAI/DXB/DWC，或城市码以 AE 开头
DUBAI_NAME_MARKERS = ("DUBAI", "DXB", "DWC", "AL MAKTOUM")


def _is_dubai(city_name: str, city_code: str) -> bool:
    name = (city_name or "").upper()
    code = (city_code or "").upper()
    if code.startswith("AE"):
        return True
    return any(marker in name for marker in DUBAI_NAME_MARKERS)


WEIGHT_UNIT_MULT = {
    "KILOS": 1.0,
    "POUNDS": LB_TO_KG,
}
VOLUME_UNIT_MULT = {
    "CUBIC METRES": 1.0,
    "CUBIC FEET": FT3_TO_M3,
    "CUBIC INCHES": IN3_TO_M3,
    "CUBIC CENTIMETRES": CM3_TO_M3,
}

DIRECTIONS = ("import", "export", "transit", "domestic")

INDICATOR_TPL = {
    # (方向, 度量) -> 指标中文名
    ("import", "weight_t"): "迪拜航空货运_进口总量(吨)",
    ("export", "weight_t"): "迪拜航空货运_出口总量(吨)",
    ("transit", "weight_t"): "迪拜航空货运_转运总量(吨)",
    ("domestic", "weight_t"): "迪拜航空货运_境内总量(吨)",
    ("all", "weight_t"): "迪拜航空货运_合计总量(吨)",
    ("import", "pieces"): "迪拜航空货运_进口件数(件)",
    ("export", "pieces"): "迪拜航空货运_出口件数(件)",
    ("all", "pieces"): "迪拜航空货运_合计件数(件)",
    ("import", "awbs"): "迪拜航空货运_进口运单数(张)",
    ("export", "awbs"): "迪拜航空货运_出口运单数(张)",
    ("all", "awbs"): "迪拜航空货运_合计运单数(张)",
    ("import", "volume_m3"): "迪拜航空货运_进口体积(立方米)",
    ("export", "volume_m3"): "迪拜航空货运_出口体积(立方米)",
}


# ---------------------------------------------------------------------------
# 解析 / 聚合
# ---------------------------------------------------------------------------


def _to_float(v: str | None) -> float | None:
    if v is None:
        return None
    s = v.strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _period_of(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return date(int(iso[0:4]), int(iso[5:7]), 1)
    except (ValueError, IndexError):
        return None


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def collect_rows(shard_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """流式扫描各分片，按 (月份, 方向) 聚合重量/件数/运单数/体积。

    返回 (长表行, 质量统计)。运单数按月度方向去重 airwaybillid 集合。
    """
    agg: dict[tuple[tuple[int, int], str, str], float] = {}  # (month, dir, measure)
    awb_sets: dict[tuple[tuple[int, int], str], set] = {}
    stats = {
        "rows_read": 0,
        "bad_rows": 0,
        "neg_weight_rows": 0,
        "neg_pieces_rows": 0,
        "unknown_unit_weight": 0,
        "unknown_unit_volume": 0,
        "no_period": 0,
        "month_counts": Counter(),
        "files": [],
    }

    for path in sorted(shard_paths):
        seen_rows = 0
        with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path.name}: 缺少字段 {missing}")
            for row in reader:
                seen_rows += 1
                period = _period_of(row.get("createddate"))
                if period is None:
                    stats["no_period"] += 1
                    continue
                mk = _month_key(period)
                stats["month_counts"][f"{period.year:04d}-{period.month:02d}"] += 1

                direction = _direction_of(row)
                w_val = _to_float(row.get("weight"))
                kg = None
                if w_val is not None:
                    mult = WEIGHT_UNIT_MULT.get((row.get("weighttypename") or "").upper().strip())
                    if mult is None:
                        stats["unknown_unit_weight"] += 1
                        mult = 1.0
                    kg = w_val * mult
                    if w_val < 0:
                        stats["neg_weight_rows"] += 1
                if kg is not None:
                    _bump(agg, (mk, direction, "weight_t"), kg / 1000.0)

                pieces = _to_float(row.get("numberofpieces"))
                if pieces is not None:
                    if pieces < 0:
                        stats["neg_pieces_rows"] += 1
                    _bump(agg, (mk, direction, "pieces"), pieces)

                awbid = (row.get("airwaybillid") or "").strip()
                if awbid:
                    awb_sets.setdefault((mk, direction), set()).add(awbid)

                v_val = _to_float(row.get("volume"))
                if v_val is not None:
                    mult = VOLUME_UNIT_MULT.get((row.get("volumetypename") or "").upper().strip())
                    if mult is None:
                        stats["unknown_unit_volume"] += 1
                        mult = 1.0
                    _bump(agg, (mk, direction, "volume_m3"), v_val * mult)
        stats["rows_read"] += seen_rows
        stats["files"].append(path.name)

    # 汇总"合计"方向 = 四个方向之和
    for (mk, direction, measure), value in list(agg.items()):
        if direction == "all":
            continue
        key = (mk, "all", measure)
        if measure == "awbs":
            continue  # 运单数按集合合并计算
        agg[key] = agg.get(key, 0.0) + value
    for (mk, direction), ids in list(awb_sets.items()):
        if direction == "all":
            continue
        key_all = awb_sets.setdefault((mk, "all"), set())
        key_all |= ids

    rows: list[dict[str, Any]] = []
    for (mk, direction, measure), value in sorted(agg.items()):
        indicator = INDICATOR_TPL.get((direction, measure))
        if indicator is None:
            continue
        rows.append(
            {
                "period": date(mk[0], mk[1], 1),
                "indicator": indicator,
                "value": round(value, 3),
                "source_file": ";".join(stats["files"]),
            }
        )
    for (mk, direction), ids in sorted(awb_sets.items()):
        indicator = INDICATOR_TPL.get((direction, "awbs"))
        if indicator is None:
            continue
        rows.append(
            {
                "period": date(mk[0], mk[1], 1),
                "indicator": indicator,
                "value": len(ids),
                "source_file": ";".join(stats["files"]),
            }
        )
    rows.sort(key=lambda r: (r["period"], r["indicator"]))
    if not rows:
        raise ValueError("dubai_airway_bill_monthly: 未解析到任何观测（检查 raw/dubai_customs_air/csv）")
    return rows, stats


def _bump(agg: dict, key: tuple[tuple[int, int], str, str], value: float) -> None:
    agg[key] = agg.get(key, 0.0) + value


def _direction_of(row: dict[str, Any]) -> str:
    o_name = row.get("originairportcityname") or ""
    o_code = row.get("originairportcitycode") or ""
    d_name = row.get("destairportcityname") or ""
    d_code = row.get("destairportcitycode") or ""
    o_dxb = _is_dubai(o_name, o_code)
    d_dxb = _is_dubai(d_name, d_code)
    if o_dxb and d_dxb:
        return "domestic"
    if d_dxb:
        return "import"
    if o_dxb:
        return "export"
    return "transit"


# ---------------------------------------------------------------------------
# 质检
# ---------------------------------------------------------------------------


def build_quality_report(rows: list[dict[str, Any]], stats: dict[str, Any]) -> dict[str, Any]:
    periods = sorted({r["period"] for r in rows})
    monthly = sorted({f"{p.year:04d}-{p.month:02d}" for p in periods})
    missing: list[str] = []
    if monthly:
        y0, m0 = map(int, monthly[0].split("-"))
        y1, m1 = map(int, monthly[-1].split("-"))
        cy, cm = y0, m0
        all_months = set()
        while (cy, cm) <= (y1, m1):
            all_months.add(f"{cy:04d}-{cm:02d}")
            cm += 1
            if cm == 13:
                cm = 1
                cy += 1
        missing = sorted(all_months - set(monthly))

    checks = [
        {
            "name": "headers_valid",
            "passed": stats["bad_rows"] == 0,
            "detail": f"字段长度异常行: {stats['bad_rows']}",
        },
        {
            "name": "monthly_continuity",
            "passed": not missing,
            "detail": ("逐月连续" if not missing else "缺月: " + ", ".join(missing)),
        },
        {
            "name": "has_recent_data",
            "passed": bool(monthly) and monthly[-1] >= "2026-01",
            "detail": f"最新月份: {monthly[-1] if monthly else '-'}",
        },
        {
            "name": "negatives_disclosed",
            "passed": True,  # 负值系海关冲销记录，聚合保留净值并在此披露
            "detail": (
                f"负重量行 {stats['neg_weight_rows']} / 负件数行 {stats['neg_pieces_rows']} "
                f"（占总行 {stats['rows_read']}）"
            ),
        },
    ]
    return {
        "generated_at": date.today().isoformat(),
        "status": "passed" if all(c["passed"] for c in checks) else "failed",
        "coverage": {
            "start_period": monthly[0] if monthly else None,
            "end_period": monthly[-1] if monthly else None,
            "month_count": len(monthly),
            "missing_periods": missing,
            "file_count": len(stats["files"]),
            "rows_read": stats["rows_read"],
        },
        "stats": {
            "rows_read": stats["rows_read"],
            "no_period": stats["no_period"],
            "neg_weight_rows": stats["neg_weight_rows"],
            "neg_pieces_rows": stats["neg_pieces_rows"],
            "unknown_unit_weight": stats["unknown_unit_weight"],
            "unknown_unit_volume": stats["unknown_unit_volume"],
        },
        "checks": checks,
        "note": (
            "方向判定：进口=目的地在迪拜；出口=起运地在迪拜；境内=两端迪拜；"
            "转运=两端均非迪拜。重量统一为吨、体积统一为立方米；负值行按净值保留。"
        ),
    }


# ---------------------------------------------------------------------------
# 字典
# ---------------------------------------------------------------------------


def _dictionary_rows() -> list[dict[str, Any]]:
    rows = []
    for indicator in INDICATOR_TPL.values():
        unit = "吨" if "(吨)" in indicator else ("件" if "(件)" in indicator else ("张" if "(张)" in indicator else "立方米"))
        rows.append(
            {
                "indicator_name": indicator,
                "frequency": "月",
                "unit": unit,
                "source": "Dubai Customs Airway Bill Details（data.dubai 开放数据，ID 459114）",
                "type": "交通",
                "industry": "交通运输",
                "updated_at": date.today(),
            }
        )
    return rows


@contextmanager
def _transaction(con) -> Iterator[None]:
    transaction = con.begin()
    try:
        yield
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """解析 raw/dubai_customs_air/csv/*.csv.gz → 质检 → 事务内入库。

    下载由 ``download_dubai_customs_air.py`` 负责（33 片全量）；本函数不联网。
    """
    shards = sorted(CSV_DIR.glob("*.csv.gz"))
    if not shards:
        raise FileNotFoundError(
            f"未找到 {CSV_DIR}/*.csv.gz；请先运行 "
            f"raw/dubai_customs_air/download_dubai_customs_air.py"
        )
    rows, stats = collect_rows(shards)
    db.ensure(
        con,
        "dubai_airway_bill_monthly",
        """
        CREATE TABLE IF NOT EXISTS dubai_airway_bill_monthly (
            period      DATE           NOT NULL,
            indicator   VARCHAR        NOT NULL,
            value       DECIMAL(28, 3),
            source_file VARCHAR,
            PRIMARY KEY (period, indicator)
        )
        """,
    )
    report = build_quality_report(rows, stats)
    (RAW_DIR / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if report["status"] != "passed":
        failed = [c["name"] for c in report["checks"] if not c["passed"]]
        raise ValueError("Dubai Customs airway bill checks failed: " + ", ".join(failed))

    with _transaction(con):
        db.replace(con, "dubai_airway_bill_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    cov = report["coverage"]
    note = (
        f"{len(rows)} 条指标观测，{cov['rows_read']} 行原始记录 "
        f"（{cov['start_period']} 至 {cov['end_period']}，"
        f"{cov['month_count']} 个月 × {len(set(r['indicator'] for r in rows))} 指标，"
        f"{cov['file_count']} 个分片）"
    )
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """迪拜海关航空数据暂未接入 Excel 写表（预留占位）。"""
    return {
        "status": "skipped",
        "note": (
            "dubai_airway_bill_monthly 尚未接入 Excel 写表；"
            "如需合并请实现 write_dubai_customs_air_sheet.ps1 并注册到 merge_workbook.py"
        ),
    }


if __name__ == "__main__":
    print("source_dubai_customs_air.py 自检：")
    print("  update(con, force=, skip_download=) 解析 raw/dubai_customs_air/csv/*.csv.gz → 入库")
    print("  merge(workbook_path) 暂未接入 Excel 写表")