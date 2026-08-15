"""
时间序列频率对齐工具模块

提供时间序列频率检测、对齐和标准化功能，供DTW分析和领先滞后分析模块共享使用。

主要功能：
1. 时间序列频率自动识别
2. 多序列频率统一对齐
3. 灵活的重采样聚合方法
4. 完整的对齐报告和错误处理
"""

import logging
from typing import Any

import pandas as pd

from dashboard.explore.core.constants import (
    FREQUENCY_MAPPINGS,
    FREQUENCY_PRIORITY,
    TIMEDELTA_TOLERANCE_DAYS,
)
from dashboard.explore.core.series_utils import identify_time_column

logger = logging.getLogger(__name__)

AGGREGATION_METHODS = ("mean", "last", "first", "sum", "median")
PANDAS_FREQUENCY_PREFIXES = (
    ("Q", "Quarterly"),
    (("M", "WOM"), "Monthly"),
    ("W", "Weekly"),
    (("D", "B"), "Daily"),
    (("A", "Y"), "Annual"),
)


def _frequency_from_pandas_alias(alias: str | None) -> str | None:
    if not alias:
        return None
    for prefixes, frequency_name in PANDAS_FREQUENCY_PREFIXES:
        if alias.startswith(prefixes):
            logger.debug(
                "识别为%s（pandas推断: %s）",
                frequency_name,
                alias,
            )
            return frequency_name
    return None


def _frequency_from_interval(median_days: int) -> str:
    frequency_order = (
        "Daily",
        "Weekly",
        "Ten_Day",
        "Monthly",
        "Quarterly",
        "Annual",
    )
    for frequency_name in frequency_order:
        minimum, maximum = TIMEDELTA_TOLERANCE_DAYS[frequency_name]
        if minimum <= median_days <= maximum:
            logger.debug(
                "基于时间间隔识别为%s（%s天在[%s, %s]范围内）",
                frequency_name,
                median_days,
                minimum,
                maximum,
            )
            return frequency_name
    logger.debug("无法匹配已知频率（%s天）, 标记为Irregular", median_days)
    return "Irregular"


def infer_series_frequency(series: pd.Series) -> str:
    """
    智能推断时间序列的频率（增强版 - 更鲁棒的频率识别）

    Args:
        series: 带有DatetimeIndex的时间序列

    Returns:
        频率标识字符串 ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annual', 'Irregular', 'Undetermined')
    """
    if len(series) < 2:
        return 'Undetermined'

    try:
        # 首先尝试pandas内置频率推断
        inferred = _frequency_from_pandas_alias(
            pd.infer_freq(series.index)
        )
        if inferred:
            return inferred

        # 如果pandas无法推断，基于时间间隔差值分析
        if not isinstance(series.index, pd.DatetimeIndex):
            return 'Undetermined'

        diffs = series.index.to_series().diff().dropna()

        if diffs.empty:
            return 'Undetermined'

        # 使用中位数而不是均值，更robust
        median_diff = diffs.median()
        median_days = abs(median_diff.days)  # 取绝对值处理倒序数据

        logger.debug(f"序列长度: {len(series)}, 中位数间隔: {median_days}天")

        return _frequency_from_interval(median_days)

    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"频率推断失败: {e}")
        return 'Undetermined'


