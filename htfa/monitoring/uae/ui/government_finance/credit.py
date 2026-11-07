from __future__ import annotations
from collections.abc import Mapping
import pandas as pd
from matplotlib.figure import Figure
from htfa.monitoring.uae.processing.government_finance.data import display_calendar_yoy
from htfa.monitoring.uae.contracts.government_finance.credit import (
    FOREIGN_LIABILITIES_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import (
    FOREIGN_CURRENCIES_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import NONRESIDENT_DEPOSITS
from htfa.monitoring.uae.contracts.government_finance.credit import (
    PRIVATE_CORPORATE_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import INDIVIDUAL_DISPLAY
from htfa.monitoring.uae.contracts.government_finance.credit import (
    BUSINESS_INDUSTRIAL_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.credit import FOREIGN_SERIES
from htfa.monitoring.uae.contracts.government_finance.credit import (
    PRIVATE_CREDIT_SERIES,
)
from collections.abc import Mapping
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from htfa.monitoring.uae.ui.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
)
from htfa.monitoring.uae.processing.sources import source_note


def build_foreign_inflow_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制银行外债、外币存款与外国主体存款同比，先算同比再取最近三年。"""
    inflow_columns = [
        FOREIGN_LIABILITIES_DISPLAY,
        FOREIGN_CURRENCIES_DISPLAY,
        NONRESIDENT_DEPOSITS,
    ]
    frame = display_calendar_yoy(values[inflow_columns]).add_suffix("同比")
    if frame.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {name: "%" for name in FOREIGN_SERIES}
    if units is not None:
        axis_units.update(units)
    return _common_line_setup(
        frame, title=title, source_text=source_text, units=axis_units
    )


def build_private_credit_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制私人企业、个人及工商业贷款同比，先算同比再取最近三年。"""
    credit_columns = [
        PRIVATE_CORPORATE_DISPLAY,
        INDIVIDUAL_DISPLAY,
        BUSINESS_INDUSTRIAL_DISPLAY,
    ]
    frame = display_calendar_yoy(values[credit_columns]).add_suffix("同比")
    if frame.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {name: "%" for name in PRIVATE_CREDIT_SERIES}
    if units is not None:
        axis_units.update(units)
    return _common_line_setup(
        frame, title=title, source_text=source_text, units=axis_units
    )


def _common_line_setup(
    frame: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None,
) -> Figure:
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units=units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
