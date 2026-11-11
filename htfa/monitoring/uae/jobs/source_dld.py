"""Dubai Land Department sales and report project counts.

Online runs refresh the official Data Dubai snapshot before rebuilding the
current detail table. Offline reconstruction is available only when the
caller explicitly sets skip_download=True and the current raw CSV exists."""

from __future__ import annotations

import csv
import gzip
import hashlib
import http.cookiejar
import io
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from htfa.monitoring.uae.processing.temporal import last_complete_month_end

from .paths import DATA_DIR
from .workbook_sheet_writer import write_indicator_sheets
from ._official_download import write_json_atomic


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量：计算窗口与发布起点
# ---------------------------------------------------------------------------

PUBLICATION_START = date(2015, 1, 5)

# Raw Data Dubai CSV directory
RAW_DLD_DIR = DATA_DIR / "raw" / "dld"

# detail.dld_transactions 仅保留被周度/月度指标与三个视图消费的列（47 → 9）。
# 「保留 = 被查询」：transaction_id(计数/主键)、instance_date(周/月分组)、
# trans_group_en/reg_type_en(Sales/Off-Plan 过滤)、project_number(项目维度)、
# actual_worth(金额)、property_type_en(Land 视图/年汇总)、
# property_usage_en(月度销售指标分市场 Residential/Commercial)、
# load_timestamp(bulk 快照时间，每行同值，字典压缩近零成本，仅用于追溯)。
KEEP_COLUMNS = (
    "actual_worth",
    "instance_date",
    "load_timestamp",
    "project_number",
    "property_type_en",
    "property_usage_en",
    "reg_type_en",
    "trans_group_en",
    "transaction_id",
)

# 工作簿写表（merge() 使用）
WORKSHEET_NAME = "周度_迪拜房地产"

# ---------------------------------------------------------------------------
# 周度原始口径 SQL：查询 detail.dld_transactions 统一长表。
# ---------------------------------------------------------------------------

RAW_WEEKLY_SQL = r"""
WITH bounds AS (
    SELECT DATE '2009-01-05' AS first_week,
           CASE WHEN max(instance_date) >= CAST(date_trunc('week', max(instance_date)) AS DATE) + 6
                THEN CAST(date_trunc('week', max(instance_date)) AS DATE)
                ELSE CAST(date_trunc('week', max(instance_date)) AS DATE) - 7 END AS last_complete_week,
           CASE WHEN max(instance_date) >= CAST(date_trunc('month', max(instance_date))
                                               + INTERVAL 1 MONTH - INTERVAL 1 DAY AS DATE)
                THEN CAST(date_trunc('month', max(instance_date)) + INTERVAL 1 MONTH - INTERVAL 1 DAY AS DATE)
                ELSE CAST(date_trunc('month', max(instance_date)) AS DATE) - 1 END AS last_complete_month_end,
           max(instance_date) AS source_data_through
    FROM detail.dld_transactions
), calendar AS (
    SELECT CAST(gs AS DATE) AS week_start, CAST(gs AS DATE) + 6 AS week_end,
           bounds.source_data_through
    FROM bounds, generate_series(bounds.first_week, bounds.last_complete_week, INTERVAL 7 DAY) AS t(gs)
    WHERE CAST(gs AS DATE) + 6 <= bounds.last_complete_month_end
), offplan_sales AS (
    SELECT instance_date, project_number,
           CAST(date_trunc('week', instance_date) AS DATE) AS week_start
    FROM detail.dld_transactions CROSS JOIN bounds
    WHERE trans_group_en = 'Sales' AND reg_type_en = 'Off-Plan Properties'
      AND instance_date >= DATE '2009-01-05' - INTERVAL 27 DAY
      AND instance_date <= bounds.last_complete_month_end
), project_week AS (
    SELECT week_start, project_number, count(*) AS sales
    FROM offplan_sales WHERE project_number IS NOT NULL GROUP BY week_start, project_number
), project_week_grid AS (
    SELECT c.week_start, p.project_number, coalesce(w.sales, 0) AS sales
    FROM calendar c CROSS JOIN (SELECT DISTINCT project_number FROM offplan_sales
                               WHERE project_number IS NOT NULL) p
    LEFT JOIN project_week w USING (week_start, project_number)
), project_trailing AS (
    SELECT week_start, project_number,
           sum(sales) OVER (PARTITION BY project_number ORDER BY week_start
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS sales_28d
    FROM project_week_grid
), active_project_week AS (
    SELECT week_start, count(*) FILTER (WHERE sales_28d >= 3) AS active_projects_28d
    FROM project_trailing GROUP BY week_start
), project_launch AS (
    SELECT project_number, min(instance_date) AS first_offplan_sale_date
    FROM detail.dld_transactions CROSS JOIN bounds
    WHERE trans_group_en = 'Sales' AND reg_type_en = 'Off-Plan Properties'
      AND project_number IS NOT NULL AND instance_date <= bounds.last_complete_month_end
    GROUP BY project_number
), project_launch_confirmed AS (
    SELECT p.project_number, p.first_offplan_sale_date, count(t.transaction_id) AS sales_first_28d
    FROM project_launch p CROSS JOIN bounds
    LEFT JOIN detail.dld_transactions t ON t.project_number = p.project_number
      AND t.trans_group_en = 'Sales' AND t.reg_type_en = 'Off-Plan Properties'
      AND t.instance_date BETWEEN p.first_offplan_sale_date AND p.first_offplan_sale_date + 27
      AND t.instance_date <= bounds.last_complete_month_end
    GROUP BY p.project_number, p.first_offplan_sale_date
), confirmed_launch_week AS (
    -- Publish only at the end of the original 28-day confirmation window.
    SELECT CAST(date_trunc('week', first_offplan_sale_date + 27) AS DATE) AS week_start,
           count(*) AS confirmed_new_projects
    FROM project_launch_confirmed WHERE sales_first_28d >= 10 GROUP BY week_start
), weekly AS (
    SELECT c.*, coalesce(cl.confirmed_new_projects, 0) AS confirmed_new_projects,
           coalesce(a.active_projects_28d, 0) AS active_projects_28d
    FROM calendar c LEFT JOIN confirmed_launch_week cl USING (week_start)
    LEFT JOIN active_project_week a USING (week_start)
)
SELECT week_start, week_end, source_data_through,
       sum(confirmed_new_projects) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
           AS confirmed_new_projects_28d,
       active_projects_28d
FROM weekly ORDER BY week_start
"""

