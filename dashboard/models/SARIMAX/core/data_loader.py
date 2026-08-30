"""Prepare the dataset selected by the data overview for model fitting."""

from __future__ import annotations

import pandas as pd

from data_overview.core.dataset import OverviewDataset

PREPROCESSING_OPTIONS = ("去零", "去负")


def dataset_time_index(dataset: OverviewDataset) -> pd.DatetimeIndex | None:
    """返回当前数据集的完整、递增日期索引。

    Parameters
    ----------
    dataset : OverviewDataset
        数据概览解析后的数据集。

    Returns
    -------
    pandas.DatetimeIndex or None
        数据集时间列排序后的完整日期索引；没有时间列时返回 ``None``。

    Raises
    ------
    ValueError
        时间列包含重复日期或无法解析的缺失日期。
    """
    if dataset.time_column is None:
        return None
    index = pd.DatetimeIndex(
        pd.to_datetime(dataset.frame[dataset.time_column], errors="coerce")
    )
    if index.has_duplicates:
        raise ValueError("日期列存在重复值，请先去除重复日期后再建模")
    if index.isna().any():
        raise ValueError("日期列存在无法解析的缺失值，请清理数据后再建模")
    return index.sort_values()


def forecast_sample_dates(
    dataset: OverviewDataset,
    training_end: pd.Timestamp,
) -> pd.DatetimeIndex | None:
    """返回训练结束日之后仍位于当前数据集内的预测样本日期。

    Parameters
    ----------
    dataset : OverviewDataset
        数据概览解析后的数据集。
    training_end : pandas.Timestamp
        训练样本结束日期，结束日属于训练样本。

    Returns
    -------
    pandas.DatetimeIndex or None
        严格晚于训练结束日的当前数据集日期；没有时间列时返回 ``None``。

    Raises
    ------
    ValueError
        ``training_end`` 不是有效日期。
    """
    dates = dataset_time_index(dataset)
    if dates is None:
        return None
    end = pd.Timestamp(training_end)
    if pd.isna(end):
        raise ValueError("训练样本结束日期无效")
    return dates[dates > end]


def prepare_modeling_inputs(
    dataset: OverviewDataset,
    target: str,
    exog_columns: tuple[str, ...] = (),
    time_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    preprocessing: tuple[str, ...] = (),
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
    preprocessing : tuple[str, ...], default=()
        Selected preprocessing rules. ``"去零"`` treats zero values as missing;
        ``"去负"`` treats negative values as missing. Rules apply to the target
        and selected exogenous variables after the training range is applied.

    Returns
    -------
    tuple[pd.Series, pd.DataFrame | None, pd.Index]
        Target series, optional exogenous frame, and the aligned modeling index.

    Raises
    ------
    ValueError
        If the target/exogenous variables, preprocessing options, or requested
        time range is invalid.
    """
    selected_preprocessing = tuple(dict.fromkeys(preprocessing or ()))
    unknown_preprocessing = [
        option
        for option in selected_preprocessing
        if option not in PREPROCESSING_OPTIONS
    ]
    if unknown_preprocessing:
        raise ValueError(
            "不支持的数据预处理："
            + ", ".join(str(option) for option in unknown_preprocessing)
        )

    frame = dataset.frame
    base = frame.copy()
    time_column = dataset.time_column
    if time_column is not None:
        index = pd.DatetimeIndex(
            pd.to_datetime(base[time_column], errors="coerce")
        )
        # 先用原始行顺序绑定日期，再整体排序，确保目标和外生变量不发生错位。
        dataset_time_index(dataset)
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

    if "去零" in selected_preprocessing:
        target_series = target_series.mask(target_series == 0.0)
        if exog_frame is not None:
            exog_frame = exog_frame.mask(exog_frame == 0.0)
    if "去负" in selected_preprocessing:
        target_series = target_series.mask(target_series < 0.0)
        if exog_frame is not None:
            exog_frame = exog_frame.mask(exog_frame < 0.0)

    return target_series, exog_frame, index


def effective_modeling_date_bounds(
    dataset: OverviewDataset,
    target: str,
    exog_columns: tuple[str, ...] = (),
    preprocessing: tuple[str, ...] = (),
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """返回预处理后参与建模变量的共同有效日期首尾边界。

    Parameters
    ----------
    dataset : OverviewDataset
        数据概览解析后的数据集。
    target : str
        目标变量列名。
    exog_columns : tuple[str, ...], default=()
        外生变量列名；所有外生变量也必须在该日期有有效值。
    preprocessing : tuple[str, ...], default=()
        应用于目标变量和外生变量的预处理规则。

    Returns
    -------
    tuple[pandas.Timestamp, pandas.Timestamp] or None
        第一个和最后一个共同有效日期；无日期列或没有共同有效值时返回
        ``None``。
    """
    if dataset.time_column is None:
        return None

    series, exog_frame, index = prepare_modeling_inputs(
        dataset,
        target,
        exog_columns,
        preprocessing=preprocessing,
    )
    valid = series.notna().to_numpy(copy=True)
    if exog_frame is not None:
        valid &= exog_frame.notna().all(axis=1).to_numpy()
    valid_dates = pd.DatetimeIndex(index[valid])
    if len(valid_dates) == 0:
        return None
    return pd.Timestamp(valid_dates[0]), pd.Timestamp(valid_dates[-1])


__all__ = [
    "PREPROCESSING_OPTIONS",
    "dataset_time_index",
    "effective_modeling_date_bounds",
    "forecast_sample_dates",
    "prepare_modeling_inputs",
]
