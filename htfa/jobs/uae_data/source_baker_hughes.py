"""UAE 石油活跃钻机数（Baker Hughes）月度入库与写表。

逻辑移植自 ``scripts/data_sources/baker_hughes/update_baker_hughes_monthly.py``：
先从 Baker Hughes Worldwide Rig Count 官方页面发现并下载最新工作簿，再从
``data/UAE/raw/baker_hughes/`` 下按"源表最新观测月"选择有效工作簿（不依赖文件名），
提取阿布扎比/迪拜/沙迦的 Oil 活跃钻机数并按月汇总，入库 ``baker_hughes_monthly``。
目标工作簿的最新状态检测（``target_is_current``）与写表协议与旧脚本完全一致。
"""

from __future__ import annotations

import calendar
import re
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urljoin, urlparse

from openpyxl import load_workbook

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)
from ._official_download import download_file, fetch_bytes  # noqa: E402

# ---------------------------------------------------------------------------
# 常量（与旧脚本一致）
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "baker_hughes"
BAKER_WORLDWIDE_URL = "https://rigcount.bakerhughes.com/intl-rig-count"
BAKER_USER_AGENT = "curl/8.0"
SOURCE_SHEET = "WW Monthly"
TARGET_SHEET = "月度_贝克休斯"
SOURCE_NAME = "Baker Hughes"
UAE_COUNTRY_PREFIX = "UAE - "
EXPECTED_STATUS = "Active Rigs"

INDICATORS = (("阿联酋石油活跃钻机数", "oil"),)

OBSOLETE_INDICATORS = (
    "阿联酋活跃钻机总数",
    "阿联酋石油钻机数",
    "阿联酋天然气钻机数",
    "阿联酋其他钻机数",
    "阿联酋陆地钻机数",
    "阿联酋海上钻机数",
)

REQUIRED_COLUMNS = (
    "Region",
    "Country",
    "DrillFor",
    "Location",
    "Rig Status",
    "Year",
    "Month",
    "Rig Count Value",
)

_BAKER_LINK_RE = re.compile(
    r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S
)
_BAKER_HREF_RE = re.compile(r"\bhref=[\"'](?P<href>[^\"']+)[\"']", re.I)


@dataclass(frozen=True)
class RigObservation:
    """一个日历月的汇总 UAE 石油钻机数。"""

    period: str
    oil: Decimal

    @property
    def values(self) -> tuple[Decimal, ...]:
        return tuple(getattr(self, key) for _, key in INDICATORS)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _number(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("Rig Count Value is blank or boolean")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid Rig Count Value: {value!r}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"Invalid Rig Count Value: {value!r}")
    return number


def _find_header(sheet: object) -> tuple[int, dict[str, int]]:
    """在源工作表中定位规范化的月度表头。"""

    for row_number, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=min(40, sheet.max_row), values_only=True),
        start=1,
    ):
        columns = {
            _text(value): column
            for column, value in enumerate(row, start=1)
            if _text(value)
        }
        if all(name in columns for name in REQUIRED_COLUMNS):
            return row_number, columns
    raise ValueError(f"Required monthly-table header not found in {SOURCE_SHEET}")


