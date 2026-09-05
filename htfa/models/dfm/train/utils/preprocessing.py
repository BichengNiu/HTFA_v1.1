# -*- coding: utf-8 -*-
"""
数据预处理工具函数

提供共享的数据标准化和预处理功能，供 factor_model.py 和 ddfm_model.py 使用。
"""

import numpy as np
import pandas as pd
from typing import Tuple
from htfa.models.dfm.train.constants import ZERO_STD_REPLACEMENT


def standardize_data(
    train_data: pd.DataFrame,
    full_data: pd.DataFrame = None
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """数据标准化：中心化和标准化

    使用训练期数据计算均值和标准差，然后应用到完整数据。

    Args:
        train_data: 训练期数据（用于计算均值和标准差）
        full_data: 完整数据（需要处理的数据），如果为None则使用train_data

    Returns:
        Tuple: (中心化数据DataFrame, 标准化数据ndarray, 均值, 标准差)
    """
    if full_data is None:
        full_data = train_data

    # 使用训练期数据计算均值和标准差
    means = train_data.mean(skipna=True).values
    stds = train_data.std(skipna=True).values

    # 处理零标准差
    stds = np.where(stds > 0, stds, ZERO_STD_REPLACEMENT)

    # 中心化数据
    obs_centered = full_data - means

    # 标准化数据并填充NaN为0
    Z_standardized = (obs_centered / stds).fillna(0).values

    return obs_centered, Z_standardized, means, stds


__all__ = ['standardize_data']
