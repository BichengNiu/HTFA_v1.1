from __future__ import annotations
import re
import pandas as pd


def chart_data_csv(frame: pd.DataFrame | pd.Series) -> bytes:
    """将图表底层数据导出为适合 Excel 打开的 UTF-8 CSV。"""
    data = frame.to_frame() if isinstance(frame, pd.Series) else frame.copy()
    if isinstance(data.index, pd.MultiIndex):
        data.index = data.index.set_names(
            [
                name or f"索引{position}"
                for position, name in enumerate(data.index.names, 1)
            ]
        )
    elif data.index.name is None:
        data.index.name = "日期"
    return data.to_csv(index=True).encode("utf-8-sig")


def safe_download_name(title: str) -> str:
    """生成 Windows 和浏览器均可接受的 CSV 文件名。"""
    stem = re.sub('[\\\\/:*?"<>|\\s]+', "_", title).strip("_.")
    return f"{stem or '图表数据'}.csv"
