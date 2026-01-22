# -*- coding: utf-8 -*-
"""
领先滞后分析模块

从combined_lead_lag_backend.py重构而来，大幅简化代码逻辑
"""

import logging
from typing import Tuple, List, Optional, Dict, Any, Union
import pandas as pd
import numpy as np

from dashboard.explore.core.validation import validate_analysis_inputs
from dashboard.explore.core.constants import MIN_SAMPLES_KL_DIVERGENCE, ERROR_MESSAGES, MAX_DISPLAY_LAG_RANGE
from dashboard.explore.core.series_utils import get_lagged_slices
from dashboard.explore.metrics.kl_divergence import series_to_distribution, kl_divergence
from dashboard.explore.preprocessing.frequency_alignment import align_series_for_analysis, format_alignment_report
from dashboard.explore.preprocessing.standardization import standardize_array
from dashboard.explore.analysis.config import LeadLagAnalysisConfig

logger = logging.getLogger(__name__)


def get_overlapping_series(
    series_a: pd.Series,
    series_b: pd.Series,
    lag: int,
    standardize_for_kl: bool = False,
    standardization_method: str = 'zscore'
) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    """
    提取两个序列在给定滞后下的重叠部分

    重构版本：优化类型转换，减少pandas↔numpy转换次数

    Args:
        series_a: 参考序列
        series_b: 待滞后序列
        lag: 滞后值（正值表示series_b领先）
        standardize_for_kl: 是否标准化
        standardization_method: 标准化方法

    Returns:
        Tuple[对齐后的series_a, 对齐后的series_b]
    """
    # 保存原始名称
    name_a = series_a.name
    name_b = series_b.name

    # 一次性转换为numpy数组（减少转换次数）
    arr_a = series_a.values
    arr_b = series_b.values

    # 使用统一的切片函数（零拷贝view）
    slice_a, slice_b = get_lagged_slices(arr_a, arr_b, lag)

    if slice_a is None or slice_b is None:
        return None, None

    # 移除NaN（直接在numpy层面处理，避免Series→DataFrame→Series转换）
    valid_mask = ~(np.isnan(slice_a) | np.isnan(slice_b))
    if np.sum(valid_mask) < 2:
        return None, None

    slice_a_clean = slice_a[valid_mask]
    slice_b_clean = slice_b[valid_mask]

    # 标准化（如果需要，直接在numpy层面处理）
    if standardize_for_kl and standardization_method != 'none':
        slice_a_clean = standardize_array(slice_a_clean, standardization_method)
        slice_b_clean = standardize_array(slice_b_clean, standardization_method)

    # 最后一次性转换回Series（只在最后转换一次）
    out_a = pd.Series(slice_a_clean, name=name_a)
    out_b = pd.Series(slice_b_clean, name=name_b)

    return out_a, out_b


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
    # 1. 预先清洗和转换（只做一次）
    target_clean = series_target.dropna()
    cand_clean = series_candidate.dropna()

    # 验证长度
    min_required = max_lags + MIN_SAMPLES_KL_DIVERGENCE
    if len(target_clean) < min_required or len(cand_clean) < min_required:
        # 数据不足，返回全NaN
        lags = list(range(-max_lags, max_lags + 1))
        return pd.DataFrame({
            'Lag': lags,
            'KL_Divergence': [np.nan] * len(lags)
        })

    # 2. 转换为numpy数组（减少pandas开销）
    target_arr = target_clean.values
    cand_arr = cand_clean.values

    # 3. 预先标准化（如果需要，只做一次）
    if standardize_for_kl and standardization_method != 'none':
        target_arr = standardize_array(target_arr, standardization_method)
        cand_arr = standardize_array(cand_arr, standardization_method)

    # 4. 批量计算KL散度（使用统一切片函数）
    kl_lags = []
    kl_values = []

    for k_lag in range(-max_lags, max_lags + 1):
        kl_lags.append(k_lag)

        # 使用统一的切片函数（view，零拷贝）
        a_view, c_view = get_lagged_slices(target_arr, cand_arr, k_lag)

        if a_view is None or c_view is None or len(a_view) < MIN_SAMPLES_KL_DIVERGENCE:
            kl_values.append(np.nan)
            continue

        # 直接计算KL散度（避免重复转换，使用自动分箱）
        try:
            a_series_temp = pd.Series(a_view)
            c_series_temp = pd.Series(c_view)

            p, q, _ = series_to_distribution(a_series_temp, c_series_temp)
            kl_val = kl_divergence(p, q)
            kl_values.append(kl_val)
        except Exception as e:
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
) -> Dict[str, Any]:
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


