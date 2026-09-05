"""Prepare the dataset selected by the data overview for model fitting."""

from __future__ import annotations

import pandas as pd

from components.data_overview.core.dataset import OverviewDataset, numeric_variable_names
from Ts.TsUtils import interpolate_missing

DATA_REPLACEMENT_OPTIONS = ("去零", "去负")
PREPROCESSING_OPTIONS = DATA_REPLACEMENT_OPTIONS
MISSING_VALUE_OPTIONS = (
    "无",
    "向前填补",
    "向后填补",
    "线性内插",
    "样条内插",
    "多项式内插",
    "卡尔曼滤波",
)
_MISSING_VALUE_METHOD_MAP = {
    "向前填补": "ffill",
    "向后填补": "bfill",
    "线性内插": "linear",
    "样条内插": "spline",
    "多项式内插": "polynomial",
    "卡尔曼滤波": "kalman",
}


def _apply_missing_value_method(
    series: pd.Series,
    method: str,
) -> pd.Series:
    """仅在单个序列首末有效值之间调用 TsUtils 处理缺失值。"""
    if method == "无":
        return series.copy()
    try:
        ts_method = _MISSING_VALUE_METHOD_MAP[method]
    except KeyError as exc:
        raise ValueError(f"不支持的缺失值处理：{method}") from exc

    valid_positions = series.notna().to_numpy().nonzero()[0]
    if valid_positions.size < 2:
        return series.copy()
    first = int(valid_positions[0])
    last = int(valid_positions[-1])
    window = series.iloc[first : last + 1]
    if not window.isna().any():
        return series.copy()

    # 先按每列识别有效区间，再处理区间内部，避免 ffill/bfill/kalman
    # 等方法把首个有效值之前或末个有效值之后的缺失值带入结果。
    filled_window = interpolate_missing(
        window,
        method=ts_method,
        edge="keep",
    ).data
    result = series.copy(deep=True)
    result.iloc[first : last + 1] = pd.Series(
        filled_window,
        index=window.index,
        name=series.name,
    ).to_numpy()
    return result


def _apply_missing_value_method_to_frame(
    frame: pd.DataFrame,
    method: str,
) -> pd.DataFrame:
    """逐列处理首末有效值之间的缺失，保持列名和索引不变。"""
    if method == "无":
        return frame.copy()
    # 每个变量的有效区间可能不同，不能以整张宽表的共同边界替代单列边界。
    return pd.DataFrame(
        {
            column: _apply_missing_value_method(frame[column], method)
            for column in frame.columns
        },
        index=frame.index,
    )


def preprocess_modeling_frame(
    frame: pd.DataFrame,
    preprocessing: tuple[str, ...] = (),
    missing_value_method: str = "无",
) -> pd.DataFrame:
    """在建模数据集阶段统一应用数据替换和缺失值处理。

    Parameters
    ----------
    frame : pandas.DataFrame
        已按用户选择的表头、数据起始行和时间列解析的数据框。
    preprocessing : tuple[str, ...], default=()
        数据替换规则；``"去零"`` 将 0 替换为缺失，``"去负"`` 将负值替换为缺失。
    missing_value_method : str, default="无"
        数据替换后应用于全部数值型变量的缺失值处理方式；每个变量仅在
        其第一个有效值和最后一个有效值之间处理缺失，区间外缺失保持不变。

    Returns
    -------
    pandas.DataFrame
        不修改输入对象的处理后数据框；非数值列保持不变，数值列首末有效值
        之外的缺失值保持不变。

    Raises
    ------
    ValueError
        ``preprocessing`` 或 ``missing_value_method`` 包含不支持的选项时抛出。
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("待处理数据必须是 pandas.DataFrame")

    selected_preprocessing = tuple(dict.fromkeys(preprocessing or ()))
    unknown_preprocessing = [
        option
        for option in selected_preprocessing
        if option not in DATA_REPLACEMENT_OPTIONS
    ]
    if unknown_preprocessing:
        raise ValueError(
            "不支持的数据预处理："
            + ", ".join(str(option) for option in unknown_preprocessing)
        )
    if missing_value_method not in MISSING_VALUE_OPTIONS:
        raise ValueError(f"不支持的缺失值处理：{missing_value_method}")

    result = frame.copy(deep=True)
    numeric_columns = numeric_variable_names(result)
    if not numeric_columns:
        return result

    # 处理可能引入 NaN；先把整数列提升为浮点，避免向 int64 列写入缺失值。
    values = result.loc[:, numeric_columns].astype(float)
    if "去零" in selected_preprocessing:
        values = values.mask(values == 0.0)
    if "去负" in selected_preprocessing:
        values = values.mask(values < 0.0)
    values = _apply_missing_value_method_to_frame(values, missing_value_method)
    for column in numeric_columns:
        result[column] = values[column]
    return result


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
    missing_value_method: str = "无",
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
        Selected data replacement rules. ``"去零"`` treats zero values as
        missing; ``"去负"`` treats negative values as missing. Rules apply to
        the target and selected exogenous variables after the training range is
        applied.
    missing_value_method : str, default="无"
        Missing-value handling method applied after data replacement. Supported
        values are ``"无"``, ``"向前填补"``, ``"向后填补"``, ``"线性内插"``,
        ``"样条内插"``, ``"多项式内插"`` and ``"卡尔曼滤波"``.

    Returns
    -------
    tuple[pd.Series, pd.DataFrame | None, pd.Index]
        Target series, optional exogenous frame, and the aligned modeling index.

    Raises
    ------
    ValueError
        If the target/exogenous variables, data replacement or missing-value
        options, or requested time range is invalid.
    """
    selected_preprocessing = tuple(dict.fromkeys(preprocessing or ()))
    unknown_preprocessing = [
        option
        for option in selected_preprocessing
        if option not in DATA_REPLACEMENT_OPTIONS
    ]
    if unknown_preprocessing:
        raise ValueError(
            "不支持的数据预处理："
            + ", ".join(str(option) for option in unknown_preprocessing)
        )
    if missing_value_method not in MISSING_VALUE_OPTIONS:
        raise ValueError(f"不支持的缺失值处理：{missing_value_method}")

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

    target_series = _apply_missing_value_method(
        target_series,
        missing_value_method,
    )
    if exog_frame is not None:
        exog_frame = _apply_missing_value_method_to_frame(
            exog_frame,
            missing_value_method,
        )

    return target_series, exog_frame, index


def effective_modeling_date_bounds(
    dataset: OverviewDataset,
    target: str,
    exog_columns: tuple[str, ...] = (),
    preprocessing: tuple[str, ...] = (),
    missing_value_method: str = "无",
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
        应用于目标变量和外生变量的数据替换规则。
    missing_value_method : str, default="无"
        应用于数据替换后目标变量和外生变量的缺失值处理方式。

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
        missing_value_method=missing_value_method,
    )
    valid = series.notna().to_numpy(copy=True)
    if exog_frame is not None:
        valid &= exog_frame.notna().all(axis=1).to_numpy()
    valid_dates = pd.DatetimeIndex(index[valid])
    if len(valid_dates) == 0:
        return None
    return pd.Timestamp(valid_dates[0]), pd.Timestamp(valid_dates[-1])


__all__ = [
    "DATA_REPLACEMENT_OPTIONS",
    "MISSING_VALUE_OPTIONS",
    "PREPROCESSING_OPTIONS",
    "dataset_time_index",
    "effective_modeling_date_bounds",
    "forecast_sample_dates",
    "preprocess_modeling_frame",
    "prepare_modeling_inputs",
]
