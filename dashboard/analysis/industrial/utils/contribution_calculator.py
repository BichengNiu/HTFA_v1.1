"""
工业增加值拉动率计算模块

计算各分组和单个行业对总体工业增加值增速的拉动率。
拉动率公式：拉动率 = 增速 × 权重
"""

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np

from dashboard.core.ui.utils.debug_helpers import debug_log


def prepare_weights_series_for_contribution(
    weights_mapping: Dict[str, Dict],
    time_index: pd.DatetimeIndex
) -> Dict[str, pd.Series]:
    """
    为每个指标准备权重时间序列

    Args:
        weights_mapping: 权重映射 {指标名: {出口依赖, 上中下游, weights_row}}
        time_index: 时间索引

    Returns:
        {指标名: 权重Series}
    """
    from .weight_calculator import get_weight_for_year

    weights_series_mapping = {}

    for indicator, info in weights_mapping.items():
        weights_row = info['weights_row']

        weights_list = []
        for timestamp in time_index:
            year = timestamp.year
            weight = get_weight_for_year(weights_row, year)
            weights_list.append(weight)

        weights_series_mapping[indicator] = pd.Series(
            weights_list,
            index=time_index,
            name=indicator
        )

    return weights_series_mapping


def calculate_individual_contributions(
    df_macro: pd.DataFrame,
    weights_mapping: Dict[str, Dict]
) -> pd.DataFrame:
    """
    计算单个行业对总体工业增加值的拉动率

    拉动率 = 行业增速 × 行业权重

    Args:
        df_macro: 宏观数据（各行业增速），已过滤2012年及以后
        weights_mapping: 权重映射

    Returns:
        DataFrame，列为各行业拉动率，索引为时间
    """
    debug_log("开始计算单个行业拉动率", "DEBUG")

    weights_series_mapping = prepare_weights_series_for_contribution(
        weights_mapping, df_macro.index
    )

    contribution_df = pd.DataFrame(index=df_macro.index)
    missing_weights = []

    for indicator in df_macro.columns:
        if indicator not in weights_series_mapping:
            missing_weights.append(indicator)
            continue

        growth_series = df_macro[indicator]
        weight_series = weights_series_mapping[indicator]

        contribution_series = growth_series * weight_series
        contribution_df[indicator] = contribution_series

    if missing_weights:
        debug_log(
            f"警告: {len(missing_weights)} 个指标缺少权重，这些行业的拉动率将被忽略",
            "WARNING"
        )
        debug_log(f"缺少权重的指标: {missing_weights}", "WARNING")

    debug_log(f"单个行业拉动率计算完成，共 {len(contribution_df.columns)} 个行业", "DEBUG")

    return contribution_df