def extract_uae_monthly(path: Path) -> list[RigObservation]:
    """从一个工作簿中提取并汇总全部 UAE 月度观测。"""

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if SOURCE_SHEET not in workbook.sheetnames:
            raise ValueError(f"Worksheet not found: {SOURCE_SHEET}")
        sheet = workbook[SOURCE_SHEET]
        header_row, columns = _find_header(sheet)
        monthly: dict[tuple[int, int], Decimal] = {}
        seen_rows: set[tuple[object, ...]] = set()

        for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
            country = _text(row[columns["Country"] - 1])
            if not country.startswith(UAE_COUNTRY_PREFIX):
                continue
            drill_for = _text(row[columns["DrillFor"] - 1])
            if drill_for != "Oil":
                continue
            status = _text(row[columns["Rig Status"] - 1])
            if status != EXPECTED_STATUS:
                raise ValueError(
                    f"Unexpected UAE rig status {status!r} in {path.name}"
                )
            year_value = row[columns["Year"] - 1]
            month_value = row[columns["Month"] - 1]
            try:
                year = int(year_value)
                month = int(month_value)
                datetime(year, month, 1)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid UAE observation period: {year_value!r}-{month_value!r}"
                ) from exc

            location = _text(row[columns["Location"] - 1])
            row_key = (year, month, country, drill_for, location, status)
            if row_key in seen_rows:
                raise ValueError(f"Duplicate UAE rig row: {row_key}")
            seen_rows.add(row_key)

            value = _number(row[columns["Rig Count Value"] - 1])
            if location not in {"Land", "Offshore"}:
                raise ValueError(f"Unexpected UAE Location value: {location!r}")
            monthly[(year, month)] = monthly.get(
                (year, month), Decimal("0")
            ) + value

        if not monthly:
            raise ValueError(f"No UAE monthly rig rows found in {path.name}")

        observations: list[RigObservation] = []
        for (year, month), oil_count in sorted(monthly.items()):
            observations.append(
                RigObservation(
                    period=f"{year:04d}-{month:02d}",
                    oil=oil_count,
                )
            )
        return observations
    finally:
        workbook.close()


def select_latest_workbook(
    directory: Path,
) -> tuple[Path, list[RigObservation], list[str]]:
    """选择包含最新观测月的有效工作簿。"""

    candidates: list[tuple[str, int, str, Path, list[RigObservation]]] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        try:
            observations = extract_uae_monthly(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        candidates.append(
            (
                observations[-1].period,
                path.stat().st_mtime_ns,
                path.name,
                path,
                observations,
            )
        )
    if not candidates:
        details = "; ".join(errors) if errors else "no .xlsx files found"
        raise FileNotFoundError(f"No valid Baker Hughes workbook: {details}")
    _, _, _, selected_path, selected_observations = max(candidates)
    return selected_path, selected_observations, errors


def _normalized_number(value: object) -> Decimal | None:
    try:
        return _number(value)
    except ValueError:
        return None


def target_is_current(path: Path, observations: Iterable[RigObservation]) -> bool:
    """判断受管目标 sheet 是否已包含这些数值。"""

    if not path.is_file():
        return False
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if TARGET_SHEET not in workbook.sheetnames:
            return False
        sheet = workbook[TARGET_SHEET]
        headers = {
            _text(value): column
            for column, value in enumerate(
                next(sheet.iter_rows(min_row=2, max_row=2, values_only=True)),
                start=1,
            )
        }
        if any(name not in headers for name, _ in INDICATORS):
            return False
        actual: dict[str, tuple[Decimal | None, ...]] = {}
        for row in sheet.iter_rows(min_row=7, values_only=True):
            raw_date = row[0]
            if not isinstance(raw_date, (date, datetime)):
                continue
            actual[raw_date.strftime("%Y-%m")] = tuple(
                _normalized_number(row[headers[name] - 1])
                for name, _ in INDICATORS
            )
        expected = {item.period: item.values for item in observations}
        return actual == expected
    finally:
        workbook.close()


def _month_end(period: str) -> date:
    """'YYYY-MM' -> 该月最后一天的 date。"""

    year, month = (int(part) for part in period.split("-"))
    return date(year, month, calendar.monthrange(year, month)[1])


@contextmanager
def _transaction(con) -> Iterator[None]:
    """事务上下文：duckdb 1.5.5 的 `with con.begin():` 退出时会把连接一并
    关闭（begin 返回的是子连接），因此手动管理提交/回滚。"""

    transaction = con.begin()
    try:
        yield
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": "阿联酋石油活跃钻机数",
            "frequency": "月",
            "unit": "台",
            "source": SOURCE_NAME,
            "type": "数量",
            "industry": "能源",
            "updated_at": date.today(),
        }
    ]


