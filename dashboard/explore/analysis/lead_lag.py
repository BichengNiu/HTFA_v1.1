"""
领先滞后分析模块

从combined_lead_lag_backend.py重构而来，大幅简化代码逻辑
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from dashboard.explore.analysis.config import LeadLagAnalysisConfig
from dashboard.explore.core.constants import (
    ERROR_MESSAGES,
    MAX_DISPLAY_LAG_RANGE,
    MIN_SAMPLES_KL_DIVERGENCE,
)
from dashboard.explore.core.series_utils import get_lagged_slices
from dashboard.explore.core.validation import validate_analysis_inputs
from dashboard.explore.metrics.kl_divergence import (
    kl_divergence,
    series_to_distribution,
)
from dashboard.explore.preprocessing.frequency_alignment import (
    align_series_for_analysis,
    format_alignment_report,
)
from dashboard.explore.preprocessing.standardization import standardize_array

logger = logging.getLogger(__name__)


def calculate_kl_divergence_optimized(
    series_target: pd.Series,
    series_candidate: pd.Series,
    max_lags: int,
    standardize_for_kl: bool,
    standardization_method: str
) -> pd.DataFrame:
    """
    优化版本的KL散度批量计算

    性能优化要点：
    1. 预先清洗和转换数据（只做一次）
    2. 预先标准化（如果需要）
    3. 使用numpy数组和view切片（减少复制）
    4. 减少重复验证
    5. 使用Stata自动分箱算法

    预期性能提升：50-70%

    Args:
        series_target: 目标序列
        series_candidate: 候选序列
        max_lags: 最大滞后阶数
        standardize_for_kl: 是否标准化
        standardization_method: 标准化方法

    Returns:
        DataFrame包含Lag和KL_Divergence列
    """
    if isinstance(max_lags, bool) or not isinstance(max_lags, (int, np.integer)):
        raise TypeError("max_lags必须是非负整数")
    if max_lags < 0:
        raise ValueError("max_lags必须是非负整数")

    # 先按时间索引对齐，再保留缺失位置执行滞后切片。
    aligned = pd.concat(
        [
            series_target.rename("target"),
            series_candidate.rename("candidate"),
        ],
        axis=1,
        join="outer",
    ).sort_index()
    target_arr = aligned["target"].astype(float).to_numpy()
    cand_arr = aligned["candidate"].astype(float).to_numpy()
    if np.isinf(target_arr).any() or np.isinf(cand_arr).any():
        raise ValueError("序列包含无穷值")

    # 预先标准化，同时保留 NaN 位置。
    if standardize_for_kl and standardization_method != 'none':
        target_arr = standardize_array(target_arr, standardization_method)
        cand_arr = standardize_array(cand_arr, standardization_method)

    # 批量计算KL散度（使用统一切片函数）
    kl_lags = []
    kl_values = []

    for k_lag in range(-max_lags, max_lags + 1):
        kl_lags.append(k_lag)

        # 使用统一的切片函数（view，零拷贝）
        a_view, c_view = get_lagged_slices(target_arr, cand_arr, k_lag)

        if a_view is None or c_view is None:
            kl_values.append(np.nan)
            continue

        valid_mask = ~(np.isnan(a_view) | np.isnan(c_view))
        if np.count_nonzero(valid_mask) < MIN_SAMPLES_KL_DIVERGENCE:
            kl_values.append(np.nan)
            continue

        # 只删除当前滞后下成对缺失的观测。
        try:
            a_series_temp = pd.Series(a_view[valid_mask])
            c_series_temp = pd.Series(c_view[valid_mask])

            p, q, _ = series_to_distribution(a_series_temp, c_series_temp)
            kl_val = kl_divergence(p, q)
            kl_values.append(kl_val)
        except ValueError as e:
            logger.debug(f"KL散度计算失败 (lag={k_lag}): {e}")
            kl_values.append(np.nan)

    return pd.DataFrame({
        'Lag': kl_lags,
        'KL_Divergence': kl_values
    })


def calculate_lead_lag_for_pair(
    series_target: pd.Series,
    series_candidate: pd.Series,
    max_lags: int,
    standardize_for_kl: bool,
    standardization_method: str
) -> dict[str, Any]:
    """
    计算单对序列的领先滞后分析（基于KL散度）

    Args:
        series_target: 目标序列
        series_candidate: 候选序列
        max_lags: 最大滞后阶数
        standardize_for_kl: 是否标准化KL计算
        standardization_method: 标准化方法

    Returns:
        分析结果字典
    """
    result = {
        'target_variable': series_target.name,
        'candidate_variable': series_candidate.name,
        'k_kl': np.nan,
        'kl_at_k_kl': np.nan,
        'full_kl_divergence_df': pd.DataFrame(),
        'notes': '计算失败'
    }

    # KL散度分析（使用优化版本，自动分箱）
    result['full_kl_divergence_df'] = calculate_kl_divergence_optimized(
        series_target,
        series_candidate,
        max_lags,
        standardize_for_kl,
        standardization_method
    )

    # 找到最优KL散度（限制在指定范围内）
    if result['full_kl_divergence_df']['KL_Divergence'].notna().any():
        kl_df_filtered = result['full_kl_divergence_df'][
            (result['full_kl_divergence_df']['Lag'] >= -MAX_DISPLAY_LAG_RANGE) &
            (result['full_kl_divergence_df']['Lag'] <= MAX_DISPLAY_LAG_RANGE)
        ].copy()

        if not kl_df_filtered.empty:
            kl_series = kl_df_filtered['KL_Divergence']
            non_nan_kl = kl_series.dropna()

            if not non_nan_kl.empty:
                # 找最小值（不包括inf）
                finite_kl = non_nan_kl[np.isfinite(non_nan_kl)]
                if not finite_kl.empty:
                    optimal_idx = finite_kl.idxmin()
                    result['k_kl'] = kl_df_filtered.loc[optimal_idx, 'Lag']
                    result['kl_at_k_kl'] = finite_kl.loc[optimal_idx]
                    result['notes'] = '计算成功'

    logger.debug(f"领先滞后分析完成: {series_candidate.name}, k_kl={result['k_kl']}")
    return result


def _coerce_lead_lag_config(
    config: LeadLagAnalysisConfig | dict,
) -> LeadLagAnalysisConfig:
    if isinstance(config, dict):
        return LeadLagAnalysisConfig(**config)
    if isinstance(config, LeadLagAnalysisConfig):
        return config
    raise TypeError(
        "config必须是LeadLagAnalysisConfig或字典，"
        f"收到: {type(config)}"
    )


def _alignment_message(
    report: dict[str, Any],
) -> tuple[str | None, str | None]:
    status = report["status"]
    if status == "error":
        return f"频率对齐失败: {report.get('error')}", None
    if status == "success":
        return None, f"频率对齐: {format_alignment_report(report)}"
    if status == "no_alignment_needed":
        return None, "频率检查: 所有序列频率一致，无需对齐"
    if status == "disabled":
        return None, "频率检查: 频率对齐功能已禁用"
    if status == "alignment_skipped":
        return None, f"频率检查: {format_alignment_report(report)}"
    return None, f"频率检查: 未知状态 - {status or 'Unknown'}"


def _align_lead_lag_data(
    df: pd.DataFrame,
    target_name: str,
    candidate_names: list[str],
    config: LeadLagAnalysisConfig,
) -> tuple[pd.DataFrame, str | None, str | None]:
    if not config.enable_frequency_alignment:
        return df, None, None

    try:
        aligned, report = align_series_for_analysis(
            df,
            target_name,
            candidate_names,
            enable_frequency_alignment=True,
            target_frequency=config.target_frequency,
            agg_method=config.freq_agg_method,
            time_column=config.time_column,
        )
    except Exception as exc:  # noqa: BLE001 - public batch API returns structured errors
        return df, f"频率对齐过程出错: {exc!s}", None

    error, warning = _alignment_message(report)
    return aligned, error, warning


def _failed_candidate_result(
    target_name: str,
    candidate_name: str,
    note: str,
) -> dict[str, Any]:
    return {
        "target_variable": target_name,
        "candidate_variable": candidate_name,
        "k_kl": np.nan,
        "kl_at_k_kl": np.nan,
        "full_kl_divergence_df": pd.DataFrame(),
        "notes": note,
    }


def _analyze_candidate(
    df: pd.DataFrame,
    target_name: str,
    candidate_name: str,
    config: LeadLagAnalysisConfig,
) -> tuple[dict[str, Any], str | None, str | None]:
    if candidate_name not in df.columns:
        note = ERROR_MESSAGES["candidate_not_found"]
        return (
            _failed_candidate_result(target_name, candidate_name, note),
            None,
            f"候选变量 '{candidate_name}' {note}，已跳过",
        )

    try:
        result = calculate_lead_lag_for_pair(
            df[target_name],
            df[candidate_name],
            config.max_lags,
            config.standardize_for_kl,
            config.standardization_method,
        )
    except Exception as exc:  # noqa: BLE001 - isolate one failed candidate
        logger.error("处理候选变量 '%s' 时出错: %s", candidate_name, exc)
        return (
            _failed_candidate_result(
                target_name,
                candidate_name,
                f"处理失败: {str(exc)[:50]}",
            ),
            f"处理 '{candidate_name}' 时出错: {str(exc)[:100]}",
            None,
        )
    return result, None, None


def perform_combined_lead_lag_analysis(
    df_input: pd.DataFrame,
    target_variable_name: str,
    candidate_variable_names_list: list[str],
    config: LeadLagAnalysisConfig | dict
) -> tuple[list[dict], list[str], list[str]]:
    """
    执行综合领先滞后分析

    重构版本：使用配置类简化参数（KISS原则）

    Args:
        df_input: 输入DataFrame
        target_variable_name: 目标变量名
        candidate_variable_names_list: 候选变量名列表
        config: 分析配置对象（LeadLagAnalysisConfig或字典）

    Returns:
        Tuple[结果列表, 错误消息列表, 警告消息列表]

    Examples:
        # 使用配置类
        config = LeadLagAnalysisConfig(max_lags=12)
        results, errors, warnings = perform_combined_lead_lag_analysis(
            df, 'target', ['cand1', 'cand2'], config
        )

        # 使用字典
        results, errors, warnings = perform_combined_lead_lag_analysis(
            df, 'target', ['cand1', 'cand2'],
            {'max_lags': 12}
        )
    """
    config = _coerce_lead_lag_config(config)
    all_results: list[dict[str, Any]] = []
    error_messages: list[str] = []
    warning_messages: list[str] = []

    # 1. 输入验证
    errors, warnings = validate_analysis_inputs(
        df_input,
        target_variable_name,
        candidate_variable_names_list,
        min_samples=config.max_lags + 2,
    )

    error_messages.extend(errors)
    warning_messages.extend(warnings)

    if errors:
        return all_results, error_messages, warning_messages

    df_aligned, alignment_error, alignment_warning = _align_lead_lag_data(
        df_input,
        target_variable_name,
        candidate_variable_names_list,
        config,
    )
    if alignment_error:
        error_messages.append(alignment_error)
        return all_results, error_messages, warning_messages
    if alignment_warning:
        warning_messages.append(alignment_warning)

    for candidate_name in candidate_variable_names_list:
        result, error, warning = _analyze_candidate(
            df_aligned,
            target_variable_name,
            candidate_name,
            config,
        )
        all_results.append(result)
        if error:
            error_messages.append(error)
        if warning:
            warning_messages.append(warning)

    logger.info(f"综合领先滞后分析完成: {len(all_results)} 个结果")
    return all_results, error_messages, warning_messages


def get_detailed_lag_data_for_candidate(
    df_input: pd.DataFrame,
    target_variable_name: str,
    candidate_variable_name: str,
    config: LeadLagAnalysisConfig | dict
) -> pd.DataFrame:
    """
    获取单个候选变量的详细滞后数据（用于绘图）

    重构版本：使用配置类简化参数，复用 _coerce_lead_lag_config 与
    _align_lead_lag_data，避免重复实现配置转换与频率对齐逻辑。

    Args:
        df_input: 输入DataFrame
        target_variable_name: 目标变量名
        candidate_variable_name: 候选变量名
        config: 分析配置对象（LeadLagAnalysisConfig或字典）

    Returns:
        KL散度DataFrame

    Raises:
        ValueError: 配置无效、频率对齐失败或变量不存在
    """
    config = _coerce_lead_lag_config(config)

    # 频率对齐
    df_aligned, error, _ = _align_lead_lag_data(
        df_input,
        target_variable_name,
        [candidate_variable_name],
        config,
    )
    if error:
        raise ValueError(error)

    # 验证变量存在
    if target_variable_name not in df_aligned.columns:
        raise ValueError(f"目标变量 '{target_variable_name}' 未找到")

    if candidate_variable_name not in df_aligned.columns:
        raise ValueError(f"候选变量 '{candidate_variable_name}' 未找到")

    series_target = df_aligned[target_variable_name]
    series_candidate = df_aligned[candidate_variable_name]

    # 计算KL散度（使用优化版本，自动分箱）
    return calculate_kl_divergence_optimized(
        series_target,
        series_candidate,
        config.max_lags,
        config.standardize_for_kl,
        config.standardization_method,
    )
