# -*- coding: utf-8 -*-
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
import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any, Optional
import warnings

from dashboard.explore.core.constants import FREQUENCY_MAPPINGS, FREQUENCY_PRIORITY, TIMEDELTA_TOLERANCE_DAYS
from dashboard.explore.core.series_utils import identify_time_column

# 抑制pandas频率相关警告
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

logger = logging.getLogger(__name__)


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
        freq = pd.infer_freq(series.index)
        if freq:
            # 注意：不能使用 'X' in freq 的方式，因为 'QE-DEC' 包含 'D'
            # 必须检查频率字符串的开头
            if freq.startswith('Q'):
                logger.debug(f"识别为Quarterly（pandas推断: {freq}）")
                return 'Quarterly'
            elif freq.startswith('M') or freq.startswith('ME') or freq.startswith('MS') or freq.startswith('WOM'):
                # WOM-*表示Week Of Month（如WOM-4FRI=每月第4个星期五），应识别为Monthly
                logger.debug(f"识别为Monthly（pandas推断: {freq}）")
                return 'Monthly'
            elif freq.startswith('W'):
                logger.debug(f"识别为Weekly（pandas推断: {freq}）")
                return 'Weekly'
            elif freq.startswith('D') or freq.startswith('B'):
                logger.debug(f"识别为Daily（pandas推断: {freq}）")
                return 'Daily'
            elif freq.startswith('A') or freq.startswith('Y'):
                logger.debug(f"识别为Annual（pandas推断: {freq}）")
                return 'Annual'

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

        # 基于中位数时间间隔判断频率
        # 按照从小到大的顺序检查，确保匹配最接近的频率
        freq_order = ['Daily', 'Weekly', 'Ten_Day', 'Monthly', 'Quarterly', 'Annual']

        for freq_name in freq_order:
            min_days, max_days = TIMEDELTA_TOLERANCE_DAYS[freq_name]
            if min_days <= median_days <= max_days:
                logger.debug(f"基于时间间隔识别为{freq_name}（{median_days}天在[{min_days}, {max_days}]范围内）")
                return freq_name

        # 如果不在任何已知频率范围内
        logger.debug(f"无法匹配已知频率（{median_days}天）, 标记为Irregular")
        return 'Irregular'

    except Exception as e:
        logger.error(f"频率推断失败: {e}")
        return 'Undetermined'


