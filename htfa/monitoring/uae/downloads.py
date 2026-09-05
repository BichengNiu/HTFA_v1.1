"""阿联酋监测图表的数据下载组件。"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def chart_data_csv(frame: pd.DataFrame | pd.Series) -> bytes:
    """将图表底层数据导出为适合 Excel 打开的 UTF-8 CSV。"""

    data = frame.to_frame() if isinstance(frame, pd.Series) else frame.copy()
    if isinstance(data.index, pd.MultiIndex):
        data.index = data.index.set_names(
            [name or f"索引{position}" for position, name in enumerate(data.index.names, 1)]
        )
    elif data.index.name is None:
        data.index.name = "日期"
    return data.to_csv(index=True).encode("utf-8-sig")


def safe_download_name(title: str) -> str:
    """生成 Windows 和浏览器均可接受的 CSV 文件名。"""

    stem = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("_.")
    return f"{stem or '图表数据'}.csv"


def render_chart_download(
    st_obj: Any,
    frame: pd.DataFrame | pd.Series,
    *,
    title: str,
    key: str,
) -> None:
    """在图表正下方左侧渲染数据下载按钮。"""

    st_obj.download_button(
        "下载数据",
        data=chart_data_csv(frame),
        file_name=safe_download_name(title),
        mime="text/csv",
        key=key,
        type="primary",
    )


__all__ = ["chart_data_csv", "render_chart_download", "safe_download_name"]
