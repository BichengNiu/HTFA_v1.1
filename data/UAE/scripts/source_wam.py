"""UAE military strike exposure and war-pressure index (WAM registry).

The reviewed daily registry is stored in ``data/UAE/raw/wam/``.  This module
validates that registry, preserves the daily detail in DuckDB, aggregates the
three weapon counts and the daily three-log pressure measure by month, and
rebuilds ``月度_WAM`` from DuckDB.

The raw pressure measure is deliberately aggregated as the sum of daily
weighted values: ``sum(9*log1p(ballistic) + 3*log1p(cruise) + log1p(uavs))``.
The monthly display index is then min-max normalized to 0-100 over the full
war window. Unclassified missiles remain visible as an auxiliary count but do
not enter that index.
"""

from __future__ import annotations

import calendar
import csv
import math
import sys
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
RAW_DIR = DATA_DIR / "raw" / "wam"
DAILY_PATH = RAW_DIR / "uae_military_strike_intensity_daily.csv"
ASSET_PATH = RAW_DIR / "asset_sources.csv"
TARGET_SHEET = "月度_WAM"
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "根据公开新闻整理"
INDUSTRY = "地缘安全"
START_DATE = date(2026, 2, 28)

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
from _excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)
import fetch_wam  # noqa: E402

REQUIRED_COLUMNS = (
    "date",
    "ballistic_missiles",
    "cruise_missiles",
    "uavs",
    "unclassified_missiles",
    "strike_intensity_log",
    "attack_any",
    "uae_asset_attack",
    "origin",
    "observation_status",
    "count_basis",
    "external_threat_alert",
    "source_url",
    "source_url_2",
    "notes",
)

# name, row key, unit, dictionary type
INDICATORS = (
    ("阿联酋军事打击:弹道导弹数量(Ballistic Missiles)", "ballistic_missiles", "枚", "数量"),
    ("阿联酋军事打击:巡航导弹数量(Cruise Missiles)", "cruise_missiles", "枚", "数量"),
    ("阿联酋军事打击:无人机数量(UAVs)", "uavs", "架", "数量"),
    ("阿联酋战争压力指标(强权重log1p之和,0-100归一化)", "strike_intensity_index", "指数", "指数"),
    ("阿联酋军事打击:未分类导弹数量(Unclassified Missiles)", "unclassified_missiles", "枚", "数量"),
    ("阿联酋军事打击:攻击天数(Attack Days)", "attack_days", "天", "数量"),
    ("阿联酋军事打击:观测天数(Observation Days)", "observation_days", "天", "数量"),
)

WEAPON_PRESSURE_WEIGHTS = {
    "ballistic_missiles": 9.0,
    "cruise_missiles": 3.0,
    "uavs": 1.0,
}
LEGACY_PRESSURE_INDICATOR = "阿联酋战争压力指标(三类武器log1p之和)"
PREVIOUS_PRESSURE_INDICATOR = "阿联酋战争压力指标(强权重log1p之和)"


@dataclass(frozen=True)
class MonthlyObservation:
    period: date | str
    observation_days: int
    ballistic_missiles: int
    cruise_missiles: int
    uavs: int
    unclassified_missiles: int
    strike_intensity_log: float
    strike_intensity_index: float
    attack_days: int
    asset_attack_days: int
    external_threat_alert_days: int

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(
            float(getattr(self, key))
            for _, key, _, _ in INDICATORS
        )


