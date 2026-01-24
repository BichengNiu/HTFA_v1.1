# -*- coding: utf-8 -*-
"""
评估层

模型评估指标计算
"""

# 指标计算
from dashboard.models.DFM.train.evaluation.metrics import (
    # Win Rate计算（支持不同配对模式）
    calculate_current_month_win_rate,
    calculate_next_month_win_rate,
    calculate_aligned_win_rate,
    # RMSE/MAE计算
    calculate_aligned_rmse,
    calculate_aligned_mae,
    # 得分计算
    calculate_weighted_score,
    compare_scores_with_winrate
)

# 数据模型（从core.models导入）
from dashboard.models.DFM.train.core.models import MetricsResult

__all__ = [
    # Win Rate
    'calculate_current_month_win_rate',
    'calculate_next_month_win_rate',
    'calculate_aligned_win_rate',
    # RMSE/MAE
    'calculate_aligned_rmse',
    'calculate_aligned_mae',
    # 得分计算
    'calculate_weighted_score',
    'compare_scores_with_winrate',
    'MetricsResult',
]
