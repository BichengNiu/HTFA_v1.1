"""RTA（迪拜道路交通管理局）交通数据集（source_rta.py）——入库。

数据来源：Data Dubai 开放门户（https://data.dubai/，由 Dubai Pulse 整合）上 RTA
发布的公开数据集。下载走门户「免 token 文件视图」：
`GET https://data.dubai/o/dda/data-services/dataset-download?datasetId=<id>&page=N...`
→ 返回签名 CDN 直链（cdn.data.dubai，10 分钟内有效），直链内容为明文 CSV
（文件名带 .gz 但**实际未压缩**，解析时先验魔数）。

收录 6 个数据集（RTA entity ERC 38d7271d-d3ae-453d-8193-db09719f7657）：

| datasetId | datasetName | 频率 | 内容 |
|---|---|---|---|
| 459793 | bus_passengers_trips_by_route_monthly | 月 | 公交按线路月度趟次（detail，全量） |
| 466217 | marine_passengers_trips_by_station_monthly | 月 | 水运按站点月度人次（detail，全量） |
| 469849 | taxis_and_number_of_trips_by_carrier_company_month | 月 | 出租车按运营商月度趟次/车队（detail，全量） |
| 459282 | average_speed_per_line_buses | 日×时段 | 公交线路平均速度（detail，4 片 ≈ 全量） |
| 466229 | marine_ridership | 日（交易级） | 水运刷卡交易，用于日度聚合 |
| 459803 | bus_ridership | 日（交易级） | 公交刷卡交易，原始文件仅保存在 raw，不入库 |

原始 CSV 全部保存在 ``data/UAE/raw/rta/``；DuckDB 只保留
``rta_transport_monthly`` / ``rta_transport_daily`` 两张聚合指标表。
这样既保留可追溯的原始数据，又避免把千万级交易明细复制进主库。

目标 sheet：`月度_RTA交通`（公交/水运/出租车月度）、`日度_RTA交通`
（水运日度人次、公交日均速度）。
"""

from __future__ import annotations

import calendar
import csv
import gzip
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import requests

import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "rta"
SOURCE_NAME = "RTA Open Data (Data Dubai)"
INDUSTRY = "交通"
DICTIONARY_SHEET = "指标字典"
MONTHLY_SHEET = "月度_RTA交通"
DAILY_SHEET = "日度_RTA交通"

BASE_DL = "https://data.dubai/o/dda/data-services/dataset-download"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

DATASETS: dict[int, str] = {
    459793: "bus_passengers_trips_by_route_monthly",
    466217: "marine_passengers_trips_by_station_monthly",
    469849: "taxis_and_number_of_trips_by_carrier_company_month",
    459282: "average_speed_per_line_buses",
    466229: "marine_ridership",
    459803: "bus_ridership",
}
MONTHLY_INDICATORS: list[tuple[str, str, str, str]] = [
    ("迪拜:公交客运人次(月)", "月", "人次", "流量"),
    ("迪拜:水运客运人次(月)", "月", "人次", "流量"),
    ("迪拜:出租车趟次(月)", "月", "趟次", "流量"),
    ("迪拜:出租车车队数(辆,月)", "月", "辆", "存量"),
]
DAILY_INDICATORS: list[tuple[str, str, str, str]] = [
    ("迪拜:水运客运人次(日)", "日", "人次", "流量"),
    ("迪拜:公交平均速度(km/h,日)", "日", "km/h", "代理指标"),
]

_TABLE_DDL: dict[str, str] = {
    "rta_transport_monthly": (
        "CREATE TABLE IF NOT EXISTS rta_transport_monthly (\n"
        "  period DATE NOT NULL, indicator VARCHAR NOT NULL,\n"
        "  value DECIMAL(20, 3), PRIMARY KEY (period, indicator))"
    ),
    "rta_transport_daily": (
        "CREATE TABLE IF NOT EXISTS rta_transport_daily (\n"
        "  period DATE NOT NULL, indicator VARCHAR NOT NULL,\n"
        "  value DECIMAL(20, 3), PRIMARY KEY (period, indicator))"
    ),
}

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_LEGACY_TABLES = (
    "rta_bus_trips_route_monthly",
    "rta_marine_trips_station_monthly",
    "rta_taxi_trips_monthly",
    "rta_bus_speed_daily_detail",
    "rta_marine_ridership_raw",
    "rta_bus_ridership_raw",
)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def _list_csv_files(dataset_id: int, max_files: int | None = None) -> list[dict]:
    """分页枚举 dataset-download 元数据，按序返回 CSV 条目（含 folder / file_url）。"""
    files: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            BASE_DL,
            params={"datasetId": dataset_id, "page": page, "pageSize": 20, "sortDir": "desc"},
            headers=HEADERS,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        for meta in data["metadata"]:
            for f in meta["files"]:
                if f.get("file_extension") == "csv":
                    item = dict(f)
                    item["folder"] = meta["file_folder"]
                    files.append(item)
        pag = data.get("pagination") or {}
        if max_files is not None and len(files) >= max_files:
            return files[:max_files]
        if page >= (pag.get("page_count") or 1) or not data["metadata"]:
            break
        page += 1
    return files