def resample_series_to_frequency(
    df: pd.DataFrame,
    target_freq: str,
    agg_method: str = 'mean'
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    将DataFrame重采样到指定频率

    Args:
        df: 输入DataFrame（必须有DatetimeIndex）
        target_freq: 目标频率 ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annual')
        agg_method: 聚合方法 ('mean', 'last', 'first', 'sum', 'median')

    Returns:
        Tuple[重采样后的DataFrame, 状态报告]
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        return df, {
            'status': 'error',
            'error': 'DataFrame必须具有DatetimeIndex才能进行频率重采样'
        }

    if target_freq not in FREQUENCY_MAPPINGS:
        return df, {
            "status": "error",
            "error": f"不支持的目标频率: {target_freq}",
        }
    if agg_method not in AGGREGATION_METHODS:
        return df, {
            "status": "error",
            "error": f"不支持的聚合方法: {agg_method}",
        }

    pandas_freq = FREQUENCY_MAPPINGS[target_freq]

    try:
        resampler = df.resample(pandas_freq)
        resampled = getattr(resampler, agg_method)()

        # 移除全为NaN的行
        result = resampled.dropna(how='all')

        return result, {
            'status': 'success',
            'target_freq': target_freq,
            'agg_method': agg_method,
            'original_rows': len(df),
            'resampled_rows': len(result)
        }

    except (TypeError, ValueError) as e:
        return df, {
            'status': 'error',
            'error': f'重采样失败: {e!s}'
        }


def _prepare_datetime_index(
    df: pd.DataFrame,
    time_column: str,
    all_series_names: list[str]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    准备DatetimeIndex

    Args:
        df: 输入DataFrame
        time_column: 指定的时间列名（可能为None）
        all_series_names: 所有需要分析的序列名称

    Returns:
        Tuple[处理后的DataFrame, 错误报告（如果有）]
    """
    df_work = df.copy()

    # 如果已经是DatetimeIndex，直接返回
    if isinstance(df_work.index, pd.DatetimeIndex):
        return df_work, {'status': 'success'}

    # 如果指定了时间列
    if time_column and time_column in df_work.columns:
        try:
            df_work[time_column] = pd.to_datetime(df_work[time_column])
            df_work = df_work.set_index(time_column)
            return df_work, {'status': 'success'}
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            return df, {
                'status': 'error',
                'error': f'无法将时间列转换为DatetimeIndex: {e!s}',
                'frequencies': {}
            }

    # 自动识别时间列
    time_col_found = identify_time_column(df_work, exclude_columns=all_series_names)

    if time_col_found:
        # 处理DatetimeIndex的特殊情况
        if time_col_found == "时间索引" or time_col_found == df_work.index.name:
            return df_work, {'status': 'success'}
        else:
            try:
                df_work[time_col_found] = pd.to_datetime(df_work[time_col_found])
                df_work = df_work.set_index(time_col_found)
                return df_work, {'status': 'success'}
            except (KeyError, TypeError, ValueError, OverflowError) as e:
                return df, {
                    'status': 'error',
                    'error': f'找到时间列但无法转换为DatetimeIndex: {e!s}',
                    'frequencies': {}
                }
    else:
        return df, {
            'status': 'error',
            'error': '无法找到有效的时间列，请指定time_column参数',
            'frequencies': {}
        }


def _analyze_series_frequencies(
    df: pd.DataFrame,
    all_series_names: list[str]
) -> dict[str, str]:
    """
    分析各序列的频率

    Args:
        df: 带DatetimeIndex的DataFrame
        all_series_names: 所有需要分析的序列名称

    Returns:
        频率分析字典 {序列名: 频率标识}
    """
    freq_analysis = {}

    # 预先清洗所有序列
    cleaned_series = {
        name: df[name].dropna()
        for name in all_series_names
        if name in df.columns
    }

    for series_name in all_series_names:
        if series_name in cleaned_series:
            series_data = cleaned_series[series_name]
            if len(series_data) >= 2:
                freq_analysis[series_name] = infer_series_frequency(series_data)
            else:
                freq_analysis[series_name] = 'Undetermined'
        else:
            freq_analysis[series_name] = 'Missing'

    return freq_analysis


def _check_frequency_consistency(
    freq_analysis: dict[str, str]
) -> tuple[bool, list[str]]:
    """
    检查频率一致性

    Args:
        freq_analysis: 频率分析字典

    Returns:
        Tuple[是否需要对齐, 有效频率列表]
    """
    valid_freqs = [
        freq for freq in freq_analysis.values()
        if freq not in ['Undetermined', 'Missing', 'Irregular']
    ]
    unique_freqs = list(set(valid_freqs))

    needs_alignment = len(unique_freqs) > 1
    return needs_alignment, unique_freqs


def _determine_target_frequency(
    unique_freqs: list[str],
    target_frequency: str | None,
    auto_align: bool
) -> tuple[str | None, dict[str, Any]]:
    """
    确定目标对齐频率

    Args:
        unique_freqs: 唯一频率列表
        target_frequency: 用户指定的目标频率（可能为None）
        auto_align: 是否自动对齐

    Returns:
        Tuple[目标频率, 错误报告（如果有）]
    """
    if target_frequency:
        return target_frequency, {'status': 'success'}

    if auto_align and unique_freqs:
        # 自动选择最低频率（避免信息丢失）
        target_freq = max(unique_freqs, key=lambda x: FREQUENCY_PRIORITY.get(x, 0))
        return target_freq, {'status': 'success'}

    return None, {
        'status': 'error',
        'error': '无法确定目标对齐频率'
    }


def _execute_frequency_alignment(
    df: pd.DataFrame,
    target_frequency: str,
    agg_method: str,
    all_series_names: list[str]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    执行频率对齐

    Args:
        df: 输入DataFrame
        target_frequency: 目标频率
        agg_method: 聚合方法
        all_series_names: 需要对齐的序列名称

    Returns:
        Tuple[对齐后的DataFrame, 对齐报告]
    """
    aligned_df, resample_report = resample_series_to_frequency(
        df[all_series_names], target_frequency, agg_method
    )

    if resample_report['status'] == 'error':
        return df, {
            'status': 'error',
            'error': resample_report.get('error', '频率对齐失败')
        }

    if aligned_df is not None and not aligned_df.empty:
        return aligned_df, {
            'status': 'success',
            'target_frequency': target_frequency,
            'agg_method': agg_method,
            'original_rows': len(df),
            'aligned_rows': len(aligned_df),
            'message': f'已将所有序列统一到{target_frequency}频率'
        }
    else:
        return df, {
            'status': 'error',
            'error': '频率对齐后结果为空'
        }


def detect_and_align_frequencies(
    df_input: pd.DataFrame,
    target_series_name: str,
    candidate_series_names: list[str],
    auto_align: bool = True,
    target_frequency: str | None = None,
    agg_method: str = 'mean',
    time_column: str | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    检测时间序列频率并进行统一化对齐处理

    已重构：将原158行函数拆分为5个职责明确的子函数
    - _prepare_datetime_index: 准备时间索引
    - _analyze_series_frequencies: 分析各序列频率
    - _check_frequency_consistency: 检查频率一致性
    - _determine_target_frequency: 确定目标频率
    - _execute_frequency_alignment: 执行频率对齐

    Args:
        df_input: 输入DataFrame
        target_series_name: 目标序列名称
        candidate_series_names: 候选序列名称列表
        auto_align: 是否自动对齐频率
        target_frequency: 指定目标频率 ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Annual')
        agg_method: 聚合方法 ('mean', 'last', 'first', 'sum', 'median')
        time_column: 时间列名称（如果索引不是DatetimeIndex）

    Returns:
        Tuple[对齐后的DataFrame, 频率分析报告]
    """
    all_series_names = [target_series_name] + candidate_series_names

    # 1. 准备时间索引
    df_work, prepare_result = _prepare_datetime_index(df_input, time_column, all_series_names)
    if prepare_result['status'] == 'error':
        return df_input, prepare_result

    # 2. 分析各序列的频率
    freq_analysis = _analyze_series_frequencies(df_work, all_series_names)

    # 3. 检查频率一致性
    needs_alignment, unique_freqs = _check_frequency_consistency(freq_analysis)

    if not needs_alignment:
        return df_work, {
            'status': 'no_alignment_needed',
            'frequencies': freq_analysis,
            'message': '所有序列频率一致或无法确定频率，无需对齐'
        }

    # 4. 确定目标频率
    target_freq, freq_result = _determine_target_frequency(unique_freqs, target_frequency, auto_align)
    if freq_result['status'] == 'error':
        return df_work, {
            'status': 'error',
            'error': freq_result['error'],
            'frequencies': freq_analysis
        }

    # 5. 执行频率对齐
    if auto_align:
        aligned_df, alignment_result = _execute_frequency_alignment(
            df_work, target_freq, agg_method, all_series_names
        )

        if alignment_result['status'] == 'error':
            return df_work, {
                'status': 'error',
                'error': alignment_result['error'],
                'frequencies': freq_analysis
            }

        # 成功对齐，添加原始频率信息
        alignment_result['original_frequencies'] = freq_analysis
        return aligned_df, alignment_result

    return df_work, {
        'status': 'alignment_skipped',
        'frequencies': freq_analysis,
        'message': '检测到频率不一致，但未启用自动对齐'
    }


def align_series_for_analysis(
    df: pd.DataFrame,
    target_var: str,
    candidate_vars: list[str],
    enable_frequency_alignment: bool = True,
    target_frequency: str | None = None,
    agg_method: str = 'mean',
    time_column: str | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    为时间序列分析准备对齐的数据
    
    专门用于领先滞后分析和DTW分析的数据预处理
    
    Args:
        df: 输入数据
        target_var: 目标变量名
        candidate_vars: 候选变量名列表
        enable_frequency_alignment: 是否启用频率对齐
        target_frequency: 目标频率
        agg_method: 聚合方法
        time_column: 时间列名
    
    Returns:
        Tuple[对齐后的数据, 对齐报告]
    """
    if not enable_frequency_alignment:
        return df, {
            'status': 'disabled',
            'message': '频率对齐功能已禁用，使用原始数据'
        }
    
    return detect_and_align_frequencies(
        df_input=df,
        target_series_name=target_var,
        candidate_series_names=candidate_vars,
        auto_align=True,
        target_frequency=target_frequency,
        agg_method=agg_method,
        time_column=time_column
    )


# 工具函数：格式化频率对齐报告
def format_alignment_report(alignment_report: dict[str, Any]) -> str:
    """格式化频率对齐报告为用户友好的文本"""
    if alignment_report['status'] == 'success':
        freqs_text = ', '.join([f"{k}:{v}" for k, v in alignment_report['original_frequencies'].items()])
        return (f"[成功] 频率对齐成功\n"
                f"原始频率: {freqs_text}\n"
                f"目标频率: {alignment_report['target_frequency']}\n"
                f"聚合方法: {alignment_report['agg_method']}\n"
                f"数据行数: {alignment_report['original_rows']} -> {alignment_report['aligned_rows']}")

    elif alignment_report['status'] == 'no_alignment_needed':
        freqs_text = ', '.join([f"{k}:{v}" for k, v in alignment_report['frequencies'].items()])
        return f"[信息] 无需对齐: {freqs_text}"

    elif alignment_report['status'] == 'alignment_skipped':
        freqs_text = ', '.join([f"{k}:{v}" for k, v in alignment_report.get('frequencies', {}).items()])
        return f"[信息] 检测到频率不一致但未对齐: {freqs_text}"

    elif alignment_report['status'] == 'error':
        return f"[错误] 对齐失败: {alignment_report.get('error', '未知错误')}"

    elif alignment_report['status'] == 'disabled':
        return "[信息] 频率对齐已禁用"

    else:
        return f"[警告] 未知状态: {alignment_report['status']}"
