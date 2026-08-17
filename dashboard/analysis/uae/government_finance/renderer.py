"""Streamlit section for government and government-related entity banking data."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.foreign_labor import (
    BANGLADESH_CLEARANCES,
    NEPAL_APPROVALS,
    ForeignLaborData,
    build_foreign_labor_figure,
    common_observations,
    latest_common_month as latest_foreign_labor_month,
    load_foreign_labor_data,
)
from dashboard.analysis.uae.government_finance.charts import (
    build_government_finance_yoy_figure,
)
from dashboard.analysis.uae.government_finance.credit import (
    CbuaeSeriesData,
    build_foreign_inflow_figure,
    build_private_credit_yoy_figure,
    load_foreign_inflow_data,
    load_private_credit_data,
)
from dashboard.analysis.uae.government_finance.data import (
    GOVERNMENT_CREDIT,
    GRE_CREDIT,
    GovernmentFinanceData,
    calculate_calendar_yoy,
    latest_complete_month,
    load_government_finance_data,
)
from dashboard.analysis.uae.government_finance.ded import (
    ENTERPRISES_DISPLAY,
    LICENCES_DISPLAY,
    DedData,
    build_ded_figure,
    load_ded_data,
)
from dashboard.analysis.uae.government_finance.pmi import (
    PMI_LABEL,
    PmiData,
    build_pmi_figure,
    display_pmi_values,
    load_pmi_data,
)
from dashboard.analysis.uae.government_finance.rates import (
    EIBOR_ONEYEAR_DISPLAY,
    EIBOR_OVERNIGHT_DISPLAY,
    RatesData,
    build_rates_figure,
    load_rates_data,
)
from dashboard.analysis.uae.government_finance.search_index import (
    SOURCE_TEXT as SEARCH_SOURCE_TEXT,
    WORK_DUBAI_COLUMN,
    WORK_UAE_COLUMN,
    build_search_index_figure,
    display_search_index_values,
    load_search_index_data,
)
from dashboard.analysis.uae.metrics import (
    _source_note_from_metadata,
    change_in_points,
    latest_calendar_yoy_and_pp,
    latest_month_value,
    month_over_month_change,
    pct_delta_text,
    points_delta_text,
    render_metric_cards,
)
from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure


@st.cache_data(show_spinner=False)
def _load_government_finance_cached(
    content: bytes,
    file_name: str,
) -> GovernmentFinanceData:
    return load_government_finance_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_foreign_labor_cached(
    content: bytes,
    file_name: str,
) -> ForeignLaborData:
    return load_foreign_labor_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_rates_cached(content: bytes, file_name: str) -> RatesData:
    return load_rates_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_foreign_inflow_cached(content: bytes, file_name: str) -> CbuaeSeriesData:
    return load_foreign_inflow_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_private_credit_cached(content: bytes, file_name: str) -> CbuaeSeriesData:
    return load_private_credit_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_ded_cached(content: bytes, file_name: str) -> DedData:
    return load_ded_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_pmi_cached(content: bytes, file_name: str) -> PmiData:
    return load_pmi_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_search_index_cached() -> pd.DataFrame:
    return load_search_index_data()


def _format_number(value: float | None, *, unit: str) -> str | None:
    """格式化带千分位的主值；None 返回 None（该卡显示 —）。"""

    if value is None:
        return None
    return f"{value:,.0f} {unit}"


def _render_finance_metrics(
    st_obj: Any,
    data: GovernmentFinanceData,
    content: bytes,
    file_name: str,
) -> None:
    """财政金融指标卡：阿联酋隔夜/1年期利率 + 政府贷款/政府控股企业贷款增速。"""

    try:
        rates = _load_rates_cached(content, file_name)
        cards = []
        for label, column in (
            ("阿联酋隔夜拆借利率", EIBOR_OVERNIGHT_DISPLAY),
            ("阿联酋1年期拆借利率", EIBOR_ONEYEAR_DISPLAY),
        ):
            value, as_of = latest_month_value(rates.values[column])
            value_text = None if value is None else f"{value:.2f}%"
            cards.append(
                (
                    label,
                    value_text,
                    points_delta_text(change_in_points(rates.values[column])),
                    _source_note_from_metadata(
                        rates.metadata, column, as_of
                    ),
                )
            )
        for label, column in (
            ("政府贷款增长率", GOVERNMENT_CREDIT),
            ("政府控股企业贷款增长率", GRE_CREDIT),
        ):
            yoy, pp, as_of = latest_calendar_yoy_and_pp(data.values, column)
            value_text = None if yoy is None else f"{yoy:+.1f}%"
            delta_text = (
                None if pp is None else f"较上月同比 {pp:+.1f} 个百分点"
            )
            cards.append(
                (
                    label,
                    value_text,
                    delta_text,
                    f"截至 {as_of.strftime('%Y-%m') if as_of is not None else '—'}；"
                    f"月度同比，口径：{column}",
                )
            )
        render_metric_cards(st_obj, cards, n=4)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.warning(f"财政金融指标未加载：{exc}")


def _render_business_metrics(
    st_obj: Any,
    latest_date: pd.Timestamp,
    content: bytes,
    file_name: str,
) -> None:
    """企业活动指标卡：PMI + 迪拜发证活动企业数/新发执照（锚定 latest_date）+ 同比。"""

    try:
        cards = []
        pmi = _load_pmi_cached(content, file_name)
        pmi_series = pmi.values[PMI_LABEL]
        pmi_value, pmi_as_of = latest_month_value(pmi_series)
        cards.append(
            (
                "非油私营部门PMI",
                None if pmi_value is None else f"{pmi_value:.1f}",
                points_delta_text(
                    change_in_points(pmi_series),
                    unit="点",
                    digits=1,
                ),
                _source_note_from_metadata(
                    pmi.metadata, PMI_LABEL, pmi_as_of
                ),
            )
        )
        ded = _load_ded_cached(content, file_name)
        # 与 DED 柱图同规则：锚定 latest_date，避开尾部欠计噪声月
        last_period = latest_date.to_period("M")
        ded_series = ded.values.loc[
            pd.PeriodIndex(ded.values.index, freq="M") <= last_period
        ]
        for label, column, unit in (
            ("迪拜发证活动企业数", ENTERPRISES_DISPLAY, "家"),
            ("迪拜新发执照数", LICENCES_DISPLAY, "张"),
        ):
            value, as_of = latest_month_value(ded_series[column])
            cards.append(
                (
                    label,
                    _format_number(value, unit=unit),
                    pct_delta_text(
                        month_over_month_change(ded_series[column])
                    ),
                    _source_note_from_metadata(
                        ded.metadata, column, as_of
                    ),
                )
            )
        yoy, pp, yoy_as_of = latest_calendar_yoy_and_pp(
            ded_series, ENTERPRISES_DISPLAY
        )
        value_text = None if yoy is None else f"{yoy:+.1f}%"
        delta_text = (
            None if pp is None else f"较上月同比 {pp:+.1f} 个百分点"
        )
        cards.append(
            (
                "发证活动企业同比",
                value_text,
                delta_text,
                f"截至 {yoy_as_of.strftime('%Y-%m') if yoy_as_of is not None else '—'}；"
                f"迪拜有发证活动企业数整月历同比",
            )
        )
        render_metric_cards(st_obj, cards, n=4)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.warning(f"企业活动指标未加载：{exc}")


def _render_labor_metrics(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> None:
    """劳动就业指标卡：尼泊尔/孟加拉国劳工人数 + 谷歌工作搜索热度。"""

    try:
        cards = []
        labor = _load_foreign_labor_cached(content, file_name)
        for label, column in (
            ("尼泊尔批准劳工人数", NEPAL_APPROVALS),
            ("孟加拉国出境许可人数", BANGLADESH_CLEARANCES),
        ):
            value, as_of = latest_month_value(labor.values[column])
            cards.append(
                (
                    label,
                    _format_number(value, unit="人"),
                    pct_delta_text(
                        month_over_month_change(labor.values[column])
                    ),
                    _source_note_from_metadata(
                        labor.metadata, column, as_of
                    ),
                )
            )
        search = _load_search_index_cached()
        for label, column in (
            ("谷歌「在迪拜工作」搜索热度", WORK_DUBAI_COLUMN),
            ("谷歌「在阿联酋工作」搜索热度", WORK_UAE_COLUMN),
        ):
            value, as_of = latest_month_value(search[column])
            value_text = None if value is None else f"{value:.0f}"
            cards.append(
                (
                    label,
                    value_text,
                    pct_delta_text(
                        month_over_month_change(search[column])
                    ),
                    f"截至 {as_of.strftime('%Y-%m') if as_of is not None else '—'}；"
                    f"按月搜索指数；来源：{SEARCH_SOURCE_TEXT}",
                )
            )
        render_metric_cards(st_obj, cards, n=4)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        st_obj.warning(f"劳动就业指标未加载：{exc}")


def _chart_frame(values: pd.DataFrame) -> pd.DataFrame:
    """Return only the two government-credit year-on-year series for download."""

    yoy = calculate_calendar_yoy(values[[GOVERNMENT_CREDIT, GRE_CREDIT]])
    return yoy.rename(
        columns={
            GOVERNMENT_CREDIT: "政府贷款同比（%）",
            GRE_CREDIT: "政府控制企业贷款同比（%）",
        }
    ).dropna(how="all")


def _render_charts(
    st_obj: Any,
    data: GovernmentFinanceData,
    latest_date: pd.Timestamp,
) -> None:
    first_month = latest_date.to_period("M") - 36
    display_values = within_month_window(
        data.values,
        first_month=first_month,
        last_month=latest_date.to_period("M"),
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "政府贷款与政府控制企业贷款增长"
    chart_frame = _chart_frame(display_values)
    render_pyplot_figure(
        st_obj,
        build_government_finance_yoy_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        chart_frame,
        title=title,
        key="analysis.uae.government_finance.yoy.download",
    )


def _render_rates_chart(
    st_obj: Any,
    data: RatesData,
    latest_date: pd.Timestamp,
) -> None:
    last_month = latest_date.to_period("M")
    display_values = within_month_window(
        data.values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "阿联酋与美国市场利率（隔夜、1年期）"
    render_pyplot_figure(
        st_obj,
        build_rates_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.government_finance.rates.download",
    )


def _render_foreign_inflow_chart(
    st_obj: Any,
    data: CbuaeSeriesData,
    latest_date: pd.Timestamp,
) -> None:
    last_month = latest_date.to_period("M")
    display_values = within_month_window(
        data.values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "外资流入同比：银行外债、外币存款与外国主体存款"
    render_pyplot_figure(
        st_obj,
        build_foreign_inflow_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    chart_frame = calculate_calendar_yoy(display_values).rename(
        columns=lambda name: f"{name}同比（%）"
    )
    render_chart_download(
        st_obj,
        chart_frame.dropna(how="all"),
        title=title,
        key="analysis.uae.government_finance.foreign_inflow.download",
    )


def _render_private_credit_chart(
    st_obj: Any,
    data: CbuaeSeriesData,
    latest_date: pd.Timestamp,
) -> None:
    last_month = latest_date.to_period("M")
    display_values = within_month_window(
        data.values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "企业及居民信贷同比"
    chart_frame = calculate_calendar_yoy(display_values).rename(
        columns=lambda name: f"{name}同比（%）"
    )
    render_pyplot_figure(
        st_obj,
        build_private_credit_yoy_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        chart_frame,
        title=title,
        key="analysis.uae.government_finance.private_credit.download",
    )


def _render_ded_chart(
    st_obj: Any,
    data: DedData,
    latest_date: pd.Timestamp,
) -> None:
    last_month = latest_date.to_period("M")
    display_values = within_month_window(
        data.values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "迪拜企业发证活动与新发执照"
    render_pyplot_figure(
        st_obj,
        build_ded_figure(
            data.values,
            title=title,
            source_text=source_text,
            last_month=last_month,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.government_finance.ded.download",
    )


def _render_foreign_labor_chart(
    st_obj: Any,
    data: ForeignLaborData,
) -> None:
    last_month = latest_foreign_labor_month(data.values)
    display_values = within_month_window(
        common_observations(data.values),
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "；".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "尼泊尔和孟加拉国入境阿联酋劳工人数"
    render_pyplot_figure(
        st_obj,
        build_foreign_labor_figure(
            display_values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.foreign_labor.monthly.download",
    )


def _render_search_index_chart(
    st_obj: Any,
    values: pd.DataFrame,
) -> None:
    title = "阿联酋工作谷歌搜索热度"
    display_values = display_search_index_values(values)
    render_pyplot_figure(
        st_obj,
        build_search_index_figure(
            values,
            title=title,
            source_text=SEARCH_SOURCE_TEXT,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.search_index.monthly.download",
    )


def _render_pmi_chart(
    st_obj: Any,
    data: PmiData,
) -> None:
    source_text = "；".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "阿联酋非油私营部门PMI"
    display_values = display_pmi_values(data.values)
    render_pyplot_figure(
        st_obj,
        build_pmi_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.pmi.monthly.download",
    )


def render_government_finance_section(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """Render the CBUAE / Wind rates, credit, DED and labour comparisons."""

    st_obj.divider()
    st_obj.subheader("财政金融")
    try:
        with st_obj.spinner("正在读取 CBUAE 月度存款与信贷数据..."):
            data = _load_government_finance_cached(content, file_name)
        latest_date = latest_complete_month(data.values)
        _render_finance_metrics(st_obj, data, content, file_name)
        _render_quad_finance_charts(
            st_obj,
            data,
            latest_date,
            content,
            file_name,
        )
        _render_business_activity_charts(
            st_obj,
            latest_date,
            content,
            file_name,
        )
        _render_labor_employment_charts(st_obj, content, file_name)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.error(f"政府及国有资本存款与信贷数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "as_of": latest_date.strftime("%Y-%m"),
    }


def _render_business_activity_charts(
    st_obj: Any,
    latest_date: pd.Timestamp,
    content: bytes,
    file_name: str,
) -> None:
    """企业活动：左侧 DED 发证活动企业/新发执照柱图，右侧非油私营部门 PMI。"""

    st_obj.divider()
    st_obj.subheader("企业活动")
    _render_business_metrics(st_obj, latest_date, content, file_name)
    ded_column, pmi_column = st_obj.columns(2, gap="small")
    try:
        with st_obj.spinner("正在读取迪拜企业发证与新发执照数据..."):
            ded = _load_ded_cached(content, file_name)
        _render_ded_chart(ded_column, ded, latest_date)
    except (KeyError, TypeError, ValueError) as exc:
        ded_column.warning(f"企业发证活动柱图未加载：{exc}")
    try:
        with st_obj.spinner("正在读取非油私营部门 PMI 数据..."):
            pmi = _load_pmi_cached(content, file_name)
        _render_pmi_chart(pmi_column, pmi)
    except (KeyError, TypeError, ValueError) as exc:
        pmi_column.warning(f"PMI 图表未加载：{exc}")


def _render_quad_finance_charts(
    st_obj: Any,
    data: GovernmentFinanceData,
    latest_date: pd.Timestamp,
    content: bytes,
    file_name: str,
) -> None:
    """财政金融 2×2：利率 / 外资流入 / 政府及国有资本信贷 / 企业及居民信贷。

    左上阿联酋与美国隔夜/1年期利率（月度均值），右上外资流入三指标同比（银行外债/
    外币存款/外国主体存款），左下政府贷款与政府控制企业贷款同比，右下企业及
    居民信贷同比。单个格子数据缺失只显示该格警告，不影响其它格。
    """

    top_left, top_right = st_obj.columns(2, gap="small")
    bottom_left, bottom_right = st_obj.columns(2, gap="small")

    try:
        with st_obj.spinner("正在读取 EIBOR 与联邦基金利率..."):
            rates = _load_rates_cached(content, file_name)
        _render_rates_chart(top_left, rates, latest_date)
    except (KeyError, TypeError, ValueError) as exc:
        top_left.warning(f"利率图未加载：{exc}")

    try:
        with st_obj.spinner("正在读取 CBUAE 外资流入数据..."):
            foreign_inflow = _load_foreign_inflow_cached(content, file_name)
        _render_foreign_inflow_chart(top_right, foreign_inflow, latest_date)
    except (KeyError, TypeError, ValueError) as exc:
        top_right.warning(f"外资流入图未加载：{exc}")

    _render_charts(bottom_left, data, latest_date)

    try:
        with st_obj.spinner("正在读取 CBUAE 企业及居民信贷数据..."):
            private_credit = _load_private_credit_cached(content, file_name)
        _render_private_credit_chart(
            bottom_right,
            private_credit,
            latest_date,
        )
    except (KeyError, TypeError, ValueError) as exc:
        bottom_right.warning(f"企业及居民信贷图未加载：{exc}")


def _render_labor_employment_charts(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> None:
    """谷歌工作搜索热度在左，入境阿联酋劳工人数在右。"""

    st_obj.divider()
    st_obj.subheader("劳动就业")
    _render_labor_metrics(st_obj, content, file_name)
    search_column, labor_column = st_obj.columns(2, gap="small")
    try:
        with st_obj.spinner("正在读取谷歌工作搜索热度数据..."):
            search_index = _load_search_index_cached()
        _render_search_index_chart(search_column, search_index)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        search_column.warning(f"谷歌搜索热度图表未加载：{exc}")
    try:
        with st_obj.spinner("正在读取外籍劳动力月度数据..."):
            foreign_labor = _load_foreign_labor_cached(content, file_name)
        _render_foreign_labor_chart(labor_column, foreign_labor)
    except (KeyError, TypeError, ValueError) as exc:
        labor_column.warning(f"外籍劳动力图表未加载：{exc}")


__all__ = ["render_government_finance_section"]
