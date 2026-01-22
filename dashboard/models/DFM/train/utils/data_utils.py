# -*- coding: utf-8 -*-
"""
数据工具模块

提供数据加载、验证和处理相关功能
"""

import pandas as pd
from pathlib import Path
from typing import Tuple, List, Optional, Callable
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.utils.file_io import read_data_file

logger = get_logger(__name__)

# 常量定义
MIN_REQUIRED_DATA_POINTS = 10  # 变量需要的最小有效数据点数


def load_and_validate_data(
    data_path: str,
    target_variable: str,
    selected_indicators: List[str],
    progress_callback: Optional[Callable] = None
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    加载和验证训练数据

    支持Excel和CSV格式，自动进行数据质量检查和清理。

    Args:
        data_path: 数据文件路径 (支持 .xlsx, .xls, .csv)
        target_variable: 目标变量名
        selected_indicators: 选中的指标列表（空列表表示使用所有变量）
        progress_callback: 进度回调函数 (message: str) -> None

    Returns:
        (data, target_data, predictor_vars):
            - data: 完整数据 DataFrame
            - target_data: 目标变量 Series
            - predictor_vars: 有效预测变量列表

    Raises:
        ValueError: 如果文件格式不支持、目标变量不存在或有效变量不足
        FileNotFoundError: 如果文件不存在

    Examples:
        >>> data, target, predictors = load_and_validate_data(
        ...     data_path='data/经济数据.xlsx',
        ...     target_variable='GDP增速',
        ...     selected_indicators=['工业增加值', '消费', '投资']
        ... )
        >>> print(f"数据形状: {data.shape}, 预测变量数: {len(predictors)}")
    """
    logger.info(f"加载数据: {data_path}")

    data = read_data_file(data_path, parse_dates=True, check_exists=True)

    # 验证目标变量
    if target_variable not in data.columns:
        raise ValueError(
            f"目标变量'{target_variable}'不在数据中. "
            f"可用列: {list(data.columns[:5])}..."
        )

    target_data = data[target_variable]

    # 确定预测变量
    if selected_indicators:
        logger.info(f"用户选择的指标数量: {len(selected_indicators)}")

        # 构建不区分大小写的列名映射 (小写 -> 原始列名)
        import unicodedata
        column_mapping = {}
        for col in data.columns:
            normalized_col = unicodedata.normalize('NFKC', str(col)).strip().lower()
            column_mapping[normalized_col] = col

        # 匹配变量（不区分大小写）
        predictor_vars = []
        missing_vars = []

        for var in selected_indicators:
            if var == target_variable:
                continue

            # 先尝试精确匹配
            if var in data.columns:
                predictor_vars.append(var)
            else:
                # 尝试不区分大小写匹配
                normalized_var = unicodedata.normalize('NFKC', str(var)).strip().lower()
                if normalized_var in column_mapping:
                    actual_col = column_mapping[normalized_var]
                    predictor_vars.append(actual_col)
                    logger.info(f"变量名大小写匹配: '{var}' -> '{actual_col}'")
                else:
                    missing_vars.append(var)

        if missing_vars:
            logger.warning(f"以下变量不在数据文件中，将被跳过: {missing_vars}")

        logger.info(f"在数据文件中找到的预测变量数: {len(predictor_vars)}")
    else:
        predictor_vars = [
            v for v in data.columns
            if v != target_variable
        ]

    # 数据质量检查和清理 - 已禁用自动过滤
    # 注意: 不再自动移除有效数据点少的变量，保留用户选择的所有变量
    logger.info(f"跳过数据质量自动过滤，保留所有用户选择的变量")

    # 验证是否还有足够的预测变量（允许单变量）
    if len(predictor_vars) < 1:
        raise ValueError(
            f"有效预测变量不足({len(predictor_vars)}个), "
            f"至少需要1个有效变量进行DFM建模"
        )

    # 单变量警告
    if len(predictor_vars) == 1:
        logger.warning(
            f"只有1个预测变量 {predictor_vars[0]}，"
            f"模型预测能力可能有限，建议补充更多预测变量"
        )

    logger.info(
        f"数据加载完成: {data.shape}, "
        f"有效预测变量数: {len(predictor_vars)}"
    )

    return data, target_data, predictor_vars


__all__ = ['load_and_validate_data']
