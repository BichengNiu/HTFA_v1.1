# -*- coding: utf-8 -*-
"""
数据工具模块

提供数据加载、验证和处理相关功能
"""

import pandas as pd
from typing import Tuple, List
from dashboard.models.DFM.utils.text_utils import match_columns_case_insensitive
from dashboard.models.DFM.train.utils.logger import get_logger

logger = get_logger(__name__)


def load_and_validate_data(
    data: pd.DataFrame,
    selected_indicators: List[str],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    加载和验证训练数据（经典DFM版本，无目标变量）

    对内存中的训练数据进行质量检查和清理。
    所有选中的指标平等参与因子提取。

    Args:
        data: 训练数据
        selected_indicators: 选中的指标列表（空列表表示使用所有变量）

    Returns:
        (data, variable_names):
            - data: 观测数据 DataFrame
            - variable_names: 有效变量列表

    Raises:
        ValueError: 如果文件格式不支持或有效变量不足
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("训练数据必须是非空DataFrame")
    data = data.copy()
    logger.info("加载内存训练数据: shape=%s", data.shape)

    # 确定观测变量
    if selected_indicators:
        logger.info(f"用户选择的指标数量: {len(selected_indicators)}")

        # 匹配变量（不区分大小写）
        variable_names, case_mismatches = match_columns_case_insensitive(
            data.columns,
            selected_indicators,
        )
        for var, actual_col in case_mismatches:
            logger.info(f"变量名大小写匹配: '{var}' -> '{actual_col}'")

        missing_vars = [
            var for var in selected_indicators if var not in variable_names
        ]
        if missing_vars:
            logger.warning(f"以下变量不在数据文件中，将被跳过: {missing_vars}")

        logger.info(f"在数据文件中找到的变量数: {len(variable_names)}")
    else:
        variable_names = list(data.columns)

    # 数据质量检查和清理 - 已禁用自动过滤
    # 注意: 不再自动移除有效数据点少的变量，保留用户选择的所有变量
    logger.info("跳过数据质量自动过滤，保留所有用户选择的变量")

    # 验证是否还有足够的变量
    if len(variable_names) < 1:
        raise ValueError(
            f"有效变量不足({len(variable_names)}个), "
            f"至少需要1个有效变量进行DFM建模"
        )

    # 单变量警告
    if len(variable_names) == 1:
        logger.warning(
            f"只有1个变量 {variable_names[0]}，"
            f"模型预测能力可能有限，建议补充更多变量"
        )

    logger.info(
        f"数据加载完成: {data.shape}, "
        f"有效变量数: {len(variable_names)}"
    )

    return data, variable_names


__all__ = ['load_and_validate_data']
