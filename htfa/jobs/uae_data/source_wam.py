"""UAE military strike exposure and war-pressure index (WAM registry).

The reviewed daily registry and the generated automatic extension are stored
in ``data/UAE/raw/wam/``.  This module validates both, preserves the daily
detail in DuckDB, aggregates the three weapon counts and the daily three-log
pressure measure by month, and rebuilds ``月度_WAM`` from DuckDB.

The raw pressure measure is deliberately aggregated as the sum of daily
weighted values: ``sum(9*log1p(ballistic) + 3*log1p(cruise) + log1p(uavs))``.
The monthly display index is then min-max normalized to 0-100 over the full
war window. Unclassified missiles remain visible as an auxiliary count but do
not enter that index.
"""

from __future__ import annotations

import calendar
import csv
import html
import math
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from htfa.data.temporal import last_complete_month_end

from .paths import DATA_DIR, SCRIPTS_DIR

RAW_DIR = DATA_DIR / "raw" / "wam"
DAILY_PATH = RAW_DIR / "uae_military_strike_intensity_daily.csv"
AUTO_DAILY_PATH = RAW_DIR / "auto_daily_observations.csv"
ASSET_PATH = RAW_DIR / "asset_sources.csv"
TARGET_SHEET = "月度_WAM"
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "根据公开新闻整理"
INDUSTRY = "地缘安全"
START_DATE = date(2026, 2, 28)


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)
from . import fetch_wam  # noqa: E402

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


def load_daily_observations(
    path: Path = DAILY_PATH,
    *,
    require_start: bool = True,
    require_contiguous: bool = True,
) -> list[dict]:
    """Load and validate a WAM daily registry or a generated extension."""

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
    if require_start and observations[0]["date"] != START_DATE:
        raise ValueError(f"WAM registry must start at {START_DATE}, got {observations[0]['date']}")
    if require_contiguous:
        expected_date = observations[0]["date"]
        for item in observations[1:]:
            expected_date = expected_date.fromordinal(expected_date.toordinal() + 1)
            if item["date"] != expected_date:
                raise ValueError(f"WAM registry has a date gap or duplicate near {item['date']}")
    return observations


_MONTHS = {
    name.casefold(): number
    for number, name in enumerate(calendar.month_name)
    if name
}
_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_NUMBER_TOKEN = r"(?:\d[\d,]*|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"


def _number_value(value: str) -> int:
    token = value.casefold().replace(",", "").strip()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS[token]


def _first_event_text(body: str, headline: str) -> str:
    """Keep the first operational statement, excluding cumulative totals."""

    text = html.unescape(f"{body} {headline}").replace("\xa0", " ")
    lowered = text.casefold()
    cut_positions = [
        lowered.find(marker)
        for marker in (
            " since the start",
            " since beginning",
            " since onset",
            " since saturday",
            " over the past",
            " in the past",
        )
        if lowered.find(marker) >= 0
    ]
    if cut_positions:
        text = text[: min(cut_positions)]
    return text


def _extract_weapon_count(text: str, kind: str) -> int:
    labels = {
        "ballistic_missiles": r"ballistic\s+miss(?:ile|les)s?",
        "cruise_missiles": r"cruise\s+miss(?:ile|les)s?",
        "uavs": r"(?:uav(?:s|'s)?|drone(?:s)?)",
        "unclassified_missiles": r"miss(?:ile|les)s?",
    }
    label = labels[kind]
    pattern = re.compile(
        rf"\b({_NUMBER_TOKEN})\s+(?:of\s+)?(?:the\s+)?{label}\b",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        return _number_value(match.group(1))
    if kind == "uavs" and re.search(
        r"\b(?:respond(?:ed|s)?|detect(?:ed|s)?|intercept(?:ed|s)?|engag(?:e|ed|es))\s+an?\s+uav\b",
        text,
        re.IGNORECASE,
    ):
        return 1
    return 0


def _event_date(record: dict, body: str) -> date | None:
    match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"[, ]+(\d{4})\b",
        body,
        re.IGNORECASE,
    )
    if match:
        return date(int(match.group(3)), _MONTHS[match.group(2).casefold()], int(match.group(1)))
    published = str(record.get("date_published") or record.get("sitemap_published_at") or "")
    try:
        return date.fromisoformat(published[:10])
    except ValueError:
        return None


