"""阿联酋经济监测的 Streamlit 页面。"""

from __future__ import annotations

from collections.abc import Mapping
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
from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.results import MacroPanelResult
from dashboard.analysis.uae.services import build_monitoring_dashboard
from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.ui.utils.chart_legend import place_chart_legend_at_bottom

TAB_CONFIG = (
    ("宏观概览", "growth_overview"),
    ("行业分析", "growth_industry"),
    ("石油财政", "oil_fiscal"),
)

GROWTH_OVERVIEW_GROUPS = (
    "实际GDP增速与GDP平减指数同比",
    "非石油实际GDP增速与非石油GDP平减指数同比",
    "非金融公司实际增加值增速与平减指数同比",
)
GROWTH_INDUSTRY_GROUPS = (
    "GDP部门拉动与石油产量同比",
    "非油实际GDP同比及行业拉动",
    "行业扩张广度指数",
    "行业增长集中度",
    "行业增长持续性与状态矩阵",
    "行业量价四象限图",
)
INDUSTRY_BREADTH_DISPLAY_TITLE = "行业增长广度与持续性"

INDUSTRY_SECTION_TITLES = {
    "GDP部门拉动与石油产量同比": "一、长期趋势：总量与增长来源",
    "行业扩张广度指数": "二、中长期结构：行业增长质量",
    "行业增长持续性与状态矩阵": (
        "三、短期动能：行业状态与量价表现"
    ),
}

GDP_SECTOR_PULL_EXPLANATION = """
- **部门拉动**：`(本季部门实际GDP－上年同期部门实际GDP)÷上年同期总体实际GDP×100`，单位为百分点；正值为拉动，负值为拖累。
- **加总关系**：非石油与石油部门拉动逐季相加等于实际GDP同比。
- **石油产量同比**：反映实物产量相对上年同期的变化率，只用于对照石油部门走势，不能与贡献柱相加，也不代表因果关系。
""".strip()

NONOIL_INDUSTRY_PULL_EXPLANATION = """
- **行业拉动**：`(本季行业实际增加值－上年同期行业实际增加值)÷上年同期非油实际GDP×100`，单位为百分点；正值为拉动，负值为拖累。
- **行业展示**：按完整样本期平均实际GDP占比固定选取前5个行业，其他11个行业合并为“其他行业”。
- **加总关系**：全部柱形逐季相加等于非油GDP同比折线；这是增长核算分解，用于判断增长来自哪里，不解释增长原因。
""".strip()

INDUSTRY_BREADTH_EXPLANATION = """
- **正增长行业比例**：当季同比增速大于0的行业数÷16个行业×100%，每个行业权重相同。
- **连续四季度正增长比例**：最近四个季度同比增速均大于0的行业数÷16个行业×100%，用于衡量增长持续性。
- **解读**：比例越高，增长覆盖面或持续性越强；50%对应8个行业，超过80%至少需要13个行业。两线差距越大，说明更多行业刚转正但尚未形成持续增长。
""".strip()

INDUSTRY_CONCENTRATION_EXPLANATION = """
- **行业贡献**：`cᵢ=(本季行业实际增加值－上年同期行业实际增加值)÷上年同期非油实际GDP×100`，单位为百分点。
- **贡献平衡指数（横轴）**：`Σcᵢ÷Σ|cᵢ|×100`，范围为－100到100。左侧表示负向拖累占主导，0表示正负贡献完全抵消，右侧表示正向拉动占主导。
- **标准化绝对贡献集中度（纵轴）**：先计算 `HHI=Σ(|cᵢ|÷Σ|cᵢ|)²`，再按固定16个行业转换为 `(HHI－1/16)÷(1－1/16)×100`。越高表示总变动越集中于少数行业，越低表示越分散；增长期和收缩期口径完全一致。
- **总变动强度（气泡面积）**：`Σ|cᵢ|`，表示行业正负贡献的绝对值合计。气泡越大，行业层面的增长或收缩变动越强；它不是净增长率。
- **组合解读**：右上方是少数行业主导增长，右下方是广泛增长，左上方是少数行业主导收缩，左下方是广泛收缩。实心圆表示净增长期，空心圆表示净收缩期；精确季度和最大正负贡献行业见悬浮信息。
- **图内时间轴**：拖动图内季度滑块或点击播放，查看截至所选季度的历史分布；深色描边气泡是当前季度，淡色气泡是此前季度。坐标轴和气泡面积尺度都按完整样本固定，切换季度不会改变视觉尺度。
- **纵轴显示**：指标理论范围为0—100；为避免低集中度样本全部贴近横轴，图中上限按完整样本最大值留出20%余量后向上取整，且最低显示到20、最高不超过100。图内会同时标明实际显示范围与理论范围。
- **空值边界**：任一行业贡献缺失，或全部行业均无变动时，该季度不绘制，避免用不完整分母或接近零的变动制造虚假高集中度。
""".strip()

