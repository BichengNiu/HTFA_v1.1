"""US DOT T-100：US↔UAE 月度航空客、货运数据入库。

数据源（美国运输统计局 BTS，官方指定）：
T-100 International Segment (All Carriers) —— 每月更新、滞后约 3-6 个月，
1990 年起。本模块解析 ``data/UAE/raw/t100/csv/uae_<year>.zip``（由
``download_uae_years.mjs`` 从 transtats.bts.gov 按年下载、按伙伴国 UAE 过滤，
43 字段全量导出），保留 US↔UAE 双向航段并月度聚合成指标入
``dot_t100_monthly``。

口径说明（BTS TableInfo）：
- PASSENGERS = Non-Stop Segment Passengers Transported（航段经停旅客数，
  非唯一旅客口径）；
- FREIGHT / MAIL = Non-Stop Segment Freight/Mail Transported (pounds)。
- 每条记录是「承运商×机场对×机型×舱等」级，月度汇总为全承运商合计。

指标（月度）：
- 美国↔阿联酋_航空旅客_合计/美→阿/阿→美(人次)
- 美国↔阿联酋_航空货运_合计/美→阿/阿→美(磅)
- 美国↔阿联酋_航空邮件_合计/美→阿/阿→美(磅)
- 美国↔阿联酋_执行航班_合计(班次)
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import sys
import subprocess
import zipfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator, TextIO

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CSV_DIR = DATA_DIR / "raw" / "t100" / "csv"
RAW_DIR = DATA_DIR / "raw" / "t100"

TARGET_SHEET = "月度_DOTT100"  # 预留（写表暂未实现）

FIELDS_REQUIRED = (
    "YEAR", "QUARTER", "MONTH",
    "DEPARTURES_PERFORMED", "PAYLOAD", "SEATS", "PASSENGERS", "FREIGHT", "MAIL",
    "ORIGIN", "DEST", "ORIGIN_COUNTRY", "DEST_COUNTRY",
)

INDICATOR_TPL = {
    # (方向, 度量) -> 指标中文名
    ("all", "passengers"): "美国↔阿联酋_航空旅客_合计(人次)",
    ("us2ae", "passengers"): "美国↔阿联酋_航空旅客_美→阿(人次)",
    ("ae2us", "passengers"): "美国↔阿联酋_航空旅客_阿→美(人次)",
    ("all", "freight"): "美国↔阿联酋_航空货运_合计(磅)",
    ("us2ae", "freight"): "美国↔阿联酋_航空货运_美→阿(磅)",
    ("ae2us", "freight"): "美国↔阿联酋_航空货运_阿→美(磅)",
    ("all", "mail"): "美国↔阿联酋_航空邮件_合计(磅)",
    ("us2ae", "mail"): "美国↔阿联酋_航空邮件_美→阿(磅)",
    ("ae2us", "mail"): "美国↔阿联酋_航空邮件_阿→美(磅)",
    ("all", "departures"): "美国↔阿联酋_执行航班_合计(班次)",
}

MIN_YEAR, MAX_YEAR = 1990, date.today().year
T100_DOWNLOAD_SCRIPT = RAW_DIR / "download_uae_years.mjs"


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _open_csv_from_zip(zip_path: Path) -> TextIO | None:
    """从年包 zip 中读取第一个 CSV 文件；无 CSV 返回 None。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".csv", ".txt", ".asc"))]
        if not names:
            return None
        raw = zf.read(names[0]).decode("utf-8-sig", errors="replace")
        return io.StringIO(raw)