# ---------------------------------------------------------------------------
# 列字典：detail.dld_transactions 仅保留 KEEP_COLUMNS 九列（含义沿用旧
# build_dld_database.sql 的 metadata.column_dictionary；land_registry 已不再建表,
# 其字典行一并移除）。
# ---------------------------------------------------------------------------

COLUMN_DICTIONARY = (
    ('detail.dld_transactions', 'actual_worth', 'DECIMAL(24,2)', '金额面积', '交易金额或实际价值', None, '通常按AED理解；源文件未单列单位'),
    ('detail.dld_transactions', 'instance_date', 'DATE', '时间', '交易登记日期', 'dld.transaction_year_summary.transaction_year', '官方源含4条1900年以前异常日期'),
    ('detail.dld_transactions', 'load_timestamp', 'TIMESTAMPTZ', '时间', 'Data Dubai生成bulk快照的时间', None, '不是交易发生时间'),
    ('detail.dld_transactions', 'project_number', 'VARCHAR', '项目建筑', '交易数据中的项目编号', None, 'RAW_WEEKLY_SQL 按项目编号聚合期房窗口'),
    ('detail.dld_transactions', 'property_type_en', 'VARCHAR', '房产分类', '房产大类英文名', 'dld.land_transactions', 'Land决定是否进入land_transactions视图'),
    ('detail.dld_transactions', 'property_usage_en', 'VARCHAR', '用途分类', '住宅/商业/酒店/其他等用途英文名', 'dld_sales_monthly', '月度销售指标按 Residential/Commercial 分市场；含阿语“أخرى”等脏值需归一化'),
    ('detail.dld_transactions', 'reg_type_en', 'VARCHAR', '登记类型', 'Existing或Off-Plan英文名', None, '现房/期房过滤键（RAW_WEEKLY_SQL）'),
    ('detail.dld_transactions', 'trans_group_en', 'VARCHAR', '交易分类', 'Sales/Mortgages/Gifts', None, '交易大类过滤键（RAW_WEEKLY_SQL）'),
    ('detail.dld_transactions', 'transaction_id', 'VARCHAR', '主键', '交易记录唯一编号', 'dld.land_transactions.transaction_id', '本表唯一主键'),
)

# ---------------------------------------------------------------------------
# 报告使用的两个周度项目计数。
# type/industry 对应工作簿「指标字典」中的当前指标分类。
# ---------------------------------------------------------------------------