def _discover_latest_worldwide_report() -> tuple[str, Path]:
    """Discover the current international Excel report from Baker Hughes."""

    html = fetch_bytes(
        BAKER_WORLDWIDE_URL,
        user_agent=BAKER_USER_AGENT,
    ).decode("utf-8", errors="replace")
    for match in _BAKER_LINK_RE.finditer(html):
        href_match = _BAKER_HREF_RE.search(match.group("attrs"))
        if href_match is None:
            continue
        body = re.sub(r"<[^>]+>", " ", match.group("body"))
        title = " ".join(body.split()).casefold()
        if "worldwide rig count report" not in title or "new report" not in title:
            continue
        url = urljoin(BAKER_WORLDWIDE_URL, href_match.group("href"))
        identifier = Path(urlparse(url).path).name
        if not identifier:
            raise ValueError("Baker Hughes 当前报告链接没有文件标识")
        suffix = identifier if identifier.lower().endswith((".xlsx", ".xls")) else f"{identifier}.xlsx"
        return url, RAW_DIR / f"auto_worldwide_{suffix}"
    raise ValueError("Baker Hughes 官网未发现 Worldwide Rig Count Report - New Report")


def _download_latest_worldwide_report(*, force: bool) -> str:
    url, target = _discover_latest_worldwide_report()
    status = download_file(
        url,
        target,
        # The landing page discovers the current report, but the newest
        # report file can also be revised in place.
        force=True,
        min_bytes=10_000,
        referer=BAKER_WORLDWIDE_URL,
        user_agent=BAKER_USER_AGENT,
    )
    return f"官网报告：{target.name}（{'新增下载' if status == 'downloaded' else '复用缓存'}）"


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """自动发现/下载 Baker Hughes 月报，再解析入库。"""

    download_note = ""
    if not skip_download:
        try:
            download_note = _download_latest_worldwide_report(force=force)
        except Exception as exc:  # noqa: BLE001 - a valid local workbook remains usable
            if not any(RAW_DIR.glob("*.xlsx")):
                raise
            download_note = f"官网报告下载失败，使用本地缓存：{exc}"

    warnings.filterwarnings(
        "ignore",
        message="Unknown extension is not supported and will be removed",
        module="openpyxl.worksheet._reader",
    )
    source_path, observations, warnings_found = select_latest_workbook(RAW_DIR)
    rows = [
        {
            "period": _month_end(observation.period),
            "oil_rigs": int(observation.oil),
        }
        for observation in observations
    ]
    with _transaction(con):
        db.replace(con, "baker_hughes_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"{len(rows)} 个月（{observations[0].period} 至 {observations[-1].period}），"
        f"源文件 {source_path.name}"
    )
    if warnings_found:
        note += f"；跳过 {len(warnings_found)} 个失效文件"
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """把 baker_hughes_monthly 写回 阿联酋.xlsx 的 月度_贝克休斯 sheet。

    保留旧脚本的 target_is_current 幂等检查：工作表已是最新则不重写。
    写表走 data/write_baker_hughes_sheet.ps1（Excel COM），失败即抛错。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_baker_hughes_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, oil_rigs FROM baker_hughes_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    observations = [
        RigObservation(
            period=period.strftime("%Y-%m"),
            oil=Decimal(str(oil_rigs)),
        )
        for period, oil_rigs in db_rows
    ]
    if not observations:
        raise ValueError("baker_hughes_monthly is empty; nothing to merge")

    if target_is_current(workbook_path, observations):
        return {
            "status": "skipped",
            "note": f"{TARGET_SHEET} 已是最新（观测至 {observations[-1].period}）",
        }

    payload = {
        "dictionary_sheet_name": "指标字典",
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": "台",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": "数量", "industry": "能源"}
            for name, _ in INDICATORS
        ],
        "obsolete_indicators": list(OBSOLETE_INDICATORS),
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload,
        prefix=".baker-hughes-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写入 {TARGET_SHEET}",
    }


if __name__ == "__main__":
    print("source_baker_hughes.py 自检：")
    print("  update(con, force=, skip_download=) 自动发现/下载官网月报并解析")
    print("    （按源表最新观测月选档）并入库 baker_hughes_monthly")
    print("  merge(workbook_path) 把表写回 月度_贝克休斯，保留幂等检查")
    print("  本文件直接运行不执行任何下载或工作簿写入。")