def _f(value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def collect_rows(zip_paths: list[Path], *, today: date | None = None) -> list[dict[str, Any]]:
    """遍历年包，过滤 US↔UAE 双向航段，按月份聚合为 10 个指标。

    返回 (period, indicator, value, source_file) 行列表。
    """
    as_of = today or date.today()
    agg: dict[tuple[date, str], dict[str, float]] = {}
    sources: dict[tuple[date, str], str] = {}
    seen_files: set[Path] = set()

    for zip_path in sorted(zip_paths):
        handle = _open_csv_from_zip(zip_path)
        if handle is None:
            continue
        seen_files.add(zip_path)
        with handle:
            reader = csv.DictReader(handle)
            missing = [f for f in FIELDS_REQUIRED if f not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{zip_path.name}: 缺少字段 {missing}")
            for row in reader:
                o_country = (row.get("ORIGIN_COUNTRY") or "").strip().upper()
                d_country = (row.get("DEST_COUNTRY") or "").strip().upper()
                if not ({o_country, d_country} == {"US", "AE"}):
                    continue
                try:
                    year = int(row["YEAR"]); month = int(row["MONTH"])
                except (TypeError, ValueError):
                    continue
                if not (1 <= month <= 12):
                    continue
                period = date(year, month, 1)
                direction = "us2ae" if (o_country == "US" and d_country == "AE") else "ae2us"
                passengers = _f(row.get("PASSENGERS"))
                freight = _f(row.get("FREIGHT"))
                mail = _f(row.get("MAIL"))
                deps = _f(row.get("DEPARTURES_PERFORMED"))
                for key, value in (
                    ((direction, "passengers"), passengers),
                    ((direction, "freight"), freight),
                    ((direction, "mail"), mail),
                    ((direction, "departures"), deps),
                ):
                    bucket = agg.setdefault((period, key), {})
                    bucket[key[1]] = bucket.get(key[1], 0.0) + value
                    sources[(period, key)] = zip_path.name

    rows: list[dict[str, Any]] = []
    for (period, (direction, measure)), totals in agg.items():
        value = totals.get(measure, 0.0)
        indicator = INDICATOR_TPL.get((direction, measure))
        if indicator is None:
            continue
        rows.append(
            {
                "period": period,
                "indicator": indicator,
                "value": round(value, 1),
                "source_file": sources.get((period, (direction, measure))),
            }
        )
    # 补"合计"指标 = 双向之和（在方向维已聚合好后加总）
    all_buckets: dict[tuple[date, str], dict[str, float]] = {}
    for (period, (direction, measure)), totals in agg.items():
        for bucket_measure, val in totals.items():
            if bucket_measure == measure:
                key = (period, ("all", measure))
                bucket = all_buckets.setdefault(key, {})
                bucket[measure] = bucket.get(measure, 0.0) + val
    for (period, (_dir, measure)), totals in all_buckets.items():
        indicator = INDICATOR_TPL.get(("all", measure))
        if indicator is None:
            continue
        rows.append(
            {
                "period": period,
                "indicator": indicator,
                "value": round(totals.get(measure, 0.0), 1),
                "source_file": ";".join(sorted({s for (p2, _k), s in sources.items() if p2 == period})),
            }
        )

    if not rows:
        raise ValueError("dot_t100_monthly: 未解析到任何 US↔UAE 观测（检查 raw/t100/csv/uae_*.zip）")
    return rows


def build_quality_report(
    rows: list[dict[str, Any]],
    *,
    today: date | None = None,
    nodata_years: set[int] | None = None,
) -> dict[str, Any]:
    """生成覆盖/连续性/区间检查报告（JSON，写 raw/t100/quality_report.json）。

    `
odata_years``：transtats 表单在该年份返回空（美阿航线尚未开航等），
    视为合法缺失，不触发 1990s 历史检查失败。
    """
    as_of = today or date.today()
    nodata_years = nodata_years or set()
    periods = sorted({r["period"] for r in rows})
    indicators = sorted({r["indicator"] for r in rows})
    continuous = True
    missing: list[str] = []
    sparse_before = None
    if periods:
        current = periods[0]
        while current <= periods[-1]:
            if current not in set(periods):
                # 2005 年起（官方全量年包覆盖期起）要求逐月连续；
                # 更早的美阿航线属稀疏历史（零星包机、9·11 后停航、反恐停摆等），允许缺月
                if current.year >= 2005:
                    missing.append(current.strftime("%Y-%m"))
                    continuous = False
                elif sparse_before is None:
                    sparse_before = periods[0].strftime("%Y-%m")
            y = current.year + (1 if current.month == 12 else 0)
            m = 1 if current.month == 12 else current.month + 1
            current = date(y, m, 1)
    earliest_year = periods[0].year if periods else None
    # 1990s 历史缺口：早于最早观测年的年份要么无数据标记，要么是 1989 之前
    gap_years_before = (
        set(range(1990, earliest_year)) - nodata_years if earliest_year else set()
    )
    checks = [
        {
            "name": "has_1990s_history",
            "passed": (
                not gap_years_before
                and bool(periods)
                and earliest_year < 2000
            ) if periods else False,
            "detail": (
                f"最早 {periods[0].strftime('%Y-%m') if periods else '-'}；"
                f"1990s 缺口年（无数据标记覆盖的除外）: "
                f"{sorted(gap_years_before) if gap_years_before else '无'}"
            ),
        },
        {
            "name": "monthly_continuity",
            "passed": continuous,
            "detail": (
                "2005 起逐月连续"
                if continuous
                else "2005 起缺口: " + ", ".join(missing)
            ) + (f"（2005 前稀疏段自 {sparse_before} 起" if sparse_before else ""),
        },
        {
            "name": "latest_within_6_months",
            "passed": bool(periods) and ((as_of.year - periods[-1].year) * 12 + as_of.month - periods[-1].month) <= 6,
            "detail": f"最新 {periods[-1].strftime('%Y-%m') if periods else '-'}（BTS 滞后约 3-6 个月）",
        },
        {
            "name": "no_negative_values",
            "passed": all(r["value"] >= 0 for r in rows),
            "detail": f"{len(rows)} 指标观测均非负",
        },
    ]
    return {
        "generated_at": date.today().isoformat(),
        "status": "passed" if all(c["passed"] for c in checks) else "failed",
        "coverage": {
            "start_period": periods[0].strftime("%Y-%m") if periods else None,
            "end_period": periods[-1].strftime("%Y-%m") if periods else None,
            "month_count": len(periods),
            "missing_periods": missing,
            "indicator_count": len(indicators),
            "source_files": sorted({r["source_file"] or "" for r in rows}),
            "nodata_years": sorted(nodata_years),
        },
        "latest": {
            "period": periods[-1].strftime("%Y-%m") if periods else None,
            "passengers_all": next((r["value"] for r in rows
                                    if r["indicator"] == INDICATOR_TPL[("all", "passengers")]
                                    and r["period"] == periods[-1]), None),
        },
        "checks": checks,
        "note": "PASSENGERS 为航段经停旅客数（非唯一旅客）；FREIGHT/MAIL 单位为磅。",
    }


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


def _dictionary_rows() -> list[dict[str, Any]]:
    rows = []
    for indicator in INDICATOR_TPL.values():
        rows.append(
            {
                "indicator_name": indicator,
                "frequency": "月",
                "unit": "磅" if "磅" in indicator else ("人次" if "人次" in indicator else "班次"),
                "source": "US DOT BTS T-100 International Segment (All Carriers)",
                "type": "交通",
                "industry": "交通运输",
                "updated_at": date.today(),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def _download_recent_years(*, force: bool) -> str:
    """Run the official TranStats browser downloader for recent years.

    BTS requires a JavaScript/browser session for the filtered table.  The
    repository already contains that official-form downloader; this adapter
    gives it a repository-relative output path and retries the current years.
    Playwright is installed under raw/t100 on first online run, which is an
    ignored cache and never part of the data commit.
    """

    if not T100_DOWNLOAD_SCRIPT.is_file():
        raise FileNotFoundError(f"T-100 下载脚本缺失: {T100_DOWNLOAD_SCRIPT}")
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        raise RuntimeError("未找到 Node.js，无法运行 BTS T-100 浏览器下载器")

    probe = subprocess.run(
        [node, "-e", "import('playwright')"],
        cwd=RAW_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if npm is None:
            raise RuntimeError("未找到 npm，无法自动安装 T-100 下载器依赖")
        install = subprocess.run(
            [npm, "install", "--no-save", "--prefix", str(RAW_DIR), "playwright@1.55.0"],
            cwd=RAW_DIR,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if install.returncode != 0:
            detail = (install.stderr or install.stdout or "").strip()[-800:]
            raise RuntimeError(f"Playwright 自动安装失败: {detail}")

    current_year = date.today().year
    start_year = max(MIN_YEAR, current_year - 2)
    years = ",".join(str(year) for year in range(start_year, current_year + 1))
    env = os.environ.copy()
    env.update(
        {
            "T100_OUTPUT": str(CSV_DIR),
            "T100_YEARS": years,
            "T100_RETRY_NODATA": "1",
            "T100_MARK_NODATA": "0",
            "T100_FORCE": "1" if force else "0",
        }
    )
    result = subprocess.run(
        [node, str(T100_DOWNLOAD_SCRIPT)],
        cwd=RAW_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if result.returncode != 0:
        detail = output[-1200:] if output else "无输出"
        raise RuntimeError(f"T-100 下载器失败: {detail}")
    return output[-1200:] if output else "已运行 BTS T-100 下载器"


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """自动抓取近期 BTS T-100 年包，再质检并入库 ``dot_t100_monthly``。"""
    import json as _json

    download_note = ""
    if not skip_download:
        try:
            # TranStats keeps the same yearly ZIP name while revising recent
            # months. The online path always refreshes the recent-year window.
            download_note = _download_recent_years(force=True)
        except Exception as exc:  # noqa: BLE001 - a valid local cache remains usable
            if not any(CSV_DIR.glob("uae_*.zip")):
                raise
            download_note = f"官网下载未完成，使用本地缓存：{exc}"

    zips = sorted(CSV_DIR.glob("uae_*.zip"))
    if not zips:
        raise FileNotFoundError(
            f"未找到 {CSV_DIR}/uae_*.zip；请先运行 "
            f"data/UAE/raw/t100/download_uae_years.mjs 下载 UAE 过滤年包"
        )
    nodata_years = {
        int(path.name.split("_")[1].split(".")[0])
        for path in CSV_DIR.glob("uae_*.nodata")
        if path.name.split("_")[1][:4].isdigit()
    }
    rows = collect_rows(zips)
    report = build_quality_report(rows, nodata_years=nodata_years)
    (RAW_DIR / "quality_report.json").write_text(
        _json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if report["status"] != "passed":
        failed = [c["name"] for c in report["checks"] if not c["passed"]]
        raise ValueError("US↔UAE T-100 quality checks failed: " + ", ".join(failed))

    with _transaction(con):
        db.replace(con, "dot_t100_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    start = report["coverage"]["start_period"]
    end = report["coverage"]["end_period"]
    note = (
        f"{len(rows)} 条指标观测（{start} 至 {end}，"
        f"{report['coverage']['month_count']} 个月 × {report['coverage']['indicator_count']} 指标）"
    )
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """由 ``source_extended.merge`` 统一写入「月度_DOTT100」。"""
    return {
        "status": "skipped",
        "note": (
            "T-100 已入 DuckDB；Excel 由 source_extended.merge 统一写入"
        ),
    }


if __name__ == "__main__":
    print("source_dot_t100.py 自检：")
    print("  update(con, force=, skip_download=) 解析 raw/t100/csv/uae_*.zip → 入库 dot_t100_monthly")
    print("  merge(workbook_path) 由 source_extended.merge 统一写入 月度_DOTT100")
