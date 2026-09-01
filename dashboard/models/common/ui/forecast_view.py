"""通用预测结果表格和图形展示模块。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from dashboard.models.common.contracts import ForecastResult


def build_forecast_table(
    result: ForecastResult,
    actual_values: np.ndarray | None = None,
) -> pd.DataFrame:
    """把稳定预测结果转换为表格，保留原始日期或期数索引。"""
    if result.dates is not None:
        index = pd.DatetimeIndex(result.dates)
        index.name = "日期"
    else:
        start = int(result.start) if isinstance(result.start, (int, np.integer)) else 0
        index = pd.RangeIndex(
            start + 1,
            start + result.steps + 1,
            name="期数",
        )
    table = pd.DataFrame(
        {
            "预测值": result.mean,
            "下界": result.lower,
            "上界": result.upper,
        },
        index=index,
    )
    if actual_values is not None:
        actual = np.asarray(actual_values, dtype=float)
        if actual.ndim != 1 or len(actual) != result.steps:
            raise ValueError("真实值数组必须与预测结果长度一致")
        table.insert(0, "真实值", actual)
    return table


def render_forecast_result(
    st_obj,
    result: ForecastResult,
    *,
    actual_values: np.ndarray | None = None,
    target: str | None = None,
    caption: str | None = None,
    download_name: str = "预测结果.csv",
    chart_renderer: Callable[..., None] | None = None,
    show_confidence_interval: bool = False,
    download_key: str = "forecast_download",
) -> pd.DataFrame:
    """展示预测表和可选模型专属图形，并返回下载用原始表格。"""
    table = build_forecast_table(result, actual_values=actual_values)
    download_table = table.rename(
        columns={"下界": "预测下界", "上界": "预测上界"}
    ).sort_index(ascending=False)
    display = download_table.reset_index()
    if "日期" in display.columns:
        display["日期"] = display["日期"].dt.strftime("%Y-%m-%d")
    if caption:
        st_obj.caption(caption)
    st_obj.dataframe(display, width="stretch")
    st_obj.download_button(
        "下载结果",
        data=download_table.to_csv(encoding="utf-8-sig").encode("utf-8-sig"),
        file_name=download_name,
        mime="text/csv",
        key=download_key,
        type="primary",
    )
    if chart_renderer is not None:
        chart_renderer(
            st_obj,
            result,
            target=target,
            show_confidence_interval=show_confidence_interval,
        )
    return download_table


__all__ = ["build_forecast_table", "render_forecast_result"]
