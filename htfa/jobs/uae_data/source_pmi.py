"""S&P Global 阿联酋非油私营部门 PMI 月度入库与写表。

逻辑移植自 ``scripts/data_sources/uae_pmi/``（download_uae_pmi.py 下载 +
process_uae_pmi.py 解析/质检/写）。原始缓存写入 ``data/UAE/raw/pmi/`` 下的
tradingeconomics_chart.json、source_metadata.json、quality_report.json。
入库表 ``pmi_monthly`` 的 period 为月末、value 保留一位小数。受管工作表名为
``月度_LSEG``（兼容工作簿 schema），单元格级来源标注真实公开来源。
"""

from __future__ import annotations

import base64
import calendar
import gzip
import html
import json
import math
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from openpyxl import load_workbook

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "pmi"
CHART_PATH = RAW_DIR / "tradingeconomics_chart.json"
METADATA_PATH = RAW_DIR / "source_metadata.json"
REPORT_PATH = RAW_DIR / "quality_report.json"

TARGET_SHEET = "月度_LSEG"
DICTIONARY_SHEET = "指标字典"
INDICATOR_NAME = "阿联酋非油私营部门采购经理人指数(PMI)"
SOURCE_LABEL = "S&P Global / Trading Economics（公开样本）"
SOURCE_URL = "https://tradingeconomics.com/united-arab-emirates/manufacturing-pmi"
MINIMUM_HISTORY_MONTHS = 24
MAX_LATEST_LAG_MONTHS = 2

# --- 下载器常量（与旧 download_uae_pmi.py 一致） ---
PUBLIC_PAGE_URL = (
    "https://tradingeconomics.com/united-arab-emirates/manufacturing-pmi"
)
SP_GLOBAL_RELEASES_URL = (
    "https://www.pmi.spglobal.com/Public/Release/PressReleases"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CONFIG_FIELDS = (
    "TEChartsDatasource",
    "TEChartsToken",
    "TEObfuscationkey",
    "TESymbol",
    "TELastUpdate",
)

# ---------------------------------------------------------------------------
# 下载器（平移自 download_uae_pmi.py）
# ---------------------------------------------------------------------------


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    """抓取一个公开 URL，带有限超时。"""

    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} while downloading {url}")
        return response.read()


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """抓取一个 UTF-8 兼容的公开页面。"""

    return fetch_bytes(url, headers).decode("utf-8", errors="replace")


def parse_chart_config(page_html: str) -> dict[str, str]:
    """从公开页面中提取图表端点配置。"""

    config: dict[str, str] = {}
    for field in CONFIG_FIELDS:
        match = re.search(
            rf"\b{re.escape(field)}\s*=\s*['\"]([^'\"]+)['\"]",
            page_html,
        )
        if match:
            config[field] = html.unescape(match.group(1)).strip()
    required = set(CONFIG_FIELDS) - {"TELastUpdate"}
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(
            "Public chart configuration is incomplete: " + ", ".join(missing)
        )
    return config


def decode_chart_response(response_body: bytes, xor_key: str) -> Any:
    """用其 Web 应用公布的算法解码图表响应。"""

    text = response_body.decode("ascii").strip()
    try:
        encoded = json.loads(text)
    except json.JSONDecodeError:
        encoded = text.strip('"')
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Unexpected public chart response envelope")
    try:
        compressed = bytearray(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError) as exc:
        raise ValueError("Public chart response is not valid base64") from exc
    key = xor_key.encode("utf-8")
    if not key:
        raise ValueError("Public chart XOR key is blank")
    for index in range(len(compressed)):
        compressed[index] ^= key[index % len(key)]
    try:
        decoded = gzip.decompress(bytes(compressed))
    except OSError as exc:
        raise ValueError("Public chart response is not valid gzip data") from exc
    try:
        return json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Public chart payload is not valid JSON") from exc


