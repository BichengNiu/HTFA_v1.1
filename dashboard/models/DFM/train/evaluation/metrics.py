# -*- coding: utf-8 -*-
"""
指标计算模块

计算模型评估指标
"""

import pandas as pd
import numpy as np
from typing import Tuple
from sklearn.metrics import mean_squared_error, mean_absolute_error
from dashboard.models.DFM.train.utils.logger import get_logger


logger = get_logger(__name__)


def calculate_rmse(y_true, y_pred) -> float:
    """
    统一的RMSE计算函数

    Args:
        y_true: 真实值（array-like或Series）
        y_pred: 预测值（array-like或Series）

    Returns:
        float: RMSE值，无有效数据时返回np.inf
    """
    # 转换为numpy数组
    if isinstance(y_true, pd.Series):
        y_true = y_true.values
    if isinstance(y_pred, pd.Series):
        y_pred = y_pred.values

    # 移除NaN值
    valid_mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not valid_mask.any():
        logger.warning("[RMSE] 无有效数据，返回np.inf")
        return np.inf

    y_true_clean = y_true[valid_mask]
    y_pred_clean = y_pred[valid_mask]

    # 使用sklearn计算RMSE
    rmse = np.sqrt(mean_squared_error(y_true_clean, y_pred_clean))

    return float(rmse)


def calculate_combined_score_with_winrate(
    oos_rmse: float,
    oos_win_rate: float
) -> Tuple[float, float, float]:
    """
    计算组合得分（RMSE为主，Win Rate为辅）

    Args:
        oos_rmse: 观察期RMSE（主指标）
        oos_win_rate: 观察期胜率（0-100，辅助指标）

    Returns:
        Tuple[float, float, float]: (win_rate, -rmse, rmse)
            - 第1元素：观察期胜率（用于显示和比较）
            - 第2元素：负RMSE（主排序键）
            - 第3元素：原始RMSE（用于容忍度计算）
    """
    if not np.isfinite(oos_rmse):
        return (np.nan, -np.inf, np.inf)

    if not np.isfinite(oos_win_rate):
        oos_win_rate = np.nan

    return (oos_win_rate, -oos_rmse, oos_rmse)


def calculate_weighted_score(
    is_rmse: float,
    oos_rmse: float,
    is_win_rate: float,
    oos_win_rate: float,
    training_weight: float = 0.5
) -> Tuple[float, float, float]:
    """
    计算训练期和验证期加权后的综合得分。

    加权公式:
    - weighted_rmse = training_weight * is_rmse + (1-training_weight) * oos_rmse
    - weighted_win_rate = training_weight * is_win_rate + (1-training_weight) * oos_win_rate

    特殊情况:
    - training_weight=0: 等同于仅验证期
    - training_weight=1: 等同于仅训练期

    Args:
        is_rmse: 训练期RMSE
        oos_rmse: 验证期RMSE
        is_win_rate: 训练期胜率 (0-100)
        oos_win_rate: 验证期胜率 (0-100)
        training_weight: 训练期权重 (0.0-1.0)

    Returns:
        Tuple[float, float, float]: (weighted_win_rate, -weighted_rmse, weighted_rmse)
            与calculate_combined_score_with_winrate返回格式一致
    """
    validation_weight = 1.0 - training_weight

    # 边界情况：仅验证期
    if training_weight == 0.0:
        if not np.isfinite(oos_rmse):
            return (np.nan, -np.inf, np.inf)
        weighted_rmse = oos_rmse
        weighted_win_rate = oos_win_rate if np.isfinite(oos_win_rate) else np.nan
        return (weighted_win_rate, -weighted_rmse, weighted_rmse)

    # 边界情况：仅训练期
    if training_weight == 1.0:
        if not np.isfinite(is_rmse):
            return (np.nan, -np.inf, np.inf)
        weighted_rmse = is_rmse
        weighted_win_rate = is_win_rate if np.isfinite(is_win_rate) else np.nan
        return (weighted_win_rate, -weighted_rmse, weighted_rmse)

    # 一般情况：加权组合
    if not np.isfinite(is_rmse) or not np.isfinite(oos_rmse):
        return (np.nan, -np.inf, np.inf)

    # 计算加权RMSE
    weighted_rmse = training_weight * is_rmse + validation_weight * oos_rmse

    # 计算加权胜率（要求两期数据都有效，否则返回NaN）
    if np.isfinite(is_win_rate) and np.isfinite(oos_win_rate):
        weighted_win_rate = training_weight * is_win_rate + validation_weight * oos_win_rate
    else:
        # 加权计算要求两期数据都有效，任一无效则结果无效
        weighted_win_rate = np.nan

    return (weighted_win_rate, -weighted_rmse, weighted_rmse)