def extract_auto_article_observation(record: dict) -> dict | None:
    """Extract one high-confidence daily observation from a WAM JSON-LD record."""

    body = html.unescape(str(record.get("article_body") or ""))
    headline = html.unescape(str(record.get("headline") or record.get("sitemap_title") or ""))
    if not body and not headline:
        return None
    full_text = f"{body} {headline}"
    lowered = full_text.casefold()
    event_text = _first_event_text(body, headline)
    counts = {
        kind: _extract_weapon_count(event_text, kind)
        for kind in WEAPON_PRESSURE_WEIGHTS
    }
    if not any(counts.values()):
        for kind in WEAPON_PRESSURE_WEIGHTS:
            counts[kind] = _extract_weapon_count(headline, kind)

    # Cumulative and interval statements cannot be assigned to one day safely.
    cumulative = bool(
        re.search(r"\bsince\s+(?:the\s+start|beginning|onset|saturday)", lowered)
    )
    interval = bool(re.search(r"\b(?:over|in)\s+the\s+past\s+\d+\s+hours?", lowered))
    if not any(counts.values()) or cumulative or interval:
        return None
    period = _event_date(record, body)
    if period is None:
        return None
    return {
        "date": period,
        **counts,
        "unclassified_missiles": 0,
        "source_url": record.get("url"),
        "published_at": record.get("date_published") or record.get("sitemap_published_at"),
        "headline": headline,
        "origin": "Iran" if "iran" in lowered else "Unknown/Not stated",
    }


def derive_auto_daily_observations(
    base_daily: list[dict], article_records: list[dict]
) -> list[dict]:
    """Build the machine-generated daily extension after the reviewed registry."""

    if not base_daily:
        raise ValueError("Cannot derive WAM automatic extension from an empty registry")
    last_date = base_daily[-1]["date"]
    by_date: dict[date, list[dict]] = {}
    for record in article_records:
        observation = extract_auto_article_observation(record)
        if observation is not None and observation["date"] > last_date:
            by_date.setdefault(observation["date"], []).append(observation)
    if not by_date:
        return []

    last_event_date = max(by_date)
    result: list[dict] = []
    period = last_date.fromordinal(last_date.toordinal() + 1)
    while period <= last_event_date:
        candidates = by_date.get(period, [])
        if candidates:
            values = {
                kind: max(item[kind] for item in candidates)
                for kind in WEAPON_PRESSURE_WEIGHTS
            }
            best = max(
                candidates,
                key=lambda item: (
                    sum(item[kind] for kind in WEAPON_PRESSURE_WEIGHTS),
                    str(item.get("published_at") or ""),
                ),
            )
            urls = list(dict.fromkeys(str(item["source_url"]) for item in candidates if item.get("source_url")))
            result.append(
                {
                    "date": period,
                    **values,
                    "unclassified_missiles": 0,
                    "strike_intensity_log": weighted_pressure(**values),
                    "attack_any": True,
                    "uae_asset_attack": False,
                    "origin": best["origin"],
                    "observation_status": "auto_extracted_wam_jsonld",
                    "count_basis": "official_wam_article_direct_daily_statement",
                    "external_threat_alert": False,
                    "source_url": urls[0] if urls else None,
                    "source_url_2": urls[1] if len(urls) > 1 else None,
                    "source_url_3": None,
                    "notes": "自动从 WAM NewsArticle JSON-LD 正文提取；同日多篇取各类武器最大明确值",
                }
            )
        else:
            result.append(
                {
                    "date": period,
                    "ballistic_missiles": 0,
                    "cruise_missiles": 0,
                    "uavs": 0,
                    "unclassified_missiles": 0,
                    "strike_intensity_log": 0.0,
                    "attack_any": False,
                    "uae_asset_attack": False,
                    "origin": "Unknown/Not stated",
                    "observation_status": "auto_wam_scan_no_verified_attack_article",
                    "count_basis": "official_wam_sitemap_scan_no_qualifying_article",
                    "external_threat_alert": False,
                    "source_url": None,
                    "source_url_2": None,
                    "source_url_3": None,
                    "notes": "WAM 官方英文月度 sitemap 扫描未发现可提取的 UAE 空袭数字；不代表绝对没有事件",
                }
            )
        period = period.fromordinal(period.toordinal() + 1)
    return result


