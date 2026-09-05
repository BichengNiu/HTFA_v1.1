"""数据预览摘要的计算口径规则。"""

from typing import List, Tuple

import pandas as pd


def uses_difference_calculation(indicator_unit: str, indicator_type: str) -> bool:
    """判断摘要变化项是否采用本期值减对比期值。"""
    return indicator_unit == '%' and indicator_type != '开工率'


def group_indicators_by_calculation(
    summary_table: pd.DataFrame,
) -> Tuple[List[str], List[str]]:
    """按摘要变化项的实际计算口径对当前表格指标分组。"""
    indicator_columns = [
        column for column in summary_table.columns
        if str(column).endswith("指标名称")
    ]
    required_columns = {'单位', '类型'}
    if not indicator_columns or not required_columns.issubset(summary_table.columns):
        return [], []

    indicator_column = indicator_columns[0]
    growth_indicators: List[str] = []
    difference_indicators: List[str] = []

    for _, row in summary_table.iterrows():
        indicator = str(row[indicator_column])
        target = (
            difference_indicators
            if uses_difference_calculation(row['单位'], row['类型'])
            else growth_indicators
        )
        if indicator not in target:
            target.append(indicator)

    return growth_indicators, difference_indicators