INDICATOR_DICTIONARY = (
    ("经确认新期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
    ("活跃期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
)

# ---------------------------------------------------------------------------
# 月度销售：住宅/商业 × 期房/现房，各保留笔数和金额。
# ---------------------------------------------------------------------------

MONTHLY_WORKSHEET_NAME = "月度_DLD"

# 月度销售指标：SQL 聚合键 (property_usage_en, reg_type_en) -> indicator 名。
# indicator 名与用户口径一一对应（Off-Plan=期房，Existing=现房/二手房）。
SALES_INDICATOR_KEYS = {
    ("Residential", "Off-Plan Properties"): "residential_offplan_sales",
    ("Residential", "Existing Properties"): "residential_ready_sales",
    ("Commercial", "Off-Plan Properties"): "commercial_offplan_sales",
    ("Commercial", "Existing Properties"): "commercial_ready_sales",
}

# 月度_DLD sheet 数据列（与 MERGE 写表一一对应；A 列为日期）。
MONTHLY_SHEET_HEADERS = (
    "日期", "迪拜:期房销售-住宅笔数", "迪拜:期房销售-住宅金额(百万AED)",
    "迪拜:现房销售-住宅笔数", "迪拜:现房销售-住宅金额(百万AED)",
    "迪拜:期房销售-商业笔数", "迪拜:期房销售-商业金额(百万AED)",
    "迪拜:现房销售-商业笔数", "迪拜:现房销售-商业金额(百万AED)",
)

# 指标字典补录（与 MONTHLY_SHEET_HEADERS[1:] 一一对应）。
MONTHLY_INDICATOR_DICTIONARY = (
    ("迪拜:期房销售-住宅笔数", "月", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("迪拜:期房销售-住宅金额(百万AED)", "月", "百万AED", "Dubai Land Department", "交易金额", "房地产"),
    ("迪拜:现房销售-住宅笔数", "月", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("迪拜:现房销售-住宅金额(百万AED)", "月", "百万AED", "Dubai Land Department", "交易金额", "房地产"),
    ("迪拜:期房销售-商业笔数", "月", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("迪拜:期房销售-商业金额(百万AED)", "月", "百万AED", "Dubai Land Department", "交易金额", "房地产"),
    ("迪拜:现房销售-商业笔数", "月", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("迪拜:现房销售-商业金额(百万AED)", "月", "百万AED", "Dubai Land Department", "交易金额", "房地产"),
)

# 下载器 URL 常量（与 download_dld_all.py 一致）
DLD_OPEN_DATA_PAGE = "https://dubailand.gov.ae/en/open-data/real-estate-data/"
DATA_DUBAI_BASE = "https://data.dubai"
DATA_DUBAI_ENTITY_ID = "62035"
TRANSACTIONS_DATASET_ID = "470061"
TRANSACTIONS_DATASET_PAGE = (
    f"{DATA_DUBAI_BASE}/en/l/{TRANSACTIONS_DATASET_ID}"
    f"?com_dda_data_and_statistics_ThemeId={DATA_DUBAI_ENTITY_ID}"
)

DOWNLOAD_API = f"{DATA_DUBAI_BASE}/o/dda/data-services/dataset-download"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
_CHUNK_SIZE = 1024 * 1024


# ---------------------------------------------------------------------------
# 计数值验证与规范化
# ---------------------------------------------------------------------------

def _numeric_value(value, *, column: str) -> float | None:
    """Validate a DuckDB numeric observation and normalize it for calculations."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError(
            f"DuckDB column {column!r} must contain a numeric value; "
            f"got {type(value).__name__}"
        )
    return float(value)


def _rounded_count(value):
    """计数列入库值：None 保持 None，否则四舍五入为整数。"""

    return None if value is None else int(round(value))


def to_weekly_table_rows(raw_rows):
    """Keep the two report counts from complete published weeks."""
    rows = []
    for row in raw_rows:
        if row["week_start"] < PUBLICATION_START:
            continue
        values = {"week_end": row["week_end"]}
        for column in ("confirmed_new_projects_28d", "active_projects_28d"):
            values[column] = _rounded_count(_numeric_value(row[column], column=column))
        rows.append(values)
    return rows


# ---------------------------------------------------------------------------
# Build current table, views, and dictionary
# ---------------------------------------------------------------------------

def _transactions_ddl(csv_path: Path) -> str:
    """transactions 建表 DDL：从 CSV 只保留 ``KEEP_COLUMNS`` 九列（TRY_CAST）。"""

    path = csv_path.resolve().as_posix()
    return rf"""
    CREATE TABLE detail.dld_transactions AS
    SELECT
        TRY_CAST(actual_worth AS DECIMAL(24, 2)) AS actual_worth,
        TRY_CAST(instance_date AS DATE) AS instance_date,
        TRY_CAST(load_timestamp AS TIMESTAMPTZ) AS load_timestamp,
        regexp_replace(project_number, '\.0+$', '') AS project_number,
        property_type_en,
        property_usage_en,
        reg_type_en,
        trans_group_en,
        transaction_id
    FROM read_csv(
        '{path}',
        header=true,
        all_varchar=true,
        nullstr='',
        strict_mode=true
    )
    """


def _assert_transaction_id_unique(con) -> None:
    """transaction_id 唯一性由数据源保证，入库后以断言兜底。

    故意不建持久化唯一索引：duckdb 的 ART 唯一索引会把事务表文件撑大约
    68MB（2026-08 瘦身），而任何查询都不需要它（RAW_WEEKLY_SQL 全表扫 /
    按项目分组，均不用主键查找）。唯一性校验移到建表阶段，零文件开销。
    """

    total, distinct = con.execute(
        "SELECT count(*), count(DISTINCT transaction_id) FROM detail.dld_transactions"
    ).fetchone()
    if total != distinct:
        raise RuntimeError(
            "detail.dld_transactions 主键不唯一："
            f"{total} 行 / {distinct} 个不同 transaction_id"
        )


def _build_base_from_csv(con) -> str:
    """Build the current detail table from the current Data Dubai CSV."""

    txn_csv = RAW_DLD_DIR / "DLD_Transactions_ALL.csv"
    if not txn_csv.exists():
        raise RuntimeError(f"缺少原始 CSV：{txn_csv.name}")
    if not db.table_exists(con, "detail.dld_transactions"):
        con.execute(_transactions_ddl(txn_csv))
        _assert_transaction_id_unique(con)
    return "从原始 CSV 全量建表"


def _create_dld_views(con) -> None:
    """每次 update 都重建的三个只读视图（显式列出保留列，规避 SELECT *）。"""

    kept = ", ".join(KEEP_COLUMNS)
    con.execute(
        "CREATE OR REPLACE VIEW dld.land_transactions AS "
        f"SELECT {kept} FROM detail.dld_transactions WHERE property_type_en = 'Land'"
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW dld.transaction_year_summary AS
        SELECT
            year(instance_date) AS transaction_year,
            trans_group_en,
            property_type_en,
            reg_type_en,
            count(*) AS transaction_count,
            sum(actual_worth) AS total_worth,
            median(actual_worth) AS median_worth
        FROM detail.dld_transactions
        GROUP BY ALL
        """
    )
    con.execute(
        "CREATE OR REPLACE VIEW dld.transaction_date_quality_issues AS "
        f"SELECT {kept} FROM detail.dld_transactions "
        "WHERE instance_date < DATE '1900-01-01' OR instance_date IS NULL"
    )


def _upsert_column_dictionary_row(con, row) -> None:
    """按 (object_name, column_name) 合并单行列字典。"""

    con.execute(
        "INSERT OR REPLACE INTO meta_column_dictionary "
        "(object_name, column_name, data_type, group_cn, meaning_cn, "
        " relates_to, caveat_cn) VALUES (?, ?, ?, ?, ?, ?, ?)",
        list(row),
    )


def _upsert_column_dictionary(con) -> None:
    """把内置的 DLD 列字典（79 行）合并进 meta_column_dictionary。"""

    for row in COLUMN_DICTIONARY:
        _upsert_column_dictionary_row(con, row)


def _upsert_indicator_dictionary(con) -> None:
    """把 6 个周度指标 + 13 个月度指标合并进 meta_indicator_dictionary。"""

    today = date.today()
    for row in INDICATOR_DICTIONARY + MONTHLY_INDICATOR_DICTIONARY:
        indicator_name, frequency, unit, source, type_, industry = row
        db.upsert_dictionary_rows(
            con,
            [
                {
                    "indicator_name": indicator_name,
                    "frequency": frequency,
                    "unit": unit,
                    "source": source,
                    "type": type_,
                    "industry": industry,
                    "updated_at": today,
                }
            ],
        )


def _fetch_raw_weekly(con) -> list[dict]:
    """执行 RAW_WEEKLY_SQL 并返回 dict 行列表。"""

    relation = con.execute(RAW_WEEKLY_SQL)
    columns = [column[0] for column in relation.description]
    return [dict(zip(columns, row)) for row in relation.fetchall()]


# ---------------------------------------------------------------------------
# 月度指标（2026-08 新增）
# a) 销售指标：detail.dld_transactions 按月聚合 Sales × 现房/期房 × 住宅/商业
# ---------------------------------------------------------------------------

def build_sales_monthly(con) -> list[dict]:
    """从 detail.dld_transactions 按月聚合 4 个销售指标（笔数 + 金额）。

    口径：trans_group_en='Sales'；用途只取 Residential / Commercial；
    登记类型只取 Off-Plan Properties（期房）与 Existing Properties（现房）。
    period 为月末日期（datum 约定），金额单位 AED 原值（写表时折算百万 AED）。
    """

    source_data_through = con.execute(
        "SELECT max(instance_date) FROM detail.dld_transactions"
    ).fetchone()[0]
    cutoff = last_complete_month_end(source_data_through)
    if cutoff is None:
        return []

    rows = con.execute(
        """
        SELECT
            (date_trunc('month', instance_date)
             + INTERVAL 1 MONTH - INTERVAL 1 DAY)::DATE AS period,
            property_usage_en,
            reg_type_en,
            count(*) AS cnt,
            sum(actual_worth) AS val
        FROM detail.dld_transactions
        WHERE trans_group_en = 'Sales'
          AND property_usage_en IN ('Residential', 'Commercial')
          AND reg_type_en IN ('Off-Plan Properties', 'Existing Properties')
          AND instance_date >= DATE '1975-01-01'
          AND instance_date <= ?
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """,
        [cutoff],
    ).fetchall()
    out = []
    for period, usage, reg, cnt, val in rows:
        key = SALES_INDICATOR_KEYS.get((usage, reg))
        if key is None:
            continue
        out.append(
            {
                "period": period,
                "indicator": key,
                "count": int(cnt),
                "value_aed": None if val is None else float(val),
            }
        )
    return out


def _ensure_base_tables(con, *, force: bool, skip_download: bool) -> str:
    """Require the current detail schema and refresh it from Data Dubai."""

    txn_csv = RAW_DLD_DIR / "DLD_Transactions_ALL.csv"
    txn_ready = db.table_exists(con, "detail.dld_transactions")
    csv_ready = txn_csv.is_file()
    downloaded = False
    refresh_note = ""

    if not skip_download:
        should_download = force or not txn_ready or not csv_ready
        if not should_download:
            remote_files = _get_bulk_csv_files(
                TRANSACTIONS_DATASET_ID, TRANSACTIONS_DATASET_PAGE
            )
            manifest_path = RAW_DLD_DIR / "DLD_download_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_names = {
                str(item.get("file_name") or "")
                for item in manifest.get("transaction_source_files", [])
            }
            remote_names = {
                str(item.get("file_name") or "") for item in remote_files
            }
            should_download = remote_names != cached_names
            refresh_note = (
                "Data Dubai has a new transaction snapshot"
                if should_download
                else "Data Dubai transaction snapshot checked online"
            )
        if should_download:
            _download_all()
            downloaded = True
            csv_ready = txn_csv.is_file()
            refresh_note = "Downloaded and rebuilt Data Dubai transaction snapshot"

    if txn_ready:
        if downloaded:
            for view in (
                "dld.land_transactions",
                "dld.transaction_year_summary",
                "dld.transaction_date_quality_issues",
            ):
                con.execute(f"DROP VIEW IF EXISTS {view}")
            con.execute("DROP TABLE detail.dld_transactions")
            rebuilt = _build_base_from_csv(con)
            return "; ".join(item for item in (refresh_note, rebuilt) if item)

        actual_columns = [
            row[0]
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'detail' "
                "AND table_name = 'dld_transactions' "
                "ORDER BY ordinal_position"
            ).fetchall()
        ]
        if actual_columns != list(KEEP_COLUMNS):
            raise ValueError(
                "detail.dld_transactions schema mismatch: "
                f"expected {KEEP_COLUMNS!r}, got {actual_columns!r}"
            )
        return refresh_note or "Current detail table checked online"

    if csv_ready:
        rebuilt = _build_base_from_csv(con)
        return "; ".join(item for item in (refresh_note, rebuilt) if item)
    if downloaded:
        raise RuntimeError(
            "Data Dubai download completed without DLD_Transactions_ALL.csv "
            f"under {RAW_DLD_DIR}"
        )
    raise RuntimeError(
        "detail.dld_transactions is missing and no current raw CSV is available; "
        "run an online update or explicitly provide the current raw CSV "
        "for skip_download mode"
    )

def _format_bytes(size):
    value = float(int(size or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _http_read(req, opener=None, timeout=90, retries=4):
    opener = opener or urllib.request.build_opener()
    for attempt in range(retries + 1):
        try:
            with opener.open(req, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
            retry_after = int(exc.headers.get("Retry-After", 0) or 0)
            time.sleep(max(retry_after or 2**attempt, 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Data Dubai request retries exhausted")


def _data_dubai_opener():
    cookies = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def _get_bulk_csv_files(dataset_id, dataset_page):
    """从 Data Dubai 取回当前带签名的 CSV 下载元数据。"""

    opener = _data_dubai_opener()
    page_req = urllib.request.Request(dataset_page, headers={"User-Agent": _USER_AGENT})
    page = _http_read(page_req, opener=opener, timeout=60, retries=2)
    token_match = re.search(r"Liferay\.authToken\s*=\s*'([^']+)'", page)
    if not token_match:
        raise RuntimeError("Data Dubai page did not provide a CSRF token")

    query = urllib.parse.urlencode(
        {
            "datasetId": dataset_id,
            "page": "1",
            "pageSize": "100",
            "sortDir": "desc",
        }
    )
    api_req = urllib.request.Request(
        f"{DOWNLOAD_API}?{query}",
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "X-CSRF-Token": token_match.group(1),
        },
    )
    for attempt in range(3):
        try:
            payload = json.loads(
                _http_read(api_req, opener=opener, timeout=60, retries=2)
            )
            break
        except json.JSONDecodeError as exc:
            # The official endpoint intermittently returns an empty/HTML 200.
            # Retry the live request; never substitute an unverified old cache.
            if attempt == 2:
                raise RuntimeError(
                    "Data Dubai download API returned invalid JSON after 3 attempts"
                ) from exc
            time.sleep(attempt + 1)
    if not payload.get("success"):
        raise RuntimeError(f"Data Dubai download API failed: {payload.get('message')}")

    files = []
    for folder in (payload.get("data") or {}).get("metadata") or []:
        for item in folder.get("files") or []:
            name = str(item.get("file_name") or "")
            extension = str(item.get("file_extension") or "").lower()
            if extension == "csv" and name.lower().endswith((".csv", ".csv.gz")):
                if not item.get("file_url"):
                    raise RuntimeError(f"Data Dubai returned no URL for {name}")
                files.append(item)

    if not files:
        raise RuntimeError(f"Data Dubai returned no CSV files for dataset {dataset_id}")
    return files


def _download_file(item, destination):
    """下载一个签名 bulk 文件并返回传输元数据。"""

    name = item["file_name"]
    req = urllib.request.Request(item["file_url"], headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as response:
        compressed_size = int(response.headers.get("Content-Length") or 0)
        print(
            f"  downloading {name}"
            + (f" ({_format_bytes(compressed_size)})" if compressed_size else ""),
            flush=True,
        )
        written = 0
        with open(destination, "wb") as output:
            while True:
                block = response.read(_CHUNK_SIZE)
                if not block:
                    break
                output.write(block)
                written += len(block)

    if compressed_size and written != compressed_size:
        raise RuntimeError(
            f"Incomplete download for {name}: expected {compressed_size}, "
            f"got {written} bytes"
        )
    return {
        "file_name": name,
        "compressed_bytes": written,
        "declared_uncompressed_bytes": int(item.get("file_size") or 0),
    }


def _open_bulk_csv(path):
    raw = open(path, "rb")
    try:
        if path.name.lower().endswith(".gz"):
            binary = gzip.GzipFile(fileobj=raw, mode="rb")
        else:
            binary = raw
        return raw, binary
    except Exception:
        raw.close()
        raise


def _parse_iso_date(value):
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _merge_transactions(archives, all_path):
    """合并交易 bulk 分区，保留全部原始行及日期质量统计。"""

    all_temp = all_path.with_suffix(all_path.suffix + ".part")
    total = 0
    first_date = None
    last_date = None
    first_date_since_1900 = None
    dates_before_1900 = 0
    unparseable_dates = 0
    snapshot_at = None
    expected_fields = None

    try:
        with open(all_temp, "w", newline="", encoding="utf-8-sig") as all_file:
            all_writer = None
            for archive in archives:
                raw, binary = _open_bulk_csv(archive)
                try:
                    with io.TextIOWrapper(
                        binary, encoding="utf-8-sig", newline=""
                    ) as text:
                        reader = csv.DictReader(text)
                        if not reader.fieldnames:
                            raise RuntimeError(f"No CSV header in {archive.name}")
                        if expected_fields is None:
                            expected_fields = reader.fieldnames
                            all_writer = csv.DictWriter(
                                all_file, fieldnames=expected_fields
                            )
                            all_writer.writeheader()
                        elif reader.fieldnames != expected_fields:
                            raise RuntimeError(
                                f"CSV schema mismatch in {archive.name}"
                            )

                        for row in reader:
                            all_writer.writerow(row)
                            total += 1
                            row_date = _parse_iso_date(row.get("instance_date"))
                            if row_date is not None:
                                first_date = (
                                    row_date
                                    if first_date is None
                                    else min(first_date, row_date)
                                )
                                last_date = (
                                    row_date
                                    if last_date is None
                                    else max(last_date, row_date)
                                )
                                if row_date < date(1900, 1, 1):
                                    dates_before_1900 += 1
                                else:
                                    first_date_since_1900 = (
                                        row_date
                                        if first_date_since_1900 is None
                                        else min(first_date_since_1900, row_date)
                                    )
                            else:
                                unparseable_dates += 1
                            load_timestamp = str(
                                row.get("load_timestamp") or ""
                            ).strip()
                            if load_timestamp:
                                snapshot_at = max(
                                    snapshot_at or load_timestamp, load_timestamp
                                )
                            if total % 250_000 == 0:
                                print(f"  transactions merged: {total:,}", flush=True)
                finally:
                    if not binary.closed:
                        binary.close()
                    if not raw.closed:
                        raw.close()

        os.replace(all_temp, all_path)
    except Exception:
        all_temp.unlink(missing_ok=True)
        raise

    return {
        "transactions_file": str(all_path),
        "transactions_rows": total,
        "transactions_bytes": all_path.stat().st_size,
        "from_date": str(first_date) if first_date else None,
        "to_date": str(last_date) if last_date else None,
        "from_date_since_1900": (
            str(first_date_since_1900) if first_date_since_1900 else None
        ),
        "dates_before_1900_rows": dates_before_1900,
        "unparseable_date_rows": unparseable_dates,
        "snapshot_at": snapshot_at,
    }


def _fetch_and_stage(files, directory):
    archives = []
    transfers = []
    for index, item in enumerate(files, start=1):
        name = Path(item["file_name"]).name
        destination = directory / f"{index:04d}_{name}"
        transfers.append(_download_file(item, destination))
        archives.append(destination)
    return archives, transfers


def _download_all() -> None:
    """完整下载 Data Dubai 官方 bulk 快照并合并到 htfa/monitoring/uae/assets/raw/dld/。

    输出：DLD_Transactions_ALL.csv / DLD_download_manifest.json。
    """

    RAW_DLD_DIR.mkdir(parents=True, exist_ok=True)
    print("DLD Full Data Downloader", flush=True)
    print("Historical source:", TRANSACTIONS_DATASET_PAGE, flush=True)
    print("Output directory:", RAW_DLD_DIR, flush=True)
    print(flush=True)

    manifest = {
        "source": "Data Dubai official bulk open data",
        "transactions_dataset": TRANSACTIONS_DATASET_PAGE,
        "dld_current_year_page": DLD_OPEN_DATA_PAGE,
        "coverage_note": (
            "The DLD real-time transaction page is limited to the current calendar year; "
            "historical coverage comes from the Data Dubai bulk snapshot."
        ),
    }

    with tempfile.TemporaryDirectory(
        prefix=".dld_download_", dir=RAW_DLD_DIR
    ) as temp_name:
        temp_dir = Path(temp_name)

        print("[Transactions] resolving official bulk files", flush=True)
        transaction_files = _get_bulk_csv_files(
            TRANSACTIONS_DATASET_ID, TRANSACTIONS_DATASET_PAGE
        )
        transaction_archives, transaction_transfers = _fetch_and_stage(
            transaction_files, temp_dir
        )
        transaction_result = _merge_transactions(
            transaction_archives,
            RAW_DLD_DIR / "DLD_Transactions_ALL.csv",
        )
        manifest.update(transaction_result)
        manifest["transaction_source_files"] = transaction_transfers


    manifest["downloaded_at"] = datetime.now().isoformat(timespec="seconds")
    print("[Verification] calculating SHA-256 checksums", flush=True)
    manifest["output_files"] = {
        "transactions": {
            "path": manifest["transactions_file"],
            "rows": manifest["transactions_rows"],
            "bytes": manifest["transactions_bytes"],
            "sha256": _sha256_file(manifest["transactions_file"]),
        },

    }
    if manifest["dates_before_1900_rows"]:
        manifest["data_quality_warning"] = (
            "The official transaction snapshot contains dates before 1900. "
            "They are preserved unchanged; use from_date_since_1900 when a modern-era "
            "coverage boundary is required."
        )
    manifest_path = RAW_DLD_DIR / "DLD_download_manifest.json"
    write_json_atomic(manifest_path, manifest)

    print("\nDONE", flush=True)
    print(f"Transactions: {manifest['transactions_rows']:,}", flush=True)
    print(f"Transaction dates: {manifest['from_date']} .. {manifest['to_date']}", flush=True)
    if manifest["dates_before_1900_rows"]:
        print(
            "Warning: official source contains "
            f"{manifest['dates_before_1900_rows']:,} transaction date(s) before 1900; "
            f"first date since 1900 is {manifest['from_date_since_1900']}.",
            flush=True,
        )
    print("Files are in:", RAW_DLD_DIR, flush=True)


# ---------------------------------------------------------------------------
# 公开入口一：update()
# ---------------------------------------------------------------------------

def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Refresh the detail table, build indicators, and load transactionally.

    Errors propagate. Offline CSV reconstruction requires skip_download=True.
    """

    db.init_schema(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS dld")
    path_note = _ensure_base_tables(con, force=force, skip_download=skip_download)
    _create_dld_views(con)

    weekly_rows = to_weekly_table_rows(_fetch_raw_weekly(con))
    sales_rows = build_sales_monthly(con)

    with db.transaction(con):
        row_count = db.replace(con, "dld_investment_pipeline_weekly", weekly_rows)
        row_count += db.replace(con, "dld_sales_monthly", sales_rows)
        # 按当前 KEEP_COLUMNS 重建交易表字段字典。
        con.execute(
            "DELETE FROM meta_column_dictionary "
            "WHERE object_name = 'detail.dld_transactions'"
        )
        _upsert_column_dictionary(con)
        _upsert_indicator_dictionary(con)

    first_week = (
        f"{weekly_rows[0]['week_end']:%Y-%m-%d}" if weekly_rows else "-"
    )
    last_week = (
        f"{weekly_rows[-1]['week_end']:%Y-%m-%d}" if weekly_rows else "-"
    )
    sales_months = sorted({row["period"] for row in sales_rows})
    note = (
        f"{path_note}；周度项目计数 {len(weekly_rows)} 行（{first_week} .. {last_week}）；"
        f"月度销售 {len(sales_rows)} 行"
    )
    return {"status": "ok", "rows": row_count, "note": note}


# ---------------------------------------------------------------------------
# 公开入口二：merge()
# ---------------------------------------------------------------------------

def sheet_specs(con):
    """Read both retained DLD sheets from DuckDB, without retired calculations."""
    names = [row[0] for row in INDICATOR_DICTIONARY]
    weekly = [(period, dict(zip(names, values))) for period, *values in con.execute(
        "SELECT week_end,confirmed_new_projects_28d,active_projects_28d "
        "FROM dld_investment_pipeline_weekly ORDER BY week_end"
    ).fetchall()]
    monthly = {}
    keys = list(SALES_INDICATOR_KEYS.values())
    for period, key, count, value in con.execute(
        "SELECT period,indicator,count,value_aed FROM dld_sales_monthly ORDER BY period"
    ).fetchall():
        index = keys.index(key) * 2 + 1
        monthly.setdefault(period, {}).update({
            MONTHLY_SHEET_HEADERS[index]: count,
            MONTHLY_SHEET_HEADERS[index + 1]: None if value is None else round(value / 1_000_000, 3),
        })
    specs = []
    for sheet, dictionary, rows in (
        (WORKSHEET_NAME, INDICATOR_DICTIONARY, weekly),
        (MONTHLY_WORKSHEET_NAME, MONTHLY_INDICATOR_DICTIONARY, list(monthly.items())),
    ):
        specs.append({"name": sheet, "title": "Dubai Land Department", "rows": rows,
                      "indicators": [row[0] for row in dictionary],
                      "metadata": {row[0]: {"frequency": row[1], "unit": row[2], "source": row[3]}
                                   for row in dictionary}})
    return specs


def merge(workbook_path: Path) -> dict:
    """Atomically rebuild retained weekly and monthly sheets from DuckDB."""
    import shutil

    path = Path(workbook_path).resolve()
    with db.connect(read_only=True) as con:
        specs = sheet_specs(con)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.with_name(f"~${path.name}").exists():
        raise PermissionError("请先关闭 Excel 工作簿")
    backups = path.parent / "backups"
    backups.mkdir(exist_ok=True)
    shutil.copy2(path, backups / f"dld_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx")
    counts = write_indicator_sheets(path, specs)
    return {"status": "ok", "rows": sum(counts.values()),
            "note": "周度2项项目计数、月度8项销售数据已从 DuckDB 合并"}