def compare_scores_with_winrate(
    score_a: Tuple[float, float, float],
    score_b: Tuple[float, float, float],
    rmse_tolerance_percent: float = 1.0,
    win_rate_tolerance_percent: float = 5.0,
    selection_criterion: str = 'hybrid',
    prioritize_win_rate: bool = True
) -> int:
    """
    比较两个得分（支持RMSE+Win Rate组合）

    比较规则（可选策略）：

    纯策略（selection_criterion='rmse'或'win_rate'）：
        - rmse: 仅比较RMSE，忽略Win Rate
        - win_rate: 仅比较Win Rate，忽略RMSE

    混合策略（selection_criterion='hybrid'）：
        策略A（Win Rate优先，prioritize_win_rate=True）：
            1. Win Rate差异 > win_rate_tolerance_percent：选Win Rate更高的
            2. Win Rate差异 <= win_rate_tolerance_percent：选RMSE更小的
            3. 都相等时返回0

        策略B（RMSE优先，prioritize_win_rate=False）：
            1. RMSE差异 > rmse_tolerance_percent：选RMSE更小的
            2. RMSE差异 <= rmse_tolerance_percent：选Win Rate更高的
            3. 都相等时返回0

    Args:
        score_a: 得分A (win_rate, -rmse, rmse)
        score_b: 得分B (win_rate, -rmse, rmse)
        rmse_tolerance_percent: RMSE容忍度（百分比，默认1%）
        win_rate_tolerance_percent: Win Rate容忍度（百分比，默认5%）
        selection_criterion: 筛选标准（'rmse', 'win_rate', 'hybrid'）
        prioritize_win_rate: 是否优先Win Rate（True=胜率优先，False=RMSE优先），仅hybrid模式有效

    Returns:
        int: 1 if A > B, -1 if B > A, 0 if equal
    """
    win_rate_a, neg_rmse_a, rmse_a = score_a
    win_rate_b, neg_rmse_b, rmse_b = score_b

    # 处理无效RMSE
    if not np.isfinite(neg_rmse_a) and not np.isfinite(neg_rmse_b):
        return 0
    if not np.isfinite(neg_rmse_a):
        return -1  # A无效，B更好
    if not np.isfinite(neg_rmse_b):
        return 1   # B无效，A更好

    # 辅助函数：比较RMSE
    def _compare_rmse() -> int:
        if neg_rmse_a > neg_rmse_b:  # A的RMSE更小
            return 1
        elif neg_rmse_a < neg_rmse_b:
            return -1
        return 0

    # 辅助函数：比较Win Rate
    def _compare_win_rate() -> int:
        if np.isnan(win_rate_a) and np.isnan(win_rate_b):
            return 0
        if np.isnan(win_rate_a):
            return -1  # A无Win Rate，B更好
        if np.isnan(win_rate_b):
            return 1   # B无Win Rate，A更好
        if win_rate_a > win_rate_b:
            return 1
        elif win_rate_a < win_rate_b:
            return -1
        return 0

    # 纯策略模式
    if selection_criterion == 'rmse':
        # 仅比较RMSE，忽略Win Rate
        return _compare_rmse()
    elif selection_criterion == 'win_rate':
        # 仅比较Win Rate，忽略RMSE
        return _compare_win_rate()

    # 混合策略模式
    if prioritize_win_rate:
        # 策略A：Win Rate优先
        # 1. 计算Win Rate差异（绝对值）
        win_rate_diff = abs(win_rate_a - win_rate_b) if (
            np.isfinite(win_rate_a) and np.isfinite(win_rate_b)
        ) else np.inf

        # 2. Win Rate差异 > 容忍度，仅比较Win Rate
        if win_rate_diff > win_rate_tolerance_percent:
            result = _compare_win_rate()
            if result != 0:
                return result
            # Win Rate完全相等时，使用RMSE作为决胜
            return _compare_rmse()

        # 3. Win Rate相近，比较RMSE
        result = _compare_rmse()
        if result != 0:
            return result
        # RMSE也相等，最终比较Win Rate作为决胜
        return _compare_win_rate()

    else:
        # 策略B：RMSE优先（原逻辑）
        # 1. 计算RMSE差异百分比（以较大值为基准）
        base_rmse = max(rmse_a, rmse_b)
        if base_rmse == 0:
            base_rmse = 1e-10
        rmse_diff_percent = abs(rmse_a - rmse_b) / base_rmse * 100

        # 2. RMSE差异 > 容忍度，仅比较RMSE
        if rmse_diff_percent > rmse_tolerance_percent:
            return _compare_rmse()

        # 3. RMSE相近，比较Win Rate
        result = _compare_win_rate()
        if result != 0:
            return result
        # Win Rate也相等，最终比较RMSE
        return _compare_rmse()


