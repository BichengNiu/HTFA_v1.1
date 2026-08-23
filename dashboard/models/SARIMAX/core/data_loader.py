"""SARIMAX 建模数据加载与准备（纯 pandas，不依赖 streamlit 渲染）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dashboard.core.ui.utils.shared_dataset import (
    fingerprint_file,
    load_shared_dataframe,
)


@dataclass(frozen=True)
class ModelingDataset:
    """一次解析后供 SARIMAX 建模共享的数据集。

    Attributes
    ----------
    fingerprint:
        文件内容指纹，用于结果缓存失效。
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


def _replace_zero_values_with_missing(frame: pd.DataFrame) -> pd.DataFrame:
    """将 SARIMAX 数据中的数值 0 和空白字符串视为缺失值。"""
    result = frame.replace(r"^\s*$", pd.NA, regex=True).copy()
    for column in result.columns:
        series = result[column]
        if (
            pd.api.types.is_datetime64_any_dtype(series)
            or pd.api.types.is_bool_dtype(series)
            or not pd.api.types.is_numeric_dtype(series)
        ):
            continue
        result[column] = series.mask(series.eq(0))
    return result.dropna(how="all").dropna(axis=1, how="all")


def build_modeling_dataset(
    frame: pd.DataFrame,
    file_name: str,
    fingerprint: str,
) -> ModelingDataset:
    """从已解析的数据框构造建模数据集（共享数据集路径）。

    Raises
    ------
    ValueError
        数据框为空或没有数值型变量时抛出，消息面向用户。
    """
    frame = _replace_zero_values_with_missing(frame)
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("文件清理后为空，没有可分析的列")
    if not numeric_variable_names(frame):
        raise ValueError("数据中没有数值型变量，无法进行 SARIMAX 建模")
    return ModelingDataset(
        fingerprint=fingerprint,
        file_name=file_name,
        frame=frame,
        time_column=_detect_time_column(frame),
    )


def load_modeling_dataset(uploaded_file: Any) -> ModelingDataset:
    """解析上传文件并返回建模数据集。

    Raises
    ------
    ValueError
        文件为空、无法解码或没有数值型变量时抛出，消息面向用户。
    """
    fingerprint = fingerprint_file(uploaded_file)
    file_name = str(getattr(uploaded_file, "name", "data"))
    frame = load_shared_dataframe(uploaded_file)
    return build_modeling_dataset(frame, file_name, fingerprint)


def prepare_modeling_inputs(
    dataset: ModelingDataset,
    target: str,
    exog_columns: tuple[str, ...] = (),
) -> tuple[pd.Series, pd.DataFrame | None, pd.Index]:
    """构建目标序列与外生变量框，两者共享同一索引。

    Returns
    -------
    tuple[pd.Series, pd.DataFrame | None, pd.Index]
        (目标序列, 外生变量框或 None, 建模索引)。日期列存在时索引为
        DatetimeIndex，否则为 RangeIndex。
    """
    frame = dataset.frame
    base = frame.copy()
    time_column = dataset.time_column
    if time_column is not None:
        index = pd.DatetimeIndex(pd.to_datetime(base[time_column], errors="coerce"))
        if index.has_duplicates:
            raise ValueError("日期列存在重复值，请先去除重复日期后再建模")
        if index.isna().any():
            raise ValueError("日期列存在无法解析的缺失值，请清理数据后再建模")
        base = base.drop(columns=[time_column])
    else:
        index = pd.RangeIndex(len(base))
    base = base.set_index(index)

    if target not in base.columns:
        raise ValueError(f"目标变量 '{target}' 不在数据表中")
    target_series = pd.to_numeric(base[target], errors="coerce").astype(float)

    if exog_columns:
        unknown = [name for name in exog_columns if name not in base.columns]
        if unknown:
            raise ValueError(f"外生变量不存在：{', '.join(unknown)}")
        if target in exog_columns:
            raise ValueError("目标变量不能同时作为外生变量")
        exog_frame = base.loc[:, list(exog_columns)].astype(float)
    else:
        exog_frame = None

    return target_series, exog_frame, index


__all__ = [
    "ModelingDataset",
    "build_modeling_dataset",
    "load_modeling_dataset",
    "numeric_variable_names",
    "prepare_modeling_inputs",
]
