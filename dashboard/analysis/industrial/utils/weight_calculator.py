"""
Weight Calculator Utility
权重计算工具 - 统一的权重计算函数

消除重复代码:
- 原 macro_operations.py:233-252 (20行)
- 原 data_processor.py:13-32 (20行)
- 原 macro_operations.py:255-277 (23行)
- 原 data_processor.py:35-57 (23行)
"""

import pandas as pd


def get_weight_for_year(df_weights_row: pd.Series, year: int) -> float:
    """
    根据年份选择合适的权重（动态检测所有可用权重列）

    权重选择规则:
    - 优先使用与目标年份完全匹配的权重
    - 如果没有完全匹配，使用最接近但不超过目标年份的权重
    - 例如：
      - 2025年 → 权重_2025
      - 2024年 → 权重_2024
      - 2023年 → 权重_2023
      - 2022年 → 权重_2022
      - 2021年 → 权重_2020（因为没有权重_2021）
      - 2020年 → 权重_2020
      - 2019年 → 权重_2018
      - 2018年 → 权重_2018
      - 2017-2012年 → 权重_2012

    Args:
        df_weights_row: 权重数据行 (Series)，应包含权重_YYYY格式的列
        year: 目标年份

    Returns:
        对应年份的权重值，如果无可用权重则返回0.0
    """
    # 1. 从行中提取所有权重列（格式：权重_YYYY）
    weight_columns = [col for col in df_weights_row.index if col.startswith('权重_')]

    # 2. 提取年份并排序
    available_years = []
    for col in weight_columns:
        try:
            weight_year = int(col.split('_')[1])
            # 只考虑有效的权重值（非空）
            if pd.notna(df_weights_row[col]):
                available_years.append(weight_year)
        except (ValueError, IndexError):
            continue

    # 排序年份（从小到大）
    available_years.sort()

    # 3. 如果没有可用权重，返回0
    if not available_years:
        return 0.0

    # 4. 如果目标年份小于最早的权重年份，返回0
    if year < available_years[0]:
        return 0.0

    # 5. 选择最接近但不超过目标年份的权重
    # 使用最大的不超过目标年份的权重年份
    selected_year = available_years[0]
    for weight_year in available_years:
        if weight_year <= year:
            selected_year = weight_year
        else:
            break

    # 6. 返回选中的权重值
    weight_col = f'权重_{selected_year}'
    return df_weights_row[weight_col]


def filter_data_from_2012(df: pd.DataFrame) -> pd.DataFrame:
    """
    过滤数据，只保留2012年及以后的数据

    由于权重数据从2012年开始，2012年之前的数据无法进行加权计算，
    因此需要过滤掉这部分数据。

    Args:
        df: 输入的DataFrame，索引应为DatetimeIndex

    Returns:
        过滤后只包含2012年及以后数据的DataFrame
    """
    if df.empty:
        return df

    # 筛选2012年及以后的日期索引
    date_indices = []
    for idx in df.index:
        if hasattr(idx, 'year') and idx.year >= 2012:
            date_indices.append(idx)

    if date_indices:
        return df.loc[date_indices]
    else:
        return pd.DataFrame()


# 已删除create_year_to_weight_mapping函数
# 原因：该函数从未被使用（违反YAGNI原则）
# 如果将来需要，可以从git历史中恢复
