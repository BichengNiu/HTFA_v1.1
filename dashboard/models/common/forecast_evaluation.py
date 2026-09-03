"""单变量预测精度评估的纯数据逻辑。

页面层只负责控件和展示；误差、方向和基准计算集中在这里，保证当前预测
窗口与历史滚动回测使用同一套指标口径。
"""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from Ts.TsMetrics import (
    compute_metrics,
    directional_accuracy,
    relative_win_rate,
    trend_correlation,
)


MAIN_METRICS = ("mae", "rmse", "mpe", "mape", "smape")
METRIC_LABELS = {
    "mae": "MAE",
    "rmse": "RMSE",
    "mpe": "MPE",
    "mape": "MAPE",
    "smape": "sMAPE",
}
_PHASE_LABELS = ("拟合表现", "样本外表现")


@dataclass(frozen=True)
class ForecastAccuracyReport:
    """一个预测窗口的误差表、方向表和逐点明细。"""

    error_table: pd.DataFrame
    direction_table: pd.DataFrame
    point_table: pd.DataFrame
    notes: tuple[str, ...] = ()


def build_accuracy_workbook(report: ForecastAccuracyReport) -> bytes:
    """将评估报告导出为包含三个工作表的 Excel 工作簿。

    Parameters
    ----------
    report : ForecastAccuracyReport
        当前预测窗口或历史滚动回测的评估报告。

    Returns
    -------
    bytes
        可直接传给 Streamlit 下载控件的 XLSX 二进制内容。
    """
    detail = report.point_table.drop(columns=["方向参考"], errors="ignore")
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        report.error_table.to_excel(writer, sheet_name="误差指标", index=False)
        report.direction_table.to_excel(
            writer,
            sheet_name="方向性指标",
            index=False,
        )
        detail.to_excel(writer, sheet_name="评估明细", index=False)
    return output.getvalue()


def evaluate_current_forecast(
    actual: Iterable[float],
    predicted: Iterable[float],
    dates: Iterable[object],
    calendar_actual: Iterable[float],
    calendar: Iterable[object],
    training_end: object,
    *,
    seasonal_period: int = 1,
) -> ForecastAccuracyReport:
    """评估当前预测窗口，并按训练期/样本外分段。

    Parameters
    ----------
    actual, predicted : iterable of float
        当前预测窗口内按日期对齐的真实值和预测值；尚未观测的真实值用 NaN。
    dates : iterable of datetime-like
        当前预测窗口的日期。
    calendar_actual : iterable of float
        与完整 ``calendar`` 对齐的真实值；未来尚未观测的位置用 NaN。
    calendar : iterable of datetime-like
        当前页面预测滑轨的完整日期。
    training_end : datetime-like
        训练样本结束日，包含在训练期。
    seasonal_period : int, default=1
        朴素基准使用的滞后期数；没有季节周期时使用 1。

    Returns
    -------
    ForecastAccuracyReport
        误差指标、方向指标、逐点误差明细和数据覆盖提示。
    """
    actual_values = _as_vector(actual, "actual")
    predicted_values = _as_vector(predicted, "predicted")
    result_dates = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    full_calendar = pd.DatetimeIndex(pd.to_datetime(list(calendar)))
    full_actual = _as_vector(calendar_actual, "calendar_actual")
    if actual_values.size != predicted_values.size or actual_values.size != len(result_dates):
        raise ValueError("当前预测的真实值、预测值和日期长度必须一致")
    if full_actual.size != len(full_calendar):
        raise ValueError("完整日历与完整真实值长度必须一致")
    positions = _calendar_positions(full_calendar, result_dates)
    training_end = pd.Timestamp(training_end)
    if pd.isna(training_end):
        raise ValueError("训练结束日无效")
    lag = _normalise_lag(seasonal_period)
    origin_candidates = np.flatnonzero(full_calendar <= training_end)
    if origin_candidates.size == 0:
        raise ValueError("完整日历中不存在训练结束日之前的样本")
    origin = int(origin_candidates[-1])

    phase_mask = result_dates <= training_end
    reference = np.full(actual_values.size, np.nan)
    for row, position in enumerate(positions):
        reference[row] = (
            full_actual[position - 1]
            if phase_mask[row] and position > 0
            else full_actual[origin]
        )
    baseline = _recursive_naive_forecast(
        full_actual,
        positions,
        origin,
        lag,
    )
    point_table = _point_table(
        result_dates,
        actual_values,
        predicted_values,
        baseline,
        reference,
        np.where(phase_mask, _PHASE_LABELS[0], _PHASE_LABELS[1]),
    )
    error_table, direction_table = _phase_tables(
        point_table,
        labels=_PHASE_LABELS,
    )
    notes = []
    if not np.isfinite(actual_values[~phase_mask]).any():
        notes.append("样本外预测尚无真实值，样本外指标暂不评分。")
    if np.any(~np.isfinite(actual_values)):
        notes.append("无真实值的日期不计入指标；覆盖率按当前窗口总期数计算。")
    if lag > 1:
        notes.append(f"相对基准采用季节朴素预测（滞后 {lag} 期）。")
    else:
        notes.append("相对基准采用滞后 1 期的朴素预测。")
    return ForecastAccuracyReport(
        error_table=error_table,
        direction_table=direction_table,
        point_table=point_table,
        notes=tuple(notes),
    )