def _int(value: object, *, field: str, row_number: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: {field} is not an integer: {value!r}") from exc
    if number < 0:
        raise ValueError(f"row {row_number}: {field} is negative: {value!r}")
    return number


def _flag(value: object, *, field: str, row_number: int) -> bool:
    number = _int(value, field=field, row_number=row_number)
    if number not in (0, 1):
        raise ValueError(f"row {row_number}: {field} must be 0 or 1")
    return bool(number)


def weighted_pressure(
    ballistic_missiles: int,
    cruise_missiles: int,
    uavs: int,
) -> float:
    """计算强权重日度压力值：弹道9、巡航3、无人机1。"""

    return (
        WEAPON_PRESSURE_WEIGHTS["ballistic_missiles"] * math.log1p(ballistic_missiles)
        + WEAPON_PRESSURE_WEIGHTS["cruise_missiles"] * math.log1p(cruise_missiles)
        + WEAPON_PRESSURE_WEIGHTS["uavs"] * math.log1p(uavs)
    )


def _url(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid source URL: {text!r}")
    return text


def _asset_sources() -> dict[str, str]:
    if not ASSET_PATH.is_file():
        return {}
    result: dict[str, str] = {}
    with ASSET_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            period = (row.get("date") or "").strip()
            if not period:
                raise ValueError(f"asset_sources.csv row {row_number}: date is blank")
            date.fromisoformat(period)
            url = _url(row.get("source_url"))
            if not url:
                raise ValueError(f"asset_sources.csv row {row_number}: source_url is blank")
            if period in result and result[period] != url:
                raise ValueError(f"asset_sources.csv has duplicate date with conflicting URL: {period}")
            result[period] = url
    return result


def load_daily_observations(path: Path = DAILY_PATH) -> list[dict]:
    """Load and validate the reviewed daily registry."""

    if not path.is_file():
        raise FileNotFoundError(f"WAM daily registry not found: {path}")
    asset_urls = _asset_sources() if path == DAILY_PATH else {}
    observations: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError(
                "Unexpected WAM CSV columns: "
                f"{reader.fieldnames!r}; expected {REQUIRED_COLUMNS!r}"
            )
        for row_number, row in enumerate(reader, start=2):
            try:
                period = date.fromisoformat((row["date"] or "").strip())
            except ValueError as exc:
                raise ValueError(f"row {row_number}: invalid date {row['date']!r}") from exc
            ballistic = _int(row["ballistic_missiles"], field="ballistic_missiles", row_number=row_number)
            cruise = _int(row["cruise_missiles"], field="cruise_missiles", row_number=row_number)
            uavs = _int(row["uavs"], field="uavs", row_number=row_number)
            unclassified = _int(row["unclassified_missiles"], field="unclassified_missiles", row_number=row_number)
            pressure = float(row["strike_intensity_log"])
            expected_pressure = weighted_pressure(ballistic, cruise, uavs)
            if not math.isfinite(pressure) or abs(pressure - expected_pressure) > 5e-8:
                raise ValueError(f"row {row_number}: strike_intensity_log does not match the weighted three-log formula")
            attack_any = _flag(row["attack_any"], field="attack_any", row_number=row_number)
            asset_attack = _flag(row["uae_asset_attack"], field="uae_asset_attack", row_number=row_number)
            external_alert = _flag(row["external_threat_alert"], field="external_threat_alert", row_number=row_number)
            expected_attack = (ballistic + cruise + uavs + unclassified) > 0
            if attack_any != expected_attack:
                raise ValueError(f"row {row_number}: attack_any does not match weapon counts")
            source_urls = [_url(row[field]) for field in ("source_url", "source_url_2")]
            source_url_3 = asset_urls.get(period.isoformat(), "")
            if attack_any and not any(source_urls) and not source_url_3:
                raise ValueError(f"row {row_number}: an attack row has no source URL")
            observations.append(
                {
                    "date": period,
                    "ballistic_missiles": ballistic,
                    "cruise_missiles": cruise,
                    "uavs": uavs,
                    "unclassified_missiles": unclassified,
                    "strike_intensity_log": pressure,
                    "attack_any": attack_any,
                    "uae_asset_attack": asset_attack,
                    "origin": (row["origin"] or "").strip() or None,
                    "observation_status": (row["observation_status"] or "").strip(),
                    "count_basis": (row["count_basis"] or "").strip() or None,
                    "external_threat_alert": external_alert,
                    "source_url": source_urls[0] or None,
                    "source_url_2": source_urls[1] or None,
                    "source_url_3": source_url_3 or None,
                    "notes": (row["notes"] or "").strip() or None,
                }
            )
    if not observations:
        raise ValueError("WAM daily registry is empty")
    observations.sort(key=lambda item: item["date"])
    if observations[0]["date"] != START_DATE:
        raise ValueError(f"WAM registry must start at {START_DATE}, got {observations[0]['date']}")
    expected_dates = {START_DATE}
    for item in observations[1:]:
        previous = max(expected_dates)
        expected_dates.add(previous.fromordinal(previous.toordinal() + 1))
        if item["date"] != max(expected_dates):
            raise ValueError(f"WAM registry has a date gap or duplicate near {item['date']}")
    return observations


def build_monthly_observations(daily: list[dict]) -> list[MonthlyObservation]:
    """Aggregate daily observations and normalize monthly pressure to 0-100."""

    grouped: dict[tuple[int, int], dict[str, float | int]] = {}
    for row in daily:
        key = (row["date"].year, row["date"].month)
        item = grouped.setdefault(
            key,
            {
                "ballistic_missiles": 0,
                "cruise_missiles": 0,
                "uavs": 0,
                "unclassified_missiles": 0,
                "strike_intensity_log": 0.0,
                "attack_days": 0,
                "observation_days": 0,
                "asset_attack_days": 0,
                "external_threat_alert_days": 0,
            },
        )
        for field in ("ballistic_missiles", "cruise_missiles", "uavs", "unclassified_missiles"):
            item[field] += row[field]
        item["strike_intensity_log"] += row["strike_intensity_log"]
        item["attack_days"] += int(row["attack_any"])
        item["observation_days"] += 1
        item["asset_attack_days"] += int(row["uae_asset_attack"])
        item["external_threat_alert_days"] += int(row["external_threat_alert"])

    monthly = [
        MonthlyObservation(
            period=date(year, month, calendar.monthrange(year, month)[1]),
            **{field: item[field] for field in item},
            strike_intensity_index=0.0,
        )
        for (year, month), item in sorted(grouped.items())
    ]
    raw_values = [row.strike_intensity_log for row in monthly]
    minimum = min(raw_values)
    maximum = max(raw_values)
    spread = maximum - minimum
    return [
        replace(
            row,
            strike_intensity_index=(
                0.0 if spread == 0 else 100.0 * (row.strike_intensity_log - minimum) / spread
            ),
        )
        for row in monthly
    ]


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": "月",
            "unit": unit,
            "source": SOURCE_NAME,
            "type": indicator_type,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, _, unit, indicator_type in INDICATORS
    ]


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


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Refresh source archives when requested, then validate and load WAM data."""

    fetch_note = ""
    if not skip_download:
        counts = fetch_wam.refresh_source_manifest(force=force)
        fetch_note = (
            f"来源页 total={counts['total']}, downloaded={counts['downloaded']}, "
            f"reused={counts['reused']}, failed={counts['failed']}"
        )
    daily = load_daily_observations()
    monthly = build_monthly_observations(daily)
    daily_rows = [dict(row) for row in daily]
    monthly_rows = [
        {
            "period": row.period,
            "observation_days": row.observation_days,
            "ballistic_missiles": row.ballistic_missiles,
            "cruise_missiles": row.cruise_missiles,
            "uavs": row.uavs,
            "unclassified_missiles": row.unclassified_missiles,
            "strike_intensity_log": row.strike_intensity_log,
            "strike_intensity_index": row.strike_intensity_index,
            "attack_days": row.attack_days,
            "asset_attack_days": row.asset_attack_days,
            "external_threat_alert_days": row.external_threat_alert_days,
        }
        for row in monthly
    ]
    with _transaction(con):
        db.replace(con, "wam_military_strike_daily", daily_rows)
        db.replace(con, "wam_military_strike_monthly", monthly_rows)
        con.execute(
            "DELETE FROM meta_indicator_dictionary "
            "WHERE indicator_name IN (?, ?, ?)",
            [LEGACY_PRESSURE_INDICATOR, PREVIOUS_PRESSURE_INDICATOR, INDICATORS[3][0]],
        )
        db.upsert_dictionary_rows(con, _dictionary_rows())
    note = (
        f"日度 {len(daily)} 行（{daily[0]['date']} 至 {daily[-1]['date']}），"
        f"月度 {len(monthly)} 行；{fetch_note or '使用本地来源缓存'}"
    )
    return {"status": "ok", "rows": len(daily) + len(monthly), "note": note}


def merge(workbook_path: Path) -> dict:
    """Rebuild ``月度_WAM`` from the monthly DuckDB table."""

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_cbuae_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")
    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT period, observation_days, ballistic_missiles, cruise_missiles,
                   uavs, unclassified_missiles, strike_intensity_log,
                   strike_intensity_index, attack_days
            FROM wam_military_strike_monthly
            ORDER BY period
            """
        ).fetchall()
    finally:
        con.close()
    observations = [
        MonthlyObservation(
            period=period.strftime("%Y-%m"),
            observation_days=int(observation_days),
            ballistic_missiles=int(ballistic),
            cruise_missiles=int(cruise),
            uavs=int(uavs),
            unclassified_missiles=int(unclassified),
            strike_intensity_log=float(pressure),
            strike_intensity_index=float(index),
            attack_days=int(attack_days),
            asset_attack_days=0,
            external_threat_alert_days=0,
        )
        for (
            period,
            observation_days,
            ballistic,
            cruise,
            uavs,
            unclassified,
            pressure,
            index,
            attack_days,
        ) in rows
    ]
    if not observations:
        raise ValueError("wam_military_strike_monthly is empty; nothing to merge")
    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": "数量/指数",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": indicator_type, "industry": INDUSTRY, "unit": unit}
            for name, _, unit, indicator_type in INDICATORS
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload, prefix=".wam-sheet-", directory=DATA_DIR
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )
    return {"status": "ok", "note": f"{len(observations)} 个月写入 {TARGET_SHEET}"}


if __name__ == "__main__":
    print("source_wam.py 自检：")
    print("  update(con, force=, skip_download=) 解析 raw/wam/ 日度登记表并入库")
    print("  merge(workbook_path) 从 DuckDB 重建 月度_WAM")
