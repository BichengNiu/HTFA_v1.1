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
| 466229 | marine_ridership | 日（交易级） | 水运刷卡交易（detail，7 片 ≈ 全历史） |
| 459803 | bus_ridership | 日（交易级） | 公交刷卡交易（detail，2060 片 ≈ 5.6 年 ≈ 278GB） |

⚠️ **bus_ridership 全量物理不可行**（2060 片共约 278GB，且分片为跨 2017–2026 的
随机混排 shard，无法按日切近期窗口）；本源默认只下载前若干片
（`BUS_RAW_PARTITIONS=10`，约 1.4GB）作为代表性抽样载入 duckdb，并在 note 中
如实标注「抽样非全量」。公交完整月度序列由 by-route 月度数据集提供。

入库表：
- 明细 rta_bus_trips_route_monthly / rta_marine_trips_station_monthly /
  rta_taxi_trips_monthly / rta_bus_speed_daily_detail /
  rta_marine_ridership_raw / rta_bus_ridership_raw
- 指标长表 rta_transport_monthly / rta_transport_daily（(period, indicator) 聚合）。

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
BUS_RAW_PARTITIONS = 20  # bus 原始抽样片数（全量 2060 片约 278GB，物理不可行；抽样供代表性分析）

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
    "rta_bus_trips_route_monthly": (
        "CREATE TABLE IF NOT EXISTS rta_bus_trips_route_monthly (\n"
        "  period DATE NOT NULL, route_name VARCHAR NOT NULL, trips BIGINT,\n"
        "  PRIMARY KEY (period, route_name))"
    ),
    "rta_marine_trips_station_monthly": (
        "CREATE TABLE IF NOT EXISTS rta_marine_trips_station_monthly (\n"
        "  period DATE NOT NULL, station VARCHAR NOT NULL,\n"
        "  passengers DECIMAL(18, 3), marine_mode VARCHAR,\n"
        "  PRIMARY KEY (period, station))"
    ),
    "rta_taxi_trips_monthly": (
        "CREATE TABLE IF NOT EXISTS rta_taxi_trips_monthly (\n"
        "  period DATE NOT NULL, carrier VARCHAR NOT NULL,\n"
        "  fleet_size BIGINT, trips BIGINT,\n"
        "  PRIMARY KEY (period, carrier))"
    ),
    "rta_bus_speed_daily_detail": (
        "CREATE TABLE IF NOT EXISTS rta_bus_speed_daily_detail (\n"
        "  txn_date DATE NOT NULL, time_period VARCHAR, service_type VARCHAR,\n"
        "  route_name VARCHAR, route_direction VARCHAR, average_speed DOUBLE)"
    ),
    "rta_marine_ridership_raw": (
        "CREATE TABLE IF NOT EXISTS rta_marine_ridership_raw (\n"
        "  txn_date DATE, txn_time VARCHAR, line_name VARCHAR, location VARCHAR,\n"
        "  txn_type VARCHAR, zone VARCHAR, txn_ts VARCHAR)"
    ),
    "rta_bus_ridership_raw": (
        "CREATE TABLE IF NOT EXISTS rta_bus_ridership_raw (\n"
        "  txn_date DATE, txn_time VARCHAR, route_name VARCHAR, start_location VARCHAR,\n"
        "  start_zone VARCHAR, end_location VARCHAR, end_zone VARCHAR,\n"
        "  txn_type VARCHAR, txn_ts VARCHAR)"
    ),
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
# 解析 / 入库（明细）
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


def _load_bus_route_monthly(con, paths: list[Path]) -> int:
    agg: dict[tuple[date, str], int] = {}
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
            key = (period, route.strip())
            agg[key] = agg.get(key, 0) + trips_n
    rows = [(p, r, n) for (p, r), n in agg.items()]
    con.executemany(
        "INSERT INTO rta_bus_trips_route_monthly (period, route_name, trips) VALUES (?, ?, ?)",
        rows,
    )
    return len(rows)


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