def _download_to(url: str, dest: Path, *, retries: int = 3) -> int:
    """流式下载；CDN 虽命名 .gz 但多数实际是明文 CSV，按魔数透明解压。"""
    for attempt in range(retries):
        try:
            with requests.get(url, headers=HEADERS, timeout=900, stream=True) as resp:
                resp.raise_for_status()
                chunks = resp.iter_content(1 << 20)
                first = next(chunks, b"")
                payload = first + b"".join(chunks)
                if payload.startswith(b"\x1f\x8b"):
                    payload = gzip.decompress(payload)
                dest.write_bytes(payload)
                return len(payload)
        except (requests.RequestException, OSError) as exc:
            if attempt == retries - 1:
                raise
            if dest.exists():
                dest.unlink()
    return 0


def _download_dataset(dataset_id: int, max_files: int | None, force: bool) -> list[Path]:
    """下载某数据集前 max_files 个分片到 raw/rta/<name>/，返回本地路径列表。"""
    name = DATASETS[dataset_id]
    dest_dir = RAW_DIR / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    entries = _list_csv_files(dataset_id, max_files=max_files)
    paths: list[Path] = []
    for f in entries:
        out = dest_dir / f"{f['folder']}.csv"
        if out.is_file() and not force:
            paths.append(out)
            continue
        _download_to(f["file_url"], out)
        paths.append(out)
    return paths


# ---------------------------------------------------------------------------
# 解析 / 聚合（raw → 指标长表）
# ---------------------------------------------------------------------------