def resample_series_to_frequency(
    df: pd.DataFrame,
    target_freq: str,
    agg_method: str = 'mean'
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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

    # 使用统一的频率映射常量（DRY）
    pandas_freq = FREQUENCY_MAPPINGS.get(target_freq, 'ME')

    # 使用字典映射优化聚合方法选择（避免if-elif链）
    AGG_METHOD_MAP = {
        'mean': lambda r: r.mean(),
        'last': lambda r: r.last(),
        'first': lambda r: r.first(),
        'sum': lambda r: r.sum(),
        'median': lambda r: r.median()
    }

    try:
        # 执行重采样（使用字典映射）
        resampler = df.resample(pandas_freq)
        agg_func = AGG_METHOD_MAP.get(agg_method, AGG_METHOD_MAP['mean'])
        resampled = agg_func(resampler)

        # 移除全为NaN的行
        result = resampled.dropna(how='all')

        return result, {
            'status': 'success',
            'target_freq': target_freq,
            'agg_method': agg_method,
            'original_rows': len(df),
            'resampled_rows': len(result)
        }

    except Exception as e:
        return df, {
            'status': 'error',
            'error': f'重采样失败: {str(e)}'
        }


def _prepare_datetime_index(
    df: pd.DataFrame,
    time_column: str,
    all_series_names: List[str]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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
        except Exception as e:
            return df, {
                'status': 'error',
                'error': f'无法将时间列转换为DatetimeIndex: {str(e)}',
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
            except Exception as e:
                return df, {
                    'status': 'error',
                    'error': f'找到时间列但无法转换为DatetimeIndex: {str(e)}',
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
    all_series_names: List[str]
) -> Dict[str, str]:
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
    freq_analysis: Dict[str, str]
) -> Tuple[bool, List[str]]:
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
    unique_freqs: List[str],
    target_frequency: Optional[str],
    auto_align: bool
) -> Tuple[Optional[str], Dict[str, Any]]:
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
    all_series_names: List[str]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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
    candidate_series_names: List[str],
    auto_align: bool = True,
    target_frequency: str = None,
    agg_method: str = 'mean',
    time_column: str = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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
    candidate_vars: List[str],
    enable_frequency_alignment: bool = True,
    target_frequency: str = None,
    agg_method: str = 'mean',
    time_column: str = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
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


def align_multiple_series_frequencies(
    df: pd.DataFrame,
    mode: str = 'stat_align',
    agg_method: str = 'mean',
    time_column: str = None
) -> pd.DataFrame:
    """
    对DataFrame中的所有序列进行频率对齐

    用于DTW批量分析的简化API，自动对齐DataFrame中的所有数值列

    Args:
        df: 输入DataFrame
        mode: 对齐模式 ('stat_align' 或 'value_align')
        agg_method: 聚合方法 ('mean', 'last', 'first', 'sum', 'median')
        time_column: 时间列名称（可选）

    Returns:
        对齐后的DataFrame
    """
    logger.info(f"[频率对齐] 开始 - 输入数据形状: {df.shape}, 列: {list(df.columns)}")

    if df.empty or len(df.columns) == 0:
        logger.warning("[频率对齐] 数据为空，直接返回")
        return df

    # 准备时间索引
    df_work = df.copy()

    logger.info(f"[频率对齐] 索引类型: {type(df_work.index).__name__}")

    # 如果没有DatetimeIndex，尝试找到并设置时间列
    if not isinstance(df_work.index, pd.DatetimeIndex):
        logger.info("[频率对齐] 非DatetimeIndex，尝试准备时间索引")
        all_cols = list(df_work.columns)
        df_work, prepare_result = _prepare_datetime_index(df_work, time_column, all_cols)
        if prepare_result['status'] == 'error':
            # 如果无法准备时间索引，返回原始数据
            logger.error(f"[频率对齐] 准备时间索引失败: {prepare_result.get('error', '未知错误')}")
            return df
        logger.info("[频率对齐] 时间索引准备成功")

    # 获取所有数值列
    numeric_cols = df_work.select_dtypes(include=[np.number]).columns.tolist()
    logger.info(f"[频率对齐] 数值列: {numeric_cols}")

    if len(numeric_cols) == 0:
        logger.warning("[频率对齐] 没有数值列，直接返回")
        return df

    # 分析各列的频率
    freq_analysis = _analyze_series_frequencies(df_work, numeric_cols)
    logger.info(f"[频率对齐] 频率分析结果: {freq_analysis}")

    # 检查是否需要对齐
    needs_alignment, unique_freqs = _check_frequency_consistency(freq_analysis)
    logger.info(f"[频率对齐] 需要对齐: {needs_alignment}, 唯一频率: {unique_freqs}")

    if not needs_alignment:
        # 频率一致，但对于月度/季度/年度数据，仍需检查时间点是否对齐
        if len(unique_freqs) == 1 and unique_freqs[0] in ['Monthly', 'Quarterly', 'Annual']:
            target_freq = unique_freqs[0]
            logger.info(f"[频率对齐] 频率相同但为{target_freq}，检查时间点对齐性")

            # 检查各序列的有效日期是否有重叠
            valid_dates_list = []
            for col in numeric_cols:
                valid_dates = df_work[col].dropna().index
                if len(valid_dates) > 0:
                    valid_dates_list.append(set(valid_dates))

            # 计算重叠日期
            if len(valid_dates_list) > 1:
                overlap = set.intersection(*valid_dates_list)
                overlap_ratio = len(overlap) / max(len(vd) for vd in valid_dates_list)
                logger.info(f"[频率对齐] 时间点重叠比例: {overlap_ratio:.2%} ({len(overlap)}/{max(len(vd) for vd in valid_dates_list)})")

                # 如果重叠率低于50%，强制对齐到月末/季末/年末
                if overlap_ratio < 0.5:
                    logger.info(f"[频率对齐] 重叠率过低，强制重采样到{target_freq}期末")
                    # 继续执行对齐流程
                else:
                    logger.info("[频率对齐] 时间点已对齐，无需重采样")
                    return df_work
            else:
                logger.info("[频率对齐] 只有一个序列，无需检查时间点对齐")
                return df_work
        else:
            # 不需要对齐，直接返回
            logger.info("[频率对齐] 频率一致，无需对齐")
            return df_work

    # 确定目标频率（选择最低频率以避免信息丢失）
    if unique_freqs:
        target_freq = max(unique_freqs, key=lambda x: FREQUENCY_PRIORITY.get(x, 0))
        logger.info(f"[频率对齐] 目标频率: {target_freq} (优先级: {FREQUENCY_PRIORITY.get(target_freq, 0)})")
    else:
        # 无法确定频率，返回原始数据
        logger.warning("[频率对齐] 无法确定目标频率")
        return df_work

    # 执行频率对齐
    logger.info(f"[频率对齐] 执行对齐 - 目标频率: {target_freq}, 聚合方法: {agg_method}")
    aligned_df, alignment_result = _execute_frequency_alignment(
        df_work, target_freq, agg_method, numeric_cols
    )

    if alignment_result['status'] == 'success':
        logger.info(f"[频率对齐] 成功 - 对齐后形状: {aligned_df.shape}")
        return aligned_df
    else:
        # 对齐失败，返回原始数据
        logger.error(f"[频率对齐] 失败: {alignment_result.get('error', '未知错误')}")
        return df_work


# 工具函数：格式化频率对齐报告
def format_alignment_report(alignment_report: Dict[str, Any]) -> str:
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