def evaluate_rolling_forecast(
    actual: np.ndarray,
    predicted: np.ndarray,
    splits: Iterable[object],
    full_actual: Iterable[float],
    dates: Iterable[object] | None = None,
    *,
    seasonal_period: int = 1,
) -> ForecastAccuracyReport:
    """评估 Ts 历史滚动回测结果，并与朴素基准比较。

    Parameters
    ----------
    actual, predicted : numpy.ndarray
        Ts ``ForecastEvaluationResult`` 中的二维真实值和预测值数组。
    splits : iterable
        与数组第一维对应的 Ts ``ForecastSplit`` 序列。
    full_actual : iterable of float
        与滚动回测模型完整数据日历对齐的原始尺度真实值。
    dates : iterable of datetime-like, optional
        完整数据日历；没有日期时逐点表使用位置编号。
    seasonal_period : int, default=1
        朴素基准使用的滞后期数；没有季节周期时使用 1。

    Returns
    -------
    ForecastAccuracyReport
        模型与朴素基准的误差表、方向表及逐点回测明细。
    """
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    if actual_values.shape != predicted_values.shape or actual_values.ndim != 2:
        raise ValueError("滚动回测真实值和预测值必须是形状一致的二维数组")
    split_values = tuple(splits)
    if len(split_values) != actual_values.shape[0]:
        raise ValueError("滚动回测 splits 数量必须与结果行数一致")
    full_values = _as_vector(full_actual, "full_actual")
    date_index = None if dates is None else _normalise_dates(dates, len(full_values))
    lag = _normalise_lag(seasonal_period)
    records = []
    for split_row, split in enumerate(split_values):
        target_indices = np.asarray(split.target_indices, dtype=int)
        if len(target_indices) != actual_values.shape[1]:
            raise ValueError("每个滚动回测 split 的目标期数必须一致")
        origin = int(split.train_indices[-1])
        baseline = _recursive_naive_forecast(
            full_values,
            target_indices,
            origin,
            lag,
        )
        reference = np.full(len(target_indices), full_values[origin])
        for horizon, target_position in enumerate(target_indices):
            date = (
                date_index[int(target_position)]
                if date_index is not None
                else int(target_position)
            )
            records.append(
                {
                    "回测期": int(split_row + 1),
                    "步长": int(horizon + 1),
                    "日期": date,
                    "实际值": actual_values[split_row, horizon],
                    "预测值": predicted_values[split_row, horizon],
                    "基准预测": baseline[horizon],
                    "误差": predicted_values[split_row, horizon]
                    - actual_values[split_row, horizon],
                    "方向参考": reference[horizon],
                }
            )
    point_table = pd.DataFrame.from_records(records)
    point_table["方向命中"] = _direction_hit_values(
        point_table["实际值"].to_numpy(),
        point_table["预测值"].to_numpy(),
        point_table["方向参考"].to_numpy(),
    )
    point_table["基准方向命中"] = _direction_hit_values(
        point_table["实际值"].to_numpy(),
        point_table["基准预测"].to_numpy(),
        point_table["方向参考"].to_numpy(),
    )
    error_table = pd.DataFrame(
        [
            _summary_row(
                "模型",
                point_table["实际值"].to_numpy(),
                point_table["预测值"].to_numpy(),
                total_count=len(point_table),
            ),
            _summary_row(
                "朴素基准",
                point_table["实际值"].to_numpy(),
                point_table["基准预测"].to_numpy(),
                total_count=len(point_table),
            ),
        ]
    )
    direction_table = pd.DataFrame(
        [
            _direction_row(
                "模型",
                point_table["实际值"].to_numpy(),
                point_table["预测值"].to_numpy(),
                point_table["基准预测"].to_numpy(),
                point_table["方向参考"].to_numpy(),
                total_count=len(point_table),
            ),
            _direction_row(
                "朴素基准",
                point_table["实际值"].to_numpy(),
                point_table["基准预测"].to_numpy(),
                None,
                point_table["方向参考"].to_numpy(),
                total_count=len(point_table),
            ),
        ]
    )
    notes = [
        "滚动回测采用扩展窗口、逐期一步预测；回测指标均为样本外指标。",
        "相对基准采用滞后 " + str(lag) + " 期的朴素预测。",
    ]
    return ForecastAccuracyReport(
        error_table=error_table,
        direction_table=direction_table,
        point_table=point_table,
        notes=tuple(notes),
    )


def _as_vector(values: Iterable[float], name: str) -> np.ndarray:
    array = np.asarray(list(values), dtype=float).reshape(-1)
    if array.ndim != 1:
        raise ValueError(f"{name} 必须是一维数值序列")
    return array


def _normalise_dates(values: Iterable[object], expected: int) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(list(values)))
    if len(dates) != expected:
        raise ValueError("日期数量与完整真实值长度必须一致")
    return dates


