# -*- coding: utf-8 -*-
"""
得分比较器模块

提供统一的得分比较逻辑，从BackwardSelector中提取
"""

import numpy as np
from typing import Tuple
from dashboard.models.DFM.train.utils.logger import get_logger

logger = get_logger(__name__)


class ScoreComparator:
    """
    得分比较器

    封装变量选择过程中的得分比较逻辑
    """

    def __init__(
        self,
        rmse_tolerance_percent: float = 1.0,
        win_rate_tolerance_percent: float = 5.0,
        selection_criterion: str = 'hybrid',
        prioritize_win_rate: bool = True
    ):
        """
        初始化得分比较器

        Args:
            rmse_tolerance_percent: RMSE容忍度百分比
            win_rate_tolerance_percent: Win Rate容忍度百分比
            selection_criterion: 筛选标准 ('rmse', 'win_rate', 'hybrid')
            prioritize_win_rate: 混合策略中是否优先考虑Win Rate
        """
        self.rmse_tolerance_percent = rmse_tolerance_percent
        self.win_rate_tolerance_percent = win_rate_tolerance_percent
        self.selection_criterion = selection_criterion
        self.prioritize_win_rate = prioritize_win_rate

    def compare(
        self,
        new_score: Tuple[float, float, float],
        current_score: Tuple[float, float, float]
    ) -> int:
        """
        比较两个得分

        Args:
            new_score: 新得分元组 (weighted_rmse, neg_oos_rmse, oos_rmse)
            current_score: 当前得分元组

        Returns:
            1: new_score更好
            0: 相当
            -1: current_score更好
        """
        from dashboard.models.DFM.train.evaluation.metrics import compare_scores_with_winrate

        return compare_scores_with_winrate(
            new_score,
            current_score,
            rmse_tolerance_percent=self.rmse_tolerance_percent,
            win_rate_tolerance_percent=self.win_rate_tolerance_percent,
            selection_criterion=self.selection_criterion,
            prioritize_win_rate=self.prioritize_win_rate
        )

    def is_better(
        self,
        new_score: Tuple[float, float, float],
        current_score: Tuple[float, float, float]
    ) -> bool:
        """
        判断新得分是否更好

        Args:
            new_score: 新得分元组
            current_score: 当前得分元组

        Returns:
            True如果new_score更好
        """
        return self.compare(new_score, current_score) > 0

    def is_improvement(
        self,
        new_rmse: float,
        current_rmse: float,
        new_win_rate: float = np.nan,
        current_win_rate: float = np.nan
    ) -> bool:
        """
        判断是否有改善（简化接口）

        Args:
            new_rmse: 新RMSE
            current_rmse: 当前RMSE
            new_win_rate: 新Win Rate
            current_win_rate: 当前Win Rate

        Returns:
            True如果有改善
        """
        # RMSE改善百分比
        if current_rmse > 0:
            rmse_improve_pct = (current_rmse - new_rmse) / current_rmse * 100
        else:
            rmse_improve_pct = 0

        # Win Rate改善
        if np.isfinite(new_win_rate) and np.isfinite(current_win_rate):
            win_rate_improve = new_win_rate - current_win_rate
        else:
            win_rate_improve = 0

        # 根据策略判断
        if self.selection_criterion == 'rmse':
            return rmse_improve_pct >= -self.rmse_tolerance_percent
        elif self.selection_criterion == 'win_rate':
            return win_rate_improve >= -self.win_rate_tolerance_percent
        else:  # hybrid
            if self.prioritize_win_rate:
                # Win Rate优先：Win Rate改善或持平时，RMSE不能恶化太多
                if win_rate_improve >= 0:
                    return rmse_improve_pct >= -self.rmse_tolerance_percent
                else:
                    return rmse_improve_pct > self.rmse_tolerance_percent
            else:
                # RMSE优先：RMSE改善或持平时，Win Rate不能恶化太多
                if rmse_improve_pct >= 0:
                    return win_rate_improve >= -self.win_rate_tolerance_percent
                else:
                    return win_rate_improve > self.win_rate_tolerance_percent


__all__ = ['ScoreComparator']