SERIES_GROUP_FIGURE_BUILDERS = {
    "行业量价四象限图": (
        build_industry_price_volume_quadrant_figure,
        None,
    ),
    "行业扩张广度指数": (
        build_industry_breadth_figure,
        INDUSTRY_BREADTH_DISPLAY_TITLE,
    ),
    "行业增长集中度": (
        build_industry_concentration_figure,
        "行业增长的方向与集中度",
    ),
    "行业增长持续性与状态矩阵": (
        build_industry_state_matrix_figure,
        None,
    ),
    "非油实际GDP同比及行业拉动": (
        build_nonoil_industry_pull_figure,
        None,
    ),
}

SERIES_GROUP_EXPLANATIONS = {
    "GDP部门拉动与石油产量同比": GDP_SECTOR_PULL_EXPLANATION,
    "非油实际GDP同比及行业拉动": NONOIL_INDUSTRY_PULL_EXPLANATION,
    "行业扩张广度指数": INDUSTRY_BREADTH_EXPLANATION,
    "行业增长集中度": INDUSTRY_CONCENTRATION_EXPLANATION,
}


def _render_series_group_explanation(st_obj, group_title: str) -> None:
    """在配置的行业图下渲染简明的指标口径说明。"""

    explanation = SERIES_GROUP_EXPLANATIONS.get(group_title)
    if explanation is None:
        return
    with st_obj.expander("指标算法与解读", expanded=False):
        st_obj.markdown(explanation)


def _source_name(file_input: Any) -> str:
    if hasattr(file_input, "name"):
        return str(file_input.name)
    return Path(file_input).name


def _ordered_series_groups(
    series_groups: Mapping[str, Any],
    series_group_titles: tuple[str, ...] | None,
) -> tuple[tuple[str, Any], ...]:
    """按显式标题顺序选择序列组，未指定时保留原始顺序。"""

    if series_group_titles is None:
        return tuple(series_groups.items())
    return tuple(
        (title, series_groups[title])
        for title in series_group_titles
        if title in series_groups
    )


def _render_panel(
    st_obj,
    panel: MacroPanelResult,
    *,
    series_group_titles: tuple[str, ...] | None = None,
) -> None:
    for group_title, frame in _ordered_series_groups(
        panel.series_groups,
        series_group_titles,
    ):
        section_title = INDUSTRY_SECTION_TITLES.get(group_title)
        if section_title is not None:
            st_obj.markdown(f"### {section_title}")
        if group_title in GROWTH_OVERVIEW_GROUPS:
            figure = build_price_volume_figure(
                frame,
                title=group_title,
            )
        elif group_title in SERIES_GROUP_FIGURE_BUILDERS:
            builder, display_title = SERIES_GROUP_FIGURE_BUILDERS[group_title]
            figure = builder(frame, title=display_title or group_title)
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
            place_chart_legend_at_bottom(figure),
            width="stretch",
            key=f"analysis.uae.{panel.key}.series.{group_title}",
        )
        render_chart_download(
            st_obj,
            frame,
            title=group_title,
            key=f"analysis.uae.{panel.key}.series.{group_title}.download",
        )
        _render_series_group_explanation(st_obj, group_title)

    for table_title, frame in panel.decomposition_tables.items():
        st_obj.plotly_chart(
            place_chart_legend_at_bottom(
                build_latest_contribution_figure(
                    frame,
                    title=table_title,
                )
            ),
            width="stretch",
            key=f"analysis.uae.{panel.key}.decomposition.{table_title}",
        )
        render_chart_download(
            st_obj,
            frame,
            title=table_title,
            key=f"analysis.uae.{panel.key}.decomposition.{table_title}.download",
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


def _render_growth_tab(
    st_obj,
    dashboard,
    series_group_titles: tuple[str, ...],
) -> None:
    if dashboard.unavailable_panels:
        st_obj.info(
            "当前工作簿不足以构建宏观监测主题："
            f"{dashboard.unavailable_panels['growth']}"
        )
        return
    _render_panel(
        st_obj,
        dashboard.require_panel("growth"),
        series_group_titles=series_group_titles,
    )


def render_uae_monitoring(st_obj=st) -> dict[str, Any]:
    """渲染阿联酋监测；不写入或生成任何工作簿。"""

    st_obj.title("阿联酋经济监测")
    file_input = get_shared_dataset_file()
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
                _render_growth_tab(
                    st_obj,
                    dashboard,
                    GROWTH_OVERVIEW_GROUPS,
                )
            elif view_key == "growth_industry":
                _render_growth_tab(
                    st_obj,
                    dashboard,
                    GROWTH_INDUSTRY_GROUPS,
                )
            else:
                from dashboard.analysis.uae.oil import render_oil_fiscal_panel

                render_oil_fiscal_panel(st_obj)
    return {
        "status": "success",
        "source": source_name,
        "panel_count": len(dashboard.panels),
    }
