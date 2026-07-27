"""
DTW批量分析模块

重构自根目录的dtw_backend.py，整合到explore模块架构中
增强功能：支持频率对齐和数据标准化
"""

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from dashboard.explore.core.series_utils import (
    clean_dataframe_columns,
    identify_time_column,
    prepare_time_index,
)
from dashboard.explore.core.validation import validate_series
from dashboard.explore.metrics.dtw import calculate_dtw_path
from dashboard.explore.preprocessing.frequency_alignment import (
    AGGREGATION_METHODS,
    align_series_for_analysis,
)
from dashboard.explore.preprocessing.standardization import standardize_series

logger = logging.getLogger(__name__)

WINDOW_TYPES = ("无限制", "固定大小窗口 (Radius约束)")
STANDARDIZATION_METHODS = ("zscore", "minmax", "none")
MIN_DTW_SAMPLES = 10


@dataclass(frozen=True)
class _DtwOptions:
    window_type: str
    window_size: int | None
    distance_display: str
    strict_alignment: bool
    standardization: str


def _validate_batch_inputs(
    df: pd.DataFrame,
    target_name: str,
    comparison_names: list[str],
    options: _DtwOptions,
    *,
    enable_frequency_alignment: bool,
    aggregation_method: str,
) -> str | None:
    if not df.columns.is_unique:
        duplicate_columns = df.columns[df.columns.duplicated()].unique().tolist()
        return f"清理后存在重复列名: {duplicate_columns}"
    if not target_name:
        return "目标变量未选择"
    if not comparison_names:
        return "对比变量未选择"
    if target_name not in df.columns:
        return f"目标序列 '{target_name}' 不存在于数据中"
    if options.window_type not in WINDOW_TYPES:
        return f"不支持的窗口类型: {options.window_type}"
    if options.window_type == WINDOW_TYPES[1] and (
        isinstance(options.window_size, bool)
        or not isinstance(options.window_size, (int, np.integer))
        or options.window_size < 1
    ):
        return "固定大小窗口的 radius 必须为正整数"
    if options.standardization not in STANDARDIZATION_METHODS:
        return f"不支持的标准化方法: {options.standardization}"
    if (
        enable_frequency_alignment
        and aggregation_method not in AGGREGATION_METHODS
    ):
        return f"不支持的聚合方法: {aggregation_method}"
    return None


def _ensure_datetime_index(
    df: pd.DataFrame,
    series_names: list[str],
) -> tuple[pd.DataFrame, str | None]:
    if isinstance(df.index, pd.DatetimeIndex):
        return df, None

    time_column = identify_time_column(df, exclude_columns=series_names)
    if time_column is None:
        return df, "数据中没有Date列，无法进行DTW分析"

    prepared, prepared_time_column = prepare_time_index(
        df,
        time_column=time_column,
        set_as_index=True,
        keep_column=False,
    )
    if prepared_time_column is None or not isinstance(
        prepared.index,
        pd.DatetimeIndex,
    ):
        return prepared, "时间列无法转换为有效的DatetimeIndex"
    return prepared, None


def _build_result(
    target_name: str,
    comparison_name: str,
    options: _DtwOptions,
) -> dict[str, Any]:
    return {
        "目标变量": target_name,
        "对比变量": comparison_name,
        "DTW距离": np.nan,
        "原因": "-",
        "窗口类型": options.window_type,
        "窗口大小": (
            options.window_size
            if options.window_type == WINDOW_TYPES[1]
            else "N/A"
        ),
        "距离度量": options.distance_display,
    }


def _align_pair(
    target: pd.Series,
    comparison: pd.Series,
    *,
    strict_alignment: bool,
) -> tuple[pd.Series, pd.Series] | None:
    if strict_alignment:
        aligned = pd.DataFrame(
            {"target": target, "compare": comparison}
        ).dropna()
        logger.debug(
            "[时点对齐] 对齐前=(%s, %s), 对齐后=%s",
            len(target),
            len(comparison),
            len(aligned),
        )
        return aligned["target"], aligned["compare"]

    target_clean = target.dropna()
    comparison_clean = comparison.dropna()
    common_start = max(target_clean.index.min(), comparison_clean.index.min())
    common_end = min(target_clean.index.max(), comparison_clean.index.max())
    if common_start > common_end:
        return None

    target_aligned = target_clean.loc[common_start:common_end]
    comparison_aligned = comparison_clean.loc[common_start:common_end]
    logger.debug(
        "[非时点对齐-共同时间范围] 范围=[%s, %s], 长度=(%s, %s)",
        common_start,
        common_end,
        len(target_aligned),
        len(comparison_aligned),
    )
    return target_aligned, comparison_aligned


