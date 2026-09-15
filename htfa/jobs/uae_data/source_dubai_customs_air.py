"""Dubai Customs "Airway Bill Details"（航空运单行项目）月度指标入库。

数据源（Data Dubai / Dubai Pulse 官方开放数据）：

- 数据集页：https://data.dubai/en/l/459114（"Airway Bill Details"，ID 459114）
- 发布机构：Dubai Customs（Open 许可，无需密钥）
- 粒度：运单行项目（line items），22 列，含 goods description、货运类型、
  件数、重量/体积及单位、起运/目的机场城市与代码、创建/修改时间戳。
- 原始文件：``data/UAE/raw/dubai_customs_air/csv/<shard>.csv.gz``（由
  ``raw/dubai_customs_air/download_dubai_customs_air.py`` 自动从 data.dubai
  manifest 发现并从 cdn.data.dubai 下载全量分片；每片约 100 万行）。

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
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Iterator

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "dubai_customs_air"
CSV_DIR = RAW_DIR / "csv"
DOWNLOAD_SCRIPT = RAW_DIR / "download_dubai_customs_air.py"

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
    # 运单号去重使用 DuckDB 的磁盘聚合，避免全量 airwaybillid 集合占满内存。
    for (mk, direction), count in sorted(_distinct_awb_counts(shard_paths).items()):
        indicator = INDICATOR_TPL.get((direction, "awbs"))
        if indicator is None:
            continue
        rows.append(
            {
                "period": date(mk[0], mk[1], 1),
                "indicator": indicator,
                "value": count,
                "source_file": ";".join(stats["files"]),
            }
        )
    rows.sort(key=lambda r: (r["period"], r["indicator"]))
    if not rows:
        raise ValueError("dubai_airway_bill_monthly: 未解析到任何观测（检查 raw/dubai_customs_air/csv）")
    return rows, stats


def _distinct_awb_counts(
    shard_paths: list[Path],
) -> dict[tuple[tuple[int, int], str], int]:
    """Count distinct airway bills with DuckDB's bounded, spillable aggregate."""

    import duckdb

    quoted_paths = ", ".join(
        "'" + str(path).replace("\\", "/").replace("'", "''") + "'"
        for path in shard_paths
    )
    if not quoted_paths:
        return {}

    def dubai_expr(name: str, code: str) -> str:
        value = f"coalesce(upper({name}), '')"
        return (
            f"({value} LIKE 'AE%' OR position('DUBAI' IN {value}) > 0 "
            f"OR position('DXB' IN {value}) > 0 "
            f"OR position('DWC' IN {value}) > 0 "
            f"OR position('AL MAKTOUM' IN {value}) > 0 "
            f"OR coalesce(upper({code}), '') LIKE 'AE%')"
        )

    origin_dubai = dubai_expr("originairportcityname", "originairportcitycode")
    dest_dubai = dubai_expr("destairportcityname", "destairportcitycode")
    direction_expr = (
        f"CASE WHEN {origin_dubai} AND {dest_dubai} THEN 'domestic' "
        f"WHEN {dest_dubai} THEN 'import' "
        f"WHEN {origin_dubai} THEN 'export' ELSE 'transit' END"
    )
    with TemporaryDirectory(prefix=".awb_duckdb_", dir=str(RAW_DIR)) as temp_dir:
        temp_sql = str(Path(temp_dir).as_posix()).replace("'", "''")
        con = duckdb.connect()
        try:
            con.execute("SET memory_limit = '1GB'")
            con.execute("SET threads = 1")
            con.execute("SET preserve_insertion_order = false")
            con.execute(f"SET temp_directory = '{temp_sql}'")
            query = f"""
                WITH base AS (
                    SELECT substr(createddate, 1, 7) AS month,
                           {direction_expr} AS direction,
                           nullif(trim(airwaybillid), '') AS airwaybillid
                    FROM read_csv_auto(
                        [{quoted_paths}],
                        header = true,
                        all_varchar = true,
                        union_by_name = true
                    )
                    WHERE regexp_matches(createddate, '^\\d{{4}}-\\d{{2}}-')
                      AND nullif(trim(airwaybillid), '') IS NOT NULL
                )
                SELECT month, direction, count(DISTINCT airwaybillid) AS count
                FROM base
                GROUP BY month, direction
                UNION ALL
                SELECT month, 'all' AS direction, count(DISTINCT airwaybillid) AS count
                FROM base
                GROUP BY month
            """
            result = con.execute(query).fetchall()
        finally:
            con.close()

    counts: dict[tuple[tuple[int, int], str], int] = {}
    for month, direction, count in result:
        if not month or len(month) != 7:
            continue
        counts[((int(month[:4]), int(month[5:7])), direction)] = int(count)
    return counts


def _current_shards() -> list[Path]:
    """Use only the files named by the newest manifest, not old snapshots."""

    manifest_path = CSV_DIR / "manifest.json"
    if manifest_path.is_file():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
            names = [
                item["file_name"]
                for item in entries
                if item.get("file_extension") == "csv" and item.get("file_name")
            ]
            paths = [CSV_DIR / name for name in names]
            if paths and all(path.is_file() for path in paths):
                return sorted(paths)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
    return sorted(CSV_DIR.glob("*.csv.gz"))


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


def _download_official_shards(*, force: bool) -> str:
    """Refresh the Data Dubai manifest and download new CSV shards."""

    if not DOWNLOAD_SCRIPT.is_file():
        raise FileNotFoundError(f"Data Dubai 下载器缺失: {DOWNLOAD_SCRIPT}")
    command = [sys.executable, str(DOWNLOAD_SCRIPT), "--out", str(CSV_DIR)]
    if force:
        command.append("--force")
    result = subprocess.run(
        command,
        cwd=RAW_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    report_path = CSV_DIR / "download_report.json"
    failed = []
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            failed = [
                item for item in report.get("files", [])
                if item.get("status") not in {"ok", "skipped"}
            ]
        except (OSError, json.JSONDecodeError):
            failed = ["download_report.json 无法读取"]
    if result.returncode != 0 or failed:
        detail = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(
            f"Data Dubai 分片下载失败（失败 {len(failed)} 个）: {detail[-1200:]}"
        )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return output[-1200:] if output else "Data Dubai 分片已刷新"


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """自动刷新 Data Dubai 分片，再质检并入库。"""

    download_note = ""
    if not skip_download:
        try:
            download_note = _download_official_shards(force=force)
        except Exception as exc:  # noqa: BLE001 - valid local shards remain usable
            if not any(CSV_DIR.glob("*.csv.gz")):
                raise
            download_note = f"官网分片下载未完成，使用本地缓存：{exc}"
    shards = _current_shards()
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
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """由 ``source_extended.merge`` 统一写入「月度_迪拜海关航空」。"""
    return {
        "status": "skipped",
        "note": (
            "迪拜海关航空已入 DuckDB；Excel 由 source_extended.merge 统一写入"
        ),
    }


if __name__ == "__main__":
    print("source_dubai_customs_air.py 自检：")
    print("  update(con, force=, skip_download=) 自动刷新 Data Dubai 分片并入库")
    print("  merge(workbook_path) 由 source_extended.merge 统一写入 月度_迪拜海关航空")
