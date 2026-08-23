"""Streamlit section for government and government-related entity banking data."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.foreign_labor import (
    BANGLADESH_CLEARANCES,
    BANGLADESH_LABEL,
    NEPAL_APPROVALS,
    NEPAL_LABEL,
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
    BUSINESS_INDUSTRIAL_DISPLAY,
    CbuaeSeriesData,
    FOREIGN_CURRENCIES_DISPLAY,
    FOREIGN_LIABILITIES_DISPLAY,
    INDIVIDUAL_DISPLAY,
    NONRESIDENT_DEPOSITS,
    PRIVATE_CORPORATE_DISPLAY,
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
    PMI_DISPLAY_NAME,
    PmiData,
    build_pmi_figure,
    display_pmi_values,
    load_pmi_data,
)
from dashboard.analysis.uae.government_finance.payments import (
    CHEQUES_AMOUNT_DISPLAY,
    CHEQUES_NUMBER_DISPLAY,
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
    PaymentData,
    build_cheques_figure,
    build_customer_transfers_figure,
    cumulative_to_monthly,
    load_payment_data,
)
from dashboard.analysis.uae.government_finance.rates import (
    EIBOR_ONEYEAR_DISPLAY,
    EIBOR_OVERNIGHT_DISPLAY,
    US_OVERNIGHT_DISPLAY,
    US_SOFR_12M_DISPLAY,
    RatesData,
    RATES_SERIES,
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
    format_count_value,
    format_currency_value,
    latest_month_value,
    month_and_year_delta_text,
    month_over_month_change,
    pct_delta_text,
    points_delta_text,
    render_metric_cards,
)
from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

FINANCE_EXPLANATION = """
- **利率**：EIBOR 隔夜/1 年期为日度拆借利率，美国对照为有效联邦基金利率（EFFR）与 SOFR 12 个月期限利率；
  四条序列统一按自然月取算术平均（单位 %）；指标卡显示绝对利率及环比、同比。
- **政府贷款 / 政府控股企业贷款**：CBUAE 月度存量（百万迪拉姆）；指标卡显示绝对量及环比、同比，
  图表按**完整月历**计算同比，缺月补空、不误用间隔超过 12 个月的相邻观测。
- **外资流入**：银行外债、外币存款与「外国主体存款」三指标的月度存量；指标卡显示绝对量及环比、同比。
  外国主体存款 =
  非居民私人企业 + 个人 + 政府及非商业实体三个互斥分项之和。存量同比只能说明境外负债规模扩张，
  归因「流入」需结合环比增量，且不含 FDI。
- **企业及居民信贷**：私人企业信贷、个人信贷与商业及工业部门信贷均为月度存量；指标卡显示绝对量及环比、同比，
  图表使用同一完整月历同比口径。
- **窗口与参考线**：各图取最新完整月往前 36 个月；红色虚线为
  2026 年 3 月美伊战争起始基准线。
""".strip()

BUSINESS_ACTIVITY_EXPLANATION = """
- **DED 企业发证**：迪拜经济局月度快照。「有发证活动企业数」按企业号筛重（家）、「当月新发执照数」
  按执照号筛重（张）；指标卡同时显示环比和同比，图仅展示「当月新发执照数」柱。
- **锚定口径**：图表与指标卡锚定最新**数据完整**月份（避开 DED 快照尾部欠计噪声月），非工作簿最末月；
  同比使用完整月历匹配，不用相邻观测替代缺失月份。
- **采购经理指数（PMI）**：阿联酋非油私营部门采购经理指数（月度_LSEG，点）；50 为荣枯分界，高于 50 表示
  非油私营部门扩张、低于 50 为收缩（图中未画参考线）；指标卡同时显示最新值的环比和同比，
  图表展示最近 37 个月。
- **客户资金转账（FTS）与支票清算**：阿联酋央行公报提供年内累计值；图表先转换为当月值，1 月使用当月累计值，
  其他连续月份使用“本月累计 − 上月累计”，指标卡与图表均使用当月值，并显示环比和同比；
  笔数和金额分别使用左右 Y 轴。中间缺月时不臆算。
- **解读**：采购经理指数（PMI）反映当期非油景气，DED 新发执照反映企业进入动能，两者互补判断企业活动扩张的真实性。
""".strip()

LABOR_EMPLOYMENT_EXPLANATION = """
- **外籍劳动力**：尼泊尔外国就业局「批准（含再入境）」与孟加拉国人力就业培训局「出境许可」人数（月度，人），
  作为外来劳动力到港的代理序列；两者均为官方批准/许可口径、反映离境准备而非实际入境，
  与真实到港存在时间滞后；指标卡同时显示环比和同比。
