"""Macro charts use the same Ts renderer and retain independently released quarters."""

import inspect

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from htfa.monitoring.uae import charts


def test_macro_ts_chart_has_no_x_title_and_keeps_real_growth_in_q2(monkeypatch):
    frame = pd.DataFrame({
        "【真实】实际GDP当季同比": [3.0, 4.0, 5.0],
        "【真实】GDP平减指数同比": [1.0, 2.0, np.nan],
    }, index=pd.to_datetime(["2025-12-31", "2026-03-31", "2026-06-30"]))
    captured = {}
    from Ts.TsPlots import plot_series

    def capture(data, **kwargs):
        inspect.signature(plot_series).bind(data, **kwargs)
        captured.update(kwargs)
        return plot_series(data, **kwargs)

    monkeypatch.setattr(charts, "plot_series", capture, raising=False)
    figure = charts.build_price_volume_figure(frame, title="GDP同比")
    assert isinstance(figure, Figure)
    axis = figure.axes[0]
    assert all(axis.get_xlabel() == "" for axis in figure.axes)
    lines = {line.get_label(): line for line in axis.lines}
    assert lines["【真实】实际GDP当季同比"].get_ydata()[-1] == 5.0
    assert np.isnan(lines["【真实】GDP平减指数同比"].get_ydata()[-1])
    assert pd.Timestamp(lines["【真实】实际GDP当季同比"].get_xdata()[-1]) == pd.Timestamp("2026-06-30")
    assert captured["xtitle"] == ""
    assert captured["facet"] is False
    assert captured["year_ruler"] is True
    assert all(
        label.get_text().endswith("月")
        for label in axis.get_xticklabels() if label.get_text()
    )
    assert any(text.get_text().strip() == "2026年" for text in axis.texts)
    assert "hlines" not in captured
    assert captured["legend_labels"] == ["实际GDP当季同比", "GDP平减指数同比"]
    assert [text.get_text() for text in axis.get_legend().get_texts()] == captured["legend_labels"]
    assert captured["figsize"] == (9.4, 6.2)
    assert captured["units"] == {name: "%" for name in frame}
    plt.close(figure)