def _load_marine_station_monthly(con, paths: list[Path]) -> int:
    agg: dict[tuple[date, str], float] = {}
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
            key = (period, station.strip())
            agg[key] = agg.get(key, 0.0) + p
    rows = [(p, s, v, "") for (p, s), v in agg.items()]
    con.executemany(
        "INSERT INTO rta_marine_trips_station_monthly "
        "(period, station, passengers, marine_mode) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def _load_taxi_monthly(con, paths: list[Path]) -> int:
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
    rows = [(p, c, fleet, trips) for (p, c), (trips, fleet) in agg.items()]
    con.executemany(
        "INSERT INTO rta_taxi_trips_monthly (period, carrier, fleet_size, trips) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def _load_bus_speed(con, paths: list[Path]) -> int:
    total = 0
    for path in paths:
        before = con.execute("SELECT count(*) FROM rta_bus_speed_daily_detail").fetchone()[0]
        con.execute(
            "INSERT INTO rta_bus_speed_daily_detail (txn_date, time_period, service_type, "
            "route_name, route_direction, average_speed) "
            "SELECT try_cast(date AS DATE), time_period, service_type, route_name, "
            "route_direction, try_cast(average_speed AS DOUBLE) "
            "FROM read_csv(?, header=true, columns=?, ignore_errors=true) "
            "WHERE try_cast(date AS DATE) IS NOT NULL",
            [str(path), {"average_speed": "VARCHAR", "date": "VARCHAR",
                         "route_direction": "VARCHAR", "route_name": "VARCHAR",
                         "service_type": "VARCHAR", "time_period": "VARCHAR",
                         "load_timestamp": "VARCHAR"}],
        )
        after = con.execute("SELECT count(*) FROM rta_bus_speed_daily_detail").fetchone()[0]
        total += after - before
    return total


def _load_marine_raw(con, paths: list[Path]) -> int:
    total = 0
    for path in paths:
        before = con.execute("SELECT count(*) FROM rta_marine_ridership_raw").fetchone()[0]
        con.execute(
            "INSERT INTO rta_marine_ridership_raw (txn_date, txn_time, line_name, "
            "location, txn_type, zone, txn_ts) "
            "SELECT try_cast(txn_date AS DATE), txn_time, line_name, location, "
            "txn_type, zone, load_timestamp "
            "FROM read_csv(?, header=true, columns=?, ignore_errors=true) "
            "WHERE try_cast(txn_date AS DATE) IS NOT NULL",
            [str(path), {"line_name": "VARCHAR", "location": "VARCHAR",
                         "txn_date": "VARCHAR", "txn_time": "VARCHAR",
                         "txn_type": "VARCHAR", "zone": "VARCHAR",
                         "load_timestamp": "VARCHAR"}],
        )
        after = con.execute("SELECT count(*) FROM rta_marine_ridership_raw").fetchone()[0]
        total += after - before
    return total


def _load_bus_raw(con, paths: list[Path]) -> int:
    # 官方表头含拼写偏差：end_loaction、txn_subtype
    total = 0
    for path in paths:
        before = con.execute("SELECT count(*) FROM rta_bus_ridership_raw").fetchone()[0]
        con.execute(
            "INSERT INTO rta_bus_ridership_raw (txn_date, txn_time, route_name, "
            "start_location, start_zone, end_location, end_zone, txn_type, txn_ts) "
            "SELECT try_cast(txn_date AS DATE), txn_time, route_name, start_location, "
            "start_zone, end_loaction, end_zone, txn_subtype, load_timestamp "
            "FROM read_csv(?, header=true, columns=?, ignore_errors=true) "
            "WHERE try_cast(txn_date AS DATE) IS NOT NULL",
            [str(path), {"end_loaction": "VARCHAR", "end_zone": "VARCHAR",
                         "route_name": "VARCHAR", "start_location": "VARCHAR",
                         "start_zone": "VARCHAR", "txn_date": "VARCHAR",
                         "txn_subtype": "VARCHAR", "txn_time": "VARCHAR",
                         "load_timestamp": "VARCHAR"}],
        )
        after = con.execute("SELECT count(*) FROM rta_bus_ridership_raw").fetchone()[0]
        total += after - before
    return total


# ---------------------------------------------------------------------------
# 聚合指标
# ---------------------------------------------------------------------------


def _rebuild_aggregates(con) -> None:
    """从明细重建 rta_transport_monthly / rta_transport_daily 指标长表。"""
    con.execute("DELETE FROM rta_transport_monthly")
    con.execute("DELETE FROM rta_transport_daily")

    # 月度指标
    con.execute(
        "INSERT INTO rta_transport_monthly (period, indicator, value) "
        "SELECT period, '迪拜:公交客运人次(月)', SUM(trips) FROM rta_bus_trips_route_monthly "
        "GROUP BY period"
    )
    con.execute(
        "INSERT INTO rta_transport_monthly (period, indicator, value) "
        "SELECT period, '迪拜:水运客运人次(月)', SUM(passengers) FROM rta_marine_trips_station_monthly "
        "GROUP BY period"
    )
    con.execute(
        "INSERT INTO rta_transport_monthly (period, indicator, value) "
        "SELECT period, '迪拜:出租车趟次(月)', SUM(trips) FROM rta_taxi_trips_monthly "
        "GROUP BY period"
    )
    con.execute(
        "INSERT INTO rta_transport_monthly (period, indicator, value) "
        "SELECT period, '迪拜:出租车车队数(辆,月)', SUM(fleet_size) FROM rta_taxi_trips_monthly "
        "GROUP BY period"
    )

    # 日度指标
    con.execute(
        "INSERT INTO rta_transport_daily (period, indicator, value) "
        "SELECT txn_date, '迪拜:水运客运人次(日)', COUNT(*) FROM rta_marine_ridership_raw "
        "GROUP BY txn_date"
    )
    con.execute(
        "INSERT INTO rta_transport_daily (period, indicator, value) "
        "SELECT txn_date, '迪拜:公交平均速度(km/h,日)', AVG(average_speed) FROM rta_bus_speed_daily_detail "
        "GROUP BY txn_date"
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
    """下载 -> 解析明细 -> 聚合指标，全量替换 rta_* 系列表。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    def need(name: str) -> bool:
        target = RAW_DIR / name
        if not target.is_dir():
            return True
        return bool(list(target.glob("*.csv")))

    missing = [n for n in DATASETS.values() if not need(n)]
    if skip_download and missing:
        raise FileNotFoundError("skip-download 但以下 RTA 原始件缺失: " + ", ".join(missing))

    # 下载：月度小文件全量；speed 4 片全量；marine 7 片全量；bus 抽样 BUS_RAW_PARTITIONS 片
    got: dict[int, list[Path]] = {}
    plans = {
        459793: None,
        466217: None,
        469849: None,
        459282: None,
        466229: None,
        459803: BUS_RAW_PARTITIONS,
    }
    for dataset_id, max_files in plans.items():
        got[dataset_id] = _download_dataset(dataset_id, max_files, force)

    with _transaction(con):
        for table in _TABLE_DDL:
            db.ensure(con, table, _TABLE_DDL[table])
            con.execute(f"DELETE FROM {table}")
        n_bus_route = _load_bus_route_monthly(con, got[459793])
        n_marine_station = _load_marine_station_monthly(con, got[466217])
        n_taxi = _load_taxi_monthly(con, got[469849])
        n_speed = _load_bus_speed(con, got[459282])
        n_marine_raw = _load_marine_raw(con, got[466229])
        n_bus_raw = _load_bus_raw(con, got[459803])
        _rebuild_aggregates(con)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"公交线路月 {n_bus_route} 行；水运站点月 {n_marine_station} 行；"
        f"出租车站 {n_taxi} 行；均速 {n_speed} 行；"
        f"水运交易 {n_marine_raw} 行；公交交易抽样 {n_bus_raw} 行"
        f"（bus_ridership 全量 2060 片约 278GB，仅取前 {BUS_RAW_PARTITIONS} 片抽样）"
    )
    return {"status": "ok", "rows": n_bus_route + n_marine_station + n_taxi + n_speed + n_marine_raw + n_bus_raw, "note": note}


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
    print("  update(con, ...) 从 Data Dubai 下载 6 个 RTA 数据集（bus 原始仅抽样）→")
    print("    明细表 + rta_transport_monthly/daily 指标长表")
    print("  merge(workbook_path) 写回 月度_RTA交通 / 日度_RTA交通")
