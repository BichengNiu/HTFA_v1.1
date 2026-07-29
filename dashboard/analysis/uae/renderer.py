"""阿联酋经济监测的 Streamlit 页面。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from dashboard.analysis.uae.charts import (
    build_latest_contribution_figure,
    build_line_figure,
)
from dashboard.analysis.uae.contracts import ProvenanceKind
from dashboard.analysis.uae.data_adapter import DEFAULT_UAE_WORKBOOK
from dashboard.analysis.uae.results import (
    MacroPanelResult,
    MonitoringDashboardResult,
)
from dashboard.analysis.uae.services import build_monitoring_dashboard
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file


TAB_CONFIG = (
    ("总览", None),
    ("增长与结构", "growth"),
    ("通货膨胀", "inflation"),
    ("就业与收入", "labor"),
    ("财政与外部", "fiscal_external"),
    ("货币与金融", "monetary"),
)


def _select_data_source() -> Any:
    """共享上传优先；未上传时使用现有阿联酋工作簿。"""

    uploaded = get_shared_dataset_file()
    return uploaded if uploaded is not None else DEFAULT_UAE_WORKBOOK


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


def _render_diagnostic(st_obj, panel: MacroPanelResult) -> None:
    headline = panel.headline
    confidence_color = {
        "高": "#1B7F3A",
        "中": "#B26A00",
        "低": "#B3261E",
    }[headline.confidence.value]
    st_obj.markdown(
        f"""
        <div style="
            border-left: 5px solid {confidence_color};
            background: #f7f9fc;
            padding: 1rem 1.15rem;
            border-radius: 6px;
            margin-bottom: 1rem;">
          <div style="font-weight: 700; margin-bottom: .35rem;">
            诊断结论｜置信度：{headline.confidence.value}
          </div>
          <div style="line-height: 1.7;">{headline.summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if headline.uses_simulated_data:
        st_obj.caption(
            "本诊断包含模拟证据；模拟值仅用于页面和分析流程开发。"
        )


def _render_metrics(st_obj, panel: MacroPanelResult) -> None:
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


def _render_panel(st_obj, panel: MacroPanelResult) -> None:
    st_obj.subheader(panel.title)
    _render_diagnostic(st_obj, panel)
    _render_metrics(st_obj, panel)

    for group_title, frame in panel.series_groups.items():
        st_obj.plotly_chart(
            build_line_figure(
                frame,
                title=group_title,
            ),
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
        st_obj.markdown("**诊断限制**")
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


def _render_overview(
    st_obj,
    dashboard: MonitoringDashboardResult,
) -> None:
    st_obj.subheader("宏观诊断总览")
    st_obj.caption(
        "每张卡片依次报告结果、核算贡献、机制证据、限制和置信度。"
    )
    panels = list(dashboard.panels.values())
    for start in range(0, len(panels), 2):
        columns = st_obj.columns(2)
        for column, panel in zip(columns, panels[start : start + 2]):
            with column:
                simulated = "含模拟数据" if panel.uses_simulated_data else "全部真实数据"
                st_obj.markdown(f"### {panel.title}")
                st_obj.caption(
                    f"置信度：{panel.headline.confidence.value}｜{simulated}"
                )
                st_obj.write(panel.headline.summary)
                st_obj.markdown("---")


def render_uae_monitoring(st_obj=st) -> dict[str, Any]:
    """渲染阿联酋监测；不写入或生成任何工作簿。"""

    file_input = _select_data_source()
    source_name = _source_name(file_input)
    st_obj.title("阿联酋经济监测")
    st_obj.caption(f"当前真实数据来源：{source_name}")
    st_obj.warning(
        "数据说明：工作簿已有指标使用真实数据；缺失指标由程序在运行时模拟。"
        "模拟序列不写回Excel，不代表官方统计、事实判断或预测。"
    )

    try:
        with st_obj.spinner("正在构建宏观诊断..."):
            dashboard = build_monitoring_dashboard(file_input)
    except Exception as exc:
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
    for tab, (_, panel_key) in zip(tab_objects, TAB_CONFIG):
        with tab:
            if panel_key is None:
                _render_overview(st_obj, dashboard)
            else:
                _render_panel(st_obj, dashboard.require_panel(panel_key))
    return {
        "status": "success",
        "source": source_name,
        "panel_count": len(dashboard.panels),
    }

