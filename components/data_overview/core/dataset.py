"""数据概览的数据契约：数据集对象与默认构建器（纯 pandas，无 streamlit）。

外部项目可提供自己的 dataset_builder 返回任意满足该契约的对象
（需要 frame / time_column / fingerprint 三个属性）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OverviewDataset:
    """一次解析后供数据概览共享的数据集。

    Attributes
    ----------
    fingerprint:
        文件内容指纹，用于缓存失效。
    file_name:
        上传文件名。
    frame:
        清理后的宽表数据框（第一列可能为日期列）。
    time_column:
        被解析为日期类型的首列列名；无日期列时为 None。
    """

    fingerprint: str
    file_name: str
    frame: pd.DataFrame
    time_column: str | None


def _detect_time_column(frame: pd.DataFrame) -> str | None:
    """返回首列中被解析为日期类型的列名，否则 None。"""
    if frame.shape[1] == 0:
        return None
    first = frame.columns[0]
    if pd.api.types.is_datetime64_any_dtype(frame[first]):
        return str(first)
    return None


def numeric_variable_names(frame: pd.DataFrame) -> list[str]:
    """返回可用于建模的数值型列名（排除日期与布尔列）。"""
    names = []
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            continue
        if pd.api.types.is_bool_dtype(series):
            continue
        if pd.api.types.is_numeric_dtype(series):
            names.append(str(column))
    return names


def build_overview_dataset(
    frame: pd.DataFrame,
    file_name: str,
    fingerprint: str,
) -> OverviewDataset:
    """从已解析的数据框构造数据概览数据集。

    Raises
    ------
    ValueError
        数据框为空或没有数值型变量时抛出，消息面向用户。
    """
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("文件清理后为空，没有可分析的列")
    if not numeric_variable_names(frame):
        raise ValueError("数据中没有数值型变量，无法进行分析")
    return OverviewDataset(
        fingerprint=fingerprint,
        file_name=file_name,
        frame=frame,
        time_column=_detect_time_column(frame),
    )


__all__ = [
    "OverviewDataset",
    "build_overview_dataset",
    "numeric_variable_names",
]
