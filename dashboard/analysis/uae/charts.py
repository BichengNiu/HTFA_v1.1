"""阿联酋监测页面的纯 Plotly 图表构造函数。"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


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
)


def _plot_index(index: pd.Index):
    if isinstance(index, pd.PeriodIndex):
        return index.astype(str)
    return index


def build_line_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    y_title: str = "",
    max_points: int = 160,
) -> go.Figure:
    """构建多序列趋势图，不改变原数据。"""

    clean = frame.dropna(how="all").tail(max_points)
    figure = go.Figure()
    for position, column in enumerate(clean.columns):
        series = clean[column].dropna()
        if series.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=_plot_index(series.index),
                y=series.values,
                name=str(column),
                mode="lines",
                line={
                    "width": 2.2,
                    "color": COLORS[position % len(COLORS)],
                },
                hovertemplate="%{x}<br>%{y:,.2f}<extra>%{fullData.name}</extra>",
            )
        )
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        height=390,
        margin={"l": 50, "r": 20, "t": 55, "b": 45},
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis_title="时期",
        yaxis_title=y_title,
        template="plotly_white",
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(0,0,0,0.08)", zeroline=True)
    return figure


def build_latest_contribution_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    unit: str = "百分点",
    max_categories: int = 14,
) -> go.Figure:
    """构建最新一期分项贡献横向条形图。"""

    clean = frame.dropna(how="all")
    if clean.empty:
        return go.Figure()
    latest = clean.iloc[-1].dropna()
    if len(latest) > max_categories:
        largest = latest.abs().nlargest(max_categories).index
        latest = latest.loc[largest]
    latest = latest.sort_values()
    colors = ["#E15759" if value < 0 else "#0B5CAD" for value in latest]
    period = clean.index[-1]
    period_label = str(period)
    figure = go.Figure(
        go.Bar(
            x=latest.values,
            y=latest.index.astype(str),
            orientation="h",
            marker_color=colors,
            text=[f"{value:.2f}" for value in latest],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,.2f} " + unit + "<extra></extra>",
        )
    )
    figure.update_layout(
        title={
            "text": f"{title}（{period_label}）",
            "x": 0.01,
            "xanchor": "left",
        },
        height=max(340, 32 * len(latest) + 110),
        margin={"l": 130, "r": 55, "t": 55, "b": 45},
        xaxis_title=unit,
        yaxis_title="",
        template="plotly_white",
        showlegend=False,
    )
    figure.update_xaxes(
        gridcolor="rgba(0,0,0,0.08)",
        zeroline=True,
        zerolinecolor="#555",
    )
    return figure

