# -*- coding: utf-8 -*-
"""
观测变量先验预测器

计算卡尔曼滤波的先验预测值：y_t|t-1 = H × f_t|t-1
用于新闻分解中���算正确的expected_value。
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict

from ..utils.exceptions import ComputationError, ValidationError

logger = logging.getLogger(__name__)


class ObservationPriorPredictor:
    """
    观测变量先验预测器

    基于卡尔曼滤波的先验因子状态和因子载荷矩阵，
    计算任意变量在任意时刻的先验预测值。

    公式：y_t|t-1 = H × f_t|t-1

    其中：
    - H: 因子载荷矩阵 (n_variables, n_factors)
    - f_t|t-1: 先验因子状态 (n_factors,)
    """

    def __init__(
        self,
        factor_states_predicted: np.ndarray,  # (n_time, n_factors)
        factor_loadings: np.ndarray,          # (n_variables, n_factors)
        variable_index_map: Dict[str, int],
        time_index: pd.DatetimeIndex
    ):
        """
        初始化先验预测器

        Args:
            factor_states_predicted: 先验因子状态数组 (n_time, n_factors)
            factor_loadings: 因子载荷矩阵 (n_variables, n_factors)
            variable_index_map: 变量名到索引的映射
            time_index: 时间索引

        Raises:
            ValidationError: 输入数据形状不匹配时抛出
        """
        # 验证factor_states_predicted形状
        if factor_states_predicted.ndim != 2:
            raise ValidationError(
                f"factor_states_predicted必须是2维数组，"
                f"实际维度: {factor_states_predicted.ndim}"
            )

        # 验证factor_loadings形状
        if factor_loadings.ndim != 2:
            raise ValidationError(
                f"factor_loadings必须是2维数组，"
                f"实际维度: {factor_loadings.ndim}"
            )

        # 验证因子数一致性
        if factor_states_predicted.shape[1] != factor_loadings.shape[1]:
            raise ValidationError(
                f"因子数不匹配: factor_states_predicted有{factor_states_predicted.shape[1]}个因子，"
                f"factor_loadings有{factor_loadings.shape[1]}个因子"
            )

        # 验证时间索引长度
        if len(time_index) != factor_states_predicted.shape[0]:
            raise ValidationError(
                f"时间索引长度({len(time_index)})与"
                f"factor_states_predicted行数({factor_states_predicted.shape[0]})不匹配"
            )

        self.H = factor_loadings                    # (n_variables, n_factors)
        self.f_pred = factor_states_predicted       # (n_time, n_factors)
        self.var_map = variable_index_map
        self.time_index = time_index

        # 预计算所有预测: (n_variables, n_time)
        # H @ f_pred.T = (n_variables, n_factors) @ (n_factors, n_time) = (n_variables, n_time)
        self.predictions = self.H @ self.f_pred.T

        logger.info("初始化完成:")
        logger.info(f"  - H矩阵形状: {self.H.shape}")
        logger.info(f"  - 先验因子状态形状: {self.f_pred.shape}")
        logger.info(f"  - 预测矩阵形状: {self.predictions.shape}")
        logger.info(f"  - 变量数: {len(self.var_map)}")
        logger.info(f"  - 时间点数: {len(self.time_index)}")

    def get_prior_prediction(self, var_name: str, timestamp: pd.Timestamp) -> float:
        """
        获取指定变量在指定时刻的先验预测值

        Args:
            var_name: 变量名
            timestamp: 时间戳

        Returns:
            先验预测值

        Raises:
            ComputationError: 变量不存在或时间戳超出范围时抛出
        """
        if var_name not in self.var_map:
            available_vars = list(self.var_map.keys())
            raise ComputationError(
                f"变量 '{var_name}' 不在先验预测器的变量映射中。\n"
                f"可用变量数: {len(available_vars)}\n"
                f"前5个可用变量: {available_vars[:5]}"
            )

        var_idx = self.var_map[var_name]

        # 边界检查：验证var_idx在predictions范围内
        if var_idx < 0 or var_idx >= self.predictions.shape[0]:
            raise ComputationError(
                f"变量索引 {var_idx} 超出预测矩阵范围 [0, {self.predictions.shape[0]})。\n"
                f"变量名: {var_name}"
            )

        # 找时间索引（找到最接近且不晚于timestamp的时间点）
        earlier = self.time_index[self.time_index <= timestamp]
        if len(earlier) == 0:
            raise ComputationError(
                f"时间戳 {timestamp} 早于所有可用时间点。\n"
                f"最早可用时间: {self.time_index.min()}"
            )

        time_idx = len(earlier) - 1

        # 边界检查
        if time_idx >= self.predictions.shape[1]:
            time_idx = self.predictions.shape[1] - 1

        prediction = float(self.predictions[var_idx, time_idx])
        return prediction
