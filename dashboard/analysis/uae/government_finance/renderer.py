"""Streamlit section for government and government-related entity banking data."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.analysis.uae.downloads import render_chart_download
from dashboard.analysis.uae.foreign_labor import (
    ForeignLaborData,
    build_foreign_labor_figure,
    common_observations,
    latest_common_month as latest_foreign_labor_month,
    load_foreign_labor_data,
)
from dashboard.analysis.uae.government_finance.charts import (
    build_government_finance_yoy_figure,
)
from dashboard.analysis.uae.government_finance.data import (
    GovernmentFinanceData,
    calculate_calendar_yoy,
    combine_government_and_state_capital,
    latest_complete_month,
    load_government_finance_data,
)
from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.core.ui.utils.chart_legend import place_chart_legend_at_bottom


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


def _chart_frame(values: pd.DataFrame) -> pd.DataFrame:
    """Return only the monthly year-on-year series supplied to the chart."""

    return calculate_calendar_yoy(
        combine_government_and_state_capital(values)
    ).rename(columns=lambda name: f"{name}同比（%）")


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
    title = "政府及国有资本存款与信贷同比"
    chart_frame = _chart_frame(display_values)
    st_obj.pyplot(
        place_chart_legend_at_bottom(
            build_government_finance_yoy_figure(
                data.values,
                title=title,
                source_text=source_text,
            )
        ),
        width="stretch",
        clear_figure=True,
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        chart_frame,
        title=title,
        key="analysis.uae.government_finance.yoy.download",
    )


def _render_foreign_labor_chart(
    st_obj: Any,
    data: ForeignLaborData,
) -> None:
    last_month = latest_foreign_labor_month(data.values)
    latest_date = last_month.to_timestamp(
        how="end"
    ).normalize()
    display_values = within_month_window(
        common_observations(data.values),
        first_month=last_month - 36,
        last_month=last_month,
    )
    source_text = "；".join(
        dict.fromkeys(metadata.source for metadata in data.metadata.values())
    )
    title = "尼泊尔和孟加拉国入境阿联酋劳工人数"
    st_obj.pyplot(
        place_chart_legend_at_bottom(
            build_foreign_labor_figure(
                display_values,
                title=title,
                source_text=source_text,
            )
        ),
        width="stretch",
        clear_figure=True,
        bbox_inches=None,
    )
    render_chart_download(
        st_obj,
        display_values,
        title=title,
        key="analysis.uae.foreign_labor.monthly.download",
    )


def render_government_finance_section(
    st_obj: Any,
    content: bytes,
    file_name: str,
) -> dict[str, Any]:
    """Render the CBUAE monthly year-on-year comparison."""

    st_obj.divider()
    st_obj.subheader("基础设施建设")
    try:
        with st_obj.spinner("正在读取 CBUAE 月度存款与信贷数据..."):
            data = _load_government_finance_cached(content, file_name)
        latest_date = latest_complete_month(data.values)
        try:
            with st_obj.spinner("正在读取外籍劳动力月度数据..."):
                foreign_labor = _load_foreign_labor_cached(content, file_name)
        except (KeyError, TypeError, ValueError) as exc:
            st_obj.warning(f"外籍劳动力图表未加载：{exc}")
            _render_charts(st_obj, data, latest_date)
        else:
            government_column, labor_column = st_obj.columns(2, gap="small")
            _render_charts(government_column, data, latest_date)
            _render_foreign_labor_chart(labor_column, foreign_labor)
    except (KeyError, TypeError, ValueError) as exc:
        st_obj.error(f"政府及国有资本存款与信贷数据加载失败：{exc}")
        return {"status": "error", "message": str(exc)}
    return {
        "status": "success",
        "source": file_name,
        "as_of": latest_date.strftime("%Y-%m"),
    }


__all__ = ["render_government_finance_section"]
