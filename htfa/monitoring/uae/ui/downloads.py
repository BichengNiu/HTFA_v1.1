from __future__ import annotations
from typing import Any
import pandas as pd
from htfa.monitoring.uae.processing.downloads import chart_data_csv
from htfa.monitoring.uae.processing.downloads import safe_download_name


def render_chart_download(
    st_obj: Any, frame: pd.DataFrame | pd.Series, *, title: str, key: str
) -> None:
    """在图表正下方左侧渲染数据下载按钮。"""
    st_obj.download_button(
        "下载数据",
        data=chart_data_csv(frame),
        file_name=safe_download_name(title),
        mime="text/csv",
        key=key,
        type="primary",
        on_click="ignore",
    )