# ==================== 下月配对评估函数（新定义）====================

def align_next_month_weekly_data(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> pd.DataFrame:
    """对齐m月所有周的nowcast与m+1月target（用于变量筛选RMSE计算）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        pd.DataFrame: 对齐后数据，列['month', 'week_date', 'nowcast', 'next_month_target']
    """
    # 使用公共函数准备数据
    nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)

    weekly_data = []

    # 按月遍历nowcast数据
    for period, group in nowcast_df.groupby('NowcastMonth'):
        # 获取下个月的period
        next_period = period + 1

        # 检查下个月是否有target数据
        if next_period in target_df.index:
            next_month_target = target_df.loc[next_period, 'Target']

            # 该月所有周的nowcast都与下月target配对
            for date, row in group.iterrows():
                weekly_data.append({
                    'month': period,
                    'week_date': date,
                    'nowcast': row['Nowcast'],
                    'next_month_target': next_month_target
                })

    if not weekly_data:
        logger.warning("[align_next_month_weekly] 未找到有效的周度-下月配对数据")
        return pd.DataFrame(columns=['month', 'week_date', 'nowcast', 'next_month_target'])

    return pd.DataFrame(weekly_data)


def align_next_month_last_friday(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> pd.DataFrame:
    """对齐m月最后周五nowcast、m月target与m+1月target（用于Hit Rate和MAE计算）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        pd.DataFrame: 对齐后数据，列['month', 'last_friday_date', 'nowcast', 'current_target', 'next_target']
    """
    # 使用公共函数准备数据
    nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)

    monthly_friday_data = []

    # 按月遍历nowcast数据
    for period, group in nowcast_df.groupby('NowcastMonth'):
        # 找到该月的所有周五 (weekday=4)
        fridays = group[group.index.weekday == 4]
        if fridays.empty:
            continue

        # 取最后一个周五
        last_friday_date = fridays.index.max()
        last_friday_nowcast = fridays.loc[last_friday_date, 'Nowcast']

        # 获取当月和下月的target
        next_period = period + 1

        if period in target_df.index and next_period in target_df.index:
            current_target = target_df.loc[period, 'Target']
            next_target = target_df.loc[next_period, 'Target']

            monthly_friday_data.append({
                'month': period,
                'last_friday_date': last_friday_date,
                'nowcast': last_friday_nowcast,
                'current_target': current_target,
                'next_target': next_target
            })

    if not monthly_friday_data:
        logger.warning("[align_next_month_last_friday] 未找到有效的月度最后周五配对数据")
        return pd.DataFrame(columns=['month', 'last_friday_date', 'nowcast', 'current_target', 'next_target'])

    df = pd.DataFrame(monthly_friday_data)
    df = df.set_index('last_friday_date').sort_index()

    return df