def _month_date(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _to_date(v: object) -> date | None:
    if v is None or v == "":
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def _month_from_label(month_text: str, year_text: str) -> date | None:
    mt = str(month_text).strip()
    try:
        y = int(str(year_text).strip()[:4])
    except (TypeError, ValueError):
        return None
    if mt.isdigit():
        m = int(mt)
    else:
        m = _MONTH_ABBR.get(mt[:3].lower())
    if not m or not 1 <= m <= 12:
        return None
    return _month_date(y, m)


def _iter_rows(path: Path):
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        yield from reader


def _aggregate_bus_route_monthly(paths: list[Path]) -> dict[date, int]:
    agg: dict[date, int] = {}
    for path in paths:
        for row in _iter_rows(path):
            if len(row) < 5:
                continue
            month, route, trips, year, *_ = row
            period = _month_from_label(month, year)
            if period is None or not route:
                continue
            trips_n = _to_bigint(trips)
            if trips_n is None:
                continue
            agg[period] = agg.get(period, 0) + trips_n
    return agg


def _to_bigint(v: object) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(str(v).strip().replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_float(v: object) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _aggregate_marine_station_monthly(paths: list[Path]) -> dict[date, float]:
    agg: dict[date, float] = {}
    for path in paths:
        for row in _iter_rows(path):
            if len(row) < 6:
                continue
            mode, station, month, passengers, year, *_ = row
            period = _month_from_label(month, year)
            if period is None or not station:
                continue
            p = _to_float(passengers)
            if p is None:
                continue
            agg[period] = agg.get(period, 0.0) + p
    return agg


def _aggregate_taxi_monthly(
    paths: list[Path],
) -> tuple[dict[date, int], dict[date, int]]:
    agg: dict[tuple[date, str], list] = {}
    for path in paths:
        for row in _iter_rows(path):
            if len(row) < 5:
                continue
            carrier, fleet_size, report_date, trips, *_ = row
            period = _to_date(report_date)
            if period is None or not carrier:
                continue
            trips_n = _to_bigint(trips)
            if trips_n is None:
                continue
            key = (period, carrier.strip())
            prev = agg.get(key)
            fleet = _to_bigint(fleet_size) or 0
            if prev is None:
                agg[key] = [trips_n, fleet]
            else:
                agg[key] = [prev[0] + trips_n, max(prev[1], fleet)]
    trips_by_period: dict[date, int] = {}
    fleet_by_period: dict[date, int] = {}
    for (period, _carrier), (trips, fleet) in agg.items():
        trips_by_period[period] = trips_by_period.get(period, 0) + trips
        fleet_by_period[period] = fleet_by_period.get(period, 0) + fleet
    return trips_by_period, fleet_by_period


def _aggregate_bus_speed(con, paths: list[Path]) -> dict[date, float]:
    totals: dict[date, tuple[float, int]] = {}
    for path in paths:
        rows = con.execute(
            "SELECT try_cast(date AS DATE) AS day, "
            "SUM(try_cast(average_speed AS DOUBLE)) AS total_speed, "
            "COUNT(try_cast(average_speed AS DOUBLE)) AS speed_count "
            "FROM read_csv(?, header=true, columns=?, ignore_errors=true) "
            "WHERE try_cast(date AS DATE) IS NOT NULL "
            "GROUP BY day",
            [str(path), {"average_speed": "VARCHAR", "date": "VARCHAR",
                         "route_direction": "VARCHAR", "route_name": "VARCHAR",
                         "service_type": "VARCHAR", "time_period": "VARCHAR",
                         "load_timestamp": "VARCHAR"}],
        ).fetchall()
        for day, total_speed, speed_count in rows:
            previous_speed, previous_count = totals.get(day, (0.0, 0))
            totals[day] = (
                previous_speed + float(total_speed or 0),
                previous_count + int(speed_count or 0),
            )
    return {
        day: total_speed / speed_count
        for day, (total_speed, speed_count) in totals.items()
        if speed_count
    }


def _aggregate_marine_daily(con, paths: list[Path]) -> dict[date, int]:
    totals: dict[date, int] = {}
    for path in paths:
        rows = con.execute(
            "SELECT try_cast(txn_date AS DATE) AS day, COUNT(*) AS records "
            "FROM read_csv(?, header=true, columns=?, ignore_errors=true) "
            "WHERE try_cast(txn_date AS DATE) IS NOT NULL "
            "GROUP BY day",
            [str(path), {"line_name": "VARCHAR", "location": "VARCHAR",
                         "txn_date": "VARCHAR", "txn_time": "VARCHAR",
                         "txn_type": "VARCHAR", "zone": "VARCHAR",
                         "load_timestamp": "VARCHAR"}],
        ).fetchall()
        for day, records in rows:
            totals[day] = totals.get(day, 0) + int(records or 0)
    return totals


# ---------------------------------------------------------------------------
# 聚合指标
# ---------------------------------------------------------------------------


def _rebuild_aggregates(
    con,
    monthly: dict[str, dict[date, int | float]],
    daily: dict[str, dict[date, int | float]],
) -> None:
    """把 raw CSV 聚合结果写入两张指标长表。"""
    con.execute("DELETE FROM rta_transport_monthly")
    con.execute("DELETE FROM rta_transport_daily")
    monthly_rows = [
        (period, indicator, value)
        for indicator, values in monthly.items()
        for period, value in values.items()
    ]
    daily_rows = [
        (period, indicator, value)
        for indicator, values in daily.items()
        for period, value in values.items()
    ]
    con.executemany(
        "INSERT INTO rta_transport_monthly (period, indicator, value) VALUES (?, ?, ?)",
        monthly_rows,
    )
    con.executemany(
        "INSERT INTO rta_transport_daily (period, indicator, value) VALUES (?, ?, ?)",
        daily_rows,
    )


def _dictionary_rows() -> list[dict]:
    rows = []
    today = date.today()
    for name, freq, unit, kind in MONTHLY_INDICATORS + DAILY_INDICATORS:
        rows.append({
            "indicator_name": name,
            "frequency": freq,
            "unit": unit,
            "source": SOURCE_NAME,
            "type": kind,
            "industry": INDUSTRY,
            "updated_at": today,
        })
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
# 统一入口 update()
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载 raw CSV -> 聚合指标，全量替换两张 rta_transport_* 表。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    def has_raw(name: str) -> bool:
        target = RAW_DIR / name
        return target.is_dir() and bool(list(target.glob("*.csv")))

    plans = {
        459793: None,
        466217: None,
        469849: None,
        459282: None,
        466229: None,
    }
    missing = [
        DATASETS[dataset_id]
        for dataset_id in plans
        if not has_raw(DATASETS[dataset_id])
    ]
    if skip_download and missing:
        raise FileNotFoundError("skip-download 但以下 RTA 原始件缺失: " + ", ".join(missing))

    # 下载：月度小文件、speed、marine 全量；bus 交易原始件不参与任何指标，保留既有 raw 文件但不再下载。
    got: dict[int, list[Path]] = {}
    for dataset_id, max_files in plans.items():
        got[dataset_id] = _download_dataset(dataset_id, max_files, force)

    with _transaction(con):
        for table in _LEGACY_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        for table in _TABLE_DDL:
            db.ensure(con, table, _TABLE_DDL[table])
            con.execute(f"DELETE FROM {table}")
        bus_monthly = _aggregate_bus_route_monthly(got[459793])
        marine_monthly = _aggregate_marine_station_monthly(got[466217])
        taxi_trips, taxi_fleet = _aggregate_taxi_monthly(got[469849])
        bus_speed_daily = _aggregate_bus_speed(con, got[459282])
        marine_daily = _aggregate_marine_daily(con, got[466229])
        _rebuild_aggregates(
            con,
            monthly={
                MONTHLY_INDICATORS[0][0]: bus_monthly,
                MONTHLY_INDICATORS[1][0]: marine_monthly,
                MONTHLY_INDICATORS[2][0]: taxi_trips,
                MONTHLY_INDICATORS[3][0]: taxi_fleet,
            },
            daily={
                DAILY_INDICATORS[0][0]: marine_daily,
                DAILY_INDICATORS[1][0]: bus_speed_daily,
            },
        )
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"月度聚合 {sum(len(values) for values in (bus_monthly, marine_monthly, taxi_trips, taxi_fleet))} 行；"
        f"日度聚合 {len(bus_speed_daily) + len(marine_daily)} 行；"
        "raw 明细仅保存在 data/UAE/raw/rta/，不写入 DuckDB"
    )
    return {
        "status": "ok",
        "rows": sum(
            len(values)
            for values in (
                bus_monthly,
                marine_monthly,
                taxi_trips,
                taxi_fleet,
                bus_speed_daily,
                marine_daily,
            )
        ),
        "note": note,
    }


# ---------------------------------------------------------------------------
# 合并回 Excel
# ---------------------------------------------------------------------------


def merge(workbook_path: Path) -> dict:
    """把 rta_transport_monthly / rta_transport_daily 写回工作簿两张 sheet。"""
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_rta_transport_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    from _excel_helpers import payload_json_file, records_latest_first, run_powershell_sheet_writer

    con = db.connect(read_only=True)
    try:
        monthly = con.execute(
            "SELECT period, indicator, value FROM rta_transport_monthly ORDER BY period"
        ).fetchall()
        daily = con.execute(
            "SELECT period, indicator, value FROM rta_transport_daily ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    def wide(rows, indicators, fmt):
        order = {name: i for i, (name, *_rest) in enumerate(indicators)}
        by_period: dict[str, list] = {}
        for period, indicator, value in rows:
            key = period.strftime(fmt)
            item = by_period.setdefault(key, [None] * len(indicators))
            if indicator in order:
                item[order[indicator]] = value
        class _Obs:
            def __init__(self, period, values):
                self.period = period
                self.values = tuple(values)
        return [_Obs(p, v) for p, v in sorted(by_period.items())]

    def payload(sheet, indicators, observations, frequency):
        return {
            "dictionary_sheet_name": DICTIONARY_SHEET,
            "source_label": SOURCE_NAME,
            "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
            "frequency": frequency,
            "unit": "见各列",
            "source": SOURCE_NAME,
            "updated_at": date.today().isoformat(),
            "indicators": [
                {"name": name, "unit": unit, "type": kind, "industry": INDUSTRY}
                for name, _f, unit, kind in indicators
            ],
            "records": records_latest_first(observations),
        }

    monthly_obs = wide(monthly, MONTHLY_INDICATORS, "%Y-%m")
    daily_obs = wide(daily, DAILY_INDICATORS, "%Y-%m-%d")
    for sheet_name, indicators, observations, freq, prefix in (
        (MONTHLY_SHEET, MONTHLY_INDICATORS, monthly_obs, "月", ".rta-monthly-"),
        (DAILY_SHEET, DAILY_INDICATORS, daily_obs, "日", ".rta-daily-"),
    ):
        if not observations:
            continue
        pld = payload(sheet_name, indicators, observations, freq)
        with payload_json_file(pld, prefix=prefix, directory=DATA_DIR) as payload_path:
            run_powershell_sheet_writer(helper_path, workbook_path, payload_path, sheet_name)
    return {
        "status": "ok",
        "note": f"{len(monthly_obs)} 个月 / {len(daily_obs)} 天写入工作簿",
    }


if __name__ == "__main__":
    print("source_rta.py 自检：")
    print("  update(con, ...) 从 Data Dubai raw CSV 聚合 5 个 RTA 数据集 →")
    print("    仅写入 rta_transport_monthly/daily 指标长表")
    print("  merge(workbook_path) 写回 月度_RTA交通 / 日度_RTA交通")
