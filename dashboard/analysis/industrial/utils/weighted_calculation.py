"""
加权计算模块
Weighted Calculation Module

目标：
1. 优化calculate_weighted_groups函数，消除重复的分组逻辑（约70行重复）
2. 提取可重用的加权计算函数
3. 提高代码可维护性和可测试性
"""

import pandas as pd
from typing import Dict, List, Tuple
import logging

from dashboard.analysis.industrial.utils import get_weight_for_year, filter_data_from_2012

logger = logging.getLogger(__name__)


def create_weight_series_for_indicator(
    weights_row: pd.Series,
    time_index: pd.DatetimeIndex
) -> pd.Series:
    """
    为指定指标创建权重Series，根据时间索引的年份选择合适的权重

    Args:
        weights_row: 权重数据行（包含权重_2012、权重_2018、权重_2020）
        time_index: 时间索引

    Returns:
        权重Series，索引与time_index对齐
    """
    weight_series = pd.Series(index=time_index, dtype=float)

    # 批量处理：按年份分组
    for year in time_index.year.unique():
        year_mask = time_index.year == year
        weight = get_weight_for_year(weights_row, year)
        weight_series.loc[year_mask] = weight

    return weight_series


def calculate_weighted_sum_for_group(
    df_macro: pd.DataFrame,
    indicators: List[str],
    weights_mapping: Dict[str, pd.Series]
) -> pd.Series:
    """
    计算一个分组的加权求和（拉动率）（向量化优化）

    加权求和 = Σ(增速_i × 权重_i)
    这表示分组对总体工业增加值的拉动率

    注意：这里计算的是拉动率，不是加权平均增速
    拉动率可以跨分组相加，拉动率总和 ≈ 总体工业增加值增速

    Args:
        df_macro: 宏观数据DataFrame
        indicators: 该分组包含的指标列表
        weights_mapping: 指标到权重Series的映射 {指标名: 权重Series}

    Returns:
        拉动率Series
    """
    if not indicators:
        return pd.Series(dtype=float)

    weighted_sum = None

    for indicator in indicators:
        if indicator not in df_macro.columns:
            continue

        # 转换为数值型，保留NaN
        series = pd.to_numeric(df_macro[indicator], errors='coerce')

        # 获取权重Series
        if indicator not in weights_mapping:
            logger.warning(f"指标 {indicator} 没有对应的权重Series")
            continue

        weight_series = weights_mapping[indicator]

        # 向量化乘法：series * weight_series
        weighted_values = series * weight_series

        # 向量化加法
        if weighted_sum is None:
            weighted_sum = weighted_values
        else:
            # 使用pandas的add方法，正确处理NaN
            weighted_sum = weighted_sum.add(weighted_values, fill_value=0)

    if weighted_sum is not None:
        # 将全为0的值转换为NaN（保持原有的NaN语义）
        weighted_sum = weighted_sum.replace(0, pd.NA)

    return weighted_sum


def build_weights_mapping(
    df_weights: pd.DataFrame,
    target_columns: List[str]
) -> Dict[str, Dict]:
    """
    构建权重映射字典

    Args:
        df_weights: 权重数据DataFrame
        target_columns: 目标列列表

    Returns:
        权重映射字典 {指标名: {出口依赖, 上中下游, 三大产业, weights_row}}
    """
    weights_mapping = {}

    for _, row in df_weights.iterrows():
        indicator_name = row['指标名称']
        if pd.notna(indicator_name) and indicator_name in target_columns:
            industry_col = row.iloc[1] if len(row) > 1 else None
            weights_mapping[indicator_name] = {
                '出口依赖': row['出口依赖'],
                '上中下游': row['上中下游'],
                '三大产业': industry_col,
                'weights_row': row
            }

    return weights_mapping


def categorize_indicators(
    weights_mapping: Dict[str, Dict]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]]]:
    """
    按出口依赖、上中下游和三大产业对指标进行分类

    Args:
        weights_mapping: 权重映射字典

    Returns:
        (export_groups, stream_groups, industry_groups) 元组
        - export_groups: {出口依赖类型: [指标列表]}
        - stream_groups: {上中下游类型: [指标列表]}
        - industry_groups: {三大产业类型: [指标列表]}
    """
    export_groups = {}
    stream_groups = {}
    industry_groups = {}

    for indicator, info in weights_mapping.items():
        export_dep = info['出口依赖']
        stream_type = info['上中下游']
        industry_type = info['三大产业']

        # 分类到出口依赖
        if pd.notna(export_dep):
            if export_dep not in export_groups:
                export_groups[export_dep] = []
            export_groups[export_dep].append(indicator)

        # 分类到上中下游
        if pd.notna(stream_type):
            if stream_type not in stream_groups:
                stream_groups[stream_type] = []
            stream_groups[stream_type].append(indicator)

        # 分类到三大产业
        if pd.notna(industry_type):
            if industry_type not in industry_groups:
                industry_groups[industry_type] = []
            industry_groups[industry_type].append(indicator)

    return export_groups, stream_groups, industry_groups


