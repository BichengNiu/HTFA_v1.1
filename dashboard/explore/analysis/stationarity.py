# -*- coding: utf-8 -*-
"""
平稳性分析模块

重构自stationarity_backend.py，将超长函数拆分为多个职责明确的小函数
"""

import logging
from typing import Tuple, Optional, Dict, Any, List
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.statespace.tools import diff as statespace_diff
import warnings

from dashboard.explore.core.constants import MIN_SAMPLES_ADF, SEASONAL_DIFF_MAP, FREQUENCY_DISPLAY_NAMES
from dashboard.explore.core.series_utils import prepare_time_index
from dashboard.explore.preprocessing.frequency_alignment import infer_series_frequency

logger = logging.getLogger(__name__)

# 处理方法选项
OPERATIONS = ['不处理', '对数', '环比差分', '同比差分']


def _format_adf_status(adf_result: str) -> str:
    """
    格式化ADF检验结果为显示状态（DRY helper）

    Args:
        adf_result: ADF检验结果 ('是', '否', 或错误信息)

    Returns:
        显示状态 ('平稳', '非平稳', 或原始错误信息)
    """
    if adf_result == '是':
        return '平稳'
    elif adf_result == '否':
        return '非平稳'
    else:
        return adf_result


def apply_single_operation(series: pd.Series, operation: str) -> Tuple[Optional[pd.Series], str]:
    """
    对序列应用单次操作

    Args:
        series: 输入序列
        operation: 操作类型 ('不处理', '对数', '环比差分', '同比差分')

    Returns:
        Tuple[处理后序列, 错误信息(如有)]
    """
    if operation == '不处理':
        return series, ''

    if operation == '对数':
        clean = series.dropna()
        if len(clean) == 0 or (clean <= 0).any():
            return None, '包含非正值，无法对数'
        return np.log(series), ''

    if operation == '环比差分':
        return statespace_diff(series, k_diff=1), ''

    if operation == '同比差分':
        return statespace_diff(series, k_diff=12), ''

    return series, ''


