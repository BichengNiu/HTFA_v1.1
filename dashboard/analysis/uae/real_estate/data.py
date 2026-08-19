"""从阿联酋工作簿读取 DLD 迪拜房地产月度销售数据。

``月度_DLD`` 沿用页面前六行元数据协议，但 8 个销售列单位混合
（笔数“笔”、金额“百万AED”），因此用定制解析（与 ``ded`` 一致），
并把住宅、商业两个分市场合并为「期房/现房 × 笔数/金额」四个聚合口径，
与用户「期房、现房笔数和金额」的展示口径一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    format_updated_at,
    open_uae_workbook,
    optional_text,
)
from dashboard.preview.core.workbook_parser import normalize_indicator_name


DLD_SHEET = "月度_DLD"

OFFPLAN_COUNT = "期房销售笔数"
OFFPLAN_AMOUNT = "期房销售金额"
READY_COUNT = "现房销售笔数"
READY_AMOUNT = "现房销售金额"

# 月度_DLD 销售 8 列：4 分市场 ×（笔数/金额），(展示名, 原始指标名, 单位)。
SALES_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("期房住宅笔数", "迪拜:期房销售-住宅笔数", "笔"),
    ("期房住宅金额", "迪拜:期房销售-住宅金额(百万AED)", "百万AED"),
    ("现房住宅笔数", "迪拜:现房销售-住宅笔数", "笔"),
    ("现房住宅金额", "迪拜:现房销售-住宅金额(百万AED)", "百万AED"),
    ("期房商业笔数", "迪拜:期房销售-商业笔数", "笔"),
    ("期房商业金额", "迪拜:期房销售-商业金额(百万AED)", "百万AED"),
    ("现房商业笔数", "迪拜:现房销售-商业笔数", "笔"),
    ("现房商业金额", "迪拜:现房销售-商业金额(百万AED)", "百万AED"),
)

# 4 个聚合口径：住宅 + 商业 合计（min_count=1：仅当两个分市场当月都缺失才留空）。
AGGREGATE_TARGETS: tuple[tuple[str, tuple[str, str], str], ...] = (
    (OFFPLAN_COUNT, ("期房住宅笔数", "期房商业笔数"), "笔"),
    (OFFPLAN_AMOUNT, ("期房住宅金额", "期房商业金额"), "百万AED"),
    (READY_COUNT, ("现房住宅笔数", "现房商业笔数"), "笔"),
    (READY_AMOUNT, ("现房住宅金额", "现房商业金额"), "百万AED"),
)

AGGREGATED_COLUMNS: tuple[str, ...] = (
    OFFPLAN_COUNT,
    OFFPLAN_AMOUNT,
    READY_COUNT,
    READY_AMOUNT,
)


@dataclass(frozen=True)
class RealEstateData:
    """迪拜房地产月度销售的最小数据集（期房/现房 × 笔数/金额，全市场合计）。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_real_estate_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> RealEstateData:
    """只读取 ``月度_DLD`` 的 8 个销售列并合并为 4 个聚合口径。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        series_map, raw_metadata = _parse_sales_sheet(excel_file)
        values, metadata = _aggregate_sales(series_map, raw_metadata)

    return RealEstateData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def _parse_sales_sheet(
    excel_file: pd.ExcelFile,
) -> tuple[dict[str, pd.Series], dict[str, SheetSeriesMetadata]]:
    """解析 DLD 销售 8 列（单位：笔 / 百万AED）。

    ``月度_DLD`` 的写表器把 A2 写成日期列头「日期」（覆盖「指标名称」标签），
    因此元数据行按标签扫描定位（频率/单位/来源/更新时间），指标名统一取自
    第 2 行（零基行 1）；标准「指标名称」布局同样兼容。
    """

    if DLD_SHEET not in excel_file.sheet_names:
        raise ValueError(f"工作簿缺少“{DLD_SHEET}”sheet")

    raw = pd.read_excel(excel_file, sheet_name=DLD_SHEET, header=None)
    if raw.shape[0] < 7 or raw.shape[1] < 2:
        raise ValueError(f"sheet“{DLD_SHEET}”不符合前六行元数据协议")
    metadata_rows = _scan_metadata_rows(raw)

    normalized_targets = {
        normalize_indicator_name(indicator_name): display_name
        for display_name, indicator_name, _ in SALES_COLUMNS
    }
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        normalized_name = normalize_indicator_name(raw.iloc[1, column_index])
        if normalized_name in normalized_targets:
            candidate_columns.setdefault(
                normalized_targets[normalized_name], []
            ).append(column_index)

    matching_columns: dict[str, int] = {}
    for display_name, indicator_name, unit in SALES_COLUMNS:
        columns = candidate_columns.get(display_name, [])
        compatible = [
            column_index
            for column_index in columns
            if optional_text(raw.iloc[metadata_rows["频率"], column_index])
            in {"月", "月度"}
            and optional_text(raw.iloc[metadata_rows["单位"], column_index])
            == unit
            and bool(
                optional_text(raw.iloc[metadata_rows["来源"], column_index])
            )
        ]
        if len(compatible) != 1:
            if not columns:
                raise ValueError(f"sheet“{DLD_SHEET}”缺少指标：{indicator_name}")
            raise ValueError(
                f"指标“{indicator_name}”应有唯一一列月度、单位“{unit}”、"
                f"来源非空的观测"
            )
        matching_columns[display_name] = compatible[0]

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{DLD_SHEET}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{DLD_SHEET}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for display_name, column_index in matching_columns.items():
        raw_values = data_block.iloc[:, column_index]
        numeric = pd.to_numeric(raw_values, errors="coerce")
        invalid = (
            raw_values.notna()
            & raw_values.astype(str).str.strip().ne("")
            & numeric.isna()
        )
        if invalid.any():
            row_number = int(invalid[invalid].index[0]) + 1
            raise ValueError(
                f"sheet“{DLD_SHEET}”指标“{display_name}”"
                f"第{row_number}行不是数值"
            )
        series = pd.Series(
            numeric.mask(numeric.eq(0)).to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=display_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{display_name}”没有非零有效观测")
        series_map[display_name] = series
        indicator_name = normalize_indicator_name(raw.iloc[1, column_index])
        metadata[display_name] = SheetSeriesMetadata(
            display_name=display_name,
            indicator_name=indicator_name,
            frequency=optional_text(
                raw.iloc[metadata_rows["频率"], column_index]
            ),
            unit=optional_text(raw.iloc[metadata_rows["单位"], column_index]),
            source=optional_text(raw.iloc[metadata_rows["来源"], column_index]),
            updated_at=format_updated_at(
                raw.iloc[metadata_rows["更新时间"], column_index]
            ),
            sheet_name=DLD_SHEET,
        )
    return series_map, metadata


def _scan_metadata_rows(raw: pd.DataFrame) -> dict[str, int]:
    """在前六行中按首列标签定位频率/单位/来源/更新时间的行号。"""

    positions: dict[str, int] = {}
    for row_index in range(1, 6):
        label = optional_text(raw.iloc[row_index, 0])
        if label in {"频率", "单位", "来源", "更新时间"}:
            if label in positions:
                raise ValueError(
                    f"sheet“{DLD_SHEET}”元数据标签“{label}”重复出现"
                )
            positions[label] = row_index
    missing = [
        label for label in ("频率", "单位", "来源", "更新时间")
        if label not in positions
    ]
    if missing:
        raise ValueError(
            f"sheet“{DLD_SHEET}”前六行缺少元数据标签：{'、'.join(missing)}"
        )
    return positions


def _aggregate_sales(
    series_map: dict[str, pd.Series],
    raw_metadata: dict[str, SheetSeriesMetadata],
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """把 8 个分市场序列合并为 4 个「期房/现房 × 笔数/金额」聚合列。"""

    raw_frame = pd.concat(
        [series_map[name] for name, _, _ in SALES_COLUMNS],
        axis=1,
        sort=False,
    ).sort_index()

    values = pd.DataFrame(index=raw_frame.index)
    metadata: dict[str, SheetSeriesMetadata] = {}
    for aggregate_name, parts, unit in AGGREGATE_TARGETS:
        example = raw_metadata[parts[0]]
        series = (
            raw_frame[list(parts)]
            .sum(axis=1, min_count=1)
            .rename(aggregate_name)
            .dropna()
        )
        values[aggregate_name] = series
        metadata[aggregate_name] = SheetSeriesMetadata(
            display_name=aggregate_name,
            indicator_name=" + ".join(
                raw_metadata[part].indicator_name for part in parts
            ),
            frequency=example.frequency,
            unit=unit,
            source=example.source,
            updated_at=example.updated_at,
            sheet_name=DLD_SHEET,
        )
    return values.sort_index(), metadata


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回期房/现房笔数与金额四个口径均有效的最新月份。"""

    complete = values.dropna(how="any").sort_index()
    if complete.empty:
        raise ValueError("月度_DLD 没有四个销售口径均完整的月份")
    return pd.Timestamp(complete.index[-1])


def anchor_last_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
) -> pd.Period:
    """锚定**已结束**的最新月份（图表窗口右端）。

    工作簿的最新月若恰为当前自然月（该月尚未过完、数值是截至目前的滚动统计），
    回退一个月；否则直接取数据侧最新完整月。``today`` 仅测试注入。
    """

    latest = latest_complete_month(values).to_period("M")
    reference = (
        pd.Timestamp.today()
        if today is None
        else pd.Timestamp(today).normalize()
    ).to_period("M")
    if latest == reference:
        return latest - 1
    return latest


__all__ = [
    "AGGREGATE_TARGETS",
    "AGGREGATED_COLUMNS",
    "DLD_SHEET",
    "OFFPLAN_AMOUNT",
    "OFFPLAN_COUNT",
    "READY_AMOUNT",
    "READY_COUNT",
    "RealEstateData",
    "anchor_last_month",
    "latest_complete_month",
    "load_real_estate_data",
]