def write_auto_daily_observations(rows: list[dict]) -> None:
    """Atomically persist the generated extension as a raw/cache artifact."""

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".tmp",
            delete=False,
            dir=RAW_DIR,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        field: (
                            row[field].isoformat()
                            if field == "date"
                            else int(row[field])
                            if field in {"ballistic_missiles", "cruise_missiles", "uavs", "unclassified_missiles"}
                            else float(row[field])
                            if field == "strike_intensity_log"
                            else int(bool(row[field]))
                            if field in {"attack_any", "uae_asset_attack", "external_threat_alert"}
                            else row[field] or ""
                        )
                        for field in REQUIRED_COLUMNS
                    }
                )
        os.replace(temporary_path, AUTO_DAILY_PATH)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_effective_daily_observations() -> list[dict]:
    """Load the reviewed registry plus any generated automatic extension."""

    base = load_daily_observations()
    if not AUTO_DAILY_PATH.is_file():
        return base
    auto = load_daily_observations(
        AUTO_DAILY_PATH,
        require_start=False,
        require_contiguous=True,
    )
    if auto and auto[0]["date"] <= base[-1]["date"]:
        raise ValueError("WAM automatic extension overlaps the reviewed registry")
    return base + auto


def build_monthly_observations(daily: list[dict]) -> list[MonthlyObservation]:
    """聚合日度观测；未完整的最新自然月不进入月度结果。"""

    if not daily:
        return []
    cutoff = last_complete_month_end(max(row["date"] for row in daily))
    if cutoff is None:
        return []
    daily = [row for row in daily if row["date"] <= cutoff]
    if not daily:
        return []

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
    monthly = [
        row
        for row in monthly
        if row.observation_days
        >= calendar.monthrange(row.period.year, row.period.month)[1]
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
    base_daily = load_daily_observations()
    if not skip_download:
        # WAM source pages and article bodies may be revised behind stable
        # URLs.  Online runs must re-fetch them; ``--skip-download`` remains
        # the explicit offline/cache-only mode.
        archive_counts = fetch_wam.refresh_source_manifest(force=True)
        auto_counts = fetch_wam.refresh_auto_articles(force=True)
        if auto_counts["failed"]:
            raise RuntimeError(
                f"WAM 自动文章抓取/解析失败 {auto_counts['failed']} 篇；"
                f"请检查 {fetch_wam.AUTO_ARTICLES_PATH}"
            )
        fetch_note = (
            f"WAM cited sources total={archive_counts['total']}, "
            f"downloaded={archive_counts['downloaded']}, reused={archive_counts['reused']}, "
            f"failed={archive_counts['failed']}; auto articles discovered={auto_counts['discovered']}, "
            f"downloaded={auto_counts['downloaded']}, reused={auto_counts['reused']}, "
            f"failed={auto_counts['failed']}"
        )
    auto_rows = derive_auto_daily_observations(
        base_daily, fetch_wam.load_auto_articles()
    )
    if auto_rows:
        write_auto_daily_observations(auto_rows)
    daily = load_effective_daily_observations()
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
        if int(observation_days)
        >= calendar.monthrange(period.year, period.month)[1]
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
