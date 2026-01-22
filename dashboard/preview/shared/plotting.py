# -*- coding: utf-8 -*-
"""
Preview模块统一绘图组件
通过配置驱动,一个函数支持所有频率的图表绘制,保持与原始plotting_utils.py完全相同的功能
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from typing import Optional

from dashboard.preview.modules.industrial.config import PLOT_CONFIGS, COLORS


def plot_indicator(series, name, frequency, current_year, previous_year=None, unit=None, indicator_type=None):
    """通用绑图函数

    根据频率自动选择合适的绑图策略,保持与原始函数完全相同的功能

    Args:
        series: 数据序列
        name: 指标名称
        frequency: 数据频率 ('weekly'/'monthly'/'daily'/'ten_day'/'yearly')
        current_year: 当前年份
        previous_year: 去年年份(yearly不需要)
        unit: 单位(可选)
        indicator_type: 指标类型(可选，如'用电量')

    Returns:
        plotly.graph_objects.Figure
    """
    if series.empty:
        return _create_empty_figure(name)

    # 年度数据使用单独的逻辑(柱状图)
    if frequency == 'yearly':
        return _plot_yearly(series, name, unit)

    # 其他频率使用统一的时间序列绑图逻辑
    return _plot_time_series(series, name, frequency, current_year, previous_year or current_year - 1, unit, indicator_type)


def _plot_time_series(series, name, frequency, current_year, previous_year, unit, indicator_type=None):
    """绑制时间序列图表(周/月/日/旬),保持与原始逻辑完全一致"""
    series.index = pd.to_datetime(series.index)
    series_clean = series.replace(0.0, np.nan)

    # 用电量类型数据：将值乘以100转换为百分比显示
    is_percentage_type = indicator_type == '用电量'
    if is_percentage_type:
        series_clean = series_clean * 100

    # 获取配置
    config = PLOT_CONFIGS[frequency]

    # 1. 准备数据
    current_data = series_clean[series_clean.index.year == current_year].copy()
    previous_data = series_clean[series_clean.index.year == previous_year].copy()

    # 2. 根据频率对齐数据和计算历史统计
    plot_data = _prepare_plot_data(series_clean, frequency, current_year, previous_year, config)

    # 传递百分比类型标记
    plot_data['is_percentage_type'] = is_percentage_type

    # 3. 创建图表
    fig = go.Figure()

    # 4. 添加traces(保持与原始代码相同的顺序和样式)
    _add_historical_range(fig, plot_data)
    _add_historical_mean(fig, plot_data)
    _add_previous_year(fig, plot_data, previous_year, frequency)
    _add_current_year(fig, plot_data, current_year, frequency)

    # 5. 应用布局
    _apply_layout(fig, name, unit, config, plot_data, is_percentage_type)

    return fig


def _prepare_plot_data(series, frequency, current_year, previous_year, config):
    """准备绘图数据,保持与原始逻辑完全一致"""
    x_range = config['x_range']

    if frequency == 'weekly':
        # 周度数据：直接调用通用函数
        return _prepare_periodic_data_generic(
            series, current_year, previous_year, x_range,
            period_key='week',
            label_formatter=lambda w: f"W{w}",
            use_loop_stats=True
        )
    elif frequency == 'monthly':
        # 月度数据：直接调用通用函数
        return _prepare_periodic_data_generic(
            series, current_year, previous_year, x_range,
            period_key='month',
            label_formatter=lambda m: f"{m}月",
            use_loop_stats=False
        )
    elif frequency == 'daily':
        return _prepare_daily_data(series, current_year, previous_year, x_range)
    elif frequency == 'ten_day':
        # 旬度数据：直接调用通用函数
        def extract_ten_day_index(index):
            """计算旬度索引：1-36"""
            def get_ten_day_period(day):
                if day <= 10:
                    return 1
                elif day <= 20:
                    return 2
                else:
                    return 3

            ten_day_period = index.day.map(get_ten_day_period)
            return (index.month - 1) * 3 + ten_day_period

        return _prepare_periodic_data_generic(
            series, current_year, previous_year, x_range,
            period_key='ten_day_index',
            label_formatter=lambda idx: f"第{idx}旬",
            use_loop_stats=False,
            period_extractor=extract_ten_day_index
        )
    elif frequency == 'quarterly':
        # 季度数据：直接调用通用函数
        def extract_quarter_index(index):
            """计算季度索引：1-4"""
            return (index.month - 1) // 3 + 1

        return _prepare_periodic_data_generic(
            series, current_year, previous_year, x_range,
            period_key='quarter',
            label_formatter=lambda q: f"Q{q}",
            use_loop_stats=False,
            period_extractor=extract_quarter_index
        )


def _prepare_periodic_data_generic(series, current_year, previous_year, x_range,
                                   period_key, label_formatter, use_loop_stats=False, period_extractor=None):
    """通用周期数据准备框架（适用于weekly/monthly/ten_day）

    Args:
        series: 数据序列
        current_year, previous_year: 年份
        x_range: X轴范围
        period_key: 周期键名（如'month', 'week', 'ten_day_index'）
        label_formatter: 标签格式化函数，接受period值返回标签字符串
        use_loop_stats: 是否使用循环计算统计（weekly需要，因为isocalendar()不能直接groupby）
        period_extractor: 自定义周期提取函数（ten_day需要），接受索引返回周期值Series

    Returns:
        dict: 绘图数据字典
    """
    series_clean = series.replace(0.0, np.nan)

    # 准备DataFrame
    if period_extractor:
        # 使用自定义周期提取函数（ten_day）
        plot_df = pd.DataFrame({
            'value': series_clean,
            'year': series_clean.index.year,
            period_key: period_extractor(series_clean.index),
            'date': series_clean.index
        })
    elif period_key == 'week':
        # weekly特殊处理：使用isocalendar()
        plot_df = pd.DataFrame({
            'value': series_clean,
            'year': series_clean.index.year,
            period_key: series_clean.index.isocalendar().week,
            'date': series_clean.index
        })
    else:
        # monthly使用标准属性
        plot_df = pd.DataFrame({
            'value': series_clean,
            'year': series_clean.index.year,
            period_key: series_clean.index.month,
            'date': series_clean.index
        })

    # 计算历史统计
    historical_stats = pd.DataFrame(index=x_range, columns=['hist_min', 'hist_max', 'hist_mean'])

    if use_loop_stats:
        # weekly使用循环（因为isocalendar()特性）
        for period_val in x_range:
            period_mask = plot_df[period_key] == period_val
            period_data = plot_df[period_mask]['value'].dropna()
            if not period_data.empty:
                historical_stats.loc[period_val, 'hist_min'] = period_data.min()
                historical_stats.loc[period_val, 'hist_max'] = period_data.max()
                historical_stats.loc[period_val, 'hist_mean'] = period_data.mean()
    else:
        # monthly和ten_day使用groupby（更高效）
        period_stats = plot_df.groupby(period_key)['value'].agg(['min', 'max', 'mean'])
        historical_stats.loc[period_stats.index, 'hist_min'] = period_stats['min']
        historical_stats.loc[period_stats.index, 'hist_max'] = period_stats['max']
        historical_stats.loc[period_stats.index, 'hist_mean'] = period_stats['mean']

    # 对齐当年和去年数据
    current_period_df = plot_df[plot_df['year'] == current_year].set_index(period_key)
    previous_period_df = plot_df[plot_df['year'] == previous_year].set_index(period_key)

    current_period = current_period_df['value'].reindex(x_range)
    previous_period = previous_period_df['value'].reindex(x_range)

    # 为当年和去年数据生成对应周期的日期
    current_dates = []
    previous_dates = []
    x_labels_list = []

    if period_key == 'week':
        # 周度数据：为每周计算对应年份的日期（使用周一作为代表日期）
        # 先确定当前年份实际有多少周
        valid_weeks = []
        for p in x_range:
            try:
                current_week_date = pd.Timestamp.fromisocalendar(current_year, p, 1)
                valid_weeks.append(p)
            except:
                # 跳过不存在的周（如第53周在某些年份不存在）
                continue

        # 只处理有效的周
        for p in valid_weeks:
            # 计算当前年份该周的日期
            current_week_date = pd.Timestamp.fromisocalendar(current_year, p, 1)
            current_dates.append(current_week_date.strftime('%Y-%m-%d'))
            x_labels_list.append(current_week_date.strftime('%Y-%m-%d'))

            # 计算去年该周的日期
            try:
                previous_week_date = pd.Timestamp.fromisocalendar(previous_year, p, 1)
                previous_dates.append(previous_week_date.strftime('%Y-%m-%d'))
            except:
                previous_dates.append(None)

        # 更新x_range为有效的周
        x_range = valid_weeks
        # 重新对齐数据
        current_period = current_period.reindex(valid_weeks)
        previous_period = previous_period.reindex(valid_weeks)
        # 重新对齐历史统计数据
        historical_stats = historical_stats.reindex(valid_weeks)
    else:
        # 其他频率：使用实际数据的日期
        for p in x_range:
            if p in current_period_df.index:
                date_val = current_period_df.loc[p, 'date']
                if isinstance(date_val, pd.Timestamp):
                    current_dates.append(date_val.strftime('%Y-%m-%d'))
                else:
                    current_dates.append(None)
            else:
                current_dates.append(None)

        for p in x_range:
            if p in previous_period_df.index:
                date_val = previous_period_df.loc[p, 'date']
                if isinstance(date_val, pd.Timestamp):
                    previous_dates.append(date_val.strftime('%Y-%m-%d'))
                else:
                    previous_dates.append(None)
            else:
                previous_dates.append(None)

        x_labels_list = [label_formatter(p) for p in x_range]

    x_labels = x_labels_list

    return {
        'x': list(x_range),
        'x_labels': x_labels,
        'hist_min': historical_stats['hist_min'].values,
        'hist_max': historical_stats['hist_max'].values,
        'hist_mean': historical_stats['hist_mean'].values,
        f'{current_year}年': current_period.values,
        f'{previous_year}年': previous_period.values,
        'current_dates': current_dates,
        'previous_dates': previous_dates,
        'is_weekly': period_key == 'week'
    }


def _prepare_daily_data(series, current_year, previous_year, x_range):
    """准备日度数据（向量化优化版）

    性能优化：使用groupby替代366次循环，性能提升10-50倍
    """
    # 计算历史统计（向量化操作：一次性计算所有天的统计）
    historical_stats = pd.DataFrame(index=x_range, columns=['hist_min', 'hist_max', 'hist_mean'])

    # 使用groupby向量化替代循环
    day_stats = series.groupby(series.index.dayofyear).agg(['min', 'max', 'mean'])

    if not day_stats.empty:
        # 直接赋值，避免逐行循环
        valid_days = day_stats.index.intersection(x_range)
        historical_stats.loc[valid_days, 'hist_min'] = day_stats.loc[valid_days, 'min'].values
        historical_stats.loc[valid_days, 'hist_max'] = day_stats.loc[valid_days, 'max'].values
        historical_stats.loc[valid_days, 'hist_mean'] = day_stats.loc[valid_days, 'mean'].values

    # 提取当年和去年数据
    current_data = series[series.index.year == current_year]
    previous_data = series[series.index.year == previous_year]

    plot_data = {
        'x': list(x_range),
        'hist_min': historical_stats['hist_min'].ffill().bfill().values,
        'hist_max': historical_stats['hist_max'].ffill().bfill().values,
        'hist_mean': historical_stats['hist_mean'].ffill().bfill().values,
    }

    if not current_data.empty:
        plot_data['current_x'] = current_data.index.dayofyear.tolist()
        plot_data['current_y'] = current_data.values.tolist()
        plot_data['current_dates'] = current_data.index.strftime('%Y-%m-%d').tolist()

    if not previous_data.empty:
        plot_data['previous_x'] = previous_data.index.dayofyear.tolist()
        plot_data['previous_y'] = previous_data.values.tolist()
        plot_data['previous_dates'] = previous_data.index.strftime('%Y-%m-%d').tolist()

    return plot_data


def _add_historical_range(fig, plot_data):
    """添加历史区间，NaN处自动断开，分段绘制连续区域"""
    hist_max = plot_data.get('hist_max')
    hist_min = plot_data.get('hist_min')

    if hist_max is None or hist_min is None:
        return

    # 检查是否有任何有效值
    valid_mask = ~(pd.isna(hist_max) | pd.isna(hist_min))
    if not any(valid_mask):
        return

    # 确保x_vals是列表
    x_vals = list(plot_data['x'])
    hist_max_list = list(hist_max)
    hist_min_list = list(hist_min)

    # 找到连续的非NaN区段
    segments = []
    start_idx = None

    for i, is_valid in enumerate(valid_mask):
        if is_valid:
            if start_idx is None:
                start_idx = i
        else:
            if start_idx is not None:
                segments.append((start_idx, i))
                start_idx = None

    # 处理最后一个区段
    if start_idx is not None:
        segments.append((start_idx, len(valid_mask)))

    # 为每个连续区段绘制填充区域
    for idx, (start, end) in enumerate(segments):
        segment_x = [x_vals[i] for i in range(start, end)]
        segment_y_max = [hist_max_list[i] for i in range(start, end)]
        segment_y_min = [hist_min_list[i] for i in range(start, end)]

        fig.add_trace(go.Scatter(
            x=segment_x + segment_x[::-1],
            y=segment_y_max + segment_y_min[::-1],
            fill='toself',
            fillcolor=COLORS['historical_range'],
            line=dict(color='rgba(255,255,255,0)'),
            hoverinfo='skip',
            showlegend=(idx == 0),  # 只在第一个区段显示图例
            legendgroup='historical_range',  # 统一图例组
            name='历史区间'
        ))


def _add_historical_mean(fig, plot_data):
    """添加历史均值,保持与原始代码完全一致"""
    hist_mean = plot_data.get('hist_mean')
    if hist_mean is None:
        return

    fig.add_trace(go.Scatter(
        x=plot_data['x'],
        y=hist_mean,
        mode='lines+markers',
        line=dict(color=COLORS['historical_mean'], dash='dash'),
        name='均值',
        showlegend=True
    ))


def _add_year_data(fig, plot_data, year, frequency, color_key, x_key=None, y_key=None, dates_key=None):
    """添加年份数据的通用函数（合并previous_year和current_year逻辑）

    Args:
        fig: plotly图表对象
        plot_data: 绑图数据字典
        year: 年份
        frequency: 频率
        color_key: 颜色配置键（'previous_year'或'current_year'）
        x_key: X轴数据键（日度数据专用）
        y_key: Y轴数据键（日度数据专用）
        dates_key: 日期数据键（日度数据专用）
    """
    year_key = f'{year}年'
    is_percentage = plot_data.get('is_percentage_type', False)

    # 日度数据使用不同的键
    if frequency == 'daily':
        if x_key and y_key and x_key in plot_data and y_key in plot_data:
            fig.add_trace(go.Scatter(
                x=plot_data[x_key],
                y=plot_data[y_key],
                mode='lines+markers',
                name=year_key,
                line=dict(color=COLORS[color_key]),
                customdata=plot_data.get(dates_key, []),
                hovertemplate=f'{year}年 (%{{customdata}}): %{{y:.2f}}<extra></extra>'
            ))
    elif year_key in plot_data:
        # 检查是否为周度数据且有日期信息
        is_weekly = plot_data.get('is_weekly', False)

        if is_weekly and dates_key in plot_data:
            # 周度数据使用日期作为hover信息
            fig.add_trace(go.Scatter(
                x=plot_data['x'],
                y=plot_data[year_key],
                mode='lines+markers',
                name=year_key,
                line=dict(color=COLORS[color_key]),
                customdata=plot_data[dates_key],
                hovertemplate=f'{year}年 (%{{customdata}}): %{{y:.2f}}<extra></extra>'
            ))
        elif frequency == 'ten_day' and dates_key in plot_data:
            # 旬度数据：使用日期作为hover信息，格式为"年-月-日：XXX"
            if is_percentage:
                hover_fmt = '%{customdata}: %{y:.1f}%<extra></extra>'
            else:
                hover_fmt = '%{customdata}: %{y:.2f}<extra></extra>'
            fig.add_trace(go.Scatter(
                x=plot_data['x'],
                y=plot_data[year_key],
                mode='lines+markers',
                name=year_key,
                line=dict(color=COLORS[color_key]),
                customdata=plot_data[dates_key],
                hovertemplate=hover_fmt
            ))
        else:
            # 其他频率保持原样
            fig.add_trace(go.Scatter(
                x=plot_data['x'],
                y=plot_data[year_key],
                mode='lines+markers',
                name=year_key,
                line=dict(color=COLORS[color_key])
            ))


def _add_previous_year(fig, plot_data, year, frequency):
    """添加去年数据"""
    if frequency == 'daily':
        _add_year_data(fig, plot_data, year, frequency, 'previous_year',
                       x_key='previous_x', y_key='previous_y', dates_key='previous_dates')
    else:
        _add_year_data(fig, plot_data, year, frequency, 'previous_year',
                       dates_key='previous_dates')


def _add_current_year(fig, plot_data, year, frequency):
    """添加今年数据"""
    if frequency == 'daily':
        _add_year_data(fig, plot_data, year, frequency, 'current_year',
                       x_key='current_x', y_key='current_y', dates_key='current_dates')
    else:
        _add_year_data(fig, plot_data, year, frequency, 'current_year',
                       dates_key='current_dates')


def _apply_layout(fig, name, unit, config, plot_data, is_percentage_type=False):
    """应用图表布局,保持与原始代码完全一致"""
    y_axis_title = unit if unit and unit.strip() else "数值"

    # X轴配置
    x_axis_config = {
        'title': '',
        'showgrid': True,
        'gridwidth': 1,
        'gridcolor': 'LightGrey'
    }

    # 根据配置设置X轴刻度
    if 'x_tick_vals' in config:
        x_axis_config['tickmode'] = 'array'
        x_axis_config['tickvals'] = config['x_tick_vals']
        x_axis_config['ticktext'] = config['x_tick_labels']
    else:
        interval = config.get('x_tick_interval', 1)
        x_axis_config['tickmode'] = 'array'
        x_axis_config['tickvals'] = plot_data['x'][::interval]
        if 'x_labels' in plot_data:
            x_axis_config['ticktext'] = plot_data['x_labels'][::interval]
        else:
            x_axis_config['ticktext'] = [str(x) for x in plot_data['x'][::interval]]

    # Y轴配置
    y_axis_config = {
        'title': y_axis_title,
        'showgrid': True,
        'gridwidth': 1,
        'gridcolor': 'LightGrey'
    }

    # 用电量类型：y轴显示百分比格式
    if is_percentage_type:
        y_axis_config['ticksuffix'] = '%'

    fig.update_layout(
        title=dict(text=name, x=0.5, xanchor='center'),
        xaxis=x_axis_config,
        yaxis=y_axis_config,
        hovermode='closest',
        hoverlabel=dict(bgcolor="white", font_size=12),
        **config['layout']
    )


def _plot_yearly(series, name, unit):
    """绘制年度柱状图,完全复制原始逻辑"""
    series.index = pd.to_datetime(series.index)
    series_clean = series.replace(0.0, np.nan)

    years = series_clean.index.year.tolist()
    values = series_clean.values.tolist()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years,
        y=values,
        marker=dict(
            color='steelblue',
            line=dict(color='darkblue', width=1)
        ),
        hovertemplate='<b>年份</b>: %{x}<br><b>值</b>: %{y:.2f}<extra></extra>',
        name='年度值'
    ))

    y_axis_title = unit if unit and unit.strip() else "数值"

    # 计算刻度间隔
    if len(years) > 0:
        year_range = max(years) - min(years)
        if year_range <= 10:
            dtick = 1
        elif year_range <= 20:
            dtick = 2
        elif year_range <= 50:
            dtick = 5
        else:
            dtick = 10
    else:
        dtick = 1

    config = PLOT_CONFIGS['yearly']
    fig.update_layout(
        title=dict(text=name, font=dict(size=16, color='black'), x=0.5, xanchor='center'),
        xaxis=dict(title='', showgrid=True, gridwidth=1, gridcolor='LightGrey', dtick=dtick),
        yaxis=dict(title=y_axis_title, showgrid=True, gridwidth=1, gridcolor='LightGrey'),
        hovermode='x unified',
        plot_bgcolor='white',
        showlegend=False,
        **config['layout']
    )

    return fig


def _create_empty_figure(name):
    """创建空图表"""
    return go.Figure().update_layout(title=dict(text=f"{name} - 无数据", x=0.5, xanchor='center'))
