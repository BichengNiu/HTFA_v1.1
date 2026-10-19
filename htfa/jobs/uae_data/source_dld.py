"""Dubai Land Department sales and lease indicators.

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
import math
import os
import re
import statistics
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from htfa.data.temporal import last_complete_month_end

from .paths import DATA_DIR, SCRIPTS_DIR
from ._excel_helpers import run_powershell_command
from ._official_download import write_json_atomic


from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量：计算窗口与发布起点
# ---------------------------------------------------------------------------

PUBLICATION_START = date(2015, 1, 5)
YOY_WEEKS = 52
BASELINE_WEEKS = 156
MIN_BASELINE_OBSERVATIONS = 104

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
WORKBOOK_MERGER = SCRIPTS_DIR / "merge_dld_indices_into_uae_workbook.ps1"

# ---------------------------------------------------------------------------
# 周度原始口径 SQL：查询 detail.dld_transactions 统一长表。
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
        CASE
            WHEN max(instance_date) IS NULL THEN NULL
            WHEN max(instance_date) >= CAST(
                date_trunc('month', max(instance_date))
                + INTERVAL 1 MONTH - INTERVAL 1 DAY AS DATE
            )
                THEN CAST(
                    date_trunc('month', max(instance_date))
                    + INTERVAL 1 MONTH - INTERVAL 1 DAY AS DATE
                )
            ELSE CAST(date_trunc('month', max(instance_date)) AS DATE) - 1
        END AS last_complete_month_end,
        max(instance_date) AS source_data_through
    FROM detail.dld_transactions
),
calendar AS (
    SELECT
        CAST(gs AS DATE) AS week_start,
        CAST(gs AS DATE) + 6 AS week_end,
        bounds.source_data_through
    FROM bounds,
         generate_series(bounds.first_week, bounds.last_complete_week, INTERVAL 7 DAY) AS t(gs)
    WHERE CAST(gs AS DATE) + 6 <= bounds.last_complete_month_end
),
offplan_sales AS (
    SELECT
        transaction_id,
        instance_date,
        CAST(date_trunc('week', instance_date) AS DATE) AS week_start,
        project_number,
        actual_worth
    FROM detail.dld_transactions
    CROSS JOIN bounds
    WHERE trans_group_en = 'Sales'
      AND reg_type_en = 'Off-Plan Properties'
      AND instance_date >= DATE '2009-01-05' - INTERVAL 27 DAY
      AND instance_date <= bounds.last_complete_month_end
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
    FROM detail.dld_transactions
    CROSS JOIN bounds
    WHERE trans_group_en = 'Sales'
      AND reg_type_en = 'Off-Plan Properties'
      AND project_number IS NOT NULL
      AND instance_date <= bounds.last_complete_month_end
    GROUP BY project_number
),
project_launch_confirmed AS (
    SELECT
        p.project_number,
        p.first_offplan_sale_date,
        count(t.transaction_id) AS sales_first_28d
    FROM project_launch p
    CROSS JOIN bounds
    LEFT JOIN detail.dld_transactions t
      ON t.project_number = p.project_number
     AND t.trans_group_en = 'Sales'
     AND t.reg_type_en = 'Off-Plan Properties'
     AND t.instance_date BETWEEN p.first_offplan_sale_date
                             AND p.first_offplan_sale_date + 27
     AND t.instance_date <= bounds.last_complete_month_end
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
    FROM detail.dld_transactions
    CROSS JOIN bounds
    WHERE trans_group_en = 'Sales'
      AND project_number IS NOT NULL
      AND instance_date <= bounds.last_complete_month_end
    GROUP BY project_number
),
project_transition AS (
    SELECT
        p.project_number,
        p.first_offplan_sale,
        p.first_existing_sale,
        count(t.transaction_id) AS offplan_sales_before_existing
    FROM project_dates p
    CROSS JOIN bounds
    LEFT JOIN detail.dld_transactions t
      ON t.project_number = p.project_number
     AND t.trans_group_en = 'Sales'
     AND t.reg_type_en = 'Off-Plan Properties'
     AND t.instance_date < p.first_existing_sale
     AND t.instance_date <= bounds.last_complete_month_end
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
# 指标字典：6 个周度指标（即 ps1 的 7 列 headers 去掉「截止日期」）。
# type/industry 对应工作簿「指标字典」中的当前指标分类。
# ---------------------------------------------------------------------------

INDICATOR_DICTIONARY = (
    ("经确认新期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
    ("期房销售笔数_近28天", "周", "笔", "Dubai Land Department", "交易笔数", "房地产"),
    ("活跃期房项目数_近28天", "周", "个", "Dubai Land Department", "项目数", "房地产"),
    ("项目启动指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
    ("期房销售吸收指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
    ("项目商业转化指数", "周", "指数", "Dubai Land Department", "指数", "房地产"),
)

# merge() 导出 CSV 的 7 列名，供当前 DLD 工作表写入脚本使用。
WEEKLY_CSV_HEADERS = (
    "截止日期",
    "经确认新期房项目数_近28天",
    "期房销售笔数_近28天",
    "活跃期房项目数_近28天",
    "项目启动指数",
    "期房销售吸收指数",
    "项目商业转化指数",
)

# ---------------------------------------------------------------------------
# 月度指标（2026-08 新增）：销售 4 指标（本地精确聚合）+ 租赁合同 5 指标
# （DLD Mo'asher 官方边缘口径，Property Finder Insights Hub 镜像）。
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

# 租赁合同边缘指标（Mo'asher Rental Performance Index 页面发布口径）。
LEASE_INDICATORS = (
    "lease_contracts_total",   # 当季/当月租赁合同总数（份）
    "lease_new_pct",           # 新签占比（%）
    "lease_renewed_pct",       # 续签占比（%）
    "lease_residential_pct",   # 住宅用途占比（%）
    "lease_commercial_pct",    # 商业用途占比（%）
)

# Mo'asher 月度页 URL 清单（Property Finder Insights Hub 镜像；每月两版：
# Official Sales Price Index / Official Rental Performance Index，按标题判别）。
# 由本模块生成/维护到 raw/dld/moasher_page_urls.txt（原始清单，不入 Git）。
MOASHER_URLS_FILE = RAW_DLD_DIR / "moasher_page_urls.txt"
MOASHER_BASE = "https://www.propertyfinder.ae/en/insightshub/moasher/"

# 月度_DLD sheet 数据列（与 MERGE 写表一一对应；A 列为日期）。
MONTHLY_SHEET_HEADERS = (
    "日期",
    "迪拜:期房销售-住宅笔数",
    "迪拜:期房销售-住宅金额(百万AED)",
    "迪拜:现房销售-住宅笔数",
    "迪拜:现房销售-住宅金额(百万AED)",
    "迪拜:期房销售-商业笔数",
    "迪拜:期房销售-商业金额(百万AED)",
    "迪拜:现房销售-商业笔数",
    "迪拜:现房销售-商业金额(百万AED)",
    "迪拜:租赁合同总数(份)",
    "迪拜:租赁合同-新签占比(%)",
    "迪拜:租赁合同-续签占比(%)",
    "迪拜:租赁合同-住宅占比(%)",
    "迪拜:租赁合同-商业占比(%)",
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
    ("迪拜:租赁合同总数(份)", "月", "份", "Dubai Land Department (Mo'asher)", "合同数", "房地产"),
    ("迪拜:租赁合同-新签占比(%)", "月", "%", "Dubai Land Department (Mo'asher)", "占比", "房地产"),
    ("迪拜:租赁合同-续签占比(%)", "月", "%", "Dubai Land Department (Mo'asher)", "占比", "房地产"),
    ("迪拜:租赁合同-住宅占比(%)", "月", "%", "Dubai Land Department (Mo'asher)", "占比", "房地产"),
    ("迪拜:租赁合同-商业占比(%)", "月", "%", "Dubai Land Department (Mo'asher)", "占比", "房地产"),
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
# 数值与指数计算
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
    """格式化指标值：整数原样，浮点保留 digits 位小数。"""

    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def build_rows(raw_rows):
    """由 RAW_WEEKLY_SQL 的原始行计算全部派生指标。

    ``raw_rows`` 每行是一个 dict，键为 RAW_WEEKLY_SQL 的 13 个输出列；
    数值列必须是 DuckDB 返回的数值类型。
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
            row[column] = _numeric_value(row[column], column=column)

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


