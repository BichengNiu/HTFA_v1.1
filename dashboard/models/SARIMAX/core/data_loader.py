"""Prepare the dataset selected by the data overview for model fitting."""

from __future__ import annotations

import pandas as pd

from data_overview.core.dataset import OverviewDataset


def prepare_modeling_inputs(
    dataset: OverviewDataset,
    target: str,
    exog_columns: tuple[str, ...] = (),
    time_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> tuple[pd.Series, pd.DataFrame | None, pd.Index]:
    """Build the target series and exogenous frame from the overview dataset.

    Parameters
    ----------
    dataset : OverviewDataset
        Dataset already parsed and cleaned by the data overview page.
    target : str
        Target variable column name.
    exog_columns : tuple[str, ...], default=()
        Exogenous variable column names.
    time_range : tuple[pd.Timestamp, pd.Timestamp] or None, default=None
        Inclusive training range for dated data; ``None`` uses all observations.

    Returns
    -------
    tuple[pd.Series, pd.DataFrame | None, pd.Index]
        Target series, optional exogenous frame, and the aligned modeling index.

    Raises
    ------
    ValueError
        If the target/exogenous variables or the requested time range is invalid.
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
        if time_range is not None:
            raise ValueError("数据没有日期列，无法选择训练时间范围")
        index = pd.RangeIndex(len(base))

    # Ts 的时间序列模型要求日期严格按递增顺序排列；对整张宽表排序，
    # 确保目标序列与外生变量按同一批日期同步重排。
    base = base.set_index(index).sort_index()
    index = base.index

    if time_range is not None:
        if len(time_range) != 2:
            raise ValueError("训练时间范围必须同时包含起始日期和结束日期")
        start, end = (pd.Timestamp(value) for value in time_range)
        if pd.isna(start) or pd.isna(end):
            raise ValueError("训练时间范围包含无效日期")
        if start > end:
            raise ValueError("起始日期不能晚于结束日期")
        base = base.loc[(base.index >= start) & (base.index <= end)]
        index = base.index

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


__all__ = ["prepare_modeling_inputs"]
