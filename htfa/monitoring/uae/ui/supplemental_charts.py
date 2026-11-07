from __future__ import annotations
import pandas as pd
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
from htfa.monitoring.uae.contracts.supplemental_data import ChartSpec


def build_supplemental_figure(
    values: pd.DataFrame, *, spec: ChartSpec, units: dict[str, str], source_text: str
) -> Figure:
    """绘制已按独立数据截止期截取的序列，显式指定同轴或双轴分组。"""
    frame = values[list(units)]
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=spec.title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        axis_groups={name: "right" if name in spec.right else "left" for name in frame},
        units=units,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
    )
    annotate_war(normalize_ts_axis(returned_axis))
    apply_htfa_fonts(figure)
    return figure
