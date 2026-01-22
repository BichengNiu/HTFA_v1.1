# -*- coding: utf-8 -*-
"""
Nowcast提取器

从保存的DFM模型中提取nowcast时间序列和相关状态信息，
为影响分析提供基础数据和基准值。
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, Optional

from ..utils.exceptions import ComputationError, DataFormatError
from .model_loader import SavedNowcastData

logger = logging.getLogger(__name__)


class NowcastExtractor:
    """
    Nowcast数据提取器

    专门用于从已保存的DFM模型数据中提取nowcast相关信息，
    提供基准预测值和状态信息用于影响分析。
    """

    def __init__(self, saved_nowcast_data: SavedNowcastData):
        """
        初始化Nowcast提取器

        Args:
            saved_nowcast_data: 已保存的nowcast数据
        """
        self.data = saved_nowcast_data

    def extract_nowcast_series(self, target_period: Optional[str] = None) -> pd.Series:
        """
        提取nowcast时间序列

        Args:
            target_period: 目标周期 (YYYY-MM格式)，None表示全部

        Returns:
            nowcast时间序列

        Raises:
            DataFormatError: 数据格式错误时抛出
        """
        try:
            if self.data.nowcast_series is None:
                raise DataFormatError("nowcast时间序列数据不可用")

            nowcast_series = self.data.nowcast_series.copy()

            # 过滤目标周期
            if target_period:
                target_date = pd.to_datetime(target_period)
                nowcast_series = nowcast_series[nowcast_series.index <= target_date]

            logger.info(f"提取nowcast序列: {len(nowcast_series)} 个数据点")
            if target_period:
                logger.info(f"目标周期: {target_period}")

            return nowcast_series

        except DataFormatError:
            raise
        except (KeyError, IndexError) as e:
            raise ComputationError(f"提取nowcast序列数据访问错误: {str(e)}", "nowcast_extraction")
        except (TypeError, ValueError) as e:
            raise ComputationError(f"提取nowcast序列数值错误: {str(e)}", "nowcast_extraction")

    def get_kalman_gains_matrix(self) -> np.ndarray:
        """
        获取最后一个可用的卡尔曼增益矩阵

        Returns:
            最后一个可用的卡尔曼增益矩阵

        Raises:
            DataFormatError: 卡尔曼增益历史不可用时抛出
        """
        if self.data.kalman_gains_history is not None and len(self.data.kalman_gains_history) > 0:
            for K_t in reversed(self.data.kalman_gains_history):
                if K_t is not None:
                    return K_t

        raise DataFormatError(
            "卡尔曼增益历史不可用。\n"
            "请使用新版本训练模块重新训练模型以支持影响分解功能。"
        )

    def extract_factor_loadings(self) -> np.ndarray:
        """
        提取因子载荷矩阵

        Returns:
            因子载荷矩阵

        Raises:
            DataFormatError: 数据不可用时抛出
        """
        if self.data.factor_loadings is None:
            raise DataFormatError("因子载荷矩阵不可用")

        logger.info(f"因子载荷矩阵: {self.data.factor_loadings.shape}")
        return self.data.factor_loadings

    def compute_baseline_prediction(self, target_date: pd.Timestamp) -> float:
        """
        计算基准预测值

        Args:
            target_date: 目标日期

        Returns:
            基准预测值

        Raises:
            ComputationError: 计算失败时抛出
        """
        try:
            nowcast_series = self.extract_nowcast_series()
            available_dates = nowcast_series.index[nowcast_series.index <= target_date]
            if len(available_dates) == 0:
                raise ComputationError(f"未找到 {target_date} 之前的基准预测")
            baseline_value = float(nowcast_series.loc[available_dates[-1]])
            logger.info(f"基准预测值 ({target_date}): {baseline_value:.4f}")
            return baseline_value
        except ComputationError:
            raise
        except (KeyError, IndexError) as e:
            raise ComputationError(f"计算基准预测数据访问错误: {str(e)}", "baseline_computation")
        except (TypeError, ValueError) as e:
            raise ComputationError(f"计算基准预测数值错误: {str(e)}", "baseline_computation")

    def get_extraction_summary(self) -> Dict[str, Any]:
        """
        获取数据提取摘要

        Returns:
            提取摘要字典
        """
        summary = {
            'target_variable': self.data.target_variable,
            'data_period': self.data.data_period,
            'nowcast_data_points': len(self.data.nowcast_series) if self.data.nowcast_series is not None else 0,
            'factor_count': self.data.factor_loadings.shape[1] if self.data.factor_loadings is not None else 0,
            'variable_count': self.data.factor_loadings.shape[0] if self.data.factor_loadings is not None else 0,
        }

        if self.data.nowcast_series is not None:
            summary.update({
                'nowcast_start_date': str(self.data.nowcast_series.index.min()),
                'nowcast_end_date': str(self.data.nowcast_series.index.max()),
                'nowcast_mean': float(self.data.nowcast_series.mean()),
                'nowcast_std': float(self.data.nowcast_series.std()),
            })

        if self.data.convergence_info:
            summary['convergence_info'] = self.data.convergence_info

        return summary