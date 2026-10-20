"""阿联酋监测页面的 Ts 时间序列与 Plotly 行业图表。"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from matplotlib.figure import Figure as MatplotlibFigure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)

COLORS = (
    "#0B5CAD",
    "#00A6A6",
    "#F28E2B",
    "#7B61A8",
    "#59A14F",
    "#E15759",
    "#76B7B2",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
    "#4E79A7",
    "#A0CBE8",
    "#8CD17D",
    "#499894",
    "#D37295",
    "#FABFD2",
)


_MACRO_HISTORY_POINTS = 60


def build_growth_and_sector_pull_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    source_text: str = "",
) -> MatplotlibFigure:
    """Ts 时间序列模板：左轴正负堆叠部门拉动，右轴石油产量同比。"""

    pull_columns = ("非石油经济部门拉动", "石油经济部门拉动")
    production_column = "石油及其他液体产量季度同比"
    plotted = [*pull_columns, production_column]
    missing = [column for column in plotted if column not in frame]
    if missing:
        raise ValueError(f"缺少部门拉动序列: {', '.join(missing)}")
    clean = frame[plotted].dropna(how="all").sort_index().tail(_MACRO_HISTORY_POINTS).copy()
    if clean.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    if isinstance(clean.index, pd.PeriodIndex):
        clean.index = clean.index.to_timestamp(how="end").normalize()
    else:
        clean.index = pd.to_datetime(clean.index)
    figure, returned_axis = plot_series(
        clean,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        year_ruler_span=3,
        quarterly_ticks=True,
        xlabel_count=12,
        grid=True,
        axis_groups={name: "left" if name in pull_columns else "right" for name in clean},
        units={name: "百分点" if name in pull_columns else "%" for name in clean},
        bar_series=list(pull_columns),
        bar_stacked=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_labels=plotted,
        legend_cols=2,
        note=source_note(source_text) if source_text else None,
        note_loc="left",
        ax=create_report_axis(),
    )
    annotate_war(normalize_ts_axis(returned_axis))
    apply_htfa_fonts(figure)
    return figure


def build_price_volume_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    source_text: str = "",
) -> MatplotlibFigure:
    """使用高频报告的 Ts 模板，分别保留实际增速与平减指数的末期。"""

    real_candidates = [
        column
        for column in frame.columns
        if "当季同比" in str(column) and "平减指数" not in str(column)
    ]
    if len(real_candidates) != 1:
        raise ValueError("无法唯一识别实际GDP同比序列")
    real_column = real_candidates[0]
    deflator_candidates = [
        column
        for column in frame.columns
        if "平减指数同比" in str(column)
    ]
    if len(deflator_candidates) != 1:
        raise ValueError("无法唯一识别GDP平减指数同比序列")
    deflator_column = deflator_candidates[0]

    required = (real_column, deflator_column)
    clean = frame[list(required)].dropna(how="all").tail(_MACRO_HISTORY_POINTS).copy()
    if clean.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    if isinstance(clean.index, pd.PeriodIndex):
        clean.index = clean.index.to_timestamp(how="end").normalize()
    else:
        clean.index = pd.to_datetime(clean.index)
    figure, returned_axis = plot_series(
        clean,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        year_ruler_span=3,
        quarterly_ticks=True,
        xlabel_count=12,
        grid=True,
        axis_groups={name: "left" for name in clean},
        units={name: "%" for name in clean},
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text) if source_text else None,
        note_loc="left",
        ax=create_report_axis(),
    )
    annotate_war(normalize_ts_axis(returned_axis))
    apply_htfa_fonts(figure)
    return figure


def build_industry_breadth_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    max_points: int = 80,
) -> go.Figure:
    """绘制不加权的行业增长广度与持续性。"""

    metrics = (
        "正增长行业比例",
        "连续四季度正增长的行业比例",
    )
    required = tuple(f"不加权｜{metric}" for metric in metrics)
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("行业扩张广度缺少字段: " + ", ".join(missing))
    clean = frame[list(required)].dropna(how="all").tail(max_points)
    if clean.empty:
        raise ValueError("行业扩张广度没有有效观测")
    quarter_labels = pd.PeriodIndex(clean.index, freq="Q").astype(str)
    metric_styles = {
        "正增长行业比例": {"color": COLORS[0], "dash": "solid"},
        "连续四季度正增长的行业比例": {
            "color": COLORS[4],
            "dash": "dash",
        },
    }

    figure = go.Figure()
    for metric in metrics:
        column = f"不加权｜{metric}"
        figure.add_trace(
            go.Scatter(
                x=quarter_labels,
                y=clean[column].values,
                name=metric,
                mode="lines+markers",
                line={"width": 2.4, **metric_styles[metric]},
                marker={"size": 5},
                hovertemplate=(
                    "%{x}<br>%{y:.1f}%<br>口径：不加权"
                    "<extra>%{fullData.name}</extra>"
                ),
            )
        )

    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=440,
        margin={"l": 60, "r": 90, "t": 75, "b": 55},
        template="plotly_white",
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "itemsizing": "constant",
        },
        shapes=[
            {
                "type": "line",
                "xref": "paper",
                "yref": "y",
                "x0": 0,
                "x1": 1,
                "y0": 50,
                "y1": 50,
                "line": {"color": "#9CA3AF", "width": 1, "dash": "dot"},
            },
            {
                "type": "line",
                "xref": "paper",
                "yref": "y",
                "x0": 0,
                "x1": 1,
                "y0": 80,
                "y1": 80,
                "line": {"color": "#6B7280", "width": 1, "dash": "dot"},
            },
        ],
        annotations=[
            {
                "text": "50% 正增长广度边界",
                "xref": "paper",
                "yref": "y",
                "x": 1.01,
                "y": 50,
                "xanchor": "left",
                "showarrow": False,
                "font": {"size": 10, "color": "#6B7280"},
            },
            {
                "text": "80% 正增长广度边界",
                "xref": "paper",
                "yref": "y",
                "x": 1.01,
                "y": 80,
                "xanchor": "left",
                "showarrow": False,
                "font": {"size": 10, "color": "#4B5563"},
            },
        ],
    )
    annual_ticks = [
        quarter for quarter in quarter_labels if quarter.endswith("Q4")
    ]
    if not annual_ticks:
        annual_ticks = quarter_labels.tolist()
    figure.update_xaxes(
        title_text="季度",
        type="category",
        categoryorder="array",
        categoryarray=quarter_labels.tolist(),
        tickmode="array",
        tickvals=annual_ticks,
        ticktext=annual_ticks,
        showgrid=False,
    )
    figure.update_yaxes(
        title_text="行业比例（%）",
        range=[0, 100],
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=False,
    )
    return figure


def _quarter_animation_controls(
    quarters: list[str], *, frame_duration_ms: int, transition_ms: int,
) -> dict[str, object]:
    """共享两张行业图的季度滑块、从头播放和暂停设置。"""
    instant = {
        "mode": "immediate", "frame": {"duration": 0, "redraw": True},
        "transition": {"duration": 0},
    }
    slider_steps = [
        {"label": quarter if quarter.endswith("Q4") else "", "method": "animate",
         "args": [[quarter], instant]}
        for quarter in quarters
    ]
    return {
        "sliders": [{
            "active": len(quarters) - 1, "steps": slider_steps,
            "x": 0.08, "len": 0.9, "y": -0.13,
            "pad": {"t": 25, "b": 0}, "currentvalue": {"visible": False},
            "tickcolor": "#9CA3AF", "font": {"size": 10},
        }],
        "updatemenus": [{
            "type": "buttons", "direction": "left", "showactive": False,
            "x": 0, "y": -0.19, "xanchor": "left", "yanchor": "top",
            "buttons": [
                {
                    "label": "▶ 从头播放", "method": "animate",
                    "args": [quarters, {
                        "mode": "immediate", "fromcurrent": False,
                        "frame": {"duration": frame_duration_ms, "redraw": True},
                        "transition": {"duration": transition_ms},
                    }],
                },
                {
                    "label": "⏸ 暂停", "method": "animate",
                    "args": [[None], {
                        "mode": "immediate", "frame": {"duration": 0, "redraw": False},
                        "transition": {"duration": 0},
                    }],
                },
            ],
        }],
    }


def build_industry_concentration_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    max_points: int = 80,
    frame_duration_ms: int = 700,
) -> go.Figure:
    """绘制带内置季度时间轴的行业方向—集中度气泡图。"""

    required = (
        "贡献平衡指数",
        "标准化绝对贡献集中度",
        "绝对贡献HHI",
        "总变动强度",
        "非油GDP同比",
        "最大正向贡献行业",
        "最大正向贡献",
        "最大负向贡献行业",
        "最大负向贡献",
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("行业增长集中度缺少字段: " + ", ".join(missing))
    clean = (
        frame[list(required)]
        .sort_index()
        .dropna(
            subset=[
                "贡献平衡指数",
                "标准化绝对贡献集中度",
                "总变动强度",
            ]
        )
        .tail(max_points)
        .copy()
    )
    if clean.empty:
        raise ValueError("行业增长集中度没有有效观测")
    quarter_labels = pd.PeriodIndex(clean.index, freq="Q").astype(str)
    if quarter_labels.duplicated().any():
        raise ValueError("行业增长集中度包含重复季度")
    clean["__quarter__"] = quarter_labels

    def _driver_text(row: pd.Series, direction: str) -> str:
        industry = row[f"最大{direction}贡献行业"]
        value = row[f"最大{direction}贡献"]
        if pd.isna(industry) or pd.isna(value):
            return "无"
        return f"{industry}（{float(value):+.2f} 个百分点）"

    clean["__positive_driver__"] = clean.apply(
        _driver_text,
        axis=1,
        direction="正向",
    )
    clean["__negative_driver__"] = clean.apply(
        _driver_text,
        axis=1,
        direction="负向",
    )
    max_intensity = float(clean["总变动强度"].max())
    if max_intensity <= 0:
        raise ValueError("行业增长集中度的总变动强度必须为正数")
    size_reference = 2 * max_intensity / 46**2
    observed_maximum = float(clean["标准化绝对贡献集中度"].max())
    y_upper = min(
        100.0,
        max(20.0, math.ceil(observed_maximum * 1.2 / 5.0) * 5.0),
    )

    custom_columns = [
        "__quarter__",
        "非油GDP同比",
        "绝对贡献HHI",
        "总变动强度",
        "__positive_driver__",
        "__negative_driver__",
    ]
    hovertemplate = (
        "季度：%{customdata[0]}<br>"
        "非油GDP同比：%{customdata[1]:+.2f}%<br>"
        "贡献平衡指数：%{x:.1f}<br>"
        "标准化集中度：%{y:.1f}%<br>"
        "绝对贡献 HHI：%{customdata[2]:.3f}<br>"
        "总变动强度：%{customdata[3]:.2f} 个百分点<br>"
        "最大正向贡献：%{customdata[4]}<br>"
        "最大负向贡献：%{customdata[5]}"
        "<extra>%{fullData.name}</extra>"
    )

    def _trace(
        subset: pd.DataFrame,
        *,
        name: str,
        color: str,
        symbol: str,
        current: bool = False,
    ) -> go.Scatter:
        return go.Scatter(
            x=subset["贡献平衡指数"],
            y=subset["标准化绝对贡献集中度"],
            name=name,
            mode="markers",
            cliponaxis=False,
            customdata=subset[custom_columns].to_numpy(),
            marker={
                "size": subset["总变动强度"],
                "sizemode": "area",
                "sizeref": size_reference,
                "sizemin": 8 if current else 7,
                "symbol": symbol,
                "color": color,
                "opacity": 0.96 if current else 0.42,
                "line": {
                    "color": "#111827" if current else color,
                    "width": 3 if current else 1.5,
                },
            },
            hovertemplate=hovertemplate,
        )

    def quarter_traces(position: int) -> list[go.Scatter]:
        history = clean.iloc[:position]
        current = clean.iloc[[position]]
        current_is_growth = bool(current["非油GDP同比"].iloc[0] >= 0)
        return [
            _trace(
                history.loc[history["非油GDP同比"].ge(0)],
                name="历史净增长期",
                color=COLORS[0],
                symbol="circle",
            ),
            _trace(
                history.loc[history["非油GDP同比"].lt(0)],
                name="历史净收缩期",
                color=COLORS[2],
                symbol="circle-open",
            ),
            _trace(
                current,
                name="当前季度",
                color=COLORS[0] if current_is_growth else COLORS[2],
                symbol="circle" if current_is_growth else "circle-open",
                current=True,
            ),
        ]

    def quarter_annotations(quarter: str) -> list[dict[str, object]]:
        return [
            {
                "text": f"<b>{quarter.replace('Q', ' Q')}</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.98,
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 18, "color": "white"},
                "bgcolor": "#0B5CAD",
                "bordercolor": "#0B5CAD",
                "borderpad": 6,
            },
            {
                "x": 0.01,
                "y": 0.98,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>拖累占主导</b>",
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "top",
                "font": {"color": "#6B7280", "size": 12},
            },
            {
                "x": 0.99,
                "y": 0.98,
                "xref": "paper",
                "yref": "paper",
                "text": "<b>拉动占主导</b>",
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "top",
                "font": {"color": "#6B7280", "size": 12},
            },
            {
                "x": 0.99,
                "y": 0.02,
                "xref": "paper",
                "yref": "paper",
                "text": f"纵轴显示 0–{y_upper:g}；理论范围 0–100",
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "bottom",
                "font": {"color": "#6B7280", "size": 11},
            },
        ]

    quarter_values = clean["__quarter__"].tolist()
    latest_position = len(quarter_values) - 1
    animation_frames = [
        go.Frame(
            name=quarter,
            data=quarter_traces(position),
            traces=[0, 1, 2],
            layout=go.Layout(annotations=quarter_annotations(quarter)),
        )
        for position, quarter in enumerate(quarter_values)
    ]
    figure = go.Figure(
        data=quarter_traces(latest_position),
        frames=animation_frames,
    )
    figure.update_layout(
        title={
            "text": (
                f"{title}<br><sup>横轴表示正负贡献平衡；纵轴表示全部行业"
                f"绝对贡献的集中程度（完整样本固定显示 0–{y_upper:g}，"
                "理论范围 0–100）；气泡面积表示总变动强度</sup>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        height=650,
        margin={"l": 75, "r": 45, "t": 110, "b": 130},
        template="plotly_white",
        hovermode="closest",
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.02,
            "xanchor": "left",
            "yanchor": "bottom",
        },
        shapes=[
            {
                "type": "line",
                "x0": 0,
                "x1": 0,
                "y0": 0,
                "y1": 1,
                "xref": "x",
                "yref": "paper",
                "line": {"color": "#555", "width": 1.4, "dash": "dash"},
            }
        ],
        annotations=quarter_annotations(quarter_values[-1]),
        **_quarter_animation_controls(
            quarter_values, frame_duration_ms=frame_duration_ms, transition_ms=180,
        ),
    )
    figure.update_xaxes(
        title_text="贡献平衡指数（%）",
        range=[-100, 100],
        tickvals=[-100, -50, 0, 50, 100],
        ticktext=["-100<br>全部拖累", "-50", "0<br>完全抵消", "50", "100<br>全部拉动"],
        gridcolor="rgba(0,0,0,0.08)",
    )
    figure.update_yaxes(
        title_text="标准化绝对贡献集中度（%）",
        range=[0, y_upper],
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=False,
    )
    return figure


def build_industry_state_matrix_figure(
    frame: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    """绘制最新完整季度的行业增长持续性状态矩阵。"""

    clean = frame.reset_index()
    required = (
        "季度",
        "行业",
        "当前实际增加值增速",
        "最近4季度平均增速",
        "最近8季度平均增速",
        "连续正增长季度数",
        "最近8季度高于自身历史趋势次数",
        "当季增速减过去4季度均值",
        "当季增速减历史趋势",
        "当季增速减上季度增速",
        "实际GDP占非油GDP比例",
        "行业状态",
    )
    missing = [column for column in required if column not in clean.columns]
    if missing:
        raise ValueError(
            "行业增长持续性与状态矩阵缺少字段: " + ", ".join(missing)
        )
    clean = clean[list(required)]
    if clean.duplicated(["季度", "行业"]).any():
        raise ValueError("行业状态矩阵包含重复的季度—行业观测")
    expected_industries = clean["行业"].astype(str).nunique()
    complete = clean.dropna(subset=list(required[2:]))
    complete_counts = complete.groupby("季度", sort=False)["行业"].nunique()
    complete_quarters = complete_counts.loc[
        complete_counts.eq(expected_industries)
    ].index
    if complete_quarters.empty:
        raise ValueError("行业状态矩阵没有完整季度")
    latest_quarter = str(
        pd.PeriodIndex(complete_quarters.astype(str), freq="Q").max()
    )
    snapshot = complete.loc[
        complete["季度"].astype(str).eq(latest_quarter)
    ].copy()
    if (snapshot["实际GDP占非油GDP比例"] <= 0).any():
        raise ValueError("行业状态矩阵的实际GDP占比必须为正数")
    share_sum = float(snapshot["实际GDP占非油GDP比例"].sum())
    if abs(share_sum - 1) > 1e-8:
        raise ValueError(
            "行业状态矩阵的行业实际GDP占比未加总为1："
            f"误差为{abs(share_sum - 1):.12g}"
        )

    states = ("高位加速", "高位放缓", "低位改善", "低位恶化")
    unknown_states = sorted(set(snapshot["行业状态"]) - set(states))
    if unknown_states:
        raise ValueError("行业状态矩阵存在未知状态: " + ", ".join(unknown_states))
    state_colors = {
        "高位加速": "#2E8B57",
        "高位放缓": "#F28E2B",
        "低位改善": "#0B5CAD",
        "低位恶化": "#E15759",
    }

    def fixed_range(series: pd.Series) -> list[float]:
        minimum = min(float(series.min()), 0.0)
        maximum = max(float(series.max()), 0.0)
        span = max(maximum - minimum, 1.0)
        padding = span * 0.12
        return [minimum - padding, maximum + padding]

    x_range = fixed_range(snapshot["当季增速减历史趋势"])
    y_range = fixed_range(snapshot["当季增速减上季度增速"])
    maximum_share = float(snapshot["实际GDP占非油GDP比例"].max())
    size_reference = 2 * maximum_share / 54**2

    figure = go.Figure()
    for state in states:
        subset = snapshot.loc[snapshot["行业状态"].eq(state)]
        if subset.empty:
            continue
        customdata = subset[
            [
                "当前实际增加值增速",
                "最近4季度平均增速",
                "最近8季度平均增速",
                "连续正增长季度数",
                "最近8季度高于自身历史趋势次数",
                "当季增速减过去4季度均值",
                "实际GDP占非油GDP比例",
            ]
        ].to_numpy()
        figure.add_trace(
            go.Scatter(
                x=subset["当季增速减历史趋势"],
                y=subset["当季增速减上季度增速"],
                name=state,
                legendgroup=state,
                mode="markers+text",
                text=subset["行业"],
                textposition="top center",
                marker={
                    "size": subset["实际GDP占非油GDP比例"],
                    "sizemode": "area",
                    "sizeref": size_reference,
                    "sizemin": 8,
                    "color": state_colors[state],
                    "opacity": 0.82,
                    "line": {"color": "white", "width": 1.2},
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    f"状态：{state}<br>"
                    "当前实际增加值增速：%{customdata[0]:.2f}%<br>"
                    "最近4季度平均增速：%{customdata[1]:.2f}%<br>"
                    "最近8季度平均增速：%{customdata[2]:.2f}%<br>"
                    "连续正增长季度数：%{customdata[3]:.0f}<br>"
                    "最近8季度高于自身历史趋势次数：%{customdata[4]:.0f}<br>"
                    "当季增速减过去4季度均值：%{customdata[5]:.2f} 个百分点<br>"
                    "实际GDP占非油GDP比例：%{customdata[6]:.1%}<br>"
                    "相对自身历史趋势：%{x:.2f} 个百分点<br>"
                    "较上季度增速变化：%{y:.2f} 个百分点"
                    "<extra></extra>"
                ),
            )
        )

    annotations = [
        {
            "text": f"<b>{latest_quarter.replace('Q', ' Q')}</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 1.15,
            "showarrow": False,
            "font": {"size": 20, "color": "white"},
            "bgcolor": "#0B5CAD",
            "bordercolor": "#0B5CAD",
            "borderpad": 7,
        },
        {
            "text": "<b>高位加速</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.98,
            "y": 0.97,
            "xanchor": "right",
            "yanchor": "top",
            "showarrow": False,
            "font": {"color": state_colors["高位加速"]},
        },
        {
            "text": "<b>高位放缓</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.98,
            "y": 0.03,
            "xanchor": "right",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"color": state_colors["高位放缓"]},
        },
        {
            "text": "<b>低位改善</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.02,
            "y": 0.97,
            "xanchor": "left",
            "yanchor": "top",
            "showarrow": False,
            "font": {"color": state_colors["低位改善"]},
        },
        {
            "text": "<b>低位恶化</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.02,
            "y": 0.03,
            "xanchor": "left",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"color": state_colors["低位恶化"]},
        },
    ]
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=620,
        margin={"l": 75, "r": 40, "t": 110, "b": 70},
        template="plotly_white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "itemsizing": "constant",
        },
        xaxis={
            "title": "相对自身历史趋势（百分点）",
            "range": x_range,
            "zeroline": False,
            "gridcolor": "rgba(0,0,0,0.08)",
        },
        yaxis={
            "title": "较上季度增速变化（百分点）",
            "range": y_range,
            "zeroline": False,
            "gridcolor": "rgba(0,0,0,0.08)",
        },
        shapes=[
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": 0,
                "x1": 0,
                "y0": 0,
                "y1": 1,
                "line": {"color": "#6B7280", "width": 1, "dash": "dash"},
            },
            {
                "type": "line",
                "xref": "paper",
                "yref": "y",
                "x0": 0,
                "x1": 1,
                "y0": 0,
                "y1": 0,
                "line": {"color": "#6B7280", "width": 1, "dash": "dash"},
            },
        ],
        annotations=annotations,
    )
    return figure


def build_industry_price_volume_quadrant_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    frame_duration_ms: int = 850,
) -> go.Figure:
    """绘制可按季度切换和播放的行业量价四象限气泡图。"""

    clean = frame.reset_index()
    required_columns = (
        "季度",
        "行业",
        "实际增加值增速",
        "行业隐含平减指数增速",
        "实际GDP占非油GDP比例",
    )
    missing_columns = [
        column for column in required_columns if column not in clean.columns
    ]
    if missing_columns:
        raise ValueError(
            "行业量价四象限缺少字段: " + ", ".join(missing_columns)
        )
    gdp_column = "非油实际GDP（十亿迪拉姆）"
    optional_columns = [gdp_column] if gdp_column in clean.columns else []
    clean = clean[[*required_columns, *optional_columns]].dropna()
    if clean.empty:
        raise ValueError("行业量价四象限没有有效观测")
    if clean.duplicated(["季度", "行业"]).any():
        raise ValueError("行业量价四象限包含重复的季度—行业观测")
    if (clean["实际GDP占非油GDP比例"] <= 0).any():
        raise ValueError("行业实际GDP占比必须为正数")

    quarter_labels = clean["季度"].astype(str).drop_duplicates().tolist()
    industry_labels = clean["行业"].astype(str).drop_duplicates().tolist()
    expected_industries = set(industry_labels)
    for quarter, snapshot in clean.groupby("季度", sort=False):
        if set(snapshot["行业"].astype(str)) != expected_industries:
            raise ValueError(f"{quarter}的行业集合不完整")
    share_sums = clean.groupby("季度", sort=False)[
        "实际GDP占非油GDP比例"
    ].sum()
    share_errors = share_sums.sub(1).abs()
    tolerances = pd.Series(1e-8, index=share_sums.index)
    if optional_columns:
        levels = clean.groupby("季度", sort=False)[gdp_column]
        if (not clean[gdp_column].map(math.isfinite).all()
                or (clean[gdp_column] <= 0).any()
                or (levels.nunique() != 1).any()):
            raise ValueError("四象限图的非油实际GDP口径异常")
        # Half a million AED per published term, including the total. Keep
        # original weights; allow only the corresponding monetary residual.
        tolerances = ((len(expected_industries) + 1) * 0.0005 / levels.first()).clip(lower=1e-8)
    max_share_error = float(share_errors.max())
    if (share_errors > tolerances).any():
        raise ValueError(
            "行业实际GDP占非油实际GDP比例未加总为1："
            f"最大误差为{max_share_error:.12g}"
        )

    def fixed_range(series: pd.Series) -> list[float]:
        minimum = min(float(series.min()), 0.0)
        maximum = max(float(series.max()), 0.0)
        span = max(maximum - minimum, 1.0)
        padding = span * 0.08
        return [minimum - padding, maximum + padding]

    x_range = fixed_range(clean["实际增加值增速"])
    y_range = fixed_range(clean["行业隐含平减指数增速"])
    maximum_share = float(clean["实际GDP占非油GDP比例"].max())
    desired_maximum_diameter = 58
    size_reference = (
        2 * maximum_share / desired_maximum_diameter**2
    )
    color_map = {
        industry: COLORS[position % len(COLORS)]
        for position, industry in enumerate(industry_labels)
    }

    def quarter_annotations(quarter: str) -> list[dict[str, object]]:
        share_total = float(share_sums.loc[quarter])
        return [
            {
                "text": f"<b>{quarter.replace('Q', ' Q')}</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 1.16,
                "showarrow": False,
                "font": {"size": 20, "color": "white"},
                "bgcolor": "#0B5CAD",
                "bordercolor": "#0B5CAD",
                "borderpad": 7,
            },
            {
                "text": f"行业占比合计：{share_total:.1%}",
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 1.08,
                "xanchor": "right",
                "showarrow": False,
                "font": {"size": 12, "color": "#374151"},
            },
            {
                "text": "<b>量减价升</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.02,
                "y": 0.97,
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 12, "color": "#6B7280"},
            },
            {
                "text": "<b>量价齐升</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.98,
                "y": 0.97,
                "xanchor": "right",
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 12, "color": "#6B7280"},
            },
            {
                "text": "<b>量价齐降</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.02,
                "y": 0.03,
                "xanchor": "left",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12, "color": "#6B7280"},
            },
            {
                "text": "<b>量增价降</b>",
                "xref": "paper",
                "yref": "paper",
                "x": 0.98,
                "y": 0.03,
                "xanchor": "right",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 12, "color": "#6B7280"},
            },
        ]

    def quarter_traces(quarter: str) -> list[go.Scatter]:
        snapshot = clean.loc[
            clean["季度"].astype(str).eq(quarter)
        ].set_index("行业")
        traces: list[go.Scatter] = []
        for industry in industry_labels:
            row = snapshot.loc[industry]
            share = float(row["实际GDP占非油GDP比例"])
            traces.append(
                go.Scatter(
                    x=[float(row["实际增加值增速"])],
                    y=[float(row["行业隐含平减指数增速"])],
                    name=industry,
                    legendgroup=industry,
                    mode="markers",
                    marker={
                        "size": [share],
                        "sizemode": "area",
                        "sizeref": size_reference,
                        "sizemin": 7,
                        "color": color_map[industry],
                        "opacity": 0.82,
                        "line": {"color": "white", "width": 1.2},
                    },
                    customdata=[[quarter, share * 100]],
                    hovertemplate=(
                        "<b>%{fullData.name}</b><br>"
                        "季度：%{customdata[0]}<br>"
                        "实际增加值增速：%{x:.2f}%<br>"
                        "隐含平减指数增速：%{y:.2f}%<br>"
                        "非油实际GDP占比：%{customdata[1]:.2f}%"
                        "<extra></extra>"
                    ),
                )
            )
        return traces

    latest_quarter = quarter_labels[-1]
    animation_frames = [
        go.Frame(
            name=quarter,
            data=quarter_traces(quarter),
            traces=list(range(len(industry_labels))),
            layout=go.Layout(annotations=quarter_annotations(quarter)),
        )
        for quarter in quarter_labels
    ]
    figure = go.Figure(
        data=quarter_traces(latest_quarter),
        frames=animation_frames,
    )
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=700,
        margin={"l": 70, "r": 230, "t": 105, "b": 130},
        template="plotly_white",
        hovermode="closest",
        annotations=quarter_annotations(latest_quarter),
        shapes=[
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": 0,
                "x1": 0,
                "y0": 0,
                "y1": 1,
                "line": {"color": "#4B5563", "width": 1.4},
            },
            {
                "type": "line",
                "xref": "paper",
                "yref": "y",
                "x0": 0,
                "x1": 1,
                "y0": 0,
                "y1": 0,
                "line": {"color": "#4B5563", "width": 1.4},
            },
        ],
        legend={
            "title": {"text": "行业"},
            "orientation": "v",
            "itemsizing": "constant",
            "yanchor": "top",
            "y": 1,
            "xanchor": "left",
            "x": 1.02,
            "font": {"size": 11},
            "tracegroupgap": 2,
        },
        **_quarter_animation_controls(
            quarter_labels, frame_duration_ms=frame_duration_ms, transition_ms=220,
        ),
    )
    figure.update_xaxes(
        title_text="实际增加值同比增速（%）",
        range=x_range,
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=False,
    )
    figure.update_yaxes(
        title_text="行业隐含平减指数同比增速（%）",
        range=y_range,
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=False,
    )
    return figure


def build_nonoil_industry_pull_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    source_text: str = "",
) -> MatplotlibFigure:
    """用 Ts 模板展示非油实际 GDP 行业拉动堆叠柱。"""
    if "其他行业" not in frame:
        raise ValueError("缺少其他行业拉动序列")
    pull_columns = [column for column in frame if column != "非油GDP同比"]
    if len(pull_columns) < 2:
        raise ValueError("至少需要一个非油行业拉动序列")
    clean = frame[pull_columns].dropna(how="all").sort_index().tail(_MACRO_HISTORY_POINTS).copy()
    if clean.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    if isinstance(clean.index, pd.PeriodIndex):
        clean.index = clean.index.to_timestamp(how="end").normalize()
    else:
        clean.index = pd.to_datetime(clean.index)
    figure, axis = plot_series(
        clean,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        year_ruler_span=3,
        quarterly_ticks=True,
        xlabel_count=12,
        grid=True,
        axis_groups={name: "left" for name in clean},
        units={name: "百分点" for name in clean},
        bar_series=pull_columns,
        bar_stacked=True,
        colors=[COLORS[i % len(COLORS)] if name != "其他行业" else "#B8BDC6"
                for i, name in enumerate(clean)],
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_cols=2,
        note=source_note(source_text) if source_text else None,
        note_loc="left",
        ax=create_report_axis(),
    )
    annotate_war(normalize_ts_axis(axis))
    apply_htfa_fonts(figure)
    return figure