def calculate_group_contributions(
    df_macro: pd.DataFrame,
    weights_mapping: Dict[str, Dict],
    groups: Dict[str, List[str]],
    prefix: str = "",
    df_overall_growth: Optional[pd.DataFrame] = None,
    industry_to_column_map: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    计算分组对总体工业增加值的拉动率

    分组拉动率 = Σ(组内各行业拉动率)

    注意：对于三大产业分组，如果提供了df_overall_growth和industry_to_column_map，
    将优先使用"总体增速 × 总权重"的方式计算拉动率，以避免细分行业数据不一致性导致的误差。

    Args:
        df_macro: 宏观数据（各行业增速），已过滤2012年及以后
        weights_mapping: 权重映射
        groups: 分组字典 {组名: [指标列表]}
        prefix: 列名前缀
        df_overall_growth: 总体增速数据（可选），用于三大产业拉动率计算
        industry_to_column_map: 产业名称到总体增速列名的映射（可选）

    Returns:
        DataFrame，列为各分组拉动率，索引为时间
    """
    debug_log(f"开始计算分组拉动率（前缀: {prefix}），共 {len(groups)} 组", "DEBUG")

    individual_contributions = calculate_individual_contributions(
        df_macro, weights_mapping
    )

    group_contribution_df = pd.DataFrame(index=df_macro.index)

    # 标记是否是三大产业分组
    is_three_industries = (prefix == "三大产业_")
    use_overall_growth = (
        is_three_industries
        and df_overall_growth is not None
        and industry_to_column_map is not None
    )

    for group_name, indicators in groups.items():
        valid_indicators = [
            ind for ind in indicators
            if ind in individual_contributions.columns
        ]

        if not valid_indicators:
            debug_log(f"警告: 分组 {group_name} 没有有效指标", "WARNING")
            continue

        # 对于三大产业，优先使用总体增速计算
        if use_overall_growth and group_name in industry_to_column_map:
            overall_col = industry_to_column_map[group_name]

            if overall_col in df_overall_growth.columns:
                # 计算该产业的总权重
                total_weight_series = pd.Series(0.0, index=df_macro.index)

                for indicator in valid_indicators:
                    if indicator in weights_mapping:
                        weights_row = weights_mapping[indicator]['weights_row']
                        weight_series = pd.Series(index=df_macro.index, dtype=float)

                        for timestamp in df_macro.index:
                            year = timestamp.year
                            from .weight_calculator import get_weight_for_year
                            weight = get_weight_for_year(weights_row, year)
                            weight_series.loc[timestamp] = weight

                        total_weight_series += weight_series

                # 对齐索引
                overall_growth_series = df_overall_growth[overall_col].reindex(df_macro.index)

                # 拉动率 = 总体增速 × 总权重
                group_contribution = overall_growth_series * total_weight_series

                debug_log(
                    f"分组 {group_name} 使用总体增速计算拉动率（{len(valid_indicators)} 个指标）",
                    "INFO"
                )
            else:
                # 如果总体增速列不存在，回退到细分行业加权和
                group_contribution = individual_contributions[valid_indicators].sum(axis=1)
                debug_log(
                    f"警告: 分组 {group_name} 总体增速列 '{overall_col}' 不存在，使用细分行业加权和",
                    "WARNING"
                )
        else:
            # 其他分组使用细分行业加权和
            group_contribution = individual_contributions[valid_indicators].sum(axis=1)

        column_name = f"{prefix}{group_name}"
        group_contribution_df[column_name] = group_contribution

        if not use_overall_growth or group_name not in industry_to_column_map:
            debug_log(
                f"分组 {group_name} 拉动率计算完成，包含 {len(valid_indicators)} 个指标",
                "DEBUG"
            )

    return group_contribution_df


def validate_contributions(
    contribution_df: pd.DataFrame,
    total_growth: pd.Series,
    tolerance: float = 0.5
) -> Tuple[bool, pd.Series, pd.Series]:
    """
    验证拉动率总和是否等于总体增速

    Args:
        contribution_df: 拉动率DataFrame（各组或各行业）
        total_growth: 总体工业增加值增速Series
        tolerance: 容忍误差（百分点）

    Returns:
        (验证通过, 拉动率总和Series, 差值Series)
    """
    debug_log("开始验证拉动率总和", "DEBUG")

    contribution_df_aligned = contribution_df.reindex(total_growth.index)
    contribution_sum = contribution_df_aligned.sum(axis=1)

    difference = contribution_sum - total_growth

    max_diff = difference.abs().max()
    mean_diff = difference.abs().mean()

    validation_passed = max_diff <= tolerance

    debug_log(
        f"拉动率验证结果: 最大误差={max_diff:.4f}百分点, "
        f"平均误差={mean_diff:.4f}百分点, "
        f"容忍阈值={tolerance}百分点",
        "INFO"
    )

    if not validation_passed:
        debug_log(
            f"警告: 拉动率总和与总体增速差异超过容忍阈值 "
            f"(最大误差 {max_diff:.4f} > {tolerance})",
            "WARNING"
        )

        max_diff_date = difference.abs().idxmax()
        debug_log(
            f"最大误差发生在: {max_diff_date}, "
            f"拉动率总和={contribution_sum.loc[max_diff_date]:.4f}, "
            f"总体增速={total_growth.loc[max_diff_date]:.4f}",
            "WARNING"
        )

    return validation_passed, contribution_sum, difference


def calculate_all_contributions(
    df_macro: pd.DataFrame,
    df_weights: pd.DataFrame,
    total_growth_column: Optional[str] = None,
    df_overall_growth: Optional[pd.DataFrame] = None
) -> Dict[str, pd.DataFrame]:
    """
    统一计算所有拉动率（分组+单个行业）

    Args:
        df_macro: 宏观数据（各行业增速），已过滤2012年及以后
        df_weights: 权重数据
        total_growth_column: 总体增速列名（可选，使用标准列名）
        df_overall_growth: 总体增速数据（可选），包含三大产业的总体增速，用于提高三大产业拉动率准确性

    Returns:
        {
            'export_groups': 出口依赖分组拉动率,
            'stream_groups': 上中下游分组拉动率,
            'industry_groups': 三大产业分组拉动率,
            'individual': 单个行业拉动率,
            'total_growth': 总体增速Series,
            'validation': 验证结果
        }
    """
    from .weighted_calculation import build_weights_mapping, categorize_indicators
    from dashboard.analysis.industrial.constants import TOTAL_INDUSTRIAL_GROWTH_COLUMN

    debug_log("开始统一拉动率计算流程", "INFO")

    # 使用标准列名
    if total_growth_column is None:
        total_growth_column = TOTAL_INDUSTRIAL_GROWTH_COLUMN

    if total_growth_column not in df_macro.columns:
        raise ValueError(
            f"总体增速列 '{total_growth_column}' 不存在。"
            f"可用列: {list(df_macro.columns)}"
        )

    total_growth = df_macro[total_growth_column]

    target_columns = [col for col in df_macro.columns if col != total_growth_column]

    weights_mapping = build_weights_mapping(df_weights, target_columns)

    export_groups, stream_groups, industry_groups = categorize_indicators(weights_mapping)

    export_contribution = calculate_group_contributions(
        df_macro, weights_mapping, export_groups, '出口依赖_'
    )

    stream_contribution = calculate_group_contributions(
        df_macro, weights_mapping, stream_groups, '上中下游_'
    )

    # 三大产业分组拉动率：使用标准列名映射
    from dashboard.analysis.industrial.constants import (
        MINING_INDUSTRY_COLUMN,
        MANUFACTURING_INDUSTRY_COLUMN,
        UTILITIES_INDUSTRY_COLUMN
    )

    industry_to_column_map = {
        '采矿业': MINING_INDUSTRY_COLUMN,
        '制造业': MANUFACTURING_INDUSTRY_COLUMN,
        '电力、热力、燃气及水生产和供应业': UTILITIES_INDUSTRY_COLUMN
    }

    debug_log(f"三大产业列名映射: {industry_to_column_map}", "INFO")

    industry_contribution = calculate_group_contributions(
        df_macro, weights_mapping, industry_groups, '三大产业_',
        df_overall_growth=df_overall_growth,
        industry_to_column_map=industry_to_column_map
    )

    individual_contribution = calculate_individual_contributions(
        df_macro, weights_mapping
    )

    validation_passed, contribution_sum, difference = validate_contributions(
        individual_contribution, total_growth
    )

    result = {
        'export_groups': export_contribution,
        'stream_groups': stream_contribution,
        'industry_groups': industry_contribution,
        'individual': individual_contribution,
        'total_growth': total_growth,
        'validation': {
            'passed': validation_passed,
            'contribution_sum': contribution_sum,
            'difference': difference
        }
    }

    debug_log(
        f"拉动率计算完成: "
        f"出口依赖 {len(export_contribution.columns)} 组, "
        f"上中下游 {len(stream_contribution.columns)} 组, "
        f"三大产业 {len(industry_contribution.columns)} 组, "
        f"单个行业 {len(individual_contribution.columns)} 个",
        "INFO"
    )

    return result


def calculate_profit_contributions(
    df_industry_profit: pd.DataFrame,
    df_weights: pd.DataFrame
) -> Dict[str, pd.DataFrame]:
    """
    计算工业企业利润分行业拉动率（按上中下游分组）

    核心算法：
    1. 将40个行业的利润累计值转换为累计同比增长率
    2. 按上中下游分组汇总利润总额，计算各分组当期权重
    3. 使用前一年同期权重（基期权重）× 当期累计同比 = 拉动率
    4. 从40个行业加总计算总体增速，验证拉动率总和

    Args:
        df_industry_profit: 分行业利润数据（40个行业的利润总额累计值）
            - 索引：时间（DatetimeIndex）
            - 列：规模以上工业企业:利润总额:行业名称:累计值
        df_weights: 权重数据（包含上中下游标签）
            - 列：指标名称, 上中下游, 权重_2012, 权重_2018, 权重_2020

    Returns:
        {
            'stream_groups': 上中下游分组拉动率DataFrame,
            'individual': 单个行业拉动率DataFrame,
            'total_growth': 总体增速Series（从40个行业加总计算）,
            'validation': 验证结果字典
        }
    """
    from .weighted_calculation import build_weights_mapping, categorize_indicators
    from dashboard.analysis.industrial.utils import convert_cumulative_to_yoy

    debug_log("开始计算工业企业利润拉动率", "INFO")

    # 步骤1: 确保数据按时间升序排列
    df_industry_profit = df_industry_profit.sort_index()

    debug_log(f"输入数据形状: {df_industry_profit.shape}", "INFO")
    debug_log(f"日期范围: {df_industry_profit.index.min()} 到 {df_industry_profit.index.max()}", "INFO")

    # 步骤2: 将累计值转换为累计同比增长率
    profit_yoy_df = pd.DataFrame(index=df_industry_profit.index)

    for col in df_industry_profit.columns:
        if '利润总额' in str(col) and '累计值' in str(col):
            yoy_series = convert_cumulative_to_yoy(df_industry_profit[col])
            profit_yoy_df[col] = yoy_series

    # 过滤掉1月和2月的数据
    jan_feb_mask = profit_yoy_df.index.month.isin([1, 2])
    profit_yoy_df = profit_yoy_df[~jan_feb_mask]

    debug_log(f"累计同比数据形状（已过滤1-2月）: {profit_yoy_df.shape}", "INFO")

    if profit_yoy_df.empty:
        raise ValueError("转换累计同比后数据为空")

    # 步骤2: 从40个行业利润累计值加总，计算总体增速
    # 加总40个行业的累计值
    total_profit_cumulative = df_industry_profit.sum(axis=1)

    # 转换为累计同比增长率
    total_growth = convert_cumulative_to_yoy(total_profit_cumulative)

    # 过滤1-2月
    total_growth = total_growth[~jan_feb_mask]

    debug_log(f"总体增速计算完成，数据点数: {len(total_growth)}", "INFO")

    # 步骤3: 建立列名映射（利润列名 -> 工业增加值列名）
    # 示例：规模以上工业企业:利润总额:汽车制造业:累计值
    #   -> 中国:工业增加值:规模以上工业企业:汽车制造业:当月同比
    profit_to_iva_mapping = {}

    def normalize_industry_name(name: str) -> str:
        """标准化行业名称，用于模糊匹配"""
        # 移除常见的分隔符和助词
        normalized = name.replace('、', '').replace('，', '').replace('。', '')
        normalized = normalized.replace('及', '').replace('和', '').replace('的', '')
        normalized = normalized.replace(' ', '').replace('　', '')
        return normalized

    for profit_col in profit_yoy_df.columns:
        if '利润总额' in str(profit_col):
            # 提取行业名称
            parts = str(profit_col).split(':')
            if len(parts) >= 3:
                industry_name = parts[2]
                industry_name_normalized = normalize_industry_name(industry_name)

                # 在权重数据中查找匹配的指标名称
                # 先尝试精确匹配
                matched = False
                for _, row in df_weights.iterrows():
                    indicator_name = row['指标名称']
                    if pd.notna(indicator_name) and industry_name in str(indicator_name):
                        profit_to_iva_mapping[profit_col] = indicator_name
                        matched = True
                        break

                # 如果精确匹配失败，尝试模糊匹配
                if not matched:
                    for _, row in df_weights.iterrows():
                        indicator_name = row['指标名称']
                        if pd.notna(indicator_name):
                            indicator_normalized = normalize_industry_name(str(indicator_name))
                            if industry_name_normalized in indicator_normalized:
                                profit_to_iva_mapping[profit_col] = indicator_name
                                debug_log(
                                    f"模糊匹配: {industry_name} -> {indicator_name}",
                                    "DEBUG"
                                )
                                matched = True
                                break

                if not matched:
                    debug_log(f"警告：未找到匹配的权重数据 - {industry_name}", "WARNING")

    debug_log(f"列名映射完成，成功映射 {len(profit_to_iva_mapping)}/{len(profit_yoy_df.columns)} 个行业", "INFO")

    # 步骤4: 构建权重映射（基于工业增加值列名）
    iva_columns = list(profit_to_iva_mapping.values())
    weights_mapping = build_weights_mapping(df_weights, iva_columns)

    # 步骤5: 按上中下游分组
    _, stream_groups, _ = categorize_indicators(weights_mapping)

    debug_log(f"上中下游分组: {list(stream_groups.keys())}", "INFO")

    # 步骤6: 计算各分组和单个行业的拉动率
    # 这里需要使用利润数据本身来计算动态权重，而不是工业增加值权重

    # 先计算利润原始值（用于计算权重）
    profit_cumulative_df = df_industry_profit.copy()
    # 过滤1-2月
    profit_cumulative_df = profit_cumulative_df[~jan_feb_mask]

    # 计算各行业的拉动率
    # 公式: 拉动率 = (当期利润 - 去年同期利润) / 去年同期总利润 × 100
    individual_contribution_df = pd.DataFrame(index=profit_yoy_df.index)

    # 计算总利润（注意：这里使用过滤后的profit_cumulative_df）
    total_profit_by_month = profit_cumulative_df.sum(axis=1)

    # 为每个日期计算拉动率
    for current_date in profit_yoy_df.index:
        # 计算去年同期日期
        base_date = current_date - pd.DateOffset(months=12)

        # 检查去年同期数据是否存在
        if base_date not in profit_cumulative_df.index or base_date not in total_profit_by_month.index:
            # 如果去年同期数据不存在，跳过
            continue

        # 获取去年同期的总利润
        total_profit_base = total_profit_by_month.loc[base_date]

        # 计算每个行业的拉动率
        for profit_col in profit_yoy_df.columns:
            if profit_col not in profit_cumulative_df.columns:
                continue

            # 当期利润
            profit_current = profit_cumulative_df.loc[current_date, profit_col]

            # 去年同期利润
            profit_base = profit_cumulative_df.loc[base_date, profit_col]

            # 拉动率 = (当期利润 - 去年同期利润) / 去年同期总利润 × 100
            contribution = (profit_current - profit_base) / total_profit_base * 100

            individual_contribution_df.loc[current_date, profit_col] = contribution

    debug_log(f"单个行业拉动率计算完成，共 {len(individual_contribution_df.columns)} 个行业", "DEBUG")

    # 步骤7: 按上中下游分组汇总拉动率
    # 保留详细分类（中游机械、中游材料、上游采掘、上游公用、下游消费）
    stream_contribution_df = pd.DataFrame(index=profit_yoy_df.index)

    for stream_name, iva_indicators in stream_groups.items():
        # 将工业增加值列名映射回利润列名
        profit_cols_in_group = [
            profit_col for profit_col, iva_col in profit_to_iva_mapping.items()
            if iva_col in iva_indicators and profit_col in individual_contribution_df.columns
        ]

        if profit_cols_in_group:
            # 分组拉动率 = 组内各行业拉动率之和
            group_contribution = individual_contribution_df[profit_cols_in_group].sum(axis=1)
            column_name = f"上中下游_{stream_name}"
            stream_contribution_df[column_name] = group_contribution

            debug_log(
                f"分组 {stream_name} 拉动率计算完成，包含 {len(profit_cols_in_group)} 个行业",
                "DEBUG"
            )

    debug_log(
        f"上中下游分组拉动率计算完成: {list(stream_contribution_df.columns)}",
        "INFO"
    )

    # 步骤8: 验证拉动率总和
    validation_passed, contribution_sum, difference = validate_contributions(
        individual_contribution_df, total_growth
    )

    result = {
        'stream_groups': stream_contribution_df,
        'individual': individual_contribution_df,
        'total_growth': total_growth,
        'validation': {
            'passed': validation_passed,
            'contribution_sum': contribution_sum,
            'difference': difference
        }
    }

    debug_log(
        f"利润拉动率计算完成: "
        f"上中下游 {len(stream_contribution_df.columns)} 组, "
        f"单个行业 {len(individual_contribution_df.columns)} 个",
        "INFO"
    )

    return result
