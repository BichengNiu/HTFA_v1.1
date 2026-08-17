"""Google 趋势工作搜索热度数据源：解析 → 入库 → 导出宽表 CSV。

无旧脚本（原数据直接人工维护在 data/UAE/工作搜索热度.csv）。本模块改为：
- 原始 CSV 统一收在 data/UAE/raw/employment/ 下；
- update() 解析成 long 行入 DuckDB（employment_search_index）；
- merge() 从库导出宽表 CSV 到 data/UAE/工作搜索热度.csv（dashboard 输入）。

口径：月份取 CSV Time 列日期原值（不改月末/月初，保持原样）；
keyword ∈ {"work in dubai", "work in uae"}（"visa uae" 列不进入管线）。
"""

from __future__ import annotations

import csv
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from db import (  # noqa: E402
    connect,
    replace,
)

RAW_EMPLOYMENT = DATA_DIR / "raw" / "employment"
EXPORT_PATH = DATA_DIR / "工作搜索热度.csv"

# dashboard/analysis/uae/government_finance/search_index.py 期望的列
KEYWORDS = ("work in dubai", "work in uae")
EXPECTED_COLUMNS = ("Time", "work in dubai", "work in uae")

SEARCH_TABLE = "employment_search_index"


@contextmanager
def _transaction(con):
    """显式事务上下文（BEGIN/COMMIT/ROLLBACK）。

    注意：duckdb 1.5.5 的 con.begin() 上下文管理器在退出时会关闭连接，
    与 update_data.py 在同一连接上继续 log_run 的约定冲突，因此自行管理事务。
    """

    con.execute("BEGIN TRANSACTION")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def _latest_source_file() -> Path:
    """取 data/UAE/raw/employment/ 下最新的 CSV（按文件名排序取末位）。"""

    files = sorted(RAW_EMPLOYMENT.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"data/UAE/raw/employment/ 下没有 CSV 输入文件: {RAW_EMPLOYMENT}")
    return files[-1]


def parse_csv(path: Path) -> list[dict[str, object]]:
    """解析输入 CSV 为 long 行（month, keyword, value）。

    列名与预期不符直接抛错（不静默）；空值单元格跳过（保留缺失语义）。
    """

    rows: list[dict[str, object]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        missing = [column for column in EXPECTED_COLUMNS if column not in fieldnames]
        if missing:
            raise ValueError(
                f"工作搜索热度列名不符：缺少 {missing}；实际列 {fieldnames}"
            )
        for line_number, raw in enumerate(reader, start=2):
            time_value = str(raw.get("Time") or "").strip()
            try:
                month = datetime.strptime(time_value, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError(
                    f"第 {line_number} 行 Time 无法按 YYYY-MM-DD 解析: {time_value!r}"
                ) from exc
            for keyword in KEYWORDS:
                cell = str(raw.get(keyword) or "").strip()
                if cell == "":
                    continue
                try:
                    value = float(cell)
                except ValueError as exc:
                    raise ValueError(
                        f"第 {line_number} 行 {keyword} 非数值: {cell!r}"
                    ) from exc
                rows.append({"month": month, "keyword": keyword, "value": value})
    return rows


def export_wide(rows: list[dict[str, object]], target: Path) -> int:
    """从 long 行导出宽表 CSV（Time, 'work in dubai', 'work in uae'）。

    月份升序；整数值不带小数位（与原始 CSV 观感一致）。
    """

    by_month: dict[str, dict[str, object]] = {}
    for row in rows:
        key = row["month"].strftime("%Y-%m-%d") if hasattr(row["month"], "strftime") else str(row["month"])
        by_month.setdefault(key, {})[row["keyword"]] = row["value"]

    def fmt(value: object) -> str:
        if value is None:
            return ""
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)

    with open(target, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["Time", *KEYWORDS])
        for key in sorted(by_month):
            writer.writerow([key, fmt(by_month[key].get("work in dubai")), fmt(by_month[key].get("work in uae"))])
    return len(by_month)


def update(
    con, *, force: bool = False, skip_download: bool = False
) -> dict[str, object]:
    """扫描 data/UAE/raw/employment/ 最新 CSV → 解析 → 事务内入库。"""

    source_path = _latest_source_file()
    rows = parse_csv(source_path)
    with _transaction(con):
        replace(con, SEARCH_TABLE, rows)
    return {
        "status": "ok",
        "rows": len(rows),
        "note": f"{source_path.name}：{len(rows)} 个 (月, 关键词) 观测已入库",
    }


def merge(workbook_path: Path) -> dict[str, object]:
    """从库导出宽表 CSV 到 data/UAE/工作搜索热度.csv（dashboard 的输入文件）。

    本模块无目标 sheet；workbook_path 参数保留以符合 merge 统一签名，实际不使用。
    """

    con = connect(read_only=True)
    try:
        rows = [
            {"month": month, "keyword": keyword, "value": value}
            for month, keyword, value in con.execute(
                f"SELECT month, keyword, value FROM {SEARCH_TABLE} ORDER BY month"
            ).fetchall()
        ]
    finally:
        con.close()
    month_count = export_wide(rows, EXPORT_PATH)
    return {
        "status": "ok",
        "note": f"已导出 {EXPORT_PATH.name}：{month_count} 个月 × {len(KEYWORDS)} 个关键词",
    }


if __name__ == "__main__":
    # 自检提示（不执行网络/工作簿写入）
    _src = _latest_source_file()
    _rows = parse_csv(_src)
    print(
        f"[source_employment] 自检：{_src.name} 解析出 {len(_rows)} 个观测，"
        f"月份范围 {_rows[0]['month']} ~ {_rows[-1]['month']}。"
    )
    print("[source_employment] 运行 data\\update_data.py --source employment 入库；"
          "data\\merge_workbook.py --source employment 导出 CSV。")