def _mark_insufficient_samples(
    result: dict[str, Any],
    target: pd.Series,
    comparison: pd.Series,
) -> bool:
    for label, series in (("目标", target), ("对比", comparison)):
        if len(series) >= MIN_DTW_SAMPLES:
            continue
        result["分析状态"] = (
            f"{label}序列样本不足 "
            f"(需要 {MIN_DTW_SAMPLES}, 实际 {len(series)})"
        )
        result["原因"] = f"{label}序列样本不足: {len(series)}"
        return True
    return False


def _calculate_comparison(
    df: pd.DataFrame,
    target_name: str,
    comparison_name: str,
    target_data: pd.Series,
    options: _DtwOptions,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None, str | None]:
    result = _build_result(target_name, comparison_name, options)
    if comparison_name not in df.columns:
        result["原因"] = "序列不存在"
        return (
            result,
            None,
            None,
            f"对比序列 '{comparison_name}' 不存在，已跳过",
        )

    validation = validate_series(
        df[comparison_name],
        min_samples=MIN_DTW_SAMPLES,
        series_name=comparison_name,
    )
    if not validation.is_valid:
        result["原因"] = "对比序列无效"
        return (
            result,
            None,
            None,
            (
                f"对比序列 '{comparison_name}' 无效: "
                f"{validation.error_message}"
            ),
        )

    aligned = _align_pair(
        target_data,
        validation.cleaned_data,
        strict_alignment=options.strict_alignment,
    )
    if aligned is None:
        result["原因"] = "时间范围无重叠"
        return (
            result,
            None,
            f"'{target_name}' 与 '{comparison_name}' 没有重叠的时间范围",
            None,
        )

    target_for_dtw, comparison_for_dtw = aligned
    if _mark_insufficient_samples(
        result,
        target_for_dtw,
        comparison_for_dtw,
    ):
        return result, None, None, None

    if options.standardization != "none":
        target_for_dtw = standardize_series(
            target_for_dtw,
            method=options.standardization,
        )
        comparison_for_dtw = standardize_series(
            comparison_for_dtw,
            method=options.standardization,
        )

    target_values = target_for_dtw.to_numpy()
    comparison_values = comparison_for_dtw.to_numpy()
    radius = (
        int(options.window_size)
        if options.window_type == WINDOW_TYPES[1]
        else None
    )
    if radius is not None:
        length_difference = abs(len(target_values) - len(comparison_values))
        if length_difference > radius:
            result["原因"] = (
                f"长度差异({length_difference}) > radius({radius})"
            )
            message = (
                f"'{target_name}' vs '{comparison_name}': "
                f"序列长度差异({length_difference})超过radius({radius})，"
                "Sakoe-Chiba约束无法满足！\n"
                f"  目标序列长度: {len(target_values)}\n"
                f"  比较序列长度: {len(comparison_values)}\n"
                f"  建议: 使用'无限制'模式，或设置radius >= "
                f"{length_difference}"
            )
            return result, None, message, None

    try:
        distance, path = calculate_dtw_path(
            target_values,
            comparison_values,
            radius=radius,
        )
    except Exception as exc:  # noqa: BLE001 - isolate one failed series pair
        error = (
            f"计算 '{target_name}' vs '{comparison_name}' DTW时出错: "
            f"{str(exc)[:200]}"
        )
        result["原因"] = f"计算错误: {str(exc)[:100]}"
        logger.error(error)
        return result, None, error, None

    result["DTW距离"] = distance
    path_data = {
        "target_np": target_values,
        "compare_np": comparison_values,
        "path": path,
        "target_index": target_for_dtw.index,
        "compare_index": comparison_for_dtw.index,
    }
    logger.debug(
        "DTW计算成功: %s vs %s, 距离=%.4f",
        target_name,
        comparison_name,
        distance,
    )
    return result, path_data, None, None


