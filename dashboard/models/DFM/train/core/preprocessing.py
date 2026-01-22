# -*- coding: utf-8 -*-
"""
数据预处理工具模块

提供统一的数据标准化功能，消除代码重复
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.constants import ZERO_STD_REPLACEMENT

logger = get_logger(__name__)


class DataStandardizer:
    """
    数据标准化器

    统一的标准化逻辑，支持fit/transform模式，避免数据泄露
    """

    def __init__(self):
        self.means_: Optional[np.ndarray] = None
        self.stds_: Optional[np.ndarray] = None
        self.column_names_: Optional[list] = None
        self._fitted = False

    def fit(self, train_data: pd.DataFrame) -> 'DataStandardizer':
        """
        使用训练数据计算标准化参数

        Args:
            train_data: 训练期数据

        Returns:
            self
        """
        self.means_ = train_data.mean(skipna=True).values
        self.stds_ = train_data.std(skipna=True).values

        # 处理零标准差
        self.stds_ = np.where(self.stds_ > 0, self.stds_, ZERO_STD_REPLACEMENT)

        self.column_names_ = train_data.columns.tolist()
        self._fitted = True

        logger.debug(
            f"DataStandardizer fitted: {len(self.column_names_)} columns, "
            f"mean range=[{self.means_.min():.2f}, {self.means_.max():.2f}]"
        )

        return self

    def transform(
        self,
        data: pd.DataFrame,
        fill_nan: bool = True,
        fill_value: float = 0.0
    ) -> np.ndarray:
        """
        标准化数据

        Args:
            data: 待标准化的数据
            fill_nan: 是否填充NaN
            fill_value: NaN填充值

        Returns:
            标准化后的numpy数组
        """
        if not self._fitted:
            raise RuntimeError("DataStandardizer未拟合，请先调用fit()")

        standardized = (data.values - self.means_) / self.stds_

        if fill_nan:
            standardized = np.nan_to_num(standardized, nan=fill_value)

        return standardized

    def fit_transform(
        self,
        train_data: pd.DataFrame,
        fill_nan: bool = True,
        fill_value: float = 0.0
    ) -> np.ndarray:
        """
        拟合并标准化数据

        Args:
            train_data: 训练数据
            fill_nan: 是否填充NaN
            fill_value: NaN填充值

        Returns:
            标准化后的numpy数组
        """
        self.fit(train_data)
        return self.transform(train_data, fill_nan, fill_value)

    def inverse_transform(self, data: np.ndarray) -> np.ndarray:
        """
        反标准化数据

        Args:
            data: 标准化后的数据

        Returns:
            原始尺度的数据
        """
        if not self._fitted:
            raise RuntimeError("DataStandardizer未拟合，请先调用fit()")

        return data * self.stds_ + self.means_

    def center(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        中心化数据（仅减去均值）

        Args:
            data: 待中心化的数据

        Returns:
            中心化后的DataFrame
        """
        if not self._fitted:
            raise RuntimeError("DataStandardizer未拟合，请先调用fit()")

        return data - self.means_

    @property
    def is_fitted(self) -> bool:
        """是否已拟合"""
        return self._fitted


def standardize_data(
    train_data: pd.DataFrame,
    full_data: Optional[pd.DataFrame] = None
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    标准化数据的便捷函数

    Args:
        train_data: 训练期数据（用于计算均值和标准差）
        full_data: 完整数据（需要处理的数据），如果为None则使用train_data

    Returns:
        Tuple: (中心化数据DataFrame, 标准化数据ndarray, 均值, 标准差)
    """
    if full_data is None:
        full_data = train_data

    standardizer = DataStandardizer()
    standardizer.fit(train_data)

    # 中心化数据
    obs_centered = standardizer.center(full_data)

    # 标准化数据
    Z_standardized = standardizer.transform(full_data, fill_nan=True, fill_value=0.0)

    return obs_centered, Z_standardized, standardizer.means_, standardizer.stds_


__all__ = [
    'DataStandardizer',
    'standardize_data'
]