def extract_series(payload: Any) -> dict[str, Any]:
    """从图表 payload 中返回并校验唯一的 UAE PMI 序列。"""

    try:
        series = payload[0]["series"][0]["serie"]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("UAE PMI series was not found in chart payload") from exc
    required = {"data", "source", "frequency", "country", "unit"}
    missing = sorted(required - series.keys())
    if missing:
        raise ValueError("UAE PMI series metadata is incomplete: " + ", ".join(missing))
    if series["country"] != "United Arab Emirates":
        raise ValueError(f"Unexpected chart country: {series['country']!r}")
    if str(series["frequency"]).lower() != "monthly":
        raise ValueError(f"Unexpected chart frequency: {series['frequency']!r}")
    if "S&P" not in str(series["source"]):
        raise ValueError(f"Unexpected chart source: {series['source']!r}")
    if not isinstance(series["data"], list) or not series["data"]:
        raise ValueError("UAE PMI chart contains no observations")
    return series


def find_latest_official_release(index_html: str) -> dict[str, str] | None:
    """在 S&P Global 的公开索引中查找当前英文 UAE PMI 发布。"""

    block_pattern = re.compile(
        r'<div\s+class="listItem">(?P<body>.*?)</div>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in block_pattern.finditer(index_html):
        body = match.group("body")
        title_match = re.search(
            r'<span\s+class="releaseTitle">(.*?)</span>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not title_match:
            continue
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        if title != "S&P Global United Arab Emirates PMI":
            continue
        date_match = re.search(
            r'<span\s+class="releaseDate">(.*?)</span>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        url_match = re.search(r'href="([^"]+)"', body, flags=re.IGNORECASE)
        if not date_match or not url_match:
            return None
        release_date = re.sub(r"<[^>]+>", "", date_match.group(1))
        release_date = " ".join(html.unescape(release_date).split())
        return {
            "title": title,
            "release_date_utc": release_date,
            "url": urljoin(SP_GLOBAL_RELEASES_URL, html.unescape(url_match.group(1))),
        }
    return None


def atomic_json_dump(path: Path, payload: Any) -> None:
    """原子写 JSON，避免失败的刷新截断既有数据。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def download(output_dir: Path) -> tuple[Path, Path]:
    """下载公开图表样本及其溯源元数据。"""

    page_html = fetch_text(PUBLIC_PAGE_URL)
    config = parse_chart_config(page_html)
    chart_url = (
        config["TEChartsDatasource"].rstrip("/")
        + "/economics/"
        + config["TESymbol"].lower()
        + "?span=max"
    )
    chart_body = fetch_bytes(
        chart_url,
        headers={"x-api-key": config["TEChartsToken"]},
    )
    payload = decode_chart_response(chart_body, config["TEObfuscationkey"])
    series = extract_series(payload)

    official_release = None
    try:
        official_release = find_latest_official_release(
            fetch_text(SP_GLOBAL_RELEASES_URL)
        )
    except (OSError, RuntimeError):
        # 可选发布索引交叉核对暂时不可用时，图表下载仍可用。
        official_release = None

    raw_path = output_dir / "tradingeconomics_chart.json"
    metadata_path = output_dir / "source_metadata.json"
    atomic_json_dump(raw_path, payload)
    atomic_json_dump(
        metadata_path,
        {
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "indicator": "S&P Global UAE headline PMI",
            "definition": (
                "UAE non-oil private-sector headline PMI, seasonally adjusted"
            ),
            "original_source": series["source"],
            "public_display_provider": "Trading Economics",
            "public_page_url": PUBLIC_PAGE_URL,
            "chart_url": chart_url,
            "chart_symbol": config["TESymbol"],
            "source_last_update": config.get("TELastUpdate"),
            "observation_count": len(series["data"]),
            "first_reference_date": series["data"][0][3],
            "last_reference_date": series["data"][-1][3],
            "latest_value": series["data"][-1][0],
            "official_release_index_url": SP_GLOBAL_RELEASES_URL,
            "latest_official_release": official_release,
            "coverage_note": (
                "Trading Economics labels this as a limited sample licensed from "
                "S&P Global. Full headline history and sub-indices require a "
                "subscription; this downloader does not claim full survey history."
            ),
        },
    )
    return raw_path, metadata_path


# ---------------------------------------------------------------------------
# 解析 / 质检 / 写表（平移自 process_uae_pmi.py）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PmiObservation:
    """一个参考月及其季调后的 headline PMI 值。"""

    period: str
    value: float


def _month_number(period: str) -> int:
    parsed = datetime.strptime(period, "%Y-%m")
    return parsed.year * 12 + parsed.month


def _expected_periods(start: str, end: str) -> list[str]:
    current = datetime.strptime(start, "%Y-%m")
    end_date = datetime.strptime(end, "%Y-%m")
    periods: list[str] = []
    while current <= end_date:
        periods.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return periods


def extract_series_from_payload(payload: Any) -> dict[str, Any]:
    """从原始图表 payload 中提取唯一的公开 UAE PMI 序列。"""

    try:
        return payload[0]["series"][0]["serie"]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("Raw file does not contain a UAE PMI chart series") from exc


def load_observations(path: Path) -> list[PmiObservation]:
    """加载、规范化并校验观测级数值。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    series = extract_series_from_payload(payload)
    if series.get("country") != "United Arab Emirates":
        raise ValueError(f"Unexpected country: {series.get('country')!r}")
    if str(series.get("frequency", "")).lower() != "monthly":
        raise ValueError(f"Unexpected frequency: {series.get('frequency')!r}")
    if "S&P" not in str(series.get("source", "")):
        raise ValueError(f"Unexpected source: {series.get('source')!r}")

    observations: list[PmiObservation] = []
    seen: set[str] = set()
    for index, item in enumerate(series.get("data", []), start=1):
        if not isinstance(item, list) or len(item) < 4:
            raise ValueError(f"Malformed observation at source row {index}")
        raw_value, raw_date = item[0], item[3]
        try:
            reference_date = datetime.strptime(str(raw_date), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid reference date: {raw_date!r}") from exc
        if reference_date.day != 1:
            raise ValueError(f"Reference date is not month-start: {raw_date!r}")
        period = reference_date.strftime("%Y-%m")
        if period in seen:
            raise ValueError(f"Duplicate UAE PMI period: {period}")
        seen.add(period)
        if isinstance(raw_value, bool):
            raise ValueError(f"Invalid UAE PMI value in {period}: {raw_value!r}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid UAE PMI value in {period}: {raw_value!r}"
            ) from exc
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"Out-of-range UAE PMI value in {period}: {value}")
        observations.append(PmiObservation(period=period, value=value))
    if not observations:
        raise ValueError("Raw UAE PMI series contains no observations")
    return sorted(observations, key=lambda item: item.period)


def build_quality_report(
    observations: list[PmiObservation],
    metadata: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """生成可复现的历史长度、连续性、区间与时效性检查。"""

    as_of = today or date.today()
    periods = [item.period for item in observations]
    expected = _expected_periods(periods[0], periods[-1])
    missing = sorted(set(expected) - set(periods))
    latest_lag = as_of.year * 12 + as_of.month - _month_number(periods[-1])
    source_update = str(metadata.get("source_last_update") or "")
    source_update_period = None
    if re_match := re.fullmatch(r"(\d{4})(\d{2})\d{2}\d*", source_update):
        source_update_period = f"{re_match.group(1)}-{re_match.group(2)}"
    checks = [
        {
            "name": "has_historical_data",
            "passed": len(observations) >= MINIMUM_HISTORY_MONTHS,
            "detail": (
                f"{len(observations)} months available; minimum "
                f"{MINIMUM_HISTORY_MONTHS}"
            ),
        },
        {
            "name": "monthly_continuity",
            "passed": not missing,
            "detail": "no missing months" if not missing else ", ".join(missing),
        },
        {
            "name": "unique_periods",
            "passed": len(periods) == len(set(periods)),
            "detail": f"{len(periods)} unique periods",
        },
        {
            "name": "valid_pmi_range",
            "passed": all(0 <= item.value <= 100 for item in observations),
            "detail": "all values are within 0-100",
        },
        {
            "name": "latest_data_is_fresh",
            "passed": 0 <= latest_lag <= MAX_LATEST_LAG_MONTHS,
            "detail": (
                f"latest reference month is {periods[-1]}; "
                f"lag={latest_lag} months"
            ),
        },
        {
            "name": "latest_matches_source_update",
            "passed": source_update_period in (None, periods[-1]),
            "detail": (
                "source update date unavailable"
                if source_update_period is None
                else f"source update period={source_update_period}"
            ),
        },
        {
            "name": "metadata_count_matches",
            "passed": metadata.get("observation_count") in (None, len(observations)),
            "detail": (
                f"metadata={metadata.get('observation_count')}; "
                f"parsed={len(observations)}"
            ),
        },
    ]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "indicator": INDICATOR_NAME,
        "source": SOURCE_LABEL,
        "coverage": {
            "start_period": periods[0],
            "end_period": periods[-1],
            "observation_count": len(observations),
            "missing_periods": missing,
            "public_sample_is_full_survey_history": False,
        },
        "latest": {
            "period": observations[-1].period,
            "value": observations[-1].value,
        },
        "checks": checks,
        "limitation": metadata.get("coverage_note"),
    }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def target_is_current(path: Path, observations: Iterable[PmiObservation]) -> bool:
    """判断目标 sheet 是否已与输入数据完全一致。"""

    if not path.is_file():
        return False
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if TARGET_SHEET not in workbook.sheetnames:
            return False
        sheet = workbook[TARGET_SHEET]
        if sheet.cell(2, 2).value != INDICATOR_NAME:
            return False
        actual: dict[str, float] = {}
        for raw_date, raw_value in sheet.iter_rows(
            min_row=7,
            max_col=2,
            values_only=True,
        ):
            if not isinstance(raw_date, (date, datetime)):
                continue
            try:
                actual[raw_date.strftime("%Y-%m")] = float(raw_value)
            except (TypeError, ValueError):
                return False
        expected = {item.period: item.value for item in observations}
        return actual == expected
    finally:
        workbook.close()


def _verify_workbook(path: Path, observations: list[PmiObservation]) -> None:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if TARGET_SHEET not in workbook.sheetnames:
            raise ValueError(f"Worksheet was not created: {TARGET_SHEET}")
        sheet = workbook[TARGET_SHEET]
        expected_rows = sorted(observations, key=lambda item: item.period, reverse=True)
        if sheet.cell(2, 2).value != INDICATOR_NAME:
            raise ValueError("Managed PMI indicator header is incorrect")
        if sheet.cell(5, 2).value != SOURCE_LABEL:
            raise ValueError("Managed PMI source metadata is incorrect")
        for row_number, expected in enumerate(expected_rows, start=7):
            raw_date = sheet.cell(row_number, 1).value
            raw_value = sheet.cell(row_number, 2).value
            if not isinstance(raw_date, (date, datetime)):
                raise ValueError(f"Invalid workbook date in row {row_number}")
            if raw_date.strftime("%Y-%m") != expected.period:
                raise ValueError(f"Workbook period mismatch in row {row_number}")
            if float(raw_value) != expected.value:
                raise ValueError(f"Workbook value mismatch in row {row_number}")
        dictionary = workbook[DICTIONARY_SHEET]
        matches = [
            row[0]
            for row in dictionary.iter_rows(min_row=2, max_col=1, values_only=True)
            if row[0] == INDICATOR_NAME
        ]
        if len(matches) != 1:
            raise ValueError(
                "Indicator dictionary should contain exactly one PMI row; "
                f"found {len(matches)}"
            )
    finally:
        workbook.close()


def write_workbook(path: Path, observations: list[PmiObservation]) -> None:
    """经 Excel COM 更新受管 sheet，带备份、校验与回滚。"""

    if not path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {path}")
    helper_path = Path(__file__).with_name("write_uae_pmi_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")
    payload = {
        "source_label": SOURCE_LABEL,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": "月",
        "unit": "点",
        "source": SOURCE_LABEL,
        "updated_at": date.today().isoformat(),
        "indicator": {
            "name": INDICATOR_NAME,
            "type": "指数",
            "industry": "宏观",
        },
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "records": [
            {"period": item.period, "value": item.value}
            for item in sorted(observations, key=lambda item: item.period, reverse=True)
        ],
    }
    backup_path: Path | None = None
    with payload_json_file(
        payload,
        prefix=".uae-pmi-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        with tempfile.NamedTemporaryFile(
            prefix=".uae-pmi-backup-",
            suffix=path.suffix,
            dir=path.parent,
            delete=False,
        ) as backup:
            backup_path = Path(backup.name)
        try:
            shutil.copy2(path, backup_path)
            run_powershell_sheet_writer(
                helper_path, path, payload_path, TARGET_SHEET
            )
            _verify_workbook(path, observations)
        except Exception:
            if backup_path is not None and backup_path.is_file():
                shutil.copy2(backup_path, path)
            raise
        finally:
            if backup_path is not None and backup_path.exists():
                backup_path.unlink()


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
            "indicator_name": INDICATOR_NAME,
            "frequency": "月",
            "unit": "点",
            "source": SOURCE_LABEL,
            "type": "指数",
            "industry": "宏观",
            "updated_at": date.today(),
        }
    ]


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（按需）→ 解析 → 质检 → 事务内入库。

    - ``skip_download=True``：只用 data/UAE/raw/pmi/ 下既有缓存，缺失即报错。
    - 否则在缓存缺失或 ``force=True`` 时调用``download`` 刷新缓存。
    - 质检报告写入 data/UAE/raw/pmi/quality_report.json；任一检查不过即抛错
      （与旧 process_uae_pmi.py 行为一致）。
    """

    download_note = ""
    if skip_download:
        if not CHART_PATH.is_file() or not METADATA_PATH.is_file():
            raise FileNotFoundError(
                f"--skip-download 但缺少缓存文件: "
                f"{CHART_PATH.name if not CHART_PATH.is_file() else METADATA_PATH.name}"
            )
    else:
        try:
            # The chart URL is stable while the payload changes when a new
            # S&P Global observation is published. Refresh it online every run.
            download(RAW_DIR)
            download_note = "已在线刷新图表与元数据"
        except Exception as exc:  # noqa: BLE001 - valid cache remains usable
            if not (CHART_PATH.is_file() and METADATA_PATH.is_file()):
                raise
            download_note = f"官网刷新失败，沿用有效缓存：{exc}"

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    observations = load_observations(CHART_PATH)
    report = build_quality_report(observations, metadata)
    _atomic_json(REPORT_PATH, report)
    if report["status"] != "passed":
        failed = [item["name"] for item in report["checks"] if not item["passed"]]
        raise ValueError("UAE PMI quality checks failed: " + ", ".join(failed))

    rows = [
        {
            "period": _month_end(observation.period),
            "value": round(observation.value, 1),
            "source_label": SOURCE_LABEL,
            "source_url": SOURCE_URL,
        }
        for observation in observations
    ]
    with _transaction(con):
        db.replace(con, "pmi_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"{len(rows)} 个月（{observations[0].period} 至 {observations[-1].period}），"
        f"最新 {observations[-1].value:.1f}"
    )
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """把 pmi_monthly 写回 阿联酋.xlsx 的 月度_LSEG sheet。

    与旧脚本一致：sheet 已最新时跳过写入但仍做一次整体校验
    （``_verify_workbook``）；否则走带备份/校验/回滚的 ``write_workbook``。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, value FROM pmi_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    observations = [
        PmiObservation(period=period.strftime("%Y-%m"), value=value)
        for period, value in db_rows
    ]
    if not observations:
        raise ValueError("pmi_monthly is empty; nothing to merge")

    if target_is_current(workbook_path, observations):
        _verify_workbook(workbook_path, observations)
        return {
            "status": "skipped",
            "note": f"{TARGET_SHEET} 已是最新（观测至 {observations[-1].period}），校验通过",
        }

    write_workbook(workbook_path, observations)
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写入 {TARGET_SHEET}",
    }


if __name__ == "__main__":
    print("source_pmi.py 自检：")
    print("  update(con, force=, skip_download=) 按需下载公开样本并解析/质检")
    print("    （质量报告写 data/UAE/raw/pmi/quality_report.json）后入库 pmi_monthly")
    print("  merge(workbook_path) 把表写回 月度_LSEG（带幂等检查与回滚）")
    print("  本文件直接运行不联网、不写工作簿。")