def _rounded_count(value):
    """计数列入库值：None 保持 None，否则四舍五入为整数。"""

    return None if value is None else int(round(value))


def _rounded_score(value):
    """指数列入库值：None 保持 None，否则保留 6 位小数。"""

    return None if value is None else round(value, 6)


def to_weekly_table_rows(built_rows):
    """把 build_rows 的结果映射成 dld_investment_pipeline_weekly 的入库行。

    仅保留 week_start >= PUBLICATION_START 的发布周；week_end 转为 DATE，
    数值列使用整数计数、6 位小数指数，None 原样保留。
    """

    rows = []
    for row in built_rows:
        if row["week_start"] < PUBLICATION_START:
            continue
        rows.append(
            {
                "week_end": row["week_end"],
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
# b) 租赁合同指标：DLD Mo'asher Rental Performance Index 官方边缘口径
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


def _moasher_month_from_slug(slug: str) -> date | None:
    """'2023-monthly-january' -> 2023-01-31（月末日期；解析失败返回 None）。"""

    match = re.search(r"(\d{4})-monthly-([a-z]+)", slug)
    if not match:
        return None
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
        "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    month = months.get(match.group(2))
    if month is None:
        return None
    year = int(match.group(1))
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _parse_moasher_rental(html: str, slug: str | None = None) -> dict | None:
    """解析 Mo'asher 页面文本，返回租赁指标字典；非租赁版返回 None。

    官方口径（例：2024-09）："67,278 rental contracts, of which 59% of
    contracts were new and 41% were renewals…62.6% were registered for
    residential purposes, while 37.4% were for commercial and other purposes"。
    页面上数字格式在 2022–2024 年间有 "59%" / "53.64 percent" / "recorded
    X leases" / "had X leases" 等多种写法；个别页面是整季报告（如 2022-03 的
    Q1 季报），必须按「月份名所在句子」取当月值，避免把季合计错当当月值。
    解析失败的值以 None 占位，不静默丢弃整月。
    """

    title = re.search(r"<title>(.*?)</title>", html, re.S)
    if not title or "Rental Performance" not in title.group(1):
        return None
    text = re.sub(r"<title>.*?</title>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    month_name = None
    if slug:
        match = re.search(r"(\d{4})-monthly-([a-z]+)", slug)
        if match:
            month_name = match.group(2)
    month_pattern = rf"\b{month_name}\b" if month_name else None
    if month_pattern:
        month_sentences = [
            sentence
            for sentence in re.split(r"[•\n]", text)
            if re.search(month_pattern, sentence, re.I)
        ]
        month_text = " ".join(month_sentences) or text
    else:
        month_text = text

    # 数字解析统一入口：月中句子优先（避免季报误配），否则全文
    def first_pct(source: str, *patterns: str) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, source, re.I)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    total = first_pct(
        month_text,
        r"had a total of\s*([\d,]+)\s*(?:rental contracts|rental leases)",
        r"recorded\s*([\d,]+)\s*(?:rental contracts|rental leases)",
        r"had\s+([\d,]+)\s*(?:rental )?leases?\b",
        r"had\s+([\d,]+)\s*(?:rental )?contracts\b",
    )
    if total is None and month_text is not text:
        total = first_pct(
            text,
            r"had a total of\s*([\d,]+)\s*(?:rental contracts|rental leases)",
            r"recorded\s*([\d,]+)\s*(?:rental contracts|rental leases)",
            r"had\s+([\d,]+)\s*(?:rental )?leases?\b",
            r"had\s+([\d,]+)\s*(?:rental )?contracts\b",
        )
    new_pct = first_pct(
        month_text,
        r"([\d.]+)\s*percent\s*(?:of contracts\s*)?were new\b",
        r"([\d.]+)\s*%\s*(?:of contracts\s*)?were new\b",
        r"([\d.]+)\s*%\s*of contracts were new",
        r"([\d.]+)\s*(?:percent|%)\s*were new leases",
    )
    if new_pct is None and month_text is not text:
        new_pct = first_pct(
            text,
            r"([\d.]+)\s*percent\s*(?:of contracts\s*)?were new\b",
            r"([\d.]+)\s*%\s*(?:of contracts\s*)?were new\b",
            r"([\d.]+)\s*%\s*of contracts were new",
            r"([\d.]+)\s*(?:percent|%)\s*were new leases",
        )
    renewed_pct = first_pct(
        month_text,
        r"([\d.]+)\s*percent\s*(?:of contracts\s*)?were renewals?\b",
        r"([\d.]+)\s*%\s*(?:of contracts\s*)?were renewals?\b",
        r"were\s+([\d.]+)\s*(?:percent|%)\s*renewals?\b",
        r"([\d.]+)\s*(?:percent|%)\s*were renewals?\b",
    )
    if renewed_pct is None and month_text is not text:
        renewed_pct = first_pct(
            text,
            r"([\d.]+)\s*percent\s*(?:of contracts\s*)?were renewals?\b",
            r"([\d.]+)\s*%\s*(?:of contracts\s*)?were renewals?\b",
            r"were\s+([\d.]+)\s*(?:percent|%)\s*renewals?\b",
            r"([\d.]+)\s*(?:percent|%)\s*were renewals?\b",
        )
    residential_pct = first_pct(
        month_text,
        r"([\d.]+)\s*percent\s*(?:were|of contracts were)\s*registered for residential",
        r"([\d.]+)\s*%\s*(?:were|of contracts were)\s*registered for residential",
        r"([\d.]+)\s*(?:percent|%)\s*were residential leases",
    )
    if residential_pct is None and month_text is not text:
        residential_pct = first_pct(
            text,
            r"([\d.]+)\s*percent\s*(?:were|of contracts were)\s*registered for residential",
            r"([\d.]+)\s*%\s*(?:were|of contracts were)\s*registered for residential",
            r"([\d.]+)\s*(?:percent|%)\s*were residential leases",
        )
    commercial_pct = first_pct(
        month_text,
        r"([\d.]+)\s*percent\s*(?:were|of contracts were)\s*(?:registered )?for commercial",
        r"([\d.]+)\s*%\s*(?:were|of contracts were)\s*(?:registered )?for commercial",
        r"([\d.]+)\s*(?:percent|%)\s*were commercial (?:and other )?leases",
    )
    if commercial_pct is None and month_text is not text:
        commercial_pct = first_pct(
            text,
            r"([\d.]+)\s*percent\s*(?:were|of contracts were)\s*(?:registered )?for commercial",
            r"([\d.]+)\s*%\s*(?:were|of contracts were)\s*(?:registered )?for commercial",
            r"([\d.]+)\s*(?:percent|%)\s*were commercial (?:and other )?leases",
        )
    if total is None and new_pct is None and renewed_pct is None:
        return None
    if total is not None:
        total = int(total)
    return {
        "lease_contracts_total": total,
        "lease_new_pct": new_pct,
        "lease_renewed_pct": renewed_pct,
        "lease_residential_pct": residential_pct,
        "lease_commercial_pct": commercial_pct,
    }


def _fetch_moasher_page(
    url: str, cached_dir: Path, *, skip_download: bool
) -> str:
    """Fetch one Mo'asher page or require its exact cache in offline mode."""

    cached_dir.mkdir(parents=True, exist_ok=True)
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    cache_path = cached_dir / f"{slug}.html"
    if skip_download:
        if not cache_path.is_file():
            raise FileNotFoundError(f"Mo'asher offline page cache not found: {cache_path}")
        return cache_path.read_text(encoding="utf-8")
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    )
    html = _http_read(request, timeout=60, retries=3)
    cache_path.write_text(html, encoding="utf-8")
    return html

def _discover_moasher_urls() -> list[str]:
    """从 Property Finder Insights Hub 分页发现全部 Mo'asher 月度页 URL 并落盘。"""

    found: set[str] = set()
    for page_no in range(1, 13):
        url = f"https://www.propertyfinder.ae/en/insightshub?page={page_no}"
        request = urllib.request.Request(
            url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        )
        html = _http_read(request, timeout=60, retries=2)
        for slug in re.findall(
            r"insightshub/moasher/(\d{4}-monthly-[a-z]+-\d+)", html
        ):
            found.add(MOASHER_BASE + slug)
        state = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S
        )
        if state is None:
            raise ValueError("Property Finder listing is missing pagination data")
        listing = json.loads(state.group(1))["props"]["pageProps"]["list"]
        pagination = listing["pagination"]
        page_count = int(pagination["pageCount"])
        if int(pagination["page"]) != page_no or page_count > 12:
            raise ValueError("Property Finder listing pagination exceeds scan bounds")
        if page_no >= page_count:
            break
    urls = sorted(found)
    if urls:
        MOASHER_URLS_FILE.write_text("\n".join(urls), encoding="utf-8")
    return urls