def prepare_weights_series_mapping(
    weights_mapping: Dict[str, Dict],
    time_index: pd.DatetimeIndex
) -> Dict[str, pd.Series]:
    """
    预先为每个指标创建权重Series

    Args:
        weights_mapping: 权重映射字典
        time_index: 时间索引

    Returns:
        {指标名: 权重Series} 映射
    """
    weights_series_mapping = {}

    for indicator, info in weights_mapping.items():
        weights_row = info['weights_row']
        weight_series = create_weight_series_for_indicator(weights_row, time_index)
        weights_series_mapping[indicator] = weight_series

    return weights_series_mapping


def calculate_grouped_weights(
    groups: Dict[str, List[str]],
    df_macro: pd.DataFrame,
    weights_series_mapping: Dict[str, pd.Series],
    group_prefix: str
) -> pd.DataFrame:
    """
    计算多个分组的加权和（通用函数）

    这个函数消除了export_groups和stream_groups的重复计算逻辑

    Args:
        groups: 分组字典 {分组名: [指标列表]}
        df_macro: 宏观数据DataFrame
        weights_series_mapping: 权重Series映射
        group_prefix: 分组前缀（如"出口依赖_"或"上中下游_"）

    Returns:
        包含各分组加权和的DataFrame
    """
    result_df = pd.DataFrame(index=df_macro.index)

    for group_name, indicators in groups.items():
        if not indicators:
            continue

        # 计算该分组的加权和
        weighted_sum = calculate_weighted_sum_for_group(
            df_macro,
            indicators,
            weights_series_mapping
        )

        if weighted_sum is not None and not weighted_sum.empty:
            column_name = f'{group_prefix}{group_name}'
            result_df[column_name] = weighted_sum

    return result_df


def calculate_weighted_groups_optimized(
    df_macro: pd.DataFrame,
    df_weights: pd.DataFrame,
    target_columns: List[str]
) -> pd.DataFrame:
    """
    优化版本的calculate_weighted_groups函数

    改进点：
    1. 消除重复代码：export和stream分组使用相同的计算逻辑
    2. 提高可维护性：拆分为多个小函数
    3. 保持性能：向量化操作
    4. 提高可测试性：每个步骤可以单独测试

    Args:
        df_macro: 宏观数据DataFrame
        df_weights: 权重数据DataFrame
        target_columns: 目标列列表

    Returns:
        包含加权分组时间序列的DataFrame
    """
    try:
        # 过滤数据，只保留2012年及以后的数据
        df_macro_filtered = filter_data_from_2012(df_macro)

        if df_macro_filtered.empty:
            logger.warning("过滤后数据为空")
            return pd.DataFrame()

        # 第1步：构建权重映射
        weights_mapping = build_weights_mapping(df_weights, target_columns)

        if not weights_mapping:
            logger.warning("未找到匹配的权重映射")
            return pd.DataFrame()

        # 第2步：按出口依赖、上中下游和三大产业分类
        export_groups, stream_groups, industry_groups = categorize_indicators(weights_mapping)

        if not export_groups and not stream_groups and not industry_groups:
            logger.warning("未找到有效的分组")
            return pd.DataFrame()

        # 第3步：预先创建所有指标的权重Series
        weights_series_mapping = prepare_weights_series_mapping(
            weights_mapping,
            df_macro_filtered.index
        )

        # 第4步：计算出口依赖分组（使用通用函数）
        export_result = calculate_grouped_weights(
            export_groups,
            df_macro_filtered,
            weights_series_mapping,
            group_prefix='出口依赖_'
        )

        # 第5步：计算上中下游分组（使用通用函数）
        stream_result = calculate_grouped_weights(
            stream_groups,
            df_macro_filtered,
            weights_series_mapping,
            group_prefix='上中下游_'
        )

        # 合并结果
        result_df = pd.concat([export_result, stream_result], axis=1)

        return result_df

    except KeyError as e:
        logger.warning(f"数据列不存在，无法计算加权分组: {e}")
        return pd.DataFrame()
    except ValueError as e:
        logger.warning(f"数据值错误，无法计算加权分组: {e}")
        return pd.DataFrame()
    except TypeError as e:
        logger.warning(f"数据类型错误，无法计算加权分组: {e}")
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        logger.warning("输入数据为空，无法计算加权分组")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"计算加权分组时发生未预期错误: {e}", exc_info=True)
        return pd.DataFrame()