def _calendar_positions(calendar: pd.DatetimeIndex, dates: pd.DatetimeIndex) -> np.ndarray:
    positions = {value: index for index, value in enumerate(calendar)}
    try:
        return np.asarray([positions[value] for value in dates], dtype=int)
    except KeyError as exc:
        raise ValueError("预测日期不在完整预测日历中") from exc


def _normalise_lag(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError("seasonal_period 必须是正整数")
    if int(value) < 1:
        return 1
    return int(value)


def _recursive_naive_forecast(
    actual: np.ndarray,
    target_positions: np.ndarray,
    origin: int,
    lag: int,
) -> np.ndarray:
    """从 origin 开始递推朴素路径，不读取 origin 之后的真实值。"""
    target_positions = np.asarray(target_positions, dtype=int)
    if np.any(target_positions <= origin):
        history_end = int(max(origin, target_positions.max(initial=origin)))
    else:
        history_end = int(target_positions.max(initial=origin))
    history: dict[int, float] = {
        position: float(actual[position])
        for position in range(origin + 1)
    }
    output = np.full(target_positions.size, np.nan)
    for position in range(origin + 1, history_end + 1):
        if position - lag in history:
            history[position] = history[position - lag]
        else:
            history[position] = np.nan
    for row, position in enumerate(target_positions):
        if position <= origin:
            output[row] = history.get(int(position - lag), np.nan)
        else:
            output[row] = history.get(int(position), np.nan)
    return output


def _point_table(dates, actual, predicted, baseline, reference, phase) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "日期": dates,
            "阶段": phase,
            "实际值": actual,
            "预测值": predicted,
            "基准预测": baseline,
            "误差": predicted - actual,
            "方向参考": reference,
        }
    )
    frame["方向命中"] = _direction_hit_values(actual, predicted, reference)
    frame["基准方向命中"] = _direction_hit_values(actual, baseline, reference)
    return frame


def _phase_tables(point_table: pd.DataFrame, *, labels: tuple[str, ...]):
    error_rows = []
    direction_rows = []
    for label in labels:
        subset = point_table.loc[point_table["阶段"] == label]
        actual = subset["实际值"].to_numpy(dtype=float)
        predicted = subset["预测值"].to_numpy(dtype=float)
        baseline = subset["基准预测"].to_numpy(dtype=float)
        reference = subset["方向参考"].to_numpy(dtype=float)
        error_rows.append(
            _summary_row(
                label,
                actual,
                predicted,
                total_count=len(subset),
            )
        )
        direction_rows.append(
            _direction_row(
                label,
                actual,
                predicted,
                baseline,
                reference,
                total_count=len(subset),
            )
        )
    return pd.DataFrame(error_rows), pd.DataFrame(direction_rows)


def _summary_row(label, actual, predicted, *, total_count):
    metrics = compute_metrics(actual, predicted)
    valid = _finite_pairs(actual, predicted)
    percentage_valid = valid & (np.asarray(actual, dtype=float) != 0.0)
    row = {"对象": label}
    row.update({METRIC_LABELS[name]: metrics[name] for name in MAIN_METRICS})
    row.update(
        {
            "有效样本数": int(valid.sum()),
            "百分比指标样本数": int(percentage_valid.sum()),
            "覆盖率": _coverage(int(valid.sum()), total_count),
        }
    )
    return row


def _direction_row(label, actual, predicted, baseline, reference, *, total_count):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    reference = np.asarray(reference, dtype=float)
    direction_valid = (
        np.isfinite(actual)
        & np.isfinite(predicted)
        & np.isfinite(reference)
    )
    row = {
        "对象": label,
        "方向命中率": directional_accuracy(actual, predicted, reference),
        "趋势相关系数": trend_correlation(actual, predicted),
        "方向有效样本数": int(direction_valid.sum()),
        "覆盖率": _coverage(int(direction_valid.sum()), total_count),
    }
    if baseline is not None:
        row["相对基准胜率"] = relative_win_rate(actual, predicted, baseline)
    return row


def _finite_pairs(actual, predicted):
    return np.isfinite(np.asarray(actual, dtype=float)) & np.isfinite(
        np.asarray(predicted, dtype=float)
    )


def _direction_hit_values(actual, predicted, reference):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    reference = np.asarray(reference, dtype=float)
    valid = np.isfinite(actual) & np.isfinite(predicted) & np.isfinite(reference)
    values = np.full(actual.shape, np.nan)
    with np.errstate(invalid="ignore"):
        values[valid] = (
            np.sign(actual[valid] - reference[valid])
            == np.sign(predicted[valid] - reference[valid])
        ).astype(float)
    return values


def _coverage(valid_count: int, total_count: int) -> float:
    return float(valid_count / total_count) if total_count else float("nan")


__all__ = [
    "ForecastAccuracyReport",
    "MAIN_METRICS",
    "METRIC_LABELS",
    "build_accuracy_workbook",
    "evaluate_current_forecast",
    "evaluate_rolling_forecast",
]
