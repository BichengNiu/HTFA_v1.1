"""Read annual investment report sheets without network or workbook writes."""

import pandas as pd
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.database import require_published_source, read_raw_table
from htfa.monitoring.uae.downloads import render_chart_download
from htfa.monitoring.uae.plot_helpers import create_report_axis, apply_htfa_fonts, source_note
from htfa.ui_shared.chart_legend import render_pyplot_figure

ANNUAL_CHARTS = (
    ("年度_资本形成", "资本形成总额", False),
    ("年度_行业资本形成", "行业资本形成总额（现价，末年前五行业）", True),
    ("年度_外资类型", "外国投资分类（历史数据）", False),
    ("年度_外资行业", "外商直接投资行业分布（历史数据，末年前五行业）", True),
    ("年度_外资来源国", "外商直接投资来源地（历史数据，末年前五项）", True),
)


def load_annual_data(source):
    """Retain observed annual dates and missing values from published sheets."""
    frames = {}
    with require_published_source(source).open() as tables:
        for sheet, _, _ in ANNUAL_CHARTS:
            raw = read_raw_table(tables, sheet_name=sheet)
            if set(raw.iloc[2, 1:].dropna()) != {"年"}:
                raise ValueError(f"{sheet} 频率不是年度")
            if set(raw.iloc[3, 1:].dropna()) != {"十亿迪拉姆"}:
                raise ValueError(f"{sheet} 单位不匹配")
            frame = raw.iloc[6:, 1:].apply(pd.to_numeric, errors="raise")
            frame.index = pd.DatetimeIndex(pd.to_datetime(raw.iloc[6:, 0], errors="raise"))
            frame.columns = [str(name).removeprefix(sheet + ":") for name in raw.iloc[1, 1:]]
            if frame.index.isna().any() or frame.index.duplicated().any():
                raise ValueError(f"{sheet} 日期异常")
            frame = frame.sort_index().dropna(how="all")
            if frame.empty:
                raise ValueError(f"{sheet} 没有年度观测")
            frames[sheet] = frame
    return frames


def displayed_annual_values(frame, top_five):
    """Choose a fixed set using the latest observed year, without zero filling."""
    if not top_five:
        return frame
    names = frame.iloc[-1].dropna().nlargest(5).index
    if names.empty:
        raise ValueError("最新年度没有可用于排序的数据")
    return frame.loc[:, names]


def build_annual_figure(frame, *, title, bars=False):
    """Use the existing Ts report template with annual ticks and one AED axis."""
    values = frame.copy()
    values.index = values.index.year
    axis = create_report_axis()
    axis.set_xlim(values.index.min() - 0.7, values.index.max() + 0.7)
    figure, _ = plot_series(
        values, facet=False, title=title, xtitle="", ytitle_position="side",
        auto_dual_y=False, axis_groups={name: "left" for name in values},
        units={name: "十亿迪拉姆" for name in values}, grid=True,
        max_ticks=min(len(values), 8), show_legend=True, legend_cols=2,
        bar_series=list(values) if bars else None, bar_stacked=bars,
        note=source_note("阿联酋联邦竞争力与统计中心（FCSC）"), note_loc="left",
        ax=axis,
    )
    step = max(1, (len(values) + 7) // 8)
    ticks = list(values.index[::step])
    if ticks[-1] != values.index[-1]:
        ticks.append(values.index[-1])
    axis.set_xticks(ticks, [str(year) for year in ticks])
    apply_htfa_fonts(figure)
    return figure


def render_annual_data(st_obj, frames):
    """Render two report charts per row and download complete industry/country series."""
    for index, (sheet, title, top_five) in enumerate(ANNUAL_CHARTS):
        if index % 2 == 0:
            columns = st_obj.columns(2, gap="small")
        host = columns[index % 2]
        frame = frames[sheet]
        title = f"{title}｜{frame.index[0].year}—{frame.index[-1].year}年"
        figure = build_annual_figure(displayed_annual_values(frame, top_five), title=title, bars=top_five)
        render_pyplot_figure(host, figure, bbox_inches=None, place_legend_bottom=False)
        render_chart_download(host, frame, title=title, key=f"analysis.uae.annual.{sheet}.download")
    with st_obj.expander("指标算法与解读", expanded=True, key="uae-indicator-explanation-annual"):
        st_obj.markdown(
            "- 资本形成采用 FCSC 官方 Gross Capital Formation 口径，不等同于固定资产投资完成额。"
            "现价与2010年不变价分别展示，不相加。\n"
            "- 行业及来源地按各表最新年份的观测值选取前五项，历史年份保持同一组项目；"
            "堆叠高度只代表所展示五项的合计。下载包含全部项目，缺失值不补零。\n"
            "- 外资细分接口当前覆盖2007—2016年，属于历史数据；不解读为最新年度数据，"
            "也不未经口径核实就当作年度新增投资流量。"
        )
