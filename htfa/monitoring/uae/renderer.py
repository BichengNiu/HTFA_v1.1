"""阿联酋经济监测的 Streamlit 页面。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from htfa.monitoring.uae.database import (
    PublishedUAEData,
    require_published_source,
    read_raw_table,
    published_source,
)
from htfa.data.economic_workbook.shared.target_reader import validate_sheet

from htfa.data.temporal import last_complete_month_end
from htfa.monitoring.uae.charts import (
    build_growth_and_sector_pull_figure,
    build_industry_breadth_figure,
    build_industry_concentration_figure,
    build_industry_price_volume_quadrant_figure,
    build_industry_state_matrix_figure,
    build_nonoil_industry_pull_figure,
    build_price_volume_figure,
)
from htfa.monitoring.uae.contracts import ProvenanceKind
from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.results import MacroPanelResult
from htfa.monitoring.uae.report import render_high_frequency_topics
from htfa.monitoring.uae.services import load_growth_panel
from htfa.monitoring.uae.plot_helpers import translate_source_text
from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom, render_pyplot_figure

TAB_CONFIG = (
    ("宏观数据", "growth_overview"),
    ("行业分析", "growth_industry"),
    ("高频数据", "oil_fiscal"),
)


_HIGH_FREQUENCY_LABELS = frozenset(
    {
        "日",
        "日度",
        "周",
        "周度",
        "旬",
        "旬度",
        "月",
        "月度",
    }
)


@st.cache_data(show_spinner=False, max_entries=4)
def _load_growth_panel_cached(source):
    """按已发布的数据版本缓存宏观监测计算。"""
    return load_growth_panel(source)


def _latest_high_frequency_month(
    source: PublishedUAEData,
    *,
    today: pd.Timestamp | None = None,
) -> pd.Period:
    observation_cutoff = (
        pd.Timestamp.today().normalize()
        if today is None
        else pd.Timestamp(today).normalize()
    )
    latest_months: list[pd.Period] = []
    with require_published_source(source).open() as tables:
        for sheet_name in tables.sheet_names[1:]:
            raw = read_raw_table(
                tables,
                sheet_name=sheet_name,
            )
            validate_sheet(raw, sheet_name)
            frequencies = {
                str(value).strip()
                for value in raw.iloc[2, 1:].tolist()
                if pd.notna(value)
            }
            if not frequencies & _HIGH_FREQUENCY_LABELS:
                continue

            dates = pd.to_datetime(raw.iloc[6:, 0], errors="coerce")
            values = raw.iloc[6:, 1:].apply(
                pd.to_numeric,
                errors="coerce",
            )
            valid = (
                dates.notna()
                & dates.le(observation_cutoff)
                & values.notna().any(axis=1)
            )
            if not valid.any():
                raise ValueError(
                    f"高频工作表“{sheet_name}”没有可用日期或数值观测"
                )
            candidate = pd.Timestamp(dates[valid].max())
            candidate_month = candidate.to_period("M")
            if frequencies & {"日", "日度", "周", "周度", "旬", "旬度"}:
                cutoff = last_complete_month_end(
                    candidate.date(),
                    today=observation_cutoff.date(),
                )
                if cutoff is None:
                    continue
                latest_months.append(pd.Timestamp(cutoff).to_period("M"))
            else:
                if candidate_month == observation_cutoff.to_period("M"):
                    candidate_month -= 1
                latest_months.append(candidate_month)

    if not latest_months:
        raise ValueError("数据库报告没有可用于报告标题的完整高频月份")
    return max(latest_months)


def _render_report_header(
    st_obj: Any,
    latest_data_month: pd.Period | None = None,
) -> None:
    """渲染网页标题，并提供仅打印显示的月报标题与报告时间。"""

    st_obj.title("阿联酋经济监测")
    report_time = (
        f"{latest_data_month.year}年{latest_data_month.month}月"
        if latest_data_month is not None
        else "—"
    )
    st_obj.markdown(
        "<div class=\"uae-print-report-header\" aria-hidden=\"true\">"
        "<div class=\"uae-print-report-title\">阿联酋经济高频数据月报</div>"
        "<div class=\"uae-print-report-meta\">"
        "<div class=\"uae-print-report-organization\">"
        "中国驻阿联酋大使馆、国家发展改革委国家信息中心"
        "</div>"
        f"<div class=\"uae-print-report-period\">{report_time}</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


MACRO_FIGURE_BUILDERS = {
    "实际GDP增速与GDP平减指数同比": build_price_volume_figure,
    "GDP部门拉动与石油产量同比": build_growth_and_sector_pull_figure,
    "非石油实际GDP增速与非石油GDP平减指数同比": build_price_volume_figure,
    "非油实际GDP行业拉动": build_nonoil_industry_pull_figure,
}
GROWTH_OVERVIEW_GROUPS = tuple(MACRO_FIGURE_BUILDERS)
GROWTH_INDUSTRY_GROUPS = (
    "行业扩张广度指数",
    "行业增长集中度",
    "行业增长持续性与状态矩阵",
    "行业量价四象限图",
)
INDUSTRY_BREADTH_DISPLAY_TITLE = "行业增长广度与持续性"

INDUSTRY_SECTION_TITLES = {
    "行业扩张广度指数": "一、中长期结构：行业增长质量",
    "行业增长持续性与状态矩阵": (
        "二、短期动能：行业状态与量价表现"
    ),
}

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
}

SERIES_GROUP_EXPLANATIONS = {
    "行业扩张广度指数": INDUSTRY_BREADTH_EXPLANATION,
    "行业增长集中度": INDUSTRY_CONCENTRATION_EXPLANATION,
}


def _render_series_group_explanation(st_obj, group_title: str) -> None:
    """在配置的行业图下渲染简明的指标口径说明。"""

    explanation = SERIES_GROUP_EXPLANATIONS.get(group_title)
    if explanation is None:
        return
    with st_obj.expander(
        "指标算法与解读", expanded=True,
        key=f"uae-indicator-explanation-{group_title}",
    ):
        st_obj.markdown(explanation)


def _ordered_series_groups(
    series_groups: Mapping[str, Any],
    series_group_titles: tuple[str, ...],
) -> tuple[tuple[str, Any], ...]:
    """按页面配置选择序列组；缺失结果必须暴露配置或计算错误。"""

    return tuple(
        (title, series_groups[title])
        for title in series_group_titles
    )


def _render_panel(
    st_obj,
    panel: MacroPanelResult,
    *,
    series_group_titles: tuple[str, ...],
) -> None:
    macro_index = 0
    for group_title, frame in _ordered_series_groups(
        panel.series_groups,
        series_group_titles,
    ):
        chart_container = st_obj
        if group_title in GROWTH_OVERVIEW_GROUPS:
            if macro_index % 2 == 0:
                macro_columns = st_obj.columns(2, gap="small")
            chart_container = macro_columns[macro_index % 2]
            macro_index += 1
        section_title = INDUSTRY_SECTION_TITLES.get(group_title)
        if section_title is not None:
            st_obj.markdown(f"### {section_title}")
        if group_title in GROWTH_OVERVIEW_GROUPS:
            source_text = "、".join(dict.fromkeys(
                translate_source_text(item.source)
                for indicator_id, item in panel.provenance.items()
                if indicator_id.startswith("growth.") or (
                    group_title == "GDP部门拉动与石油产量同比"
                    and indicator_id == "oil.crude_production"
                )
            ))
            builder = MACRO_FIGURE_BUILDERS[group_title]
            figure = builder(
                frame,
                title=group_title,
                source_text=source_text,
            )
        else:
            builder, display_title = SERIES_GROUP_FIGURE_BUILDERS[group_title]
            figure = builder(frame, title=display_title or group_title)
        if group_title in GROWTH_OVERVIEW_GROUPS:
            render_pyplot_figure(
                chart_container, figure, bbox_inches=None, place_legend_bottom=False,
            )
        else:
            st_obj.plotly_chart(
                place_chart_legend_at_bottom(figure),
                width="stretch",
                key=f"analysis.uae.{panel.key}.series.{group_title}",
            )
        render_chart_download(
            chart_container,
            frame,
            title=group_title,
            key=f"analysis.uae.{panel.key}.series.{group_title}.download",
        )
        if group_title not in GROWTH_OVERVIEW_GROUPS:
            _render_series_group_explanation(chart_container, group_title)

    if series_group_titles == GROWTH_OVERVIEW_GROUPS:
        return

    with st_obj.expander("证据、来源与方法限制", expanded=False):
        st_obj.markdown("**数据与解释限制**")
        st_obj.write(panel.limitation)
        st_obj.markdown("**证据类型**")
        for item in panel.evidence:
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
    """从只读 DuckDB 发布版本渲染阿联酋监测，无需上传文件。"""
    try:
        source = published_source()
    except (OSError, ValueError) as exc:
        _render_report_header(st_obj)
        message = f"阿联酋数据库未就绪：{exc}"
        st_obj.error(message)
        return {
            "status": "error",
            "message": message,
            "panel_count": 0,
        }

    source_name = source.name
    try:
        _render_report_header(st_obj, _latest_high_frequency_month(source))
        st_obj.caption(f"数据库发布于 {source.published_at} UTC")
    except Exception as exc:  # noqa: BLE001 - 页面边界需展示数据库解析错误
        for key in list(st.session_state):
            if str(key).startswith("analysis.uae."):
                del st.session_state[key]
        st_obj.error(f"阿联酋监测数据加载失败：{exc}")
        return {
            "status": "error",
            "message": str(exc),
            "source": source_name,
        }

    tab_objects = st_obj.tabs(
        [label for label, _ in TAB_CONFIG],
        default="高频数据",
        key="analysis.uae.active_tab",
        on_change="rerun",
    )
    topic_results = {}
    panel_count = 0
    for tab, (_, view_key) in zip(tab_objects, TAB_CONFIG):
        if not tab.open:
            continue
        with tab:
            if view_key == "oil_fiscal":
                with st_obj.container(key="uae-high-frequency-print"):
                    topic_results = render_high_frequency_topics(st_obj, source)
            else:
                try:
                    with st_obj.spinner("正在构建宏观监测页面..."):
                        panel = _load_growth_panel_cached(source)
                except ValueError as exc:
                    st_obj.info(f"当前数据库报告不足以构建宏观监测主题：{exc}")
                    continue
                panel_count = 1
                _render_panel(
                    st_obj,
                    panel,
                    series_group_titles=GROWTH_OVERVIEW_GROUPS
                    if view_key == "growth_overview"
                    else GROWTH_INDUSTRY_GROUPS,
                )
    return {
        "status": "success",
        "source": source_name,
        "panel_count": panel_count,
        "high_frequency": topic_results,
    }