- **谷歌工作搜索热度**：Google 趋势「在迪拜工作 / 在阿联酋工作」月度搜索指数（0—100 相对强度）；
  指标卡显示原始指数环比；图中曲线先 Savitzky-Golay 平滑（窗口 7、2 阶）再 Z-score 标准化，
  使两条关键词可在同一坐标轴比较相对强弱。
- **解读**：搜索热度通常领先实际到港；两者结合判断外籍劳动力供给动能。红色虚线为
  2026 年 3 月美伊战争起始基准线。
""".strip()


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
def _load_payment_cached(content: bytes, file_name: str) -> PaymentData:
    return load_payment_data(content, file_name=file_name)


@st.cache_data(show_spinner=False)
def _load_search_index_cached(content: bytes, file_name: str) -> pd.DataFrame:
    return load_search_index_data(content, file_name=file_name)


def _format_finance_value(
    value: float | None,
    *,
    unit: str,
) -> str | None:
    """格式化财政金融绝对量；工作簿百万迪拉姆换算为统一数量级。"""

    if unit == "百万迪拉姆":
        return format_currency_value(
            value,
            "迪拉姆",
            input_scale=1_000_000,
        )
    return format_count_value(value, unit)


def _render_finance_metrics(
    st_obj: Any,
    data: GovernmentFinanceData,
    content: bytes,
    file_name: str,
) -> None:
    """财政金融指标卡：覆盖四类图表序列，主值为绝对量并显示环比和同比。"""

    try:
        rates = _load_rates_cached(content, file_name)
        rate_cards = []
        for label, column in (
            ("阿联酋隔夜拆借利率", EIBOR_OVERNIGHT_DISPLAY),
            ("阿联酋1年期拆借利率", EIBOR_ONEYEAR_DISPLAY),
            ("美国隔夜拆借利率", US_OVERNIGHT_DISPLAY),
            ("美国1年期拆借利率", US_SOFR_12M_DISPLAY),
        ):
            series = rates.values[column]
            value, as_of = latest_month_value(series)
            value_text = None if value is None else f"{value:.2f}%"
            rate_cards.append(
                (
                    label,
                    value_text,
                    month_and_year_delta_text(series),
                    _source_note_from_metadata(
                        rates.metadata, column, as_of
                    ),
                )
            )

        cards = rate_cards

        def _amount_cards(
            values: pd.DataFrame,
            metadata: dict[str, Any],
            specs: tuple[tuple[str, str, str, str | None], ...],
        ) -> list[tuple[str, str | None, str | None, str]]:
            cards = []
            for label, column, unit, source_column in specs:
                series = values[column]
                value, as_of = latest_month_value(series)
                source_key = source_column or column
                help_text = _source_note_from_metadata(
                    metadata,
                    source_key,
                    as_of,
                )
                if column == NONRESIDENT_DEPOSITS:
                    help_text += "；由非居民私人企业、个人、政府及非商业实体存款合计"
                cards.append(
                    (
                        label,
                        _format_finance_value(value, unit=unit),
                        month_and_year_delta_text(series),
                        help_text,
                    )
                )
            return cards

        foreign = _load_foreign_inflow_cached(content, file_name)
        cards.extend(
            _amount_cards(
                foreign.values,
                foreign.metadata,
                (
                    ("银行外债", FOREIGN_LIABILITIES_DISPLAY, "百万迪拉姆", None),
                    ("外币存款", FOREIGN_CURRENCIES_DISPLAY, "百万迪拉姆", None),
                    (
                        "外国主体存款",
                        NONRESIDENT_DEPOSITS,
                        "百万迪拉姆",
                        "非居民私人企业存款",
                    ),
                ),
            ),
        )

        cards.extend(
            _amount_cards(
                data.values,
                data.metadata,
                (
                    ("政府贷款", GOVERNMENT_CREDIT, "百万迪拉姆", None),
                    ("政府控股企业贷款", GRE_CREDIT, "百万迪拉姆", None),
                ),
            )
        )

        private = _load_private_credit_cached(content, file_name)
        cards.extend(
            _amount_cards(
                private.values,
                private.metadata,
                (
                    ("私人企业信贷", PRIVATE_CORPORATE_DISPLAY, "百万迪拉姆", None),
                    ("个人信贷", INDIVIDUAL_DISPLAY, "百万迪拉姆", None),
                    ("工商业贷款", BUSINESS_INDUSTRIAL_DISPLAY, "百万迪拉姆", None),
                ),
            )
        )
        for offset in range(0, len(cards), 4):
            render_metric_cards(st_obj, cards[offset : offset + 4], n=4)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.warning(f"财政金融指标未加载：{exc}")


def _render_business_metrics(
    st_obj: Any,
    latest_date: pd.Timestamp,
    content: bytes,
    file_name: str,
) -> None:
    """企业活动指标卡：企业活动三项与支付数据四项，均显示环比和同比。"""

    try:
        cards = []
        pmi = _load_pmi_cached(content, file_name)
        pmi_series = pmi.values[PMI_LABEL]
        pmi_value, pmi_as_of = latest_month_value(pmi_series)
        cards.append(
            (
                PMI_DISPLAY_NAME,
                None if pmi_value is None else f"{pmi_value:.1f}",
                month_and_year_delta_text(pmi_series),
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
                    format_count_value(value, unit),
                    month_and_year_delta_text(ded_series[column]),
                    _source_note_from_metadata(
                        ded.metadata, column, as_of
                    ),
                )
            )
        st_obj.caption("企业活动核心指标")
        render_metric_cards(st_obj, cards, n=3)

        payment = _load_payment_cached(content, file_name)
        payment_values = cumulative_to_monthly(payment.values).loc[
            pd.PeriodIndex(payment.values.index, freq="M") <= last_period
        ]
        payment_cards = []
        for label, column, unit in (
            (CUSTOMER_TRANSFERS_NUMBER_DISPLAY, CUSTOMER_TRANSFERS_NUMBER_DISPLAY, "笔"),
            (CUSTOMER_TRANSFERS_AMOUNT_DISPLAY, CUSTOMER_TRANSFERS_AMOUNT_DISPLAY, "百万迪拉姆"),
            ("支票清算笔数", CHEQUES_NUMBER_DISPLAY, "张"),
            ("支票清算金额", CHEQUES_AMOUNT_DISPLAY, "百万迪拉姆"),
        ):
            series = payment_values[column]
            value, as_of = latest_month_value(series)
            payment_cards.append(
                (
                    label,
                    _format_finance_value(value, unit=unit),
                    month_and_year_delta_text(series),
                    _source_note_from_metadata(
                        payment.metadata, column, as_of
                    ),
                )
            )
        st_obj.caption("支付活动")
        render_metric_cards(st_obj, payment_cards, n=4)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.warning(f"企业活动指标未加载：{exc}")


def _render_labor_metrics(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> None:
    """劳动就业指标卡：劳工人数与工作搜索热度的环比和同比。"""

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
                    format_count_value(value, "人"),
                    month_and_year_delta_text(labor.values[column]),
                    _source_note_from_metadata(
                        labor.metadata, column, as_of
                    ),
                )
            )
        search = _load_search_index_cached(content, file_name)
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
                    month_and_year_delta_text(search[column]),
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
            GRE_CREDIT: "政府控股企业贷款同比（%）",
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
    title = "政府贷款与政府控股企业贷款同比"
    chart_frame = _chart_frame(display_values)
    render_pyplot_figure(
        st_obj,
        build_government_finance_yoy_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        bbox_inches=None,
        place_legend_bottom=False,
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
            units={
                name: data.metadata[name].unit
                for name in RATES_SERIES
            },
        ),
        bbox_inches=None,
        place_legend_bottom=False,
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
        place_legend_bottom=False,
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
        place_legend_bottom=False,
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
    title = "迪拜新发执照数"
    render_pyplot_figure(
        st_obj,
        build_ded_figure(
            data.values,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={LICENCES_DISPLAY: data.metadata[LICENCES_DISPLAY].unit},
        ),
        bbox_inches=None,
        place_legend_bottom=False,
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
            units={
                NEPAL_LABEL: data.metadata[NEPAL_APPROVALS].unit,
                BANGLADESH_LABEL: data.metadata[BANGLADESH_CLEARANCES].unit,
            },
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
        place_legend_bottom=False,
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
    title = PMI_DISPLAY_NAME
    display_values = display_pmi_values(data.values)
    render_pyplot_figure(
        st_obj,
        build_pmi_figure(
            data.values,
            title=title,
            source_text=source_text,
            units={PMI_LABEL: data.metadata[PMI_LABEL].unit},
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.pmi.monthly.download",
    )


def _render_customer_transfers_chart(
    st_obj: Any,
    data: PaymentData,
    latest_date: pd.Timestamp,
) -> None:
    """渲染 FTS 客户转账当月值双轴图及其下载。"""

    last_month = latest_date.to_period("M")
    monthly_values = cumulative_to_monthly(data.values)
    display_values = within_month_window(
        monthly_values[
            [
                CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
                CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
            ]
        ],
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "客户资金转账（FTS）"
    render_pyplot_figure(
        st_obj,
        build_customer_transfers_figure(
            data.values,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={
                CUSTOMER_TRANSFERS_NUMBER_DISPLAY: data.metadata[
                    CUSTOMER_TRANSFERS_NUMBER_DISPLAY
                ].unit,
                CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: data.metadata[
                    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY
                ].unit,
            },
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.government_finance.customer_transfers.download",
    )


def _render_cheques_chart(
    st_obj: Any,
    data: PaymentData,
    latest_date: pd.Timestamp,
) -> None:
    """渲染支票清算当月值双轴图及其下载。"""

    last_month = latest_date.to_period("M")
    monthly_values = cumulative_to_monthly(data.values)
    display_values = within_month_window(
        monthly_values[[CHEQUES_NUMBER_DISPLAY, CHEQUES_AMOUNT_DISPLAY]],
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "、".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "支票清算"
    render_pyplot_figure(
        st_obj,
        build_cheques_figure(
            data.values,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={
                CHEQUES_NUMBER_DISPLAY: data.metadata[
                    CHEQUES_NUMBER_DISPLAY
                ].unit,
                CHEQUES_AMOUNT_DISPLAY: data.metadata[
                    CHEQUES_AMOUNT_DISPLAY
                ].unit,
            },
        ),
        bbox_inches=None,
        place_legend_bottom=False,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.government_finance.cheques.download",
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
        with st_obj.expander("指标算法与解读", expanded=False):
            st_obj.markdown(FINANCE_EXPLANATION)
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
    """企业活动：DED/采购经理指数第一行，客户资金转账/支票清算第二行。"""

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
        with st_obj.spinner("正在读取非油私营部门采购经理指数（PMI）数据..."):
            pmi = _load_pmi_cached(content, file_name)
        _render_pmi_chart(pmi_column, pmi)
    except (KeyError, TypeError, ValueError) as exc:
        pmi_column.warning(f"采购经理指数（PMI）图表未加载：{exc}")

    customer_transfers_column, cheques_column = st_obj.columns(
        2,
        gap="small",
    )
    try:
        with st_obj.spinner("正在读取 CBUAE 客户转账与支票清算数据..."):
            payment = _load_payment_cached(content, file_name)
    except (KeyError, TypeError, ValueError) as exc:
        customer_transfers_column.warning(f"客户转账图未加载：{exc}")
        cheques_column.warning(f"支票清算图未加载：{exc}")
    else:
        try:
            _render_customer_transfers_chart(
                customer_transfers_column,
                payment,
                latest_date,
            )
        except (KeyError, TypeError, ValueError) as exc:
            customer_transfers_column.warning(f"客户转账图未加载：{exc}")
        try:
            _render_cheques_chart(cheques_column, payment, latest_date)
        except (KeyError, TypeError, ValueError) as exc:
            cheques_column.warning(f"支票清算图未加载：{exc}")

    with st_obj.expander("指标算法与解读", expanded=False):
        st_obj.markdown(BUSINESS_ACTIVITY_EXPLANATION)


def _render_quad_finance_charts(
    st_obj: Any,
    data: GovernmentFinanceData,
    latest_date: pd.Timestamp,
    content: bytes,
    file_name: str,
) -> None:
    """财政金融 2×2：利率 / 外资流入 / 政府及国有资本信贷 / 企业及居民信贷。

    左上阿联酋与美国隔夜/1年期利率（月度均值），右上外资流入三指标同比（银行外债/
    外币存款/外国主体存款），左下政府贷款与政府控股企业贷款同比，右下企业及
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
            search_index = _load_search_index_cached(content, file_name)
        _render_search_index_chart(search_column, search_index)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        search_column.warning(f"谷歌搜索热度图表未加载：{exc}")
    try:
        with st_obj.spinner("正在读取外籍劳动力月度数据..."):
            foreign_labor = _load_foreign_labor_cached(content, file_name)
        _render_foreign_labor_chart(labor_column, foreign_labor)
    except (KeyError, TypeError, ValueError) as exc:
        labor_column.warning(f"外籍劳动力图表未加载：{exc}")
    with st_obj.expander("指标算法与解读", expanded=False):
        st_obj.markdown(LABOR_EMPLOYMENT_EXPLANATION)


__all__ = ["render_government_finance_section"]