def calculate_next_month_rmse(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """计算m月所有周nowcast与m+1月target配对的RMSE（用于变量筛选）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: RMSE值，失败返回np.inf
    """
    try:
        aligned_df = align_next_month_weekly_data(nowcast_series, target_series)

        if aligned_df.empty or len(aligned_df) < 2:
            logger.warning(f"[next_month_rmse] 配对数据不足: {len(aligned_df)}个数据点")
            return np.inf

        # 计算RMSE
        squared_errors = (aligned_df['nowcast'] - aligned_df['next_month_target']) ** 2
        rmse = np.sqrt(squared_errors.mean())
        return float(rmse)

    except Exception as e:
        logger.error(f"[next_month_rmse] 计算失败: {e}")
        return np.inf


def calculate_next_month_mae(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """计算m月最后周五nowcast与m+1月target配对的MAE

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: MAE值，失败返回np.inf
    """
    try:
        aligned_df = align_next_month_last_friday(nowcast_series, target_series)

        if aligned_df.empty or len(aligned_df) < 2:
            logger.warning(f"[next_month_mae] 配对数据不足: {len(aligned_df)}个数据点")
            return np.inf

        # 计算MAE
        abs_errors = np.abs(aligned_df['nowcast'] - aligned_df['next_target'])
        mae = abs_errors.mean()
        return float(mae)

    except Exception as e:
        logger.error(f"[next_month_mae] 计算失败: {e}")
        return np.inf


# ==================== 本月配对评估函数（2025-12新增）====================

def align_current_month_weekly_data(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> pd.DataFrame:
    """对齐m月所有周的nowcast与m月target（用于本月配对RMSE计算）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        pd.DataFrame: 对齐后数据，列['month', 'week_date', 'nowcast', 'current_month_target']
    """
    # 使用公共函数准备数据
    nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)

    weekly_data = []

    # 按月遍历nowcast数据
    for period, group in nowcast_df.groupby('NowcastMonth'):
        # 检查当月是否有target数据
        if period in target_df.index:
            current_month_target = target_df.loc[period, 'Target']

            # 该月所有周的nowcast都与当月target配对
            for date, row in group.iterrows():
                weekly_data.append({
                    'month': period,
                    'week_date': date,
                    'nowcast': row['Nowcast'],
                    'current_month_target': current_month_target
                })

    if not weekly_data:
        logger.warning("[align_current_month_weekly] 未找到有效的周度-当月配对数据")
        return pd.DataFrame(columns=['month', 'week_date', 'nowcast', 'current_month_target'])

    return pd.DataFrame(weekly_data)


def align_current_month_last_friday(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> pd.DataFrame:
    """对齐m月最后周五nowcast与m月target、m-1月target（用于本月配对Hit Rate和MAE计算）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        pd.DataFrame: 对齐后数据，列['month', 'last_friday_date', 'nowcast', 'prev_target', 'current_target']
    """
    # 使用公共函数准备数据
    nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)

    monthly_friday_data = []

    for period, group in nowcast_df.groupby('NowcastMonth'):
        # 找到该月的所有周五 (weekday=4)
        fridays = group[group.index.weekday == 4]
        if fridays.empty:
            continue

        last_friday_date = fridays.index.max()
        last_friday_nowcast = fridays.loc[last_friday_date, 'Nowcast']

        # 获取上月��当月的target
        prev_period = period - 1

        if prev_period in target_df.index and period in target_df.index:
            prev_target = target_df.loc[prev_period, 'Target']
            current_target = target_df.loc[period, 'Target']

            monthly_friday_data.append({
                'month': period,
                'last_friday_date': last_friday_date,
                'nowcast': last_friday_nowcast,
                'prev_target': prev_target,
                'current_target': current_target
            })

    if not monthly_friday_data:
        logger.warning("[align_current_month_last_friday] 未找到有效的月度最后周五配对数据")
        return pd.DataFrame(columns=['month', 'last_friday_date', 'nowcast', 'prev_target', 'current_target'])

    df = pd.DataFrame(monthly_friday_data)
    df = df.set_index('last_friday_date').sort_index()

    return df


def calculate_current_month_rmse(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """计算m月所有周nowcast与m月target配对的RMSE（本月配对）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: RMSE值，失败返回np.inf
    """
    try:
        aligned_df = align_current_month_weekly_data(nowcast_series, target_series)

        if aligned_df.empty or len(aligned_df) < 2:
            logger.warning(f"[current_month_rmse] 配对数据不足: {len(aligned_df)}个数据点")
            return np.inf

        squared_errors = (aligned_df['nowcast'] - aligned_df['current_month_target']) ** 2
        rmse = np.sqrt(squared_errors.mean())
        return float(rmse)

    except Exception as e:
        logger.error(f"[current_month_rmse] 计算失败: {e}")
        return np.inf


def calculate_current_month_mae(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """计算m月最后周五nowcast与m月target配对的MAE（本月配对）

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: MAE值，失败返回np.inf
    """
    try:
        aligned_df = align_current_month_last_friday(nowcast_series, target_series)

        if aligned_df.empty or len(aligned_df) < 2:
            logger.warning(f"[current_month_mae] 配对数据不足: {len(aligned_df)}个数据点")
            return np.inf

        abs_errors = np.abs(aligned_df['nowcast'] - aligned_df['current_target'])
        mae = abs_errors.mean()
        return float(mae)

    except Exception as e:
        logger.error(f"[current_month_mae] 计算失败: {e}")
        return np.inf


# ==================== 统一调度函数 ====================

def calculate_aligned_rmse(
    nowcast_series: pd.Series,
    target_series: pd.Series,
    alignment_mode: str = 'next_month'
) -> float:
    """根据配对模式计算RMSE

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列
        alignment_mode: 配对模式 ('current_month' 或 'next_month')

    Returns:
        float: RMSE值
    """
    if alignment_mode == 'current_month':
        return calculate_current_month_rmse(nowcast_series, target_series)
    else:
        return calculate_next_month_rmse(nowcast_series, target_series)


def calculate_aligned_mae(
    nowcast_series: pd.Series,
    target_series: pd.Series,
    alignment_mode: str = 'next_month'
) -> float:
    """根据配对模式计算MAE

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列
        alignment_mode: 配对模式 ('current_month' 或 'next_month')

    Returns:
        float: MAE值
    """
    if alignment_mode == 'current_month':
        return calculate_current_month_mae(nowcast_series, target_series)
    else:
        return calculate_next_month_mae(nowcast_series, target_series)


# ==================== Win Rate计算（2025-12-20重构：消除重复代码）====================

def _prepare_monthly_dataframes(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    准备对齐所需的标准化DataFrame

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]:
            - nowcast_df: 带NowcastMonth列的DataFrame
            - target_df: 按月分组后的DataFrame（Period索引）
    """
    # 转换DatetimeIndex
    if not isinstance(nowcast_series.index, pd.DatetimeIndex):
        nowcast_series = nowcast_series.copy()
        nowcast_series.index = pd.to_datetime(nowcast_series.index)
    if not isinstance(target_series.index, pd.DatetimeIndex):
        target_series = target_series.copy()
        target_series.index = pd.to_datetime(target_series.index)

    # 创建带月份列的DataFrame
    nowcast_df = nowcast_series.to_frame('Nowcast').copy()
    nowcast_df['NowcastMonth'] = nowcast_df.index.to_period('M')

    target_df = target_series.to_frame('Target').copy()
    target_df['TargetMonth'] = target_df.index.to_period('M')
    # 确保每月只有一个target值（先dropna避免取到NaN行）
    target_df = target_df.dropna(subset=['Target']).groupby('TargetMonth').last()

    return nowcast_df, target_df


def _calculate_win_rate_core(
    nowcast_df: pd.DataFrame,
    target_df: pd.DataFrame,
    alignment_mode: str
) -> float:
    """
    核心Win Rate计算逻辑

    Args:
        nowcast_df: 带NowcastMonth列的DataFrame
        target_df: 月度分组的target DataFrame（Period索引）
        alignment_mode: 'current_month' 或 'next_month'

    Returns:
        float: Win Rate百分比（0-100），数据不足返回np.nan
    """
    hits = 0
    total = 0

    for date, row in nowcast_df.iterrows():
        current_month = row['NowcastMonth']
        current_nowcast = row['Nowcast']

        # 根据模式选择月份关系
        if alignment_mode == 'current_month':
            ref_month = current_month - 1
            target_month = current_month
        else:  # next_month
            ref_month = current_month
            target_month = current_month + 1

        # 检查数据可用性
        if ref_month not in target_df.index or target_month not in target_df.index:
            continue

        ref_target = target_df.loc[ref_month, 'Target']
        target_value = target_df.loc[target_month, 'Target']

        # 检查有效性
        if not (np.isfinite(ref_target) and np.isfinite(target_value) and np.isfinite(current_nowcast)):
            continue

        # 计算方向
        pred_direction = np.sign(current_nowcast - ref_target)
        actual_direction = np.sign(target_value - ref_target)

        # 判断吻合
        if pred_direction == actual_direction:
            hits += 1
        total += 1

    # 验证数据充足性
    if total < 2:
        logger.warning(f"[{alignment_mode}_win_rate] 有效周数不足: {total}个数据点")
        return np.nan

    return (hits / total) * 100.0


def calculate_current_month_win_rate(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """
    计算本月配对模式的预测胜率

    对每周t（所属月份为m）：
    - 预测方向：sign(nowcast[t] - target[m-1])
    - 实际方向：sign(target[m] - target[m-1])
    - 吻合：符号相同

    语义：nowcast是否正确预测了"本月相对上月"的变化方向

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: Win Rate百分比（0-100），数据不足返回np.nan
    """
    try:
        nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)
        return _calculate_win_rate_core(nowcast_df, target_df, 'current_month')
    except Exception as e:
        logger.error(f"[current_month_win_rate] 计算失败: {e}")
        return np.nan


def calculate_next_month_win_rate(
    nowcast_series: pd.Series,
    target_series: pd.Series
) -> float:
    """
    计算下月配对模式的预测胜率

    对每周t（所属月份为m）：
    - 预测方向：sign(nowcast[t] - target[m])
    - 实际方向：sign(target[m+1] - target[m])
    - 吻合：符号相同

    语义：nowcast是否正确预测了"下月相对本月"的变化方向

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列

    Returns:
        float: Win Rate百分比（0-100），数据不足返回np.nan
    """
    try:
        nowcast_df, target_df = _prepare_monthly_dataframes(nowcast_series, target_series)
        return _calculate_win_rate_core(nowcast_df, target_df, 'next_month')
    except Exception as e:
        logger.error(f"[next_month_win_rate] 计算失败: {e}")
        return np.nan


def calculate_aligned_win_rate(
    nowcast_series: pd.Series,
    target_series: pd.Series,
    alignment_mode: str = 'next_month'
) -> float:
    """根据配对模式计算Win Rate

    Args:
        nowcast_series: 周度nowcast序列
        target_series: 月度target序列
        alignment_mode: 配对模式 ('current_month' 或 'next_month')

    Returns:
        float: Win Rate百分比（0-100）
    """
    if alignment_mode == 'current_month':
        return calculate_current_month_win_rate(nowcast_series, target_series)
    else:
        return calculate_next_month_win_rate(nowcast_series, target_series)