def perform_combined_lead_lag_analysis(
    df_input: pd.DataFrame,
    target_variable_name: str,
    candidate_variable_names_list: List[str],
    config: Union[LeadLagAnalysisConfig, Dict]
) -> Tuple[List[Dict], List[str], List[str]]:
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
    # 配置处理：支持字典或配置类
    if isinstance(config, dict):
        config = LeadLagAnalysisConfig(**config)
    elif not isinstance(config, LeadLagAnalysisConfig):
        raise TypeError(f"config必须是LeadLagAnalysisConfig或字典，收到: {type(config)}")

    # 提取配置参数
    max_lags = config.max_lags
    std_for_kl = config.standardize_for_kl
    std_method = config.standardization_method
    enable_freq_align = config.enable_frequency_alignment
    target_freq = config.target_frequency
    agg_method = config.freq_agg_method
    time_col = config.time_column
    all_results = []
    error_messages = []
    warning_messages = []

    # 1. 输入验证
    errors, warnings = validate_analysis_inputs(
        df_input,
        target_variable_name,
        candidate_variable_names_list,
        min_samples=max_lags + 2
    )

    error_messages.extend(errors)
    warning_messages.extend(warnings)

    if errors:
        return all_results, error_messages, warning_messages

    # 2. 频率对齐
    df_aligned = df_input
    if enable_freq_align:
        try:
            df_aligned, alignment_report = align_series_for_analysis(
                df_input,
                target_variable_name,
                candidate_variable_names_list,
                enable_frequency_alignment=True,
                target_frequency=target_freq,
                agg_method=agg_method,
                time_column=time_col
            )

            if alignment_report['status'] == 'success':
                warning_messages.append(f"频率对齐: {format_alignment_report(alignment_report)}")
            elif alignment_report['status'] == 'error':
                error_messages.append(f"频率对齐失败: {alignment_report.get('error')}")
                return all_results, error_messages, warning_messages
            elif alignment_report['status'] == 'no_alignment_needed':
                warning_messages.append("频率检查: 所有序列频率一致，无需对齐")
            elif alignment_report['status'] == 'disabled':
                warning_messages.append("频率检查: 频率对齐功能已禁用")
            elif alignment_report['status'] == 'alignment_skipped':
                warning_messages.append(f"频率检查: {format_alignment_report(alignment_report)}")
            else:
                warning_messages.append(f"频率检查: 未知状态 - {alignment_report.get('status', 'Unknown')}")

        except Exception as e:
            error_messages.append(f"频率对齐过程出错: {str(e)}")
            return all_results, error_messages, warning_messages

    # 3. 准备目标序列
    series_target = df_aligned[target_variable_name]

    # 4. 批量处理候选序列
    for candidate_name in candidate_variable_names_list:
        if candidate_name not in df_aligned.columns:
            warning_messages.append(f"候选变量 '{candidate_name}' {ERROR_MESSAGES['candidate_not_found']}，已跳过")
            all_results.append({
                'target_variable': target_variable_name,
                'candidate_variable': candidate_name,
                'k_kl': np.nan,
                'kl_at_k_kl': np.nan,
                'full_kl_divergence_df': pd.DataFrame(),
                'notes': ERROR_MESSAGES['candidate_not_found']
            })
            continue

        try:
            series_candidate = df_aligned[candidate_name]

            # 执行分析
            result = calculate_lead_lag_for_pair(
                series_target,
                series_candidate,
                max_lags,
                std_for_kl,
                std_method
            )

            all_results.append(result)

        except Exception as e:
            logger.error(f"处理候选变量 '{candidate_name}' 时出错: {e}")
            error_messages.append(f"处理 '{candidate_name}' 时出错: {str(e)[:100]}")
            all_results.append({
                'target_variable': target_variable_name,
                'candidate_variable': candidate_name,
                'k_kl': np.nan,
                'kl_at_k_kl': np.nan,
                'full_kl_divergence_df': pd.DataFrame(),
                'notes': f"处理失败: {str(e)[:50]}"
            })

    logger.info(f"综合领先滞后分析完成: {len(all_results)} 个结果")
    return all_results, error_messages, warning_messages


def get_detailed_lag_data_for_candidate(
    df_input: pd.DataFrame,
    target_variable_name: str,
    candidate_variable_name: str,
    config: Union[LeadLagAnalysisConfig, Dict]
) -> pd.DataFrame:
    """
    获取单个候选变量的详细滞后数据（用于绘图）

    重构版本：使用配置类简化参数

    Args:
        df_input: 输入DataFrame
        target_variable_name: 目标变量名
        candidate_variable_name: 候选变量名
        config: 分析配置对象（LeadLagAnalysisConfig或字典）

    Returns:
        KL散度DataFrame

    Examples:
        config = LeadLagAnalysisConfig(max_lags=12)
        kl_df = get_detailed_lag_data_for_candidate(
            df, 'target', 'candidate', config
        )
    """
    # 配置处理：支持字典或配置类
    if isinstance(config, dict):
        config = LeadLagAnalysisConfig(**config)
    elif not isinstance(config, LeadLagAnalysisConfig):
        raise TypeError(f"config必须是LeadLagAnalysisConfig或字典，收到: {type(config)}")

    # 提取配置参数
    max_lags = config.max_lags
    std_for_kl = config.standardize_for_kl
    std_method = config.standardization_method
    enable_freq_align = config.enable_frequency_alignment
    target_freq = config.target_frequency
    agg_method = config.freq_agg_method
    time_col = config.time_column
    # 频率对齐
    df_aligned = df_input
    if enable_freq_align:
        try:
            df_aligned, _ = align_series_for_analysis(
                df_input,
                target_variable_name,
                [candidate_variable_name],
                enable_frequency_alignment=True,
                target_frequency=target_freq,
                agg_method=agg_method,
                time_column=time_col
            )
        except Exception as e:
            logger.error(f"频率对齐失败: {e}")
            raise ValueError(f"频率对齐过程出错: {str(e)}")

    # 验证变量存在
    if target_variable_name not in df_aligned.columns:
        raise ValueError(f"目标变量 '{target_variable_name}' 未找到")

    if candidate_variable_name not in df_aligned.columns:
        raise ValueError(f"候选变量 '{candidate_variable_name}' 未找到")

    series_target = df_aligned[target_variable_name]
    series_candidate = df_aligned[candidate_variable_name]

    # 计算KL散度（使用优化版本，自动分箱）
    kl_divergence_df = calculate_kl_divergence_optimized(
        series_target,
        series_candidate,
        max_lags,
        std_for_kl,
        std_method
    )

    return kl_divergence_df