def _align_frequencies(
    df: pd.DataFrame,
    target_name: str,
    comparison_names: list[str],
    *,
    enabled: bool,
    aggregation_method: str,
) -> tuple[pd.DataFrame, str | None]:
    if not enabled:
        return df, None

    logger.info("执行频率对齐: 聚合方法=%s", aggregation_method)
    try:
        aligned, report = align_series_for_analysis(
            df[[target_name, *comparison_names]],
            target_name,
            comparison_names,
            enable_frequency_alignment=True,
            agg_method=aggregation_method,
        )
    except Exception as exc:  # noqa: BLE001 - public batch API returns structured errors
        return df, f"频率对齐失败: {exc!s}"

    if report["status"] == "error":
        return df, f"频率对齐失败: {report.get('error', '未知错误')}"
    logger.info("[频率对齐] 完成: 数据形状 %s", aligned.shape)
    return aligned, None


def perform_batch_dtw_calculation(
    df_input: pd.DataFrame,
    target_series_name: str,
    comparison_series_names: list[str],
    window_type_param: str,
    window_size_param: int | None,
    dist_metric_display_param: str,
    enable_freq_alignment: bool = True,
    freq_agg_method: str = 'mean',
    strict_alignment: bool = True,
    standardization_method: str = "zscore",
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str], list[str]]:
    """
    执行批量DTW分析（增强版）

    重构自原dtw_backend.py，增加频率对齐和标准化功能

    Args:
        df_input: 输入DataFrame
        target_series_name: 目标序列名称
        comparison_series_names: 对比序列名称列表
        window_type_param: 窗口类型 ("无限制" 或 "固定大小窗口 (Radius约束)")
        window_size_param: 窗口大小（固定窗口时使用）
        dist_metric_display_param: 距离度量显示名称
        enable_freq_alignment: 是否启用频率对齐
        freq_agg_method: 聚合方法 ('mean', 'last', 'first', 'sum', 'median')
        strict_alignment: 是否时点对齐（成对删除NA值）
        standardization_method: 标准化方法 ('zscore', 'minmax', 'none')

    Returns:
        Tuple[结果列表, 路径字典, 错误列表, 警告列表]
    """
    df = df_input.copy()
    clean_dataframe_columns(df)
    logger.info(f"[DTW批量计算] 已清理列名空格，列数: {len(df.columns)}")

    results_list: list[dict[str, Any]] = []
    paths_dict: dict[str, dict[str, Any]] = {}
    error_messages: list[str] = []
    warning_messages: list[str] = []
    options = _DtwOptions(
        window_type=window_type_param,
        window_size=window_size_param,
        distance_display=dist_metric_display_param,
        strict_alignment=strict_alignment,
        standardization=standardization_method,
    )

    validation_error = _validate_batch_inputs(
        df,
        target_series_name,
        comparison_series_names,
        options,
        enable_frequency_alignment=enable_freq_alignment,
        aggregation_method=freq_agg_method,
    )
    if validation_error:
        error_messages.append(validation_error)
        return results_list, paths_dict, error_messages, warning_messages

    all_series_names = [target_series_name, *comparison_series_names]
    df, time_error = _ensure_datetime_index(df, all_series_names)
    if time_error:
        error_messages.append(time_error)
        return results_list, paths_dict, error_messages, warning_messages

    # 频率对齐必须在验证目标序列之前执行。
    df, alignment_error = _align_frequencies(
        df,
        target_series_name,
        comparison_series_names,
        enabled=enable_freq_alignment,
        aggregation_method=freq_agg_method,
    )
    if alignment_error:
        error_messages.append(alignment_error)
        return results_list, paths_dict, error_messages, warning_messages

    # 验证并清洗目标序列（在频率对齐之后）
    # 注意：不在这里标准化，因为需要针对每对序列单独对齐后再标准化
    target_series = df[target_series_name]
    target_validation = validate_series(
        target_series,
        min_samples=MIN_DTW_SAMPLES,
        series_name=target_series_name,
    )

    if not target_validation.is_valid:
        error_messages.append(f"目标序列 '{target_series_name}' 无效: {target_validation.error_message}")
        return results_list, paths_dict, error_messages, warning_messages

    target_data_clean = target_validation.cleaned_data
    logger.info(f"目标序列准备完成: 长度={len(target_data_clean)}")

    for compare_name in comparison_series_names:
        result, path_data, error, warning = _calculate_comparison(
            df,
            target_series_name,
            compare_name,
            target_data_clean,
            options,
        )
        results_list.append(result)
        if path_data is not None:
            paths_dict[compare_name] = path_data
        if error:
            error_messages.append(error)
        if warning:
            warning_messages.append(warning)

    logger.info(f"批量DTW分析完成: {len(results_list)} 个对比序列")
    return results_list, paths_dict, error_messages, warning_messages