def _moasher_urls(*, skip_download: bool) -> list[str]:
    """Read the explicit offline URL list or discover current online pages."""

    if skip_download:
        if not MOASHER_URLS_FILE.is_file():
            raise FileNotFoundError(
                f"Mo'asher offline URL list not found: {MOASHER_URLS_FILE}"
            )
        urls = [
            line.strip("\ufeff \t\r\n")
            for line in MOASHER_URLS_FILE.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not urls:
            raise ValueError(f"Mo'asher offline URL list is empty: {MOASHER_URLS_FILE}")
        return urls
    discovered = _discover_moasher_urls()
    if not discovered:
        raise ValueError("Mo'asher online discovery returned no monthly pages")
    return discovered

def build_lease_monthly(*, skip_download: bool = False) -> list[dict]:
    """抓取/解析 Mo'asher 租赁指数页面，输出 dld_lease_monthly 入库行。

    页面按标题判别：仅处理 "Official Rental Performance Index"（租赁版）；
    销售指数版跳过。解析失败的值以 None 入库（Excel 留空），源码 URL 记录
    在 source_url 以便追溯。
    """

    urls = _moasher_urls(skip_download=skip_download)
    cached_dir = RAW_DLD_DIR / "moasher"
    rows: list[dict] = []
    seen: set[date] = set()
    for url in urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        # Rental pages can be revised at the same URL; online mode must
        # refresh them, while skip_download explicitly reuses HTML cache.
        html = _fetch_moasher_page(
            url,
            cached_dir,
            skip_download=skip_download,
        )
        parsed = _parse_moasher_rental(html, slug=slug)
        if parsed is None:
            continue
        period = _moasher_month_from_slug(slug)
        if period is None:
            raise ValueError(f"Mo'asher 页面月份无法解析: {slug}")
        if period in seen:
            continue  # 同月有两个变体 URL（EN 镜像重复）；取首个
        seen.add(period)
        for indicator in LEASE_INDICATORS:
            rows.append(
                {
                    "period": period,
                    "indicator": indicator,
                    "value": parsed.get(indicator),
                    "source_url": url,
                }
            )
    return rows


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
    """完整下载 Data Dubai 官方 bulk 快照并合并到 data/UAE/raw/dld/。

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

    built = build_rows(_fetch_raw_weekly(con))
    weekly_rows = to_weekly_table_rows(built)
    sales_rows = build_sales_monthly(con)
    lease_rows = build_lease_monthly(skip_download=skip_download)

    with db.transaction(con):
        row_count = db.replace(con, "dld_investment_pipeline_weekly", weekly_rows)
        row_count += db.replace(con, "dld_sales_monthly", sales_rows)
        row_count += db.replace(con, "dld_lease_monthly", lease_rows)
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
    lease_months = sorted({row["period"] for row in lease_rows})
    note = (
        f"{path_note}；周度指标 {row_count - len(sales_rows) - len(lease_rows)} 行"
        f"（{first_week} .. {last_week}）；月度销售 {len(sales_rows)} 行"
        f"（{sales_months[0]:%Y-%m} .. {sales_months[-1]:%Y-%m}）；"
        f"月度租赁合同 {len(lease_rows)} 行"
        f"（{lease_months[0]:%Y-%m} .. {lease_months[-1]:%Y-%m}）"
        if sales_months and lease_months
        else f"{path_note}；周度指标 {row_count} 行（{first_week} .. {last_week}）"
    )
    return {"status": "ok", "rows": row_count, "note": note}


# ---------------------------------------------------------------------------
# 公开入口二：merge()
# ---------------------------------------------------------------------------

def _query_monthly_rows() -> list[dict]:
    """从 dld_sales_monthly / dld_lease_monthly 组装「月度_DLD」14 列行（月末降序）。

    销售金额由 AED 原值折算为百万 AED（保留 3 位）；租赁占比为官方发布值；
    缺失月份不补齐（约定：缺报留空，不插值、不前向填充）。
    """

    con = db.connect(read_only=True)
    try:
        sales = con.execute(
            "SELECT period, indicator, count, value_aed "
            "FROM dld_sales_monthly ORDER BY period, indicator"
        ).fetchall()
        lease = con.execute(
            "SELECT period, indicator, value "
            "FROM dld_lease_monthly ORDER BY period, indicator"
        ).fetchall()
    finally:
        con.close()

    sales_map: dict[tuple[date, str], tuple[int | None, float | None]] = {
        (row[0], row[1]): (row[2], row[3]) for row in sales
    }
    lease_map: dict[tuple[date, str], float | None] = {
        (row[0], row[1]): row[2] for row in lease
    }
    periods = sorted(
        {row[0] for row in sales} | {row[0] for row in lease}, reverse=True
    )
    rows = []
    for period in periods:
        values = []
        for key in ("residential_offplan_sales", "residential_ready_sales",
                    "commercial_offplan_sales", "commercial_ready_sales"):
            count, value = sales_map.get((period, key), (None, None))
            values.append(count)
            values.append(None if value is None else round(value / 1_000_000, 3))
        for indicator in LEASE_INDICATORS:
            values.append(lease_map.get((period, indicator)))
        rows.append({"period": period, "values": values})
    return rows


def _write_monthly_sheet(workbook_path: Path) -> int:
    """以 openpyxl 直写「月度_DLD」sheet（参照 source_ded 的 update_sheet）。

    头部 6 行元信息（指标名称/频率/单位/来源/更新时间）+ 数据行按月降序；
    缺失值写入空单元格。返回写入的数据行数。
    """

    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill

    header_font = Font(name="Microsoft YaHei", size=9, bold=True)
    body_font = Font(name="Microsoft YaHei", size=9)
    header_fill = PatternFill("solid", fgColor="D9E1F2")

    rows = _query_monthly_rows()
    wb = load_workbook(workbook_path)
    if MONTHLY_WORKSHEET_NAME in wb.sheetnames:
        del wb[MONTHLY_WORKSHEET_NAME]
    ws = wb.create_sheet(MONTHLY_WORKSHEET_NAME)

    headers = MONTHLY_SHEET_HEADERS
    units = [row[2] for row in MONTHLY_INDICATOR_DICTIONARY]
    sources = [row[3] for row in MONTHLY_INDICATOR_DICTIONARY]
    ws.cell(row=1, column=1, value="Dubai Land Department（迪拜土地局）月度指标")
    ws.cell(row=2, column=1, value="指标名称")
    ws.cell(row=3, column=1, value="频率")
    ws.cell(row=4, column=1, value="单位")
    ws.cell(row=5, column=1, value="来源")
    ws.cell(row=6, column=1, value="更新时间")
    for col, header in enumerate(headers[1:], start=2):
        ws.cell(row=2, column=col, value=header)
    for col, unit in enumerate(units, start=2):
        ws.cell(row=3, column=col, value="月")
        ws.cell(row=4, column=col, value=unit)
        ws.cell(row=5, column=col, value=sources[col - 2])
    now = datetime.now()
    for col in range(2, len(headers) + 1):
        ws.cell(row=6, column=col, value=now)

    for i, row in enumerate(rows):
        r = 7 + i
        ws.cell(row=r, column=1, value=row["period"])
        for col, value in enumerate(row["values"], start=2):
            ws.cell(row=r, column=col, value=value)

    for cell in ws[1]:
        cell.font = Font(name="Microsoft YaHei", size=11, bold=True)
    for row_cells in ws.iter_rows(min_row=2, max_row=6, max_col=len(headers)):
        for cell in row_cells:
            cell.font = header_font
            cell.fill = header_fill
    for row_cells in ws.iter_rows(min_row=7, max_row=ws.max_row, max_col=len(headers)):
        for cell in row_cells:
            cell.font = body_font

    ws.column_dimensions["A"].width = 13
    for label, width in zip("BCDEFGHIJKLMN", (18, 22, 18, 26, 18, 26, 18, 26, 18, 20, 20, 20, 20)):
        ws.column_dimensions[label].width = width
    ws.freeze_panes = "B7"

    wb.save(workbook_path)
    return len(rows)


def _write_weekly_csv(handle, rows) -> None:
    """按 7 列中文表头写出周度 CSV（截止日期 yyyy-MM-dd，空数值留空）。"""

    writer = csv.writer(handle)
    writer.writerow(WEEKLY_CSV_HEADERS)
    for week_end, confirmed, sales, active, launch, absorption, transition in rows:
        writer.writerow(
            [
                f"{week_end:%Y-%m-%d}",
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

        completed = run_powershell_command(
            (
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
                f"{rows[-1][0]:%Y-%m-%d}",
                "-SheetName",
                WORKSHEET_NAME,
            )
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

    latest = f"{rows[-1][0]:%Y-%m-%d}"
    monthly_rows = _write_monthly_sheet(workbook_path)
    return {
        "status": "ok",
        "note": f"已写入 {workbook_path.name}：周度 {len(rows)} 行截至 {latest}；"
        f"「{MONTHLY_WORKSHEET_NAME}」月度数据 {monthly_rows} 行按月降序",
    }


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
