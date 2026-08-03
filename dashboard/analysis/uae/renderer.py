"""阿联酋经济监测的 Streamlit 页面。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from dashboard.analysis.uae.charts import (
    build_growth_and_sector_pull_figure,
    build_industry_breadth_figure,
    build_industry_concentration_figure,
    build_industry_price_volume_quadrant_figure,
    build_industry_state_matrix_figure,
    build_latest_contribution_figure,
    build_line_figure,
    build_nonoil_industry_pull_figure,
    build_price_volume_figure,
)
from dashboard.analysis.uae.contracts import ProvenanceKind
from dashboard.analysis.uae.results import MacroPanelResult
from dashboard.analysis.uae.services import build_monitoring_dashboard
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file

TAB_CONFIG = (
    ("宏观概览", "growth_overview"),
    ("行业分析", "growth_industry"),
    ("通货膨胀", "inflation"),
    ("就业与收入", "labor"),
    ("财政与外部", "fiscal_external"),
    ("货币与金融", "monetary"),
)

GROWTH_OVERVIEW_GROUPS = (
    "实际GDP增速与GDP平减指数同比",
    "非石油实际GDP增速与非石油GDP平减指数同比",
    "非金融公司实际增加值增速与平减指数同比",
)
GROWTH_INDUSTRY_GROUPS = (
    "GDP部门拉动与石油产量同比",
    "非油实际GDP同比及行业拉动",
    "行业量价四象限图",
    "行业扩张广度指数",
    "行业增长集中度",
    "行业增长持续性与状态矩阵",
)


def _select_data_source() -> Any:
    """仅返回当前会话已经上传的共享工作簿。"""

    return get_shared_dataset_file()


def _source_name(file_input: Any) -> str:
    if hasattr(file_input, "name"):
        return str(file_input.name)
    return Path(file_input).name


def _metric_label(metric) -> str:
    prefix = (
        "【模拟】"
        if metric.provenance_kind is ProvenanceKind.SIMULATED
        else "【真实】"
    )
    return f"{prefix}{metric.label}"


def _render_metrics(st_obj, panel: MacroPanelResult) -> None:
    if not panel.metrics:
        return
    columns = st_obj.columns(len(panel.metrics))
    for column, metric in zip(columns, panel.metrics):
        with column:
            st_obj.metric(
                _metric_label(metric),
                f"{metric.value:,.2f}{metric.unit}",
                help=(
                    f"观测期：{metric.period}"
                    + (f"；{metric.help_text}" if metric.help_text else "")
                ),
            )


def _render_panel(
    st_obj,
    panel: MacroPanelResult,
    *,
    show_title: bool = True,
    series_group_titles: tuple[str, ...] | None = None,
) -> None:
    if show_title:
        st_obj.subheader(panel.title)
    _render_metrics(st_obj, panel)

    for group_title, frame in panel.series_groups.items():
        if (
            series_group_titles is not None
            and group_title not in series_group_titles
        ):
            continue
        if group_title in GROWTH_OVERVIEW_GROUPS:
            figure = build_price_volume_figure(
                frame,
                title=group_title,
            )
        elif group_title == "行业量价四象限图":
            figure = build_industry_price_volume_quadrant_figure(
                frame,
                title=group_title,
            )
        elif group_title == "行业扩张广度指数":
            figure = build_industry_breadth_figure(
                frame,
                title=group_title,
            )
        elif group_title == "行业增长集中度":
            figure = build_industry_concentration_figure(
                frame,
                title=group_title,
            )
        elif group_title == "行业增长持续性与状态矩阵":
            figure = build_industry_state_matrix_figure(
                frame,
                title=group_title,
            )
        elif group_title == "非油实际GDP同比及行业拉动":
            figure = build_nonoil_industry_pull_figure(
                frame,
                title=group_title,
            )
        elif {
            "【真实】非石油经济部门拉动",
            "【真实】石油经济部门拉动",
        }.issubset(frame.columns):
            figure = build_growth_and_sector_pull_figure(
                frame,
                title=group_title,
            )
        else:
            figure = build_line_figure(
                frame,
                title=group_title,
            )
        st_obj.plotly_chart(
            figure,
            use_container_width=True,
            key=f"analysis.uae.{panel.key}.series.{group_title}",
        )

    for table_title, frame in panel.decomposition_tables.items():
        st_obj.plotly_chart(
            build_latest_contribution_figure(
                frame,
                title=table_title,
            ),
            use_container_width=True,
            key=f"analysis.uae.{panel.key}.decomposition.{table_title}",
        )

    with st_obj.expander("证据、来源与方法限制", expanded=False):
        st_obj.markdown("**数据与解释限制**")
        st_obj.write(panel.headline.limitation)
        st_obj.markdown("**证据类型**")
        for item in panel.headline.evidence:
            source_tag = (
                "模拟"
                if item.provenance_kind is ProvenanceKind.SIMULATED
                else "真实"
            )
            st_obj.markdown(
                f"- `{item.evidence_class.value}` `{source_tag}` "
                f"{item.label}：{item.value}{item.unit}（{item.as_of}）"
            )
        st_obj.markdown("**方法说明**")
        for note in panel.methodology_notes:
            st_obj.markdown(f"- {note}")
        st_obj.markdown("**指标来源**")
        for provenance in panel.provenance.values():
            st_obj.markdown(
                f"- `{provenance.kind.value}` {provenance.display_name}｜"
                f"{provenance.source}｜{provenance.coverage}｜"
                f"截至 {provenance.as_of}"
            )


def render_uae_monitoring(st_obj=st) -> dict[str, Any]:
    """渲染阿联酋监测；不写入或生成任何工作簿。"""

    st_obj.title("阿联酋经济监测")
    file_input = _select_data_source()
    if file_input is None:
        message = (
            "请先在侧边栏“共享数据集”上传阿联酋工作簿。"
            "只有上传并通过工作簿协议校验后，才会读取数据并显示图表。"
        )
        st_obj.info(message)
        return {
            "status": "no_data",
            "message": message,
            "panel_count": 0,
        }

    source_name = _source_name(file_input)
    st_obj.caption(f"当前上传数据来源：{source_name}")
    st_obj.warning(
        "数据说明：工作簿已有指标使用真实数据；缺失指标由程序在运行时模拟。"
        "模拟序列不写回Excel，不代表官方统计、事实判断或预测。"
    )

    try:
        with st_obj.spinner("正在构建宏观监测页面..."):
            dashboard = build_monitoring_dashboard(file_input)
    except Exception as exc:  # noqa: BLE001 - 页面边界需展示工作簿解析错误
        for key in list(st.session_state):
            if str(key).startswith("analysis.uae."):
                del st.session_state[key]
        st_obj.error(f"阿联酋监测数据加载失败：{exc}")
        return {
            "status": "error",
            "message": str(exc),
            "source": source_name,
        }

    tab_objects = st_obj.tabs([label for label, _ in TAB_CONFIG])
    for tab, (_, view_key) in zip(tab_objects, TAB_CONFIG):
        with tab:
            if view_key == "growth_overview":
                _render_panel(
                    st_obj,
                    dashboard.require_panel("growth"),
                    show_title=False,
                    series_group_titles=GROWTH_OVERVIEW_GROUPS,
                )
            elif view_key == "growth_industry":
                _render_panel(
                    st_obj,
                    dashboard.require_panel("growth"),
                    show_title=False,
                    series_group_titles=GROWTH_INDUSTRY_GROUPS,
                )
            else:
                _render_panel(st_obj, dashboard.require_panel(view_key))
    return {
        "status": "success",
        "source": source_name,
        "panel_count": len(dashboard.panels),
    }
