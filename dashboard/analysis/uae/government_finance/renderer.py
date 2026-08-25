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
    format_count_value,
    format_currency_value,
    latest_month_value,
    month_and_year_delta_text,
    render_metric_cards,
    source_text_from_metadata,
)
from dashboard.analysis.uae.periods import within_month_window
from dashboard.core.ui.utils.chart_legend import render_pyplot_figure

FINANCE_EXPLANATION = """
- **利率**：由阿联酋央行发布，美国利率依据“根据新闻整理”；原始数据为日度/周度阿联酋 EIBOR、美国 EFFR 和 SOFR 12 个月利率，按自然月取算术平均形成月度利率序列，
  反映银行间融资成本及美国利率基准。
- **政府贷款与政府控股企业贷款**：由阿联酋央行发布；原始数据为月度存量（百万迪拉姆），
  反映政府及政府控股企业的银行信贷余额。
- **银行外债、外币存款**：由阿联酋央行发布；原始数据为月度存量，分别反映银行境外负债和外币资金存款规模。
- **外国主体存款**：由阿联酋央行发布；原始数据为月度非居民私人企业、个人、政府及非商业实体存款，三项相加后反映非居民在阿联酋银行体系的存款规模，
  属存量指标，不等同于 FDI 或当期资金流入。
- **企业及居民信贷**：由阿联酋央行发布；原始数据为私人企业、个人及商业工业部门月度信贷存量，
  反映国内企业和居民融资规模。
- **同比**：原始数据为各指标月度观测；按完整自然月与上年同月比较，缺失月份留空，不用相邻观测替代。
""".strip()

BUSINESS_ACTIVITY_EXPLANATION = """
- **DED 企业发证**：由 data.dubai 商业登记库发布；原始数据为月度快照，有发证活动企业数按企业号去重、当月新发执照数按执照号去重，
  分别反映企业发证活跃度和新执照进入活动。
- **非油私营部门采购经理指数（PMI）**：由标普全球/全球经济数据平台发布；原始数据为月度景气指数（点）；50 为荣枯线，高于50表示非油私营部门扩张，
  低于50表示收缩。
- **客户资金转账与支票清算**：由阿联酋央行发布；原始数据为月度累计笔数和金额；当月值为1月累计值，
  其余月份为本月累计减上月累计，反映银行支付交易数量和金额；缺月不作差分。
""".strip()

LABOR_EMPLOYMENT_EXPLANATION = """
- **外籍劳动力**：由尼泊尔外国就业局、孟加拉国人力就业培训局发布；原始数据为月度批准（含再入境）和出境许可人数，
  反映劳工离境准备，是外籍劳动力到港的代理，通常存在时间滞后。
- **谷歌工作搜索热度**：由谷歌趋势发布；原始数据为月度“在迪拜工作”和“在阿联酋工作”相对指数（0—100），
  先用 Savitzky-Golay（窗口7、二阶）平滑，再做 Z-score 标准化；用于比较两类关键词的相对求职关注度，
  不代表绝对搜索量。
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


def _render_figure_with_download(
    st_obj: Any,
    figure: Any,
    values: pd.DataFrame,
    *,
    title: str,
    download_key: str,
    place_legend_bottom: bool = False,
) -> None:
    """统一渲染政府金融图表并提供其下载数据。"""

    render_pyplot_figure(
        st_obj,
        figure,
        bbox_inches=None,
        place_legend_bottom=place_legend_bottom,
    )
    render_chart_download(
        st_obj,
        values,
        title=title,
        key=download_key,
    )


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
    source_text = source_text_from_metadata(data.metadata)
    title = "政府贷款与政府控股企业贷款同比"
    chart_frame = _chart_frame(display_values)
    _render_figure_with_download(
        st_obj,
        build_government_finance_yoy_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        chart_frame,
        title=title,
        download_key="analysis.uae.government_finance.yoy.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "阿联酋与美国市场利率（隔夜、1年期）"
    _render_figure_with_download(
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
        display_values,
        title=title,
        download_key="analysis.uae.government_finance.rates.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "外资流入同比：银行外债、外币存款与外国主体存款"
    figure = build_foreign_inflow_figure(
        data.values,
        title=title,
        source_text=source_text,
    )
    chart_frame = calculate_calendar_yoy(display_values).rename(
        columns=lambda name: f"{name}同比（%）"
    )
    _render_figure_with_download(
        st_obj,
        figure,
        chart_frame.dropna(how="all"),
        title=title,
        download_key="analysis.uae.government_finance.foreign_inflow.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "企业及居民信贷同比"
    chart_frame = calculate_calendar_yoy(display_values).rename(
        columns=lambda name: f"{name}同比（%）"
    )
    _render_figure_with_download(
        st_obj,
        build_private_credit_yoy_figure(
            data.values,
            title=title,
            source_text=source_text,
        ),
        chart_frame,
        title=title,
        download_key="analysis.uae.government_finance.private_credit.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "迪拜新发执照数"
    _render_figure_with_download(
        st_obj,
        build_ded_figure(
            data.values,
            title=title,
            source_text=source_text,
            last_month=last_month,
            units={LICENCES_DISPLAY: data.metadata[LICENCES_DISPLAY].unit},
        ),
        display_values,
        title=title,
        download_key="analysis.uae.government_finance.ded.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata, separator="；")
    title = "尼泊尔和孟加拉国入境阿联酋劳工人数"
    _render_figure_with_download(
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
        display_values,
        title=title,
        download_key="analysis.uae.foreign_labor.monthly.download",
        place_legend_bottom=True,
    )


def _render_search_index_chart(
    st_obj: Any,
    values: pd.DataFrame,
) -> None:
    title = "阿联酋工作谷歌搜索热度"
    display_values = display_search_index_values(values)
    _render_figure_with_download(
        st_obj,
        build_search_index_figure(
            values,
            title=title,
            source_text=SEARCH_SOURCE_TEXT,
        ),
        display_values,
        title=title,
        download_key="analysis.uae.search_index.monthly.download",
        place_legend_bottom=False,
    )


def _render_pmi_chart(
    st_obj: Any,
    data: PmiData,
) -> None:
    source_text = source_text_from_metadata(data.metadata, separator="；")
    title = PMI_DISPLAY_NAME
    display_values = display_pmi_values(data.values)
    _render_figure_with_download(
        st_obj,
        build_pmi_figure(
            data.values,
            title=title,
            source_text=source_text,
            units={PMI_LABEL: data.metadata[PMI_LABEL].unit},
        ),
        display_values,
        title=title,
        download_key="analysis.uae.pmi.monthly.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "客户资金转账（FTS）"
    _render_figure_with_download(
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
        display_values,
        title=title,
        download_key="analysis.uae.government_finance.customer_transfers.download",
        place_legend_bottom=False,
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
    source_text = source_text_from_metadata(data.metadata)
    title = "支票清算"
    _render_figure_with_download(
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
        display_values,
        title=title,
        download_key="analysis.uae.government_finance.cheques.download",
        place_legend_bottom=False,
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
        # 设定稳定的容器 key，供打印媒体查询只压缩财政金融的图表，
        # 不改变企业活动、劳动就业和网页端的图表尺寸。
        with st_obj.container(key="uae-finance-part"):
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
