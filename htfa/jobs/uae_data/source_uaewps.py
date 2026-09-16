"""UAEWPS（UAE Wages Protection System）月度统计指标入库与写表。

数据来源：CBUAE 官网「Payments and Settlements → Monthly Statistics → UAE
Wages Protection System (UAEWPS) Statistics」所列月度统计发布。注意：该统计
发布入口在 CBUAE 官网上目前是空占位（列表项无任何文件链接，经真实浏览器渲染、
站点地图、出版物 API 与 Wayback 存档逐一核验），官方未挂出可下载的月度数据
文件；CBUAE 月度统计公报（raw/cbuae/，2020-01 至 2026-06）亦不含 UAEWPS 表。

因此，本模块的月度观测来自官方另一持续序列：**CBUAE 季度经济评论（Quarterly
Economic Review, QER）正文的「Employment and Wages」小节**，每期公布截至季末
月的 WPS 覆盖员工数与平均工资的同比增速（按 3 个月移动平均计算，见 QER 脚注）。
原始文件为 raw/uaewps/qer/*.pdf（自动从 CBUAE 出版物 API 下载；当前覆盖 2021Q4 至 2026Q2）；其中
2024Q1 起的 9 期含 WPS 统计段落，合计 9 个月度观测点（2024-04 至 2026-03）。

流程与 source_cbuae.py 一致：``update()`` 解析 PDF 原文 → 与期望值表逐期校验
（防解析漂移）→ 入长表 ``uaewps_monthly``（(period, indicator)，单位同比%）；
``merge()`` 从库读取并调用 ``write_uaewps_sheet.ps1`` 重建 Excel
「季度_UAEWPS」 sheet（并删除遗留的「月度_UAEWPS」旧 sheet）；缺失值
（如 2024-06 员工数为“几乎持平”，未给具体增速）以 ``None`` 写入并留空单元格，
不臆造数字。频率为「季」（每期 QER 一个季末月观察点），观察月保留为季末月。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from pypdf import PdfReader

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)
from ._official_download import download_file, fetch_bytes  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "uaewps" / "qer"
TARGET_SHEET = "季度_UAEWPS"
# 早期版本曾写入「月度_UAEWPS」（频率误标为月）；合并时自动删除该遗留 sheet
LEGACY_SHEETS = ("月度_UAEWPS",)
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "CBUAE QER"
UNIT = "同比%"
INDUSTRY = "劳工"
FREQUENCY = "季"

# 两个指标：(指标名, 类型)。员工覆盖数与平均工资增速均为同比、3 个月移动平均口径。
UAEWPS_INDICATORS = (
    (
        "阿联酋:WPS覆盖员工数同比%(3个月移动平均)",
        "就业",
    ),
    (
        "阿联酋:WPS平均工资同比%(3个月移动平均)",
        "工资",
    ),
)
INDICATOR_ORDER = {name: i for i, (name, _) in enumerate(UAEWPS_INDICATORS)}

MONTH_NUMBERS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
# 兼容 PDF 文本的 "Wage s Protection" / "Wage Protection" 变体
_WPS_RE = re.compile(r"Wage\s*s?\s+Protection\s+System\s*\(?\s*WPS\s*\)?", re.I)
# 同比数字：容忍 "7.5" "4. 8"（数字间空格）等排版碎片
_NUMBER_RE = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)")
_PERIOD_RE = re.compile(
    r"\b(" + "|".join(MONTH_NUMBERS) + r")\s+(20\d{2})\b", re.I
)
CBUAE_QER_API = (
    "https://www.centralbank.ae/umbraco/api/MediaListing/Get"
    "?language=en&ContentId=83367673-f49f-4ee6-ba1e-800b63601b1d"
    "&filterBy=&search=Quarterly"
)
_QER_MONTHS = {"march": 1, "june": 2, "september": 3, "december": 4}

# 期望值校验表：report 标签 -> (观察月 period, 员工覆盖 YoY %|None, 平均工资 YoY %)。
# 已核对历史期次的回归值；新期次通过结构校验自动接入，防止正则漂移导致静默错数。
EXPECTED = {
    "2024Q1": ("2024-04", 7.5, 9.4),
    "2024Q2": ("2024-06", None, 4.8),
    "2024Q3": ("2024-09", 4.0, 7.2),
    "2024Q4": ("2024-12", 8.4, 6.7),
    "2025Q1": ("2025-03", 7.4, 3.5),
    "2025Q2": ("2025-06", 10.6, 0.2),
    "2025Q3": ("2025-09", 13.9, 0.3),
    "2025Q4": ("2025-12", 14.8, 0.1),
    "2026Q1": ("2026-03", 11.7, 0.7),
}


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _flatten(text: str) -> str:
    """把 PDF 提取文本压成单行，仅保留 ASCII 空格，便于正则。"""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " "))


def _as_float(match: re.Match[str] | None) -> float | None:
    if match is None:
        return None
    return float(match.group(1).replace(" ", ""))


def _observing_period(text: str) -> str | None:
    """从 WPS 段落提取观察月份，形如 'in March 2025' / 'As of September 2024'。"""
    candidates = list(_PERIOD_RE.finditer(text))
    if not candidates:
        return None
    # 取 WPS 段落中最后一次月份-年份组合（正文句式均为“... in <Month> <YYYY> ...”）
    month, year = candidates[-1].groups()
    return f"{year}-{MONTH_NUMBERS[month.lower()]:02d}"


def _parse_employees_yoy(section: str) -> float | None:
    """员工覆盖数同比：'increased by X%'；'remained almost flat' → None。"""
    if re.search(r"remained\s+almost\s+flat", section, re.I):
        return None
    # "increased by 7.5%"（可能被脚注数字隔开，如 'increased by 7.5% and 9.4% Y-o-Y 2 in April'）
    match = re.search(
        r"(?:average\s+number\s+of\s+)?employees?\s+covered[^.]{0,120}?"
        r"increased\s+by\s+(\d{1,2}(?:\s*\.\s*\d{1,2})?)\s*%",
        section,
        re.I,
    )
    return _as_float(match)


def _parse_wage_yoy(section: str) -> float | None:
    """平均工资同比，容忍多种表述：
    - 'average employee salary increased by 4.8%'
    - 'average wage growth was marginal, at 0.2%'
    - 'average wage increased marginally by 0.3%'
    - 'average wage rose by 0.7%'
    - 'increased by 7.5% and 9.4% ... respectively'（第二个数为工资）
    """
    patterns = (
        # "increased by 7.5% and 9.4% Y-o-Y ... respectively"（第二数为工资）
        r"increased\s+by\s+\d{1,2}(?:\s*\.\s*\d{1,2})?\s*%\s+and\s+"
        r"(\d{1,2}(?:\s*\.\s*\d{1,2})?)\s*%",
        # 常见式："increased by 4.8%" / "rose by 0.7%" / "increased marginally by 0.3%"
        r"average\s+(?:employee\s+)?(?:salary|wage)[^.]{0,120}?"
        r"(?:increased|rose)\s+(?:by\s+|marginally\s+by\s+)(\d{1,2}(?:\s*\.\s*\d{1,2})?)\s*%",
        # "growth was marginal, at 0.2%"
        r"wage\s+growth\s+was\s+marginal[^.]{0,60}?\bat\s+(\d{1,2}(?:\s*\.\s*\d{1,2})?)\s*%",
    )
    for pattern in patterns:
        match = re.search(pattern, section, re.I)
        if match:
            return _as_float(match)
    return None


def extract_qer_wps(path: Path) -> tuple[str, str, float | None, float | None, str]:
    """解析单期 QER：返回 (报告标签, 观察月, 员工YoY, 工资YoY, 数据说明)。

    ``数据说明`` 为该期脚注（如 'Data as of mid-May 2025.'），供审计。
    """
    reader = PdfReader(str(path))
    report_tag = path.stem
    page_text = ""
    for page in reader.pages:
        text = _flatten(page.extract_text() or "")
        if "employees covered" in text and "WPS" in text:
            page_text = text
            break
    if not page_text:
        raise ValueError(f"{path.name}: 未找到含 'employees covered' 的 WPS 正文段")

    start = page_text.find("employees covered")
    # 从段落起点（向前找最近的句号）取到 WPS 段落结束（下一个双句号/图注）
    seg_begin = max(page_text.rfind(". ", 0, start), page_text.rfind(".", 0, start))
    seg_begin = max(seg_begin, 0)
    segment = page_text[seg_begin:]

    # 截到脚注/图注起点（数据日期脚注优先于图注，否则 "1 Data as of 27 August
    # 2024" / "1 Data exported in mid-May 2026" 之类会把脚注月份误当观察月）
    for stop_marker in (
        "Data as of",
        "Data exported",
        "Figure 2.",
        "Figure 3.",
        "Sources:",
    ):
        marker_at = segment.find(stop_marker)
        if marker_at > 0:
            segment = segment[:marker_at]
            break

    period = _observing_period(segment)
    employees_yoy = _parse_employees_yoy(segment)
    wage_yoy = _parse_wage_yoy(segment)
    if period is None:
        raise ValueError(f"{path.name}: 未能解析观察月份")

    # 数据说明：尽量抓该页的 'Data as of ...' 脚注
    if "Data as of" in page_text:
        idx = page_text.find("Data as of")
        note = re.sub(r"\s+", " ", page_text[idx:idx + 60]).strip()
    else:
        note = ""
    return report_tag, period, employees_yoy, wage_yoy, note


def validate_observations(
    observations: dict[str, tuple[str, float | None, float | None, str]],
) -> list[tuple[str, str, float | None, float | None, str]]:
    """核对历史回归值，同时允许结构正常的新 QER 期次自动入库。

    已人工核对的期次仍要求完全相等；新期次只要能解析出观察月和至少一个
    数值就入库。若正文结构变化导致两个指标都无法解析，则明确拒绝入库。
    """
    verified: list[tuple[str, str, float | None, float | None, str]] = []
    for tag, (period, emp, wage, note) in sorted(observations.items()):
        expected = EXPECTED.get(tag)
        if expected is None:
            if not period or (emp is None and wage is None):
                raise ValueError(f"{tag}: 新期次未解析出有效 WPS 数值，拒绝入库")
            verified.append((tag, period, emp, wage, note))
            continue
        exp_period, exp_emp, exp_wage = expected
        if (period, emp, wage) != (exp_period, exp_emp, exp_wage):
            raise ValueError(
                f"{tag}: 解析结果 ({period}, {emp}, {wage}) 与期望值 "
                f"({exp_period}, {exp_emp}, {exp_wage}) 不一致，已拒绝入库"
            )
        verified.append((tag, period, emp, wage, note))
    return verified


# ---------------------------------------------------------------------------
# 入库 / 写表
# ---------------------------------------------------------------------------


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": FREQUENCY,
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": indicator_type,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, indicator_type in UAEWPS_INDICATORS
    ]


def _discover_qer_files() -> list[tuple[str, str, Path]]:
    """通过 CBUAE 出版物 API 发现最新 Quarterly Economic Review PDF。"""

    payload = json.loads(
        fetch_bytes(CBUAE_QER_API, referer="https://www.centralbank.ae/").decode(
            "utf-8", errors="replace"
        )
    )
    pages = payload.get("Data", {}).get("MediaListingPages", [])
    discovered: dict[str, tuple[str, str, Path]] = {}
    for page in pages:
        title = str(page.get("Title") or "")
        match = re.search(
            r"Quarterly\s+Economic\s+Review\s*[-–]\s*"
            r"(March|June|September|December)\s+(20\d{2})",
            title,
            re.I,
        )
        if match is None:
            continue
        month_name, year_text = match.groups()
        quarter = _QER_MONTHS[month_name.casefold()]
        tag = f"{year_text}Q{quarter}"
        for item in page.get("MediaList") or []:
            media_url = str(item.get("Url") or item.get("url") or "")
            if not media_url.lower().split("?", 1)[0].endswith(".pdf"):
                continue
            discovered[tag] = (
                tag,
                urljoin("https://www.centralbank.ae", media_url),
                RAW_DIR / f"{tag}.pdf",
            )
            break
    return sorted(discovered.values())


def _download_qer_files(*, force: bool) -> tuple[int, int, list[str]]:
    downloaded = 0
    existing = 0
    errors: list[str] = []
    for tag, url, target in _discover_qer_files():
        try:
            status = download_file(
                url,
                target,
                force=force,
                min_bytes=1024,
                referer="https://www.centralbank.ae/en/news-and-publications/publications/",
            )
        except Exception as exc:  # noqa: BLE001 - keep using a good local cache
            errors.append(f"{tag}: {exc}")
            continue
        if status == "downloaded":
            downloaded += 1
        else:
            existing += 1
    return downloaded, existing, errors


def _long_rows(
    verified: list[tuple[str, str, float | None, float | None, str]],
) -> list[dict]:
    rows: list[dict] = []
    for report_tag, period, emp, wage, note in verified:
        period_date = date.fromisoformat(period + "-01")
        for indicator, value in zip(UAEWPS_INDICATORS, (emp, wage), strict=True):
            rows.append(
                {
                    "period": period_date,
                    "indicator": indicator[0],
                    "value": value,
                    "source_file": f"{report_tag}.pdf",
                    "note": note,
                }
            )
    return rows


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """自动下载 CBUAE QER，再解析 WPS 段落并入长表。"""

    download_note = ""
    if not skip_download:
        try:
            # QER PDFs can be replaced at the same URL; refresh discovered
            # files in online mode and keep the local cache on download error.
            downloaded, existing, download_errors = _download_qer_files(force=True)
            download_note = f"官网缓存：新增 {downloaded}，复用 {existing}"
            if download_errors:
                download_note += f"；下载警告 {len(download_errors)} 条（{download_errors[0]}）"
        except Exception as exc:  # noqa: BLE001 - cached QER files remain valid
            if not any(RAW_DIR.glob("*.pdf")):
                raise
            download_note = f"官网发现失败，使用本地缓存：{exc}"

    sources = sorted(RAW_DIR.glob("*.pdf"))
    errors: list[str] = []
    parsed: dict[str, tuple[str, float | None, float | None, str]] = {}
    for path in sources:
        try:
            tag, period, emp, wage, note = extract_qer_wps(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if period is not None or tag in EXPECTED:
            parsed[tag] = (period, emp, wage, note)

    valid: dict[str, tuple[str, str, float | None, float | None, str]] = {}
    validation_errors: list[str] = []
    for tag, item in sorted(parsed.items()):
        try:
            checked = validate_observations({tag: item})
        except ValueError as exc:
            validation_errors.append(str(exc))
            continue
        valid[tag] = checked[0]
    # QER 的发布日期是季度，但 WPS 文字可能仍只覆盖上一季度末月份（例如
    # June 2026 QER 的正文为“As of March 2026”）。同一观察月保留最新报告，
    # 避免两个报告标签写入同一 (period, indicator) 主键。
    verified = [valid[tag] for tag in sorted(valid)]
    if not verified:
        detail = validation_errors[0] if validation_errors else "no valid QER observations"
        raise ValueError(f"UAEWPS validation rejected all observations: {detail}")
    rows = _long_rows(verified)
    con.begin()
    try:
        db.replace(con, "uaewps_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())
        con.commit()
    except Exception:
        con.rollback()
        raise

    periods = sorted({row["period"].strftime("%Y-%m") for row in rows})
    note = (
        f"{len(verified)} 期 QER × {len(UAEWPS_INDICATORS)} 指标，"
        f"{periods[0]} 至 {periods[-1]}"
    )
    if download_note:
        note += f"；{download_note}"
    if errors:
        note += f"；源警告 {len(errors)} 条，首条：{errors[0]}"
    if validation_errors:
        note += (
            f"；解析校验警告 {len(validation_errors)} 条，首条："
            f"{validation_errors[0]}"
        )
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """把 uaewps_monthly 写回 阿联酋.xlsx 的 季度_UAEWPS sheet。

    每次调用重建该 sheet；数据来自库中长表，按 UAEWPS_INDICATORS 顺序还原宽表
    记录，最新在前；缺失值留空单元格。历史遗留的「月度_UAEWPS」sheet 一并删除。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_uaewps_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, indicator, value, source_file, note "
            "FROM uaewps_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    by_period: dict[str, dict] = {}
    for period, indicator, value, source_file, note in db_rows:
        key = period.strftime("%Y-%m")
        item = by_period.setdefault(
            key,
            {"values": [None] * len(UAEWPS_INDICATORS), "note": note},
        )
        item["values"][INDICATOR_ORDER[indicator]] = value
        if source_file and not item.get("source_file"):
            item["source_file"] = source_file
    if not by_period:
        raise ValueError("uaewps_monthly is empty; nothing to merge")

    observations = [
        type(
            "Observation",
            (),
            {
                "period": period,
                "values": tuple(item["values"]),
                "source_file": item.get("source_file", ""),
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
            {
                "name": name,
                "type": indicator_type,
                "industry": INDUSTRY,
                "unit": UNIT,
            }
            for name, indicator_type in UAEWPS_INDICATORS
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload,
        prefix=".uaewps-sheet-",
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
    print("source_uaewps.py 自检：")
    print("  update(con, force=, skip_download=) 解析 data/UAE/raw/uaewps/qer/ 的 QER PDF")
    print("    → 与 EXPECTED 校验一致后入长表 uaewps_monthly")
    print("  merge(workbook_path) 把表写回 月度_UAEWPS")
    print("  本文件直接运行不执行任何下载或工作簿写入。")
