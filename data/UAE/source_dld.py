"""Dubai Land Department（DLD）数据源模块。

职责（对应 ``update()`` 一个入口）：
1. 建库：确保 ``dld`` schema、``dld.transactions`` 基表（优先从
   ``data/UAE/raw/dld/DLD.duckdb`` 旧库迁移，否则按 ``build_dld_database.sql``
   的 TRY_CAST 逻辑从 CSV 建表）、三个只读视图、唯一索引，以及
   ``meta_column_dictionary`` / ``meta_indicator_dictionary``。
2. 下载：仅当缺失原始数据或 ``force=True`` 且 ``skip_download=False`` 时，
   按 ``download_dld_all.py`` 的流程从 Data Dubai 官方 bulk 数据抓取并合并
   原始 CSV 到 ``data/UAE/raw/dld/`` 下。
3. 周度指标：移植 ``generate_dld_investment_indices.py`` 的全部分析逻辑
   （RAW_WEEKLY_SQL + build_rows），结果事务内写入 ``dld_investment_pipeline_weekly``。

表结构瘦身（2026-08）：``dld.transactions`` 只保留被周度指标与三个视图消费的
列（``KEEP_COLUMNS``，47 → 8）；``dld.land_registry`` 仓库内零消费，不再建表
入库（原始 CSV / 旧库仍保留在 ``data/UAE/raw/dld/``，需要时可单独重建）。

回调写表（对应 ``merge()`` 一个入口）：
从库中查询周度指标 → 导出 7 列临时 CSV（列名与旧
``merge_dld_indices_into_uae_workbook.ps1`` 完全一致）→ 调用
``data/merge_dld_indices_into_uae_workbook.ps1`` 写回工作簿。

只许使用标准库 + duckdb。
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import http.cookiejar
import io
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量：计算窗口与发布起点（与旧 generate 脚本一致）
# ---------------------------------------------------------------------------

CALCULATION_START = date(2009, 1, 5)
PUBLICATION_START = date(2015, 1, 5)
YOY_WEEKS = 52
BASELINE_WEEKS = 156
MIN_BASELINE_OBSERVATIONS = 104

# 原始 CSV / 旧库所在目录（与 data/UAE/raw/dld/ 一致）
RAW_DLD_DIR = DATA_DIR / "raw" / "dld"

# dld.transactions 仅保留被 RAW_WEEKLY_SQL 与三个视图消费的列（47 → 8）。
# 「保留 = 被查询」：transaction_id(计数/主键)、instance_date(周/年分组)、
# trans_group_en/reg_type_en(Sales/Off-Plan 过滤)、project_number(项目维度)、
# actual_worth(金额)、property_type_en(Land 视图/年汇总)、
# load_timestamp(bulk 快照时间，每行同值，字典压缩近零成本，仅用于追溯)。
KEEP_COLUMNS = (
    "actual_worth",
    "instance_date",
    "load_timestamp",
    "project_number",
    "property_type_en",
    "reg_type_en",
    "trans_group_en",
    "transaction_id",
)

# 工作簿写表（merge() 使用）
WORKSHEET_NAME = "周度_迪拜房地产"
WORKBOOK_MERGER = DATA_DIR / "merge_dld_indices_into_uae_workbook.ps1"

# ---------------------------------------------------------------------------
# 周度原始口径 SQL：移植自 generate_dld_investment_indices.py 的 RAW_WEEKLY_SQL，
# 唯一差异是数据库引用改为统一库的 dld.transactions（原为裸表名）。
# ---------------------------------------------------------------------------

RAW_WEEKLY_SQL = r"""
WITH RECURSIVE
bounds AS (
    SELECT
        DATE '2009-01-05' AS first_week,
        CASE
            WHEN max(instance_date) >= CAST(date_trunc('week', max(instance_date)) AS DATE) + 6
                THEN CAST(date_trunc('week', max(instance_date)) AS DATE)
            ELSE CAST(date_trunc('week', max(instance_date)) AS DATE) - 7
        END AS last_complete_week,
        max(instance_date) AS source_data_through
    FROM dld.transactions
),
calendar AS (
    SELECT
        CAST(gs AS DATE) AS week_start,
        CAST(gs AS DATE) + 6 AS week_end,
        bounds.source_data_through
    FROM bounds,
         generate_series(bounds.first_week, bounds.last_complete_week, INTERVAL 7 DAY) AS t(gs)
),
offplan_sales AS (
    SELECT
        transaction_id,
        instance_date,
        CAST(date_trunc('week', instance_date) AS DATE) AS week_start,
        project_number,
        actual_worth
    FROM dld.transactions
    WHERE trans_group_en = 'Sales'
      AND reg_type_en = 'Off-Plan Properties'
      AND instance_date >= DATE '2009-01-05' - INTERVAL 27 DAY
),
offplan_week AS (
    SELECT
        week_start,
        count(*) AS sales,
        count(*) FILTER (WHERE project_number IS NOT NULL) AS sales_with_project,
        sum(actual_worth) AS sales_value
    FROM offplan_sales
    GROUP BY week_start
),
project_list AS (
    SELECT DISTINCT project_number
    FROM offplan_sales
    WHERE project_number IS NOT NULL
),
project_week AS (
    SELECT week_start, project_number, count(*) AS sales
    FROM offplan_sales
    WHERE project_number IS NOT NULL
    GROUP BY week_start, project_number
),
project_week_grid AS (
    SELECT
        c.week_start,
        p.project_number,
        coalesce(w.sales, 0) AS sales
    FROM calendar c
    CROSS JOIN project_list p
    LEFT JOIN project_week w USING (week_start, project_number)
),
project_trailing AS (
    SELECT
        week_start,
        project_number,
        sum(sales) OVER (
            PARTITION BY project_number
            ORDER BY week_start
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS sales_28d
    FROM project_week_grid
),
active_project_week AS (
    SELECT
        week_start,
        count(*) FILTER (WHERE sales_28d >= 3) AS active_projects_28d
    FROM project_trailing
    GROUP BY week_start
),
project_launch AS (
    SELECT
        project_number,
        min(instance_date) AS first_offplan_sale_date
    FROM dld.transactions
    WHERE trans_group_en = 'Sales'
      AND reg_type_en = 'Off-Plan Properties'
      AND project_number IS NOT NULL
    GROUP BY project_number
),
project_launch_confirmed AS (
    SELECT
        p.project_number,
        p.first_offplan_sale_date,
        count(t.transaction_id) AS sales_first_28d
    FROM project_launch p
    LEFT JOIN dld.transactions t
      ON t.project_number = p.project_number
     AND t.trans_group_en = 'Sales'
     AND t.reg_type_en = 'Off-Plan Properties'
     AND t.instance_date BETWEEN p.first_offplan_sale_date
                             AND p.first_offplan_sale_date + 27
    GROUP BY p.project_number, p.first_offplan_sale_date
),
initial_launch_week AS (
    SELECT
        CAST(date_trunc('week', first_offplan_sale_date) AS DATE) AS week_start,
        count(*) AS initial_new_projects
    FROM project_launch_confirmed
    GROUP BY week_start
),
confirmed_launch_week AS (
    -- Count at the end of the 28-day confirmation window. This prevents
    -- future sales from being assigned to an earlier publication week.
    SELECT
        CAST(date_trunc('week', first_offplan_sale_date + 27) AS DATE) AS week_start,
        count(*) AS confirmed_new_projects
    FROM project_launch_confirmed
    WHERE sales_first_28d >= 10
    GROUP BY week_start
),
project_dates AS (
    SELECT
        project_number,
        min(instance_date) FILTER (
            WHERE reg_type_en = 'Off-Plan Properties'
        ) AS first_offplan_sale,
        min(instance_date) FILTER (
            WHERE reg_type_en = 'Existing Properties'
        ) AS first_existing_sale
    FROM dld.transactions
    WHERE trans_group_en = 'Sales'
      AND project_number IS NOT NULL
    GROUP BY project_number
),
project_transition AS (
    SELECT
        p.project_number,
        p.first_offplan_sale,
        p.first_existing_sale,
        count(t.transaction_id) AS offplan_sales_before_existing
    FROM project_dates p
    LEFT JOIN dld.transactions t
      ON t.project_number = p.project_number
     AND t.trans_group_en = 'Sales'
     AND t.reg_type_en = 'Off-Plan Properties'
     AND t.instance_date < p.first_existing_sale
    WHERE p.first_offplan_sale IS NOT NULL
      AND p.first_existing_sale >= p.first_offplan_sale + 180
    GROUP BY p.project_number, p.first_offplan_sale, p.first_existing_sale
),
transition_week AS (
    SELECT
        CAST(date_trunc('week', first_existing_sale) AS DATE) AS week_start,
        count(*) AS commercial_transition_projects
    FROM project_transition
    WHERE offplan_sales_before_existing >= 20
    GROUP BY week_start
),
weekly_base AS (
    SELECT
        c.week_start,
        c.week_end,
        c.source_data_through,
        coalesce(l.initial_new_projects, 0) AS initial_new_projects,
        coalesce(cl.confirmed_new_projects, 0) AS confirmed_new_projects,
        coalesce(o.sales, 0) AS offplan_sales,
        coalesce(o.sales_with_project, 0) AS offplan_sales_with_project,
        coalesce(o.sales_value, 0) AS offplan_sales_value,
        coalesce(a.active_projects_28d, 0) AS active_projects_28d,
        coalesce(t.commercial_transition_projects, 0) AS commercial_transition_projects
    FROM calendar c
    LEFT JOIN initial_launch_week l USING (week_start)
    LEFT JOIN confirmed_launch_week cl USING (week_start)
    LEFT JOIN offplan_week o USING (week_start)
    LEFT JOIN active_project_week a USING (week_start)
    LEFT JOIN transition_week t USING (week_start)
),
weekly_rolling AS (
    SELECT
        *,
        sum(confirmed_new_projects) OVER (
            ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS confirmed_new_projects_28d,
        sum(offplan_sales) OVER (
            ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS offplan_sales_28d,
        sum(offplan_sales_with_project) OVER (
            ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS offplan_sales_with_project_28d,
        sum(offplan_sales_value) OVER (
            ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS offplan_sales_value_28d,
        sum(commercial_transition_projects) OVER (
            ORDER BY week_start ROWS BETWEEN 12 PRECEDING AND CURRENT ROW
        ) AS commercial_transition_projects_13w
    FROM weekly_base
)
SELECT
    week_start,
    week_end,
    source_data_through,
    initial_new_projects,
    confirmed_new_projects,
    confirmed_new_projects_28d,
    offplan_sales_28d,
    offplan_sales_value_28d,
    active_projects_28d,
    CASE WHEN active_projects_28d > 0
         THEN offplan_sales_28d::DOUBLE / active_projects_28d END
        AS offplan_sales_per_active_project_28d,
    CASE WHEN offplan_sales_28d > 0
         THEN 100.0 * offplan_sales_with_project_28d / offplan_sales_28d END
        AS project_number_coverage_pct_28d,
    commercial_transition_projects,
    commercial_transition_projects_13w
FROM weekly_rolling
ORDER BY week_start
"""

# ---------------------------------------------------------------------------
# 列字典：dld.transactions 仅保留 KEEP_COLUMNS 八列（含义沿用旧
# build_dld_database.sql 的 metadata.column_dictionary；land_registry 已不再建表,
# 其字典行一并移除）。
# ---------------------------------------------------------------------------

COLUMN_DICTIONARY = (
    ('dld.transactions', 'actual_worth', 'DECIMAL(24,2)', '金额面积', '交易金额或实际价值', None, '通常按AED理解；源文件未单列单位'),
    ('dld.transactions', 'instance_date', 'DATE', '时间', '交易登记日期', 'transaction_year_summary.transaction_year', '官方源含4条1900年以前异常日期'),
    ('dld.transactions', 'load_timestamp', 'TIMESTAMPTZ', '时间', 'Data Dubai生成bulk快照的时间', None, '不是交易发生时间'),
    ('dld.transactions', 'project_number', 'VARCHAR', '项目建筑', '交易数据中的项目编号', None, 'RAW_WEEKLY_SQL 按项目编号聚合期房窗口'),
    ('dld.transactions', 'property_type_en', 'VARCHAR', '房产分类', '房产大类英文名', 'land_transactions', 'Land决定是否进入land_transactions视图'),
    ('dld.transactions', 'reg_type_en', 'VARCHAR', '登记类型', 'Existing或Off-Plan英文名', None, '现房/期房过滤键（RAW_WEEKLY_SQL）'),
    ('dld.transactions', 'trans_group_en', 'VARCHAR', '交易分类', 'Sales/Mortgages/Gifts', None, '交易大类过滤键（RAW_WEEKLY_SQL）'),
    ('dld.transactions', 'transaction_id', 'VARCHAR', '主键', '交易记录唯一编号', 'land_transactions.transaction_id', '本表唯一主键'),
)

# ---------------------------------------------------------------------------
# 指标字典：6 个周度指标（即 ps1 的 7 列 headers 去掉「截止日期」）。
# type/industry 沿用旧 ps1 写入工作簿「指标字典」时的口径
# （项目数/交易笔数/…、房地产），来源与频率为统一口径。
# ---------------------------------------------------------------------------

INDICATOR_DICTIONARY = (
    ("经确认新期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
    ("期房销售笔数_近28天", "周", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("活跃期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
    ("项目启动指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
    ("期房销售吸收指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
    ("项目商业转化指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
)

# merge() 导出 CSV 的 7 列名（与旧 merge_dld_indices_into_uae_workbook.ps1 完全一致）
WEEKLY_CSV_HEADERS = (
    "截止日期",
    "经确认新期房项目数_近28天",
    "期房销售笔数_近28天",
    "活跃期房项目数_近28天",
    "项目启动指数",
    "期房销售吸收指数",
    "项目商业转化指数",
)

# 下载器 URL 常量（与 download_dld_all.py 一致）
DLD_OPEN_DATA_PAGE = "https://dubailand.gov.ae/en/open-data/real-estate-data/"
DATA_DUBAI_BASE = "https://data.dubai"
DATA_DUBAI_ENTITY_ID = "62035"
TRANSACTIONS_DATASET_ID = "470061"
LAND_REGISTRY_DATASET_ID = "465348"
TRANSACTIONS_DATASET_PAGE = (
    f"{DATA_DUBAI_BASE}/en/l/{TRANSACTIONS_DATASET_ID}"
    f"?com_dda_data_and_statistics_ThemeId={DATA_DUBAI_ENTITY_ID}"
)
LAND_REGISTRY_DATASET_PAGE = (
    f"{DATA_DUBAI_BASE}/en/l/{LAND_REGISTRY_DATASET_ID}"
    f"?com_dda_data_and_statistics_ThemeId={DATA_DUBAI_ENTITY_ID}"
)
DOWNLOAD_API = f"{DATA_DUBAI_BASE}/o/dda/data-services/dataset-download"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
_CHUNK_SIZE = 1024 * 1024


# ---------------------------------------------------------------------------
# 数值与指数计算的纯函数（移植自 generate_dld_investment_indices.py）
# ---------------------------------------------------------------------------

def parse_float(value):
    """把字符串/数值转成 float；空值与 None 保持 None。"""

    if value is None or value == "":
        return None
    return float(value)


def log_momentum(current, previous):
    """log1p 同比动量；任一缺失或负值返回 None。"""

    if current is None or previous is None or current < 0 or previous < 0:
        return None
    return math.log1p(current) - math.log1p(previous)


def rolling_robust_z(values, baseline_weeks=BASELINE_WEEKS):
    """只用历史观测做标准化（绝不借用未来周），结果截断到 [-5, 5]。"""

    result = []
    for index, value in enumerate(values):
        if value is None:
            result.append(None)
            continue
        history = [
            item
            for item in values[max(0, index - baseline_weeks) : index]
            if item is not None
        ]
        if len(history) < MIN_BASELINE_OBSERVATIONS:
            result.append(None)
            continue
        center = statistics.median(history)
        mad = statistics.median(abs(item - center) for item in history)
        if mad <= 1e-12:
            result.append(None)
            continue
        z_value = (value - center) / (1.4826 * mad)
        result.append(max(-5.0, min(5.0, z_value)))
    return result


def score_from_z(value):
    """把稳健 z 分数映射到 0-100 指数（线性 50 + 10z，双向截断）。"""

    if value is None:
        return None
    return max(0.0, min(100.0, 50.0 + 10.0 * value))


def formatted(value, digits=6):
    """旧 generate 脚本的数值格式化：整数原样，浮点保留 digits 位小数。"""

    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def build_rows(raw_rows):
    """由 RAW_WEEKLY_SQL 的原始行计算全部派生指标（与旧脚本逐行等价）。

    ``raw_rows`` 每行是一个 dict，键为 RAW_WEEKLY_SQL 的 13 个输出列；
    数值列既接受字符串（旧 CSV 流程）也接受 float/int（统一库直查流程）。
    返回行数不变，每行在原字段基础上追加动量/稳健 z/指数等派生字段。
    """

    numeric_columns = (
        "initial_new_projects",
        "confirmed_new_projects",
        "confirmed_new_projects_28d",
        "offplan_sales_28d",
        "offplan_sales_value_28d",
        "active_projects_28d",
        "offplan_sales_per_active_project_28d",
        "project_number_coverage_pct_28d",
        "commercial_transition_projects",
        "commercial_transition_projects_13w",
    )
    for row in raw_rows:
        for column in numeric_columns:
            row[column] = parse_float(row[column])

    launch_momentum = []
    absorption_count_momentum = []
    absorption_breadth_momentum = []
    absorption_velocity_momentum = []
    transition_momentum = []
    for index, row in enumerate(raw_rows):
        if index < YOY_WEEKS:
            launch_momentum.append(None)
            absorption_count_momentum.append(None)
            absorption_breadth_momentum.append(None)
            absorption_velocity_momentum.append(None)
            transition_momentum.append(None)
            continue
        previous = raw_rows[index - YOY_WEEKS]
        launch_momentum.append(
            log_momentum(
                row["confirmed_new_projects_28d"],
                previous["confirmed_new_projects_28d"],
            )
        )
        absorption_count_momentum.append(
            log_momentum(row["offplan_sales_28d"], previous["offplan_sales_28d"])
        )
        absorption_breadth_momentum.append(
            log_momentum(
                row["active_projects_28d"], previous["active_projects_28d"]
            )
        )
        absorption_velocity_momentum.append(
            log_momentum(
                row["offplan_sales_per_active_project_28d"],
                previous["offplan_sales_per_active_project_28d"],
            )
        )
        transition_momentum.append(
            log_momentum(
                row["commercial_transition_projects_13w"],
                previous["commercial_transition_projects_13w"],
            )
        )

    launch_z = rolling_robust_z(launch_momentum)
    count_z = rolling_robust_z(absorption_count_momentum)
    breadth_z = rolling_robust_z(absorption_breadth_momentum)
    velocity_z = rolling_robust_z(absorption_velocity_momentum)
    transition_z = rolling_robust_z(transition_momentum)

    output = []
    for index, row in enumerate(raw_rows):
        absorption_parts = (count_z[index], breadth_z[index], velocity_z[index])
        absorption_z = (
            0.4 * absorption_parts[0]
            + 0.3 * absorption_parts[1]
            + 0.3 * absorption_parts[2]
            if all(value is not None for value in absorption_parts)
            else None
        )
        launch_score = score_from_z(launch_z[index])
        absorption_score = score_from_z(absorption_z)
        transition_score = score_from_z(transition_z[index])
        component_scores = (launch_score, absorption_score, transition_score)
        composite_score = (
            0.3 * component_scores[0]
            + 0.5 * component_scores[1]
            + 0.2 * component_scores[2]
            if all(value is not None for value in component_scores)
            else None
        )
        coverage = row["project_number_coverage_pct_28d"]
        quality_flag = "ok" if coverage is not None and coverage >= 99.0 else "low_project_coverage"
        output.append(
            {
                **row,
                "confirmed_launch_yoy_log_momentum": launch_momentum[index],
                "confirmed_launch_z": launch_z[index],
                "confirmed_launch_score": launch_score,
                "absorption_count_yoy_log_momentum": absorption_count_momentum[index],
                "absorption_breadth_yoy_log_momentum": absorption_breadth_momentum[index],
                "absorption_velocity_yoy_log_momentum": absorption_velocity_momentum[index],
                "absorption_count_z": count_z[index],
                "absorption_breadth_z": breadth_z[index],
                "absorption_velocity_z": velocity_z[index],
                "offplan_absorption_z": absorption_z,
                "offplan_absorption_score": absorption_score,
                "commercial_transition_yoy_log_momentum": transition_momentum[index],
                "commercial_transition_z": transition_z[index],
                "commercial_transition_score": transition_score,
                "dld_investment_pipeline_score": composite_score,
                "quality_flag": quality_flag,
            }
        )
    return output


def _as_date(value):
    """把 DATE 值或 'yyyy-mm-dd' 字符串统一成 datetime.date。"""

    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _rounded_count(value):
    """计数列入库值：None 保持 None，否则四舍五入为整数（与旧 CSV 一致）。"""

    return None if value is None else int(round(value))


def _rounded_score(value):
    """指数列入库值：None 保持 None，否则保留 6 位小数（与旧 formatted() 一致）。"""

    return None if value is None else round(float(value), 6)


def to_weekly_table_rows(built_rows):
    """把 build_rows 的结果映射成 dld_investment_pipeline_weekly 的入库行。

    仅保留 week_start >= PUBLICATION_START 的发布周；week_end 转为 DATE，
    数值列按旧脚本口径（整数计数 / 6 位小数指数）格式化，None 原样保留。
    """

    rows = []
    for row in built_rows:
        if _as_date(row["week_start"]) < PUBLICATION_START:
            continue
        rows.append(
            {
                "week_end": _as_date(row["week_end"]),
                "confirmed_new_projects_28d": _rounded_count(
                    row["confirmed_new_projects_28d"]
                ),
                "offplan_sales_28d": _rounded_count(row["offplan_sales_28d"]),
                "active_projects_28d": _rounded_count(
                    row["active_projects_28d"]
                ),
                "project_launch_index": _rounded_score(
                    row["confirmed_launch_score"]
                ),
                "offplan_absorption_index": _rounded_score(
                    row["offplan_absorption_score"]
                ),
                "project_commercial_transition_index": _rounded_score(
                    row["commercial_transition_score"]
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 建库：迁移 / CSV 建表 / 视图 / 字典
# ---------------------------------------------------------------------------

def _transactions_ddl(csv_path: Path) -> str:
    """transactions 建表 DDL：从 CSV 只保留 ``KEEP_COLUMNS`` 八列（TRY_CAST）。"""

    path = csv_path.resolve().as_posix()
    return rf"""
    CREATE TABLE dld.transactions AS
    SELECT
        TRY_CAST(actual_worth AS DECIMAL(24, 2)) AS actual_worth,
        TRY_CAST(instance_date AS DATE) AS instance_date,
        TRY_CAST(load_timestamp AS TIMESTAMPTZ) AS load_timestamp,
        regexp_replace(project_number, '\.0+$', '') AS project_number,
        property_type_en,
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
        "SELECT count(*), count(DISTINCT transaction_id) FROM dld.transactions"
    ).fetchone()
    if total != distinct:
        raise RuntimeError(
            "dld.transactions 主键不唯一："
            f"{total} 行 / {distinct} 个不同 transaction_id"
        )


def _migrate_from_old_db(con) -> str:
    """从 data/UAE/raw/dld/DLD.duckdb 迁移 dld.transactions（只保留必需列）。"""

    old_db = RAW_DLD_DIR / "DLD.duckdb"
    attach = old_db.resolve().as_posix()
    con.execute(f"ATTACH '{attach}' AS old_dld (READ_ONLY)")
    try:
        if not db.table_exists(con, "dld.transactions"):
            con.execute(
                "CREATE TABLE dld.transactions AS "
                "SELECT " + ", ".join(KEEP_COLUMNS) + " FROM old_dld.transactions"
            )
            _assert_transaction_id_unique(con)
        dictionary = con.execute(
            "SELECT object_name, column_name, data_type, group_cn, meaning_cn, "
            "relates_to, caveat_cn FROM old_dld.metadata.column_dictionary "
            "WHERE object_name = 'transactions'"
        ).fetchall()
    finally:
        try:
            con.execute("DETACH old_dld")
        except Exception:  # noqa: BLE001 - 已分离时忽略
            pass
    for row in dictionary:
        if row[1] in KEEP_COLUMNS:
            _upsert_column_dictionary_row(con, ("dld.transactions", *row[1:]))
    return f"迁移旧库 {old_db.name}"


def _build_base_from_csv(con) -> str:
    """旧库缺失时按 build_dld_database.sql 的 TRY_CAST 逻辑从 CSV 建表（只保留必需列）。"""

    txn_csv = RAW_DLD_DIR / "DLD_Transactions_ALL.csv"
    if not txn_csv.exists():
        raise RuntimeError(f"缺少原始 CSV：{txn_csv.name}")
    if not db.table_exists(con, "dld.transactions"):
        con.execute(_transactions_ddl(txn_csv))
        _assert_transaction_id_unique(con)
    return "从原始 CSV 全量建表"


def _create_dld_views(con) -> None:
    """每次 update 都重建的三个只读视图（显式列出保留列，规避 SELECT *）。"""

    kept = ", ".join(KEEP_COLUMNS)
    con.execute(
        "CREATE OR REPLACE VIEW dld.land_transactions AS "
        f"SELECT {kept} FROM dld.transactions WHERE property_type_en = 'Land'"
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
        FROM dld.transactions
        GROUP BY ALL
        """
    )
    con.execute(
        "CREATE OR REPLACE VIEW dld.transaction_date_quality_issues AS "
        f"SELECT {kept} FROM dld.transactions "
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
    """把 6 个周度指标合并进 meta_indicator_dictionary。"""

    today = date.today()
    for indicator_name, frequency, unit, source, type_, industry in INDICATOR_DICTIONARY:
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


def _ensure_base_tables(con, *, force: bool, skip_download: bool) -> str:
    """确保 dld.transactions 存在，必要时触发下载。

    land_registry 自 2026-08 起不再入库（仓库内零消费，瘦身）；原始 CSV / 旧库
    仍保留在 data/UAE/raw/dld/ 供需要时单独重建。

    下载触发条件：基表缺失且 raw 目录无 CSV（首次安装）、或 force=True ——
    两者都必须 not skip_download。下载输出的 CSV 覆盖到 data/UAE/raw/dld/ 后，
    自动进入「CSV 全量建表」路径。
    """

    txn_csv = RAW_DLD_DIR / "DLD_Transactions_ALL.csv"
    old_db = RAW_DLD_DIR / "DLD.duckdb"
    txn_ready = db.table_exists(con, "dld.transactions")
    csv_ready = txn_csv.exists()

    downloaded = False
    if ((not txn_ready and not csv_ready) or force) and not skip_download:
        _download_all()
        downloaded = True

    if txn_ready:
        if downloaded:
            return "基表已存在（本次已强制重新下载原始 CSV；基表保持原快照，重建需删表后重跑）"
        return "基表已存在"

    if old_db.exists() and not downloaded:
        return _migrate_from_old_db(con)
    if csv_ready:
        return _build_base_from_csv(con)
    if downloaded:
        raise RuntimeError(
            "下载已完成但 data/UAE/raw/dld/ 下仍缺少 DLD_Transactions_ALL.csv，"
            "请检查下载日志"
        )
    raise RuntimeError(
        "dld.transactions 不存在，且 data/UAE/raw/dld/ 下"
        "既无旧库（DLD.duckdb）也无原始 CSV；请先去下载（不带 --skip-download）"
    )


# ---------------------------------------------------------------------------
# 下载器：移植 download_dld_all.py（Data Dubai 官方 bulk 开放数据）
# ---------------------------------------------------------------------------

def _format_bytes(size):
    size = int(size or 0)
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while True:
            block = source.read(_CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _http_read(req, opener=None, timeout=90, retries=4):
    opener = opener or urllib.request.build_opener()
    last = None
    for attempt in range(retries + 1):
        try:
            with opener.open(req, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                retry_after = int(exc.headers.get("Retry-After", 0) or 0)
                time.sleep(max(retry_after or 2**attempt, 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(2**attempt)
                continue
            raise
    raise last


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
    payload = json.loads(_http_read(api_req, opener=opener, timeout=60, retries=2))
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


def _is_land_transaction(row):
    for key in (
        "property_type_en",
        "PROP_TYPE_EN",
        "PROPERTY_TYPE_EN",
        "property_type",
        "PROPERTY_TYPE",
    ):
        if str(row.get(key) or "").strip().lower() == "land":
            return True
    return False


def _merge_transactions(archives, all_path, land_path):
    """合并交易 bulk 分区并生成「仅土地」抽取文件。"""

    all_temp = all_path.with_suffix(all_path.suffix + ".part")
    land_temp = land_path.with_suffix(land_path.suffix + ".part")
    total = 0
    land_total = 0
    first_date = None
    last_date = None
    first_date_since_1900 = None
    dates_before_1900 = 0
    unparseable_dates = 0
    snapshot_at = None
    expected_fields = None

    try:
        with open(all_temp, "w", newline="", encoding="utf-8-sig") as all_file, open(
            land_temp, "w", newline="", encoding="utf-8-sig"
        ) as land_file:
            all_writer = None
            land_writer = None
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
                            land_writer = csv.DictWriter(
                                land_file, fieldnames=expected_fields
                            )
                            all_writer.writeheader()
                            land_writer.writeheader()
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
                            if _is_land_transaction(row):
                                land_writer.writerow(row)
                                land_total += 1
                            if total % 250_000 == 0:
                                print(f"  transactions merged: {total:,}", flush=True)
                finally:
                    if not binary.closed:
                        binary.close()
                    if not raw.closed:
                        raw.close()

        os.replace(all_temp, all_path)
        os.replace(land_temp, land_path)
    except Exception:
        for path in (all_temp, land_temp):
            path.unlink(missing_ok=True)
        raise

    return {
        "transactions_file": str(all_path),
        "transactions_rows": total,
        "transactions_bytes": all_path.stat().st_size,
        "land_transactions_file": str(land_path),
        "land_transactions_rows": land_total,
        "land_transactions_bytes": land_path.stat().st_size,
        "from_date": str(first_date) if first_date else None,
        "to_date": str(last_date) if last_date else None,
        "from_date_since_1900": (
            str(first_date_since_1900) if first_date_since_1900 else None
        ),
        "dates_before_1900_rows": dates_before_1900,
        "unparseable_date_rows": unparseable_dates,
        "snapshot_at": snapshot_at,
    }


def _merge_land_registry(archives, output_path):
    """合并土地登记表 bulk 分区。"""

    temp_path = output_path.with_suffix(output_path.suffix + ".part")
    total = 0
    snapshot_at = None
    expected_fields = None
    try:
        with open(temp_path, "w", newline="", encoding="utf-8-sig") as output:
            writer = None
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
                            writer = csv.DictWriter(
                                output, fieldnames=expected_fields
                            )
                            writer.writeheader()
                        elif reader.fieldnames != expected_fields:
                            raise RuntimeError(
                                f"CSV schema mismatch in {archive.name}"
                            )
                        for row in reader:
                            writer.writerow(row)
                            total += 1
                            load_timestamp = str(
                                row.get("load_timestamp") or ""
                            ).strip()
                            if load_timestamp:
                                snapshot_at = max(
                                    snapshot_at or load_timestamp, load_timestamp
                                )
                            if total % 250_000 == 0:
                                print(f"  land registry merged: {total:,}", flush=True)
                finally:
                    if not binary.closed:
                        binary.close()
                    if not raw.closed:
                        raw.close()
        os.replace(temp_path, output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {
        "land_registry_file": str(output_path),
        "land_registry_rows": total,
        "land_registry_bytes": output_path.stat().st_size,
        "land_registry_snapshot_at": snapshot_at,
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
    """完整下载 Data Dubai 官方 bulk 快照并合并到 data/UAE/raw/dld/。

    输出：DLD_Transactions_ALL.csv / DLD_Land_Transactions_ALL.csv /
    DLD_Land_Registry_ALL.csv / DLD_download_manifest.json。
    """

    RAW_DLD_DIR.mkdir(parents=True, exist_ok=True)
    print("DLD Full Data Downloader", flush=True)
    print("Historical source:", TRANSACTIONS_DATASET_PAGE, flush=True)
    print("Output directory:", RAW_DLD_DIR, flush=True)
    print(flush=True)

    manifest = {
        "source": "Data Dubai official bulk open data",
        "transactions_dataset": TRANSACTIONS_DATASET_PAGE,
        "land_registry_dataset": LAND_REGISTRY_DATASET_PAGE,
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
            RAW_DLD_DIR / "DLD_Land_Transactions_ALL.csv",
        )
        manifest.update(transaction_result)
        manifest["transaction_source_files"] = transaction_transfers

        print("[Land Registry] resolving official bulk files", flush=True)
        registry_files = _get_bulk_csv_files(
            LAND_REGISTRY_DATASET_ID, LAND_REGISTRY_DATASET_PAGE
        )
        registry_archives, registry_transfers = _fetch_and_stage(
            registry_files, temp_dir
        )
        registry_result = _merge_land_registry(
            registry_archives, RAW_DLD_DIR / "DLD_Land_Registry_ALL.csv"
        )
        manifest.update(registry_result)
        manifest["land_registry_source_files"] = registry_transfers

    manifest["downloaded_at"] = datetime.now().isoformat(timespec="seconds")
    print("[Verification] calculating SHA-256 checksums", flush=True)
    manifest["output_files"] = {
        "transactions": {
            "path": manifest["transactions_file"],
            "rows": manifest["transactions_rows"],
            "bytes": manifest["transactions_bytes"],
            "sha256": _sha256_file(manifest["transactions_file"]),
        },
        "land_transactions": {
            "path": manifest["land_transactions_file"],
            "rows": manifest["land_transactions_rows"],
            "bytes": manifest["land_transactions_bytes"],
            "sha256": _sha256_file(manifest["land_transactions_file"]),
        },
        "land_registry": {
            "path": manifest["land_registry_file"],
            "rows": manifest["land_registry_rows"],
            "bytes": manifest["land_registry_bytes"],
            "sha256": _sha256_file(manifest["land_registry_file"]),
        },
    }
    if manifest["dates_before_1900_rows"]:
        manifest["data_quality_warning"] = (
            "The official transaction snapshot contains dates before 1900. "
            "They are preserved unchanged; use from_date_since_1900 when a modern-era "
            "coverage boundary is required."
        )
    manifest_path = RAW_DLD_DIR / "DLD_download_manifest.json"
    manifest_temp = manifest_path.with_suffix(manifest_path.suffix + ".part")
    manifest_temp.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(manifest_temp, manifest_path)

    print("\nDONE", flush=True)
    print(f"Transactions: {manifest['transactions_rows']:,}", flush=True)
    print(f"Land transactions: {manifest['land_transactions_rows']:,}", flush=True)
    print(f"Land registry: {manifest['land_registry_rows']:,}", flush=True)
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
    """建库/迁移 → 周度指标计算 → 事务内入库。

    返回 {"status": "ok", "rows": 周度指标入库行数, "note": 路径简述}；
    异常直接抛出，由总控（update_data.py）捕获记入 meta_source_runs。
    """

    db.init_schema(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS dld")
    path_note = _ensure_base_tables(con, force=force, skip_download=skip_download)
    _create_dld_views(con)

    built = build_rows(_fetch_raw_weekly(con))
    weekly_rows = to_weekly_table_rows(built)

    con.begin()
    try:
        row_count = db.replace(con, "dld_investment_pipeline_weekly", weekly_rows)
        # 瘦身后只保留 transactions 的 KEEP_COLUMNS 字典行；历史 land_registry
        # 字典行一并清理（保证 update 幂等，不以库内旧行为准）。
        con.execute(
            "DELETE FROM meta_column_dictionary "
            "WHERE object_name IN ('dld.transactions', 'dld.land_registry')"
        )
        _upsert_column_dictionary(con)
        _upsert_indicator_dictionary(con)
        con.commit()
    except BaseException:
        con.rollback()
        raise

    first_week = (
        f"{weekly_rows[0]['week_end']:%Y-%m-%d}" if weekly_rows else "-"
    )
    last_week = (
        f"{weekly_rows[-1]['week_end']:%Y-%m-%d}" if weekly_rows else "-"
    )
    note = (
        f"{path_note}；周度指标共 {row_count} 行入库"
        f"（{first_week} .. {last_week}）"
    )
    return {"status": "ok", "rows": row_count, "note": note}


# ---------------------------------------------------------------------------
# 公开入口二：merge()
# ---------------------------------------------------------------------------

def _write_weekly_csv(handle, rows) -> None:
    """按 7 列中文表头写出周度 CSV（截止日期 yyyy-MM-dd，空数值留空）。"""

    writer = csv.writer(handle)
    writer.writerow(WEEKLY_CSV_HEADERS)
    for week_end, confirmed, sales, active, launch, absorption, transition in rows:
        writer.writerow(
            [
                f"{_as_date(week_end):%Y-%m-%d}",
                "" if confirmed is None else str(int(round(confirmed))),
                "" if sales is None else str(int(round(sales))),
                "" if active is None else str(int(round(active))),
                "" if launch is None else formatted(launch),
                "" if absorption is None else formatted(absorption),
                "" if transition is None else formatted(transition),
            ]
        )


def merge(workbook_path: Path) -> dict:
    """查询周度表 → 导出 7 列临时 CSV → 调用 ps1 写回工作簿。

    临时 CSV 放在 data/ 下（防止跨盘权限问题）；成功则删除，失败则保留
    并在抛出的异常信息中给出路径以便排查。
    """

    workbook_path = Path(workbook_path).resolve()
    if not WORKBOOK_MERGER.exists():
        raise FileNotFoundError(WORKBOOK_MERGER)
    if not workbook_path.exists():
        raise FileNotFoundError(workbook_path)

    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            "SELECT week_end, confirmed_new_projects_28d, offplan_sales_28d, "
            "active_projects_28d, project_launch_index, "
            "offplan_absorption_index, project_commercial_transition_index "
            "FROM dld_investment_pipeline_weekly ORDER BY week_end"
        ).fetchall()
    finally:
        con.close()
    if not rows:
        raise RuntimeError("dld_investment_pipeline_weekly 为空，无法合并")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            prefix=".dld_indices_",
            suffix=".csv",
            dir=DATA_DIR,
            encoding="utf-8-sig",
            newline="",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            _write_weekly_csv(handle, rows)

        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(WORKBOOK_MERGER),
                "-CsvPath",
                str(temporary_path),
                "-WorkbookPath",
                str(workbook_path),
                "-SourceDataThrough",
                f"{_as_date(rows[-1][0]):%Y-%m-%d}",
                "-SheetName",
                WORKSHEET_NAME,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Excel 写表失败（临时 CSV 已保留供排查）: "
                + ((completed.stderr or completed.stdout or "").strip())
            )
        temporary_path.unlink(missing_ok=True)
        temporary_path = None
    except Exception:
        if temporary_path is not None and temporary_path.exists():
            print(
                f"[source_dld] 临时 CSV 保留以便排查: {temporary_path}",
                flush=True,
            )
        raise

    latest = f"{_as_date(rows[-1][0]):%Y-%m-%d}"
    return {
        "status": "ok",
        "note": f"已写入 {workbook_path.name}：共 {len(rows)} 行周度数据，"
        f"截至 {latest}",
    }


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def self_check() -> str:
    """不触碰真实库/网络/工作簿的自检：纯函数冒烟 + 常量完整性。"""

    assert parse_float(None) is None
    assert parse_float("") is None
    assert parse_float("12.5") == 12.5
    assert log_momentum(9.0, 2.0) == math.log1p(9.0) - math.log1p(2.0)
    assert log_momentum(-1.0, 2.0) is None
    assert log_momentum(5.0, None) is None
    assert score_from_z(None) is None
    assert score_from_z(0.0) == 50.0
    assert score_from_z(5.0) == 100.0
    assert score_from_z(-5.0) == 0.0
    assert score_from_z(9.0) == 100.0
    assert formatted(None) == ""
    assert formatted(5) == "5"
    assert formatted(5.5) == "5.500000"
    assert len(INDICATOR_DICTIONARY) == 6
    assert len(COLUMN_DICTIONARY) == len(KEEP_COLUMNS) == 8
    assert all(len(row) == 7 for row in COLUMN_DICTIONARY)
    assert {row[1] for row in COLUMN_DICTIONARY} == set(KEEP_COLUMNS)
    assert [row[0] for row in INDICATOR_DICTIONARY] == list(WEEKLY_CSV_HEADERS[1:])
    assert "FROM dld.transactions" in RAW_WEEKLY_SQL
    # 周度 SQL 与视图所需列必须全部属于保留列
    required = {
        "actual_worth",
        "instance_date",
        "project_number",
        "property_type_en",
        "reg_type_en",
        "trans_group_en",
        "transaction_id",
    }
    assert required <= set(KEEP_COLUMNS)
    # 短序列冒烟：build_rows 输出形状与 None 传播
    small = [
        {
            "week_start": "2009-01-05",
            "week_end": "2009-01-11",
            "source_data_through": "2026-08-10",
            "initial_new_projects": "3",
            "confirmed_new_projects": "2",
            "confirmed_new_projects_28d": "10",
            "offplan_sales_28d": "100",
            "offplan_sales_value_28d": "50000",
            "active_projects_28d": "20",
            "offplan_sales_per_active_project_28d": "5.0",
            "project_number_coverage_pct_28d": "99.5",
            "commercial_transition_projects": "1",
            "commercial_transition_projects_13w": "12",
        }
    ]
    built = build_rows(small)
    assert len(built) == 1
    assert built[0]["confirmed_launch_yoy_log_momentum"] is None
    assert built[0]["confirmed_launch_z"] is None
    assert built[0]["offplan_absorption_score"] is None
    assert built[0]["quality_flag"] == "ok"
    return "source_dld 自检通过：模块导入、纯函数、常量完整性与短序列冒烟检查均 OK"


if __name__ == "__main__":
    print(self_check())
    print()
    print("用法提示：")
    print("  1) 全量更新（含库迁移/建表与周度指标）:")
    print("     import source_dld, db; con = db.connect(); source_dld.update(con)")
    print("  2) 跳过下载仅本地重建: update(con, skip_download=True)")
    print("  3) 强制重新下载原始快照: update(con, force=True)")
    print("  4) 写回工作簿: source_dld.merge(Path('data/UAE/阿联酋.xlsx'))")