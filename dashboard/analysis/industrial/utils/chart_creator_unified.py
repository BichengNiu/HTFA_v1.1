"""
统一的图表创建工具
Unified Chart Creator Utility

目标：消除create_single_axis_chart和create_overall_industrial_chart的重复代码（约180行）
遵循KISS原则：一个通用函数，通过参数控制不同需求
"""

import pandas as pd
import plotly.graph_objects as go
from typing import List, Optional, Dict
import logging

from dashboard.analysis.industrial.utils.time_filter import filter_data_by_time_range
from dashboard.analysis.industrial.utils.chart_config import (
    get_chart_color,
    create_xaxis_config,
    create_yaxis_config,
    create_standard_layout,
    calculate_dtick_by_time_span,
    DTICK_3_MONTHS
)

logger = logging.getLogger(__name__)


def clean_variable_name(var: str) -> str:
    """
    清理变量名用于图例显示

    Args:
        var: 原始变量名

    Returns:
        清理后的显示名称
    """
    display_name = var

    # 处理出口依赖前缀
    if var.startswith('出口依赖_'):
        display_name = var.replace('出口依赖_', '') + '行业'
    # 处理上中下游前缀
    elif var.startswith('上中下游_'):
        display_name = var.replace('上中下游_', '')

    return display_name


def get_date_range_from_data(
    df: pd.DataFrame,
    variables: List[str]
) -> tuple:
    """
    从数据中提取实际的日期范围

    Args:
        df: 数据DataFrame
        variables: 变量列表

    Returns:
        (min_date, max_date) 元组
    """
    all_dates = []

    for var in variables:
        if var in df.columns:
            series = pd.to_numeric(df[var], errors='coerce').dropna()
            if not series.empty:
                try:
                    if isinstance(series.index, pd.DatetimeIndex):
                        all_dates.extend(series.index.tolist())
                    else:
                        try:
                            date_index = pd.to_datetime(series.index)
                            all_dates.extend(date_index.tolist())
                        except (ValueError, TypeError):
                            continue
                except Exception as e:
                    logger.warning(f"处理变量 {var} 的日期时出错: {e}")
                    continue

    if all_dates:
        return min(all_dates), max(all_dates)
    else:
        return None, None


def create_time_series_chart(
    df: pd.DataFrame,
    variables: List[str],
    title: str = "",
    time_range: str = "全部",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None,
    var_name_mapping: Optional[Dict[str, str]] = None,
    y_axis_title: str = "",
    height: int = 500,
    bottom_margin: int = 180,
) -> go.Figure:
    """
    创建统一的时间序列图表

    Args:
        df: 数据DataFrame，索引为时间
        variables: 要绘制的变量列表
    Returns:
        Plotly Figure对象
    """
    # 检查输入
    if df.empty or not variables:
        logger.warning("数据为空或变量列表为空")
        return go.Figure()

    # 应用时间过滤
    filtered_df = filter_data_by_time_range(
        df, time_range, custom_start_date, custom_end_date
    )

    if filtered_df.empty:
        logger.warning("时间过滤后数据为空")
        return go.Figure()

    # 创建图表
    fig = go.Figure()

    # 添加每个变量的trace
    for i, var in enumerate(variables):
        if var not in filtered_df.columns:
            logger.debug(f"变量 {var} 不在数据列中，跳过")
            continue

        # 清理数据
        series = pd.to_numeric(filtered_df[var], errors='coerce').dropna()

        if series.empty:
            logger.debug(f"变量 {var} 清理后为空，跳过")
            continue

        # 确定显示名称
        if var_name_mapping and var in var_name_mapping:
            display_name = var_name_mapping[var]
        else:
            display_name = clean_variable_name(var)

        # 获取颜色
        color = get_chart_color(i)

        # 创建并添加trace
        try:
            trace = go.Scatter(
                x=series.index,
                y=series.values.tolist(),
                showlegend=True,
                line=dict(color=color, width=2.5),
                connectgaps=True,
                mode='lines+markers',
                marker=dict(size=6),
                name=display_name,
                hovertemplate='%{fullData.name}: %{y:.2f}<extra></extra>'
            )
            fig.add_trace(trace)
        except Exception as e:
            logger.error(f"创建变量 {var} 的trace时出错: {e}")
            continue

    # 获取实际数据的日期范围
    min_date, max_date = get_date_range_from_data(filtered_df, variables)

    # 计算合适的时间刻度间隔
    dtick = calculate_dtick_by_time_span(min_date, max_date, default=DTICK_3_MONTHS)

    # 配置X轴
    xaxis_config = create_xaxis_config(
        dtick=dtick,
        tickformat="%Y-%m",
        min_date=min_date,
        max_date=max_date
    )

    # 配置Y轴
    yaxis_config = create_yaxis_config(title=y_axis_title)

    # 创建布局
    layout_config = create_standard_layout(
        title=title,
        height=height,
        margin={'l': 50, 'r': 50, 't': 40, 'b': bottom_margin}
    )

    # 应用配置（hovermode已在layout_config中设置）
    fig.update_layout(
        **layout_config,
        xaxis=xaxis_config,
        yaxis=yaxis_config
    )

    return fig