def apply_variable_transformations(
    df: pd.DataFrame,
    transform_config: pd.DataFrame,
    alpha: float = 0.05
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    对变量应用转换并进行平稳性检验

    Args:
        df: 原始数据DataFrame
        transform_config: 转换配置DataFrame，包含列：变量名, 第一次处理, 第二次处理, 第三次处理
        alpha: 显著性水平

    Returns:
        Tuple[处理后数据, 检验结果DataFrame, 未通过检验的变量列表]
    """
    results = []
    failed_vars = []
    processed_data = {}

    for _, row in transform_config.iterrows():
        var_name = row['变量名']
        ops = [row['第一次处理'], row['第二次处理'], row['第三次处理']]

        if var_name not in df.columns:
            continue

        series = df[var_name].copy()
        error_msg = ''

        # 依次应用三次处理
        for op in ops:
            if op == '不处理':
                break
            series, error_msg = apply_single_operation(series, op)
            if series is None:
                break

        if series is None:
            results.append({
                '变量名': var_name,
                'ADF检验P值': None,
                'ADF检验结果': f'处理失败({error_msg})'
            })
            failed_vars.append(f"{var_name}(处理失败)")
            continue

        # 执行检验
        adf_p, adf_result = run_adf_test(series, alpha)
        adf_status = _format_adf_status(adf_result)

        results.append({
            '变量名': var_name,
            'ADF检验P值': round(adf_p, 4) if adf_p is not None else None,
            'ADF检验结果': adf_status
        })

        # 记录未通过的变量
        if adf_status == '非平稳':
            failed_vars.append(f"{var_name}(ADF)")

        # 保存处理后数据
        processed_data[var_name] = series

    results_df = pd.DataFrame(results)
    processed_df = pd.DataFrame(processed_data)

    return processed_df, results_df, failed_vars


def run_stationarity_tests(
    df: pd.DataFrame,
    alpha: float = 0.05
) -> pd.DataFrame:
    """
    对所有数值变量执行ADF平稳性检验

    Args:
        df: 输入DataFrame
        alpha: 显著性水平

    Returns:
        DataFrame with columns: 变量名, 有效值个数, ADF检验P值, ADF检验结果
    """
    results = []

    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        series = df[col].dropna()
        valid_count = len(series)

        # ADF检验
        adf_p, adf_result = run_adf_test(series, alpha)

        results.append({
            '变量名': col,
            '有效值个数': valid_count,
            'ADF检验P值': round(adf_p, 4) if adf_p is not None else None,
            'ADF检验结果': _format_adf_status(adf_result)
        })

    return pd.DataFrame(results)


def run_adf_test(series: pd.Series, alpha: float = 0.05) -> Tuple[Optional[float], str]:
    """
    执行ADF平稳性检验

    Args:
        series: 输入序列
        alpha: 显著性水平

    Returns:
        Tuple[p值, 平稳性状态]
    """
    series_cleaned = series.dropna()

    if series_cleaned.empty or len(series_cleaned) < MIN_SAMPLES_ADF:
        logger.warning(f"序列 '{series.name}' 样本数不足，无法执行ADF检验")
        return None, '数据不足'

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = adfuller(series_cleaned, regression='ct')

        p_value = result[1]
        is_stationary = '是' if p_value < alpha else '否'
        logger.debug(f"ADF检验: p={p_value:.4f}, 平稳={is_stationary}")

        return p_value, is_stationary

    except Exception as e:
        logger.error(f"ADF检验失败: {e}")

        # 提供更具体的错误信息
        if "Ensure that you have included enough lag variables" in str(e):
            return None, '计算失败(滞后阶数不足)'
        elif "degrees of freedom" in str(e):
            return None, '计算失败(自由度不足)'
        else:
            return None, f'计算失败({type(e).__name__})'


def apply_differencing(
    series: pd.Series,
    order: int = 1,
    use_log: bool = False
) -> Tuple[Optional[pd.Series], str]:
    """
    对序列应用差分处理

    Args:
        series: 输入序列
        order: 差分阶数
        use_log: 是否先取对数

    Returns:
        Tuple[差分后的序列, 方法描述]
    """
    try:
        temp_series = series.copy()
        method_desc = f"{order}阶差分" if not use_log else f"{order}阶对数差分"

        # 对数转换
        if use_log:
            temp_series_clean = temp_series.dropna()
            if len(temp_series_clean) == 0 or (temp_series_clean <= 0).any():
                logger.warning(f"序列 '{series.name}' 包含非正值，无法应用对数转换")
                return None, method_desc + " (无法应用对数)"

            temp_series = np.log(temp_series)

        # 差分
        diff_series = statespace_diff(temp_series, k_diff=order)

        logger.info(f"应用 {method_desc} 成功")
        return diff_series, method_desc

    except Exception as e:
        logger.error(f"差分处理失败: {e}")
        return None, method_desc + " (处理失败)"


def process_nonstationary_series(
    series: pd.Series,
    processing_method: str,
    diff_order: int,
    alpha: float
) -> Dict[str, Any]:
    """
    处理非平稳序列

    Args:
        series: 非平稳序列
        processing_method: 处理方法 ('diff', 'log_diff', 'log_then_diff', 'keep')
        diff_order: 差分阶数
        alpha: ADF检验显著性水平

    Returns:
        处理结果字典
    """
    result = {
        'processed_series': None,
        'new_column_name': None,
        'method_description': '原始序列',
        'p_value': None,
        'is_stationary': '否'
    }

    if processing_method == 'keep':
        result['method_description'] = '保留原始 (非平稳)'
        return result

    # 根据处理方法确定参数
    if processing_method == 'log_then_diff':
        use_log = True
        suffix = f"_log_diff{diff_order}"
    elif processing_method == 'log_diff':
        use_log = True
        suffix = f"_log_diff{diff_order}"
    else:  # diff
        use_log = False
        suffix = f"_diff{diff_order}"

    diff_series, method_desc = apply_differencing(series, diff_order, use_log)

    if diff_series is None:
        result['method_description'] = method_desc
        return result

    # 检验差分后的平稳性
    p_value, is_stationary = run_adf_test(diff_series, alpha)

    result.update({
        'method_description': method_desc,
        'p_value': p_value,
        'is_stationary': is_stationary
    })

    if is_stationary == '是':
        # 差分成功使序列平稳
        result['processed_series'] = diff_series
        result['new_column_name'] = f"{series.name}{suffix}"
        logger.info(f"序列 '{series.name}' 经 {method_desc} 后平稳")

    return result


def test_and_process_stationarity(
    df_in: pd.DataFrame,
    alpha: float = 0.05,
    processing_method: str = 'keep',
    diff_order: int = 1
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    测试并处理序列平稳性

    Args:
        df_in: 输入DataFrame
        alpha: 显著性水平
        processing_method: 处理方法 ('keep', 'diff', 'log_diff', 'log_then_diff')
        diff_order: 差分阶数

    Returns:
        Tuple[摘要DataFrame, 处理后的数据DataFrame]
    """
    logger.info(f"开始平稳性检验: shape={df_in.shape}, method={processing_method}, order={diff_order}")

    df = df_in.copy()
    summary_results = []
    processed_data = {}

    # 1. 准备时间索引
    df_work, time_column = prepare_time_index(df, time_column=None, set_as_index=True, keep_column=True)

    # 记录时间列信息
    if time_column:
        summary_results.append({
            '指标名称': time_column,
            '原始P值': None,
            '原始是否平稳': '时间戳列',
            '处理方法': '保留',
            '处理后P值': None,
            '最终是否平稳': '时间戳列'
        })
        processed_data[time_column] = df_work[time_column] if time_column in df_work.columns else df_work.index
        logger.info(f"时间列: '{time_column}'")

    # 2. 处理每个数值列
    for col_name in df_work.columns:
        # 跳过已处理的时间列
        if col_name == time_column:
            continue

        if not pd.api.types.is_numeric_dtype(df_work[col_name]):
            logger.debug(f"跳过非数值列: '{col_name}'")
            continue

        logger.info(f"\n处理列: '{col_name}'")
        series = df_work[col_name]

        # 保留原始数值序列
        processed_data[col_name] = series.copy()

        # 初始ADF检验
        original_p_value, original_status = run_adf_test(series, alpha)
        logger.info(f"  初始ADF: p={original_p_value}, 平稳={original_status}")

        # 准备摘要条目
        summary_entry = {
            '指标名称': col_name,
            '原始P值': original_p_value,
            '原始是否平稳': original_status,
            '处理方法': '原始序列',
            '处理后P值': None,
            '最终是否平稳': original_status
        }

        # 如果非平稳且需要处理
        if original_status == '否' and processing_method != 'keep':
            process_result = process_nonstationary_series(
                series, processing_method, diff_order, alpha
            )

            summary_entry['处理方法'] = process_result['method_description']
            summary_entry['处理后P值'] = process_result['p_value']
            summary_entry['最终是否平稳'] = process_result['is_stationary']

            # 添加新的处理后序列
            if process_result['processed_series'] is not None:
                new_col_name = process_result['new_column_name']
                processed_data[new_col_name] = process_result['processed_series']
                logger.info(f"  生成新列: '{new_col_name}'")

        elif original_status == '否' and processing_method == 'keep':
            summary_entry['处理方法'] = '保留原始 (非平稳)'

        summary_results.append(summary_entry)

    # 3. 组装结果
    summary_df = pd.DataFrame(summary_results)

    # 将时间列排在第一行
    if time_column:
        is_time_col = summary_df['指标名称'] == time_column
        summary_df = pd.concat([summary_df[is_time_col], summary_df[~is_time_col]], ignore_index=True)

    # 创建最终DataFrame
    if time_column and time_column in processed_data:
        # 时间列在第一列
        ordered_columns = [time_column] + [col for col in processed_data.keys() if col != time_column]
        final_df = pd.DataFrame({col: processed_data[col] for col in ordered_columns})
    else:
        final_df = pd.DataFrame(processed_data)

    # 设置时间索引
    if time_column and time_column in final_df.columns:
        try:
            if isinstance(df_work.index, pd.DatetimeIndex):
                final_df.index = df_work.index
            logger.info(f"已设置时间索引")
        except Exception as e:
            logger.warning(f"设置时间索引失败: {e}")

    logger.info(f"完成: 摘要 {summary_df.shape}, 数据 {final_df.shape}")

    return summary_df, final_df


def auto_detect_differencing_options(
    df: pd.DataFrame,
    nonstationary_vars: List[str],
    alpha: float = 0.05
) -> pd.DataFrame:
    """
    对非平稳变量自动检测差分处理方案

    Args:
        df: 原始数据DataFrame
        nonstationary_vars: 非平稳变量列表
        alpha: ADF检验显著性水平

    Returns:
        DataFrame with columns: 变量名, 频率, 环比差分, 同比差分, 推荐处理
    """
    results = []

    # 准备时间索引（修复频率检测需要DatetimeIndex）
    df_work, time_col = prepare_time_index(df, time_column=None, set_as_index=True, keep_column=False)

    for var in nonstationary_vars:
        if var not in df_work.columns:
            continue

        series = df_work[var].dropna()
        if len(series) < MIN_SAMPLES_ADF:
            results.append({
                '变量名': var, '频率': FREQUENCY_DISPLAY_NAMES.get('Undetermined', '未确定'),
                '环比差分': '数据不足', '同比差分': '数据不足', '推荐处理': '不处理'
            })
            continue

        # 频率检测
        freq = infer_series_frequency(series)

        # 环比差分检验 (k_diff=1)
        mom_diff = statespace_diff(df_work[var], k_diff=1)
        mom_p, mom_result = run_adf_test(mom_diff, alpha)
        mom_status = '平稳' if mom_result == '是' else ('非平稳' if mom_result == '否' else '无法计算')

        # 同比差分检验
        seasonal_k = SEASONAL_DIFF_MAP.get(freq)
        if seasonal_k is not None and len(series) > seasonal_k:
            yoy_diff = statespace_diff(df_work[var], k_diff=seasonal_k)
            yoy_p, yoy_result = run_adf_test(yoy_diff, alpha)
            yoy_status = '平稳' if yoy_result == '是' else ('非平稳' if yoy_result == '否' else '无法计算')
        else:
            yoy_status = '不支持'

        # 确定推荐处理
        if mom_status == '平稳':
            recommended = '环比差分'
        elif yoy_status == '平稳':
            recommended = '同比差分'
        else:
            recommended = '不处理'

        results.append({
            '变量名': var,
            '频率': FREQUENCY_DISPLAY_NAMES.get(freq, freq),
            '环比差分': mom_status,
            '同比差分': yoy_status,
            '推荐处理': recommended
        })

    return pd.DataFrame(results)


def apply_automated_transformations(
    df: pd.DataFrame,
    config_df: pd.DataFrame,
    alpha: float = 0.05
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    应用自动化差分处理配置

    Args:
        df: 原始数据DataFrame
        config_df: 处理配置表（需包含'变量名', '频率', '用户选择'列）
        alpha: 显著性水平

    Returns:
        Tuple[处理后数据, 检验结果, 未通过ADF检验的变量列表]
    """
    results = []
    failed_vars = []
    processed_data = {}

    for _, row in config_df.iterrows():
        var_name = row['变量名']
        choice = row['用户选择']
        freq = row.get('频率', 'Monthly')

        if var_name not in df.columns:
            continue

        series = df[var_name].copy()

        # 应用处理
        if choice == '环比差分':
            processed_series = statespace_diff(series, k_diff=1)
        elif choice == '同比差分':
            k_diff = SEASONAL_DIFF_MAP.get(freq, 12)
            processed_series = statespace_diff(series, k_diff=k_diff)
        else:  # 不处理
            processed_series = series

        # 检验
        adf_p, adf_result = run_adf_test(processed_series, alpha)
        adf_status = _format_adf_status(adf_result)

        results.append({
            '变量名': var_name,
            '处理方法': choice,
            'ADF检验P值': round(adf_p, 4) if adf_p is not None else None,
            'ADF检验结果': adf_status
        })

        if adf_status == '非平稳':
            failed_vars.append(f"{var_name}(ADF)")

        processed_data[var_name] = processed_series

    return pd.DataFrame(processed_data), pd.DataFrame(results), failed_vars
