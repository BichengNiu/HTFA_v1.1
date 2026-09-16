"""UN Comtrade 阿联酋设备进口：下载 → 聚合 → 入库与写表。

逻辑移植自 ``data/capitalImports/``（download_comtrade.py 下载 +
process_and_merge.py 聚合/质检 + merge_with_excel.ps1 写表）。原始 JSON 缓存
写入 ``data/UAE/raw/comtrade/``；API 密钥读 ``data/UAE/.env``。入库表三张：
comtrade_monthly（五类金额/台数）、detail.comtrade_partner_detail（镜像申报国明细）、
detail.comtrade_quantity_detail（HS6 数量明细）。工作簿 sheet 为 ``月度_UNComtrade``。
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import run_powershell_command  # noqa: E402
from .source_comtrade_scope import (  # noqa: E402
    CODE_DESCRIPTIONS,
    EXCLUDED_RELATED_CODES,
    SERIES,
    UAE_CODE,
    all_equipment_codes,
    series_for_code,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "comtrade"
REFERENCE_DIR = RAW_DIR / "reference"
# merge_with_excel.ps1 reads this generated CSV from the package-local
# processed/ directory.  Keep the derived intermediary beside the helper;
# source data still enters DuckDB before it is reconstructed here.
PROCESSED_DIR = SCRIPTS_DIR / "processed"
REPORTERS_PATH = REFERENCE_DIR / "reporters.json"
QUALITY_PATH = RAW_DIR / "quality_report.json"
MERGE_SCRIPT = SCRIPTS_DIR / "merge_with_excel.ps1"

API_ROOT = "https://comtradeapi.un.org/data/v1/get"
REPORTERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
START_YEAR = 2017
ITEM_UNIT_CODE = 5
MIN_API_INTERVAL = 6.0


# ---------------------------------------------------------------------------
# 下载器（平移自 download_comtrade.py）
# ---------------------------------------------------------------------------


def replace_with_retry(source: Path, destination: Path) -> None:
    """Atomically replace a file, tolerating short cloud-sync locks."""

    for attempt in range(12):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(min(10.0, 0.5 * (attempt + 1)))


def load_api_key() -> str:
    """Load the API key without writing it to logs or output files."""

    key = os.environ.get("COMTRADE_API_KEY", "").strip()
    env_path = DATA_DIR / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("COMTRADE_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    if not key:
        raise RuntimeError(
            "COMTRADE_API_KEY is missing. Add it to data/UAE/.env."
        )
    return key


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HTFA-UAE-equipment-pipeline/1.0"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    temporary.write_bytes(payload)
    replace_with_retry(temporary, destination)


class ComtradeClient:
    def __init__(self, api_key: str, min_interval: float) -> None:
        self.api_key = api_key
        self.min_interval = min_interval
        self.last_request_at = 0.0

    def get(
        self,
        frequency: str,
        params: dict[str, str | int],
        destination: Path,
        force: bool = False,
    ) -> dict[str, Any]:
        if destination.exists() and not force:
            return json.loads(destination.read_text(encoding="utf-8"))

        query = dict(params)
        query["subscription-key"] = self.api_key
        query.setdefault("maxRecords", 100000)
        query.setdefault("includeDesc", "false")
        query.setdefault("breakdownMode", "classic")
        encoded = urllib.parse.urlencode(query, safe=",")
        url = f"{API_ROOT}/C/{frequency}/HS?{encoded}"
        temporary = destination.with_suffix(".json.part")

        for attempt in range(7):
            delay = self.min_interval - (
                time.monotonic() - self.last_request_at
            )
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "HTFA-UAE-equipment-pipeline/1.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    payload = json.load(response)
                self.last_request_at = time.monotonic()
                rows = payload.get("data", [])
                if len(rows) >= int(query["maxRecords"]):
                    raise RuntimeError(
                        f"API result may be truncated at {len(rows):,} records"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                replace_with_retry(temporary, destination)
                return payload
            except urllib.error.HTTPError as error:
                self.last_request_at = time.monotonic()
                if error.code not in {429, 500, 502, 503, 504} or attempt == 6:
                    message = error.read(1000).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"UN Comtrade HTTP {error.code}: {message}"
                    ) from error
                time.sleep(min(90.0, 8.0 * (2**attempt)))
            except (TimeoutError, urllib.error.URLError) as error:
                self.last_request_at = time.monotonic()
                if attempt == 6:
                    raise RuntimeError(
                        "UN Comtrade request failed"
                    ) from error
                time.sleep(min(90.0, 8.0 * (2**attempt)))
        raise AssertionError("unreachable")


def months_for_year(year: int) -> list[str]:
    if year < date.today().year:
        last_month = 12
    elif year == date.today().year:
        last_month = date.today().month
    else:
        return []
    return [f"{year}{month:02d}" for month in range(1, last_month + 1)]


def download_monthly(client: ComtradeClient, force: bool) -> None:
    codes = ",".join(all_equipment_codes())
    current_year = date.today().year
    for year in range(START_YEAR, current_year + 1):
        periods = ",".join(months_for_year(year))
        queries = {
            "equipment_uae_reported": {
                "period": periods,
                "reporterCode": UAE_CODE,
                "partnerCode": 0,
                "flowCode": "M",
                "cmdCode": codes,
            },
            "equipment_all_mirror": {
                "period": periods,
                "partnerCode": UAE_CODE,
                "flowCode": "X",
                "cmdCode": codes,
            },
        }
        for source, parameters in queries.items():
            path = RAW_DIR / source / f"{source}_{year}.json"
            # Comtrade revises the current calendar year behind the same
            # endpoint/file name. Historical years remain cache candidates.
            payload = client.get(
                "M", parameters, path, force or year == current_year
            )


def write_scope_file() -> None:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / "commodity_scope.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["series", "code", "description", "basis"])
        for key, definition in SERIES.items():
            for code in sorted(definition["codes"]):
                writer.writerow(
                    [key, code, CODE_DESCRIPTIONS[code], definition["basis"]]
                )
    excluded_path = REFERENCE_DIR / "commodity_scope_exclusions.csv"
    with excluded_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["code_or_range", "exclusion_reason"])
        writer.writerows(EXCLUDED_RELATED_CODES.items())


# ---------------------------------------------------------------------------
# 聚合（平移自 process_and_merge.py aggregate()）
# ---------------------------------------------------------------------------


def load_reporters() -> dict[int, dict[str, Any]]:
    payload = json.loads(REPORTERS_PATH.read_text(encoding="utf-8"))
    records = payload.get("results", payload)
    return {int(record["reporterCode"]): record for record in records}


def iter_raw_rows(source: str):
    for path in sorted((RAW_DIR / source).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("data", []):
            yield row


def month_grid(latest_period: str) -> list[str]:
    """Return months newest-first from the latest observation to 2017-01."""

    result = []
    for year in range(START_YEAR, int(latest_period[:4]) + 1):
        for month in range(1, 13):
            period = f"{year}{month:02d}"
            if period <= latest_period:
                result.append(period)
    return list(reversed(result))


def item_quantity(row: dict[str, Any]) -> tuple[float, bool, str] | None:
    """Return one item count without double counting qty and altQty."""

    candidates = [
        ("altQty", "altQtyUnitCode", "isAltQtyEstimated", False),
        ("qty", "qtyUnitCode", "isQtyEstimated", False),
        ("altQty", "altQtyUnitCode", "isAltQtyEstimated", True),
        ("qty", "qtyUnitCode", "isQtyEstimated", True),
    ]
    for value_field, unit_field, estimate_field, estimated in candidates:
        if row.get(unit_field) != ITEM_UNIT_CODE:
            continue
        value = row.get(value_field)
        if value is None or float(value) <= 0:
            continue
        row_estimated = bool(row.get(estimate_field))
        if row_estimated != estimated:
            continue
        return float(value), row_estimated, value_field
    return None


def aggregate() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[tuple[str, str], str],
    list[dict[str, Any]],
]:
    """Aggregate with UAE imports first and full-country mirror fallback."""

    reporters = load_reporters()
    direct_values: dict[tuple[str, str], float] = defaultdict(float)
    mirror_values: dict[tuple[str, str], float] = defaultdict(float)
    mirror_detail: dict[tuple[str, str, int], float] = defaultdict(float)
    direct_observed: set[tuple[str, str]] = set()
    mirror_observed: set[tuple[str, str]] = set()
    direct_units: dict[tuple[str, str, str], float] = defaultdict(float)
    direct_estimated_units: dict[tuple[str, str, str], float] = defaultdict(
        float
    )
    mirror_units: dict[tuple[str, str, str], float] = defaultdict(float)
    mirror_estimated_units: dict[tuple[str, str, str], float] = defaultdict(
        float
    )
    mirror_unit_reporters: dict[tuple[str, str, str], set[int]] = defaultdict(
        set
    )

    for row in iter_raw_rows("equipment_uae_reported"):
        period = str(row.get("period", ""))
        categories = series_for_code(str(row.get("cmdCode", "")))
        if len(period) != 6 or not categories:
            continue
        code = str(row.get("cmdCode", "")).zfill(6)
        quantity = item_quantity(row)
        for category in categories:
            if row.get("primaryValue") is not None:
                direct_observed.add((period, category))
                direct_values[(period, category)] += float(
                    row["primaryValue"]
                )
            if quantity is not None:
                value, estimated, _field = quantity
                unit_key = (period, category, code)
                direct_units[unit_key] += value
                if estimated:
                    direct_estimated_units[unit_key] += value

    unknown_reporters: set[int] = set()
    for row in iter_raw_rows("equipment_all_mirror"):
        period = str(row.get("period", ""))
        categories = series_for_code(str(row.get("cmdCode", "")))
        if len(period) != 6 or not categories:
            continue
        reporter = int(row.get("reporterCode") or 0)
        metadata = reporters.get(reporter)
        if metadata is None:
            unknown_reporters.add(reporter)
            continue
        if bool(metadata.get("isGroup")) or reporter == UAE_CODE:
            continue
        code = str(row.get("cmdCode", "")).zfill(6)
        quantity = item_quantity(row)
        for category in categories:
            if row.get("primaryValue") is not None:
                value = float(row["primaryValue"])
                mirror_observed.add((period, category))
                mirror_values[(period, category)] += value
                mirror_detail[(period, category, reporter)] += value
            if quantity is not None:
                value, estimated, _field = quantity
                unit_key = (period, category, code)
                mirror_units[unit_key] += value
                mirror_unit_reporters[unit_key].add(reporter)
                if estimated:
                    mirror_estimated_units[unit_key] += value

    if unknown_reporters:
        raise RuntimeError(
            "Unknown Comtrade reporter codes: "
            + ", ".join(map(str, sorted(unknown_reporters)))
        )

    available_months = (
        {period for period, _category in direct_observed}
        | {period for period, _category in mirror_observed}
        | {period for period, _category, _code in direct_units}
        | {period for period, _category, _code in mirror_units}
    )
    if not available_months:
        raise RuntimeError("No monthly equipment observations found")

    latest_period = max(available_months)
    sources: dict[tuple[str, str], str] = {}
    quantity_detail: list[dict[str, Any]] = []
    output: list[dict[str, Any]] = []
    for period in month_grid(latest_period):
        year = int(period[:4])
        month = int(period[4:])
        result: dict[str, Any] = {
            "month": period,
            "date": date(year, month, monthrange(year, month)[1]),
        }
        for category in SERIES:
            key = (period, category)
            if key in direct_observed:
                value: float | None = direct_values[key]
                sources[key] = "uae_reported"
            elif key in mirror_observed:
                value = mirror_values[key]
                sources[key] = "all_partner_mirror"
            else:
                value = None
                sources[key] = "missing"
            result[f"{category}_usd"] = (
                round(value, 3) if value is not None else None
            )
            result[f"{category}_usd_mn"] = (
                round(value / 1_000_000, 6) if value is not None else None
            )
            units = 0.0
            unit_codes = 0
            for code in sorted(SERIES[category]["codes"]):
                unit_key = (period, category, code)
                if unit_key in direct_units:
                    unit_value = direct_units[unit_key]
                    estimated_units = direct_estimated_units[unit_key]
                    unit_source = "uae_reported"
                    reporter_count = 1
                elif unit_key in mirror_units:
                    unit_value = mirror_units[unit_key]
                    estimated_units = mirror_estimated_units[unit_key]
                    unit_source = "all_partner_mirror"
                    reporter_count = len(mirror_unit_reporters[unit_key])
                else:
                    continue
                units += unit_value
                unit_codes += 1
                quantity_detail.append(
                    {
                        "month": period,
                        "series": category,
                        "hs6": code,
                        "source": unit_source,
                        "units": round(unit_value, 3),
                        "reported_units": round(unit_value - estimated_units, 3),
                        "estimated_units": round(estimated_units, 3),
                        "reporter_count": reporter_count,
                    }
                )
            result[f"{category}_units"] = (
                round(units, 3) if unit_codes else None
            )
        output.append(result)

    detail = []
    for (period, category, reporter), value in sorted(
        mirror_detail.items(),
        key=lambda item: item[0],
        reverse=True,
    ):
        if (period, category) in direct_observed:
            continue
        detail.append(
            {
                "month": period,
                "series": category,
                "reporter_code": reporter,
                "reporter_name": reporters[reporter].get("reporterDesc", ""),
                "trade_value_usd": round(value, 3),
            }
        )
    return output, detail, sources, quantity_detail


# ---------------------------------------------------------------------------
# 入库
# ---------------------------------------------------------------------------


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


def _period_end(period: str) -> date:
    year = int(period[:4])
    month = int(period[4:])
    return date(year, month, monthrange(year, month)[1])


def _to_db_rows(
    rows: list[dict[str, Any]],
    detail: list[dict[str, Any]],
    quantity_detail: list[dict[str, Any]],
) -> tuple[list[dict], list[dict], list[dict]]:
    monthly_rows: list[dict] = []
    for row in rows:
        period = _period_end(row["month"])
        for category in SERIES:
            value = row.get(f"{category}_usd")
            units = row.get(f"{category}_units")
            if value is None and units is None:
                continue
            monthly_rows.append(
                {
                    "period": period,
                    "category": category,
                    "value": value,
                    "units": units,
                }
            )

    detail_rows = [
        {
            "period": _period_end(item["month"]),
            "category": item["series"],
            "reporter": item["reporter_name"],
            "partner": "UAE",
            "value": item["trade_value_usd"],
        }
        for item in detail
    ]
    quantity_rows = [
        {
            "period": _period_end(item["month"]),
            "hs6": item["hs6"],
            "item_count": item["units"],
            "source_type": item["source"],
            "reported_estimated": item["reported_units"],
            "mirror_reporter_count": item["reporter_count"],
        }
        for item in quantity_detail
    ]
    return monthly_rows, detail_rows, quantity_rows


def _dictionary_rows() -> list[dict]:
    themes = {
        "manufacturing_equipment": "工业",
        "civil_construction_equipment": "建筑",
        "energy_project_equipment": "能源",
        "drilling_equipment": "能源",
        "port_rail_equipment": "基建",
    }
    rows = []
    for category, definition in SERIES.items():
        name = definition["name_zh"].removesuffix("进口")
        rows.append(
            {
                "indicator_name": f"阿联酋:进口:{name}:当月值",
                "frequency": "月",
                "unit": "百万美元",
                "source": "UN Comtrade",
                "type": "金额",
                "industry": themes[category],
                "updated_at": date.today(),
            }
        )
        rows.append(
            {
                "indicator_name": f"阿联酋:进口:{name}:台数:当月值",
                "frequency": "月",
                "unit": "台/件",
                "source": "UN Comtrade",
                "type": "数量",
                "industry": themes[category],
                "updated_at": date.today(),
            }
        )
    return rows


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（缓存恢复）→ 聚合 → 三表事务内入库。"""

    if skip_download:
        missing = [
            path
            for path in (
                REPORTERS_PATH,
                RAW_DIR / "equipment_uae_reported",
                RAW_DIR / "equipment_all_mirror",
            )
            if not path.exists()
        ]
        if missing:
            raise FileNotFoundError(
                "--skip-download 但缺少 Comtrade 输入: "
                + ", ".join(str(path) for path in missing)
            )
    else:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        download_file(REPORTERS_URL, REPORTERS_PATH)
        write_scope_file()
        client = ComtradeClient(load_api_key(), MIN_API_INTERVAL)
        download_monthly(client, force)

    rows, detail, sources, quantity_detail = aggregate()
    monthly_rows, detail_rows, quantity_rows = _to_db_rows(
        rows, detail, quantity_detail
    )
    with _transaction(con):
        db.replace(con, "comtrade_monthly", monthly_rows)
        db.replace(con, "comtrade_partner_detail", detail_rows)
        db.replace(con, "comtrade_quantity_detail", quantity_rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    quality = _quality_report(rows, detail, sources, quantity_detail, None)
    _atomic_json(QUALITY_PATH, quality)
    note = (
        f"{len(rows)} 个月（{rows[-1]['month']} 至 {rows[0]['month']}），"
        f"明细 {len(detail_rows)} 行"
    )
    return {"status": "ok", "rows": len(monthly_rows), "note": note}


def _quality_report(
    rows: list[dict[str, Any]],
    detail: list[dict[str, Any]],
    sources: dict[tuple[str, str], str],
    quantity_detail: list[dict[str, Any]],
    workbook_path: Path | None,
) -> dict:
    months = [row["month"] for row in rows]
    reporter_counts: dict[str, dict[str, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for row in detail:
        if float(row["trade_value_usd"]) != 0:
            reporter_counts[row["month"]][row["series"]].add(
                int(row["reporter_code"])
            )
    total_units = sum(float(row["units"]) for row in quantity_detail)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": len(rows),
        "unique_month_count": len(set(months)),
        "first_month": min(months),
        "last_month": max(months),
        "source_cell_counts": {
            source: sum(value == source for value in sources.values())
            for source in {"uae_reported", "all_partner_mirror", "missing"}
        },
        "missing_by_series": {
            category: sum(row[f"{category}_usd"] is None for row in rows)
            for category in SERIES
        },
        "quantity_missing_by_series": {
            category: sum(row[f"{category}_units"] is None for row in rows)
            for category in SERIES
        },
        "quantity_source_rows": dict(
            Counter(row["source"] for row in quantity_detail)
        ),
        "estimated_quantity_share": (
            round(
                sum(float(row["estimated_units"]) for row in quantity_detail)
                / total_units,
                6,
            )
            if total_units
            else None
        ),
        "latest_month_reporter_counts": {
            category: len(reporter_counts[max(months)][category])
            for category in SERIES
        },
        "negative_value_count": sum(
            value < 0
            for row in rows
            for key, value in row.items()
            if key.endswith("_usd") and value is not None
        ),
        "workbook_output": str(workbook_path) if workbook_path else None,
    }


# ---------------------------------------------------------------------------
# 写表（走 merge_with_excel.ps1，协议不变）
# ---------------------------------------------------------------------------


def _reconstruct_rows(con) -> list[dict[str, Any]]:
    """从库重建旧 process_and_merge 的 rows 结构（含缺失月补空）。"""

    records = con.execute(
        "SELECT period, category, value, units FROM comtrade_monthly"
    ).fetchall()
    by_period: dict[date, dict[str, Any]] = defaultdict(dict)
    for period, category, value, units in records:
        by_period[period][category] = (value, units)
    rows = []
    for period in sorted(by_period, reverse=True):
        result: dict[str, Any] = {
            "month": period.strftime("%Y%m"),
            "date": period,
        }
        for category in SERIES:
            value, units = by_period[period].get(category, (None, None))
            result[f"{category}_usd"] = value
            result[f"{category}_usd_mn"] = (
                round(value / 1_000_000, 6) if value is not None else None
            )
            result[f"{category}_units"] = units
        rows.append(result)
    return rows


def merge(workbook_path: Path) -> dict:
    """把 comtrade 三表合并进 月度_UNComtrade sheet（Excel COM 原生合并）。"""

    workbook_path = workbook_path.resolve()
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    if not MERGE_SCRIPT.is_file():
        raise FileNotFoundError(f"Excel merge helper not found: {MERGE_SCRIPT}")
    lock_path = workbook_path.with_name(f"~${workbook_path.name}")
    if lock_path.exists():
        raise PermissionError(
            f"Close Excel before updating the workbook: {lock_path}"
        )

    con = db.connect(read_only=True)
    try:
        rows = _reconstruct_rows(con)
    finally:
        con.close()
    if not rows:
        raise ValueError("comtrade_monthly is empty; nothing to merge")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = PROCESSED_DIR / "uae_imports_monthly.csv"
    fieldnames = ["month", "date"]
    for category in SERIES:
        fieldnames.extend(
            [f"{category}_usd", f"{category}_usd_mn", f"{category}_units"]
        )
    with monthly_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        value.isoformat()
                        if isinstance(value, date)
                        else value
                    )
                    for key, value in row.items()
                }
            )

    completed = run_powershell_command(
        (
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MERGE_SCRIPT),
            "-SourceWorkbook",
            str(workbook_path),
        )
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Excel merge did not complete successfully: "
            f"{(completed.stderr or completed.stdout or '').strip()}"
        )
    return {"status": "ok", "note": f"月度_UNComtrade 已更新（{len(rows)} 个月）"}


if __name__ == "__main__":
    print("source_comtrade: 模块入口由 htfa.jobs.uae_data.update_data 与 htfa.jobs.uae_data.merge_workbook 调用")
