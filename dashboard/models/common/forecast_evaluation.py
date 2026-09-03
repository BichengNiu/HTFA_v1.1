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
    horizon_error_table: pd.DataFrame | None = None
    horizon_direction_table: pd.DataFrame | None = None


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


def evaluate_in_sample_fit(
    actual: Iterable[float],
    fitted: Iterable[float],
    dates: Iterable[object],
    *,
    seasonal_period: int = 1,
) -> ForecastAccuracyReport:
    """评估完整训练期拟合值，并与朴素基准比较。

    Parameters
    ----------
    actual, fitted : iterable of float
        按训练期日期排列的实际值和模型拟合值。
    dates : iterable of datetime-like
        与 ``actual`` 和 ``fitted`` 对齐的训练期日期。
    seasonal_period : int, default=1
        朴素基准使用的滞后期数；没有季节周期时使用 1。

    Returns
    -------
    ForecastAccuracyReport
        完整训练期的模型、朴素基准误差和方向性指标。
    """
    actual_values = _as_vector(actual, "actual")
    fitted_values = _as_vector(fitted, "fitted")
    date_index = _normalise_dates(dates, len(actual_values))
    if actual_values.size != fitted_values.size:
        raise ValueError("训练期实际值、拟合值和日期长度必须一致")
    lag = _normalise_lag(seasonal_period)
    baseline = np.full(actual_values.size, np.nan)
    reference = np.full(actual_values.size, np.nan)
    for position in range(actual_values.size):
        if position >= lag:
            baseline[position] = actual_values[position - lag]
        if position > 0:
            reference[position] = actual_values[position - 1]
    point_table = _point_table(
        date_index,
        actual_values,
        fitted_values,
        baseline,
        reference,
        np.full(actual_values.size, "完整训练期拟合", dtype=object),
    )
    error_table, direction_table = _comparison_tables(
        point_table,
        total_count=len(point_table),
    )
    return ForecastAccuracyReport(
        error_table=error_table,
        direction_table=direction_table,
        point_table=point_table,
        notes=(
            "完整训练期评估使用一次拟合得到的拟合值；不属于样本外预测。",
            f"相对基准采用滞后 {lag} 期的朴素预测。",
        ),
    )


def evaluate_fixed_holdout(
    actual: Iterable[float],
    predicted: Iterable[float],
    dates: Iterable[object],
    full_actual: Iterable[float],
    full_dates: Iterable[object],
    training_end: object,
    *,
    seasonal_period: int = 1,
) -> ForecastAccuracyReport:
    """评估固定起点的完整样本外验证窗口。

    Parameters
    ----------
    actual, predicted : iterable of float
        训练结束日之后、已经存在真实值的样本外实际值和固定起点预测值。
    dates : iterable of datetime-like
        与 ``actual`` 和 ``predicted`` 对齐的样本外日期。
    full_actual : iterable of float
        与 ``full_dates`` 对齐的完整处理后实际值序列。
    full_dates : iterable of datetime-like
        完整处理后数据日历。
    training_end : datetime-like
        固定起点，即训练样本结束日。
    seasonal_period : int, default=1
        朴素基准使用的滞后期数；没有季节周期时使用 1。

    Returns
    -------
    ForecastAccuracyReport
        完整样本外验证窗口的模型、朴素基准误差和方向性指标。
    """
    actual_values = _as_vector(actual, "actual")
    predicted_values = _as_vector(predicted, "predicted")
    if actual_values.size != predicted_values.size:
        raise ValueError("样本外实际值、预测值和日期长度必须一致")
    date_index = _normalise_dates(dates, len(actual_values))
    full_values = _as_vector(full_actual, "full_actual")
    full_date_index = _normalise_dates(full_dates, len(full_values))
    if len(date_index) == 0:
        return _empty_comparison_report(
            "训练结束日之后没有可评分的真实观测。"
        )
    training_end = pd.Timestamp(training_end)
    if pd.isna(training_end):
        raise ValueError("训练结束日无效")
    if np.any(date_index <= training_end):
        raise ValueError("样本外评估日期必须严格晚于训练结束日")
    positions = _calendar_positions(full_date_index, date_index)
    origin_candidates = np.flatnonzero(full_date_index <= training_end)
    if origin_candidates.size == 0:
        raise ValueError("完整数据日历中不存在训练结束日之前的样本")
    origin = int(origin_candidates[-1])
    lag = _normalise_lag(seasonal_period)
    baseline = _recursive_naive_forecast(full_values, positions, origin, lag)
    reference = np.full(actual_values.size, full_values[origin])
    point_table = _point_table(
        date_index,
        actual_values,
        predicted_values,
        baseline,
        reference,
        np.full(actual_values.size, "完整样本外验证", dtype=object),
    )
    error_table, direction_table = _comparison_tables(
        point_table,
        total_count=len(point_table),
    )
    return ForecastAccuracyReport(
        error_table=error_table,
        direction_table=direction_table,
        point_table=point_table,
        notes=(
            "完整样本外验证复用一次拟合结果，不在验证窗口内重新拟合。",
            f"相对基准采用滞后 {lag} 期的朴素预测。",
        ),
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
    error_table, direction_table = _comparison_tables(
        point_table,
        total_count=len(point_table),
    )
    horizon_error_table, horizon_direction_table = _horizon_tables(
        point_table,
        horizon=actual_values.shape[1],
        split_count=len(split_values),
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
        horizon_error_table=horizon_error_table,
        horizon_direction_table=horizon_direction_table,
    )


def evaluate_training_rolling(
    actual: np.ndarray,
    predicted: np.ndarray,
    splits: Iterable[object],
    full_actual: Iterable[float],
    dates: Iterable[object] | None = None,
    *,
    horizon: int,
    seasonal_period: int = 1,
) -> ForecastAccuracyReport:
    """评估训练集内部的 H 期滚动伪样本外预测。

    Parameters
    ----------
    actual, predicted : numpy.ndarray
        Ts ``ForecastEvaluationResult`` 中的二维真实值和预测值数组。
    splits : iterable
        与数组第一维对应的 Ts ``ForecastSplit`` 序列。
    full_actual : iterable of float
        训练期完整处理后实际值序列。
    dates : iterable of datetime-like, optional
        与 ``full_actual`` 对齐的训练期日期。
    horizon : int
        每个滚动起点评估的预测期数。
    seasonal_period : int, default=1
        朴素基准使用的滞后期数；没有季节周期时使用 1。

    Returns
    -------
    ForecastAccuracyReport
        训练期滚动误差、方向指标、按步长表和逐点明细。
    """
    if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)):
        raise TypeError("horizon 必须是正整数")
    horizon = int(horizon)
    if horizon < 1:
        raise ValueError("horizon 必须是正整数")
    split_values = tuple(splits)
    if not split_values:
        return _empty_comparison_report(
            f"训练期没有形成完整的 {horizon} 期滚动验证窗口。"
        )
    expected_initial = max(10, 2 * horizon)
    initial_window = len(split_values[0].train_indices)
    if initial_window != expected_initial:
        raise ValueError(
            "训练期滚动初始窗口必须为 max(10, 2H)，"
            f"当前为 {initial_window}，H={horizon} 时应为 {expected_initial}"
        )
    if any(len(split.target_indices) != horizon for split in split_values):
        raise ValueError("训练期滚动每个窗口必须包含完整 H 期目标")
    report = evaluate_rolling_forecast(
        actual,
        predicted,
        split_values,
        full_actual,
        dates,
        seasonal_period=seasonal_period,
    )
    return ForecastAccuracyReport(
        error_table=report.error_table,
        direction_table=report.direction_table,
        point_table=report.point_table,
        notes=(
            "训练期滚动评估是训练集内部的伪样本外验证；采用扩展窗口、step=1。",
            *report.notes[1:],
        ),
        horizon_error_table=report.horizon_error_table,
        horizon_direction_table=report.horizon_direction_table,
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


def _comparison_tables(point_table: pd.DataFrame, *, total_count: int):
    """为同一窗口构造模型和朴素基准的整体表。"""
    actual = point_table["实际值"].to_numpy(dtype=float)
    predicted = point_table["预测值"].to_numpy(dtype=float)
    baseline = point_table["基准预测"].to_numpy(dtype=float)
    reference = point_table["方向参考"].to_numpy(dtype=float)
    error_table = pd.DataFrame(
        [
            _summary_row("模型", actual, predicted, total_count=total_count),
            _summary_row(
                "朴素基准",
                actual,
                baseline,
                total_count=total_count,
            ),
        ]
    )
    direction_table = pd.DataFrame(
        [
            _direction_row(
                "模型",
                actual,
                predicted,
                baseline,
                reference,
                total_count=total_count,
            ),
            _direction_row(
                "朴素基准",
                actual,
                baseline,
                None,
                reference,
                total_count=total_count,
            ),
        ]
    )
    return error_table, direction_table


def _horizon_tables(
    point_table: pd.DataFrame,
    *,
    horizon: int,
    split_count: int,
):
    """按预测步长构造模型与朴素基准的指标表。"""
    error_rows = []
    direction_rows = []
    for step in range(1, horizon + 1):
        subset = point_table.loc[point_table["步长"] == step]
        actual = subset["实际值"].to_numpy(dtype=float)
        predicted = subset["预测值"].to_numpy(dtype=float)
        baseline = subset["基准预测"].to_numpy(dtype=float)
        reference = subset["方向参考"].to_numpy(dtype=float)
        for label, values in (
            ("模型", predicted),
            ("朴素基准", baseline),
        ):
            row = _summary_row(
                label,
                actual,
                values,
                total_count=split_count,
            )
            row = {"步长": step, **row}
            error_rows.append(row)
        model_direction = _direction_row(
            "模型",
            actual,
            predicted,
            baseline,
            reference,
            total_count=split_count,
        )
        baseline_direction = _direction_row(
            "朴素基准",
            actual,
            baseline,
            None,
            reference,
            total_count=split_count,
        )
        direction_rows.extend(
            [
                {"步长": step, **model_direction},
                {"步长": step, **baseline_direction},
            ]
        )
    return pd.DataFrame(error_rows), pd.DataFrame(direction_rows)


def _empty_comparison_report(note: str) -> ForecastAccuracyReport:
    """返回没有可评分样本时仍保持表结构的空报告。"""
    empty = np.asarray([], dtype=float)
    error_table, direction_table = _comparison_tables(
        _empty_point_table(),
        total_count=0,
    )
    return ForecastAccuracyReport(
        error_table=error_table,
        direction_table=direction_table,
        point_table=_empty_point_table(),
        notes=(note,),
    )


def _empty_point_table() -> pd.DataFrame:
    """返回评估明细的空表结构。"""
    return pd.DataFrame(
        columns=[
            "日期",
            "阶段",
            "实际值",
            "预测值",
            "基准预测",
            "误差",
            "方向参考",
            "方向命中",
            "基准方向命中",
        ]
    )


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
        "相对基准胜率": (
            relative_win_rate(actual, predicted, baseline)
            if baseline is not None
            else float("nan")
        ),
        "趋势相关系数": trend_correlation(actual, predicted),
        "方向有效样本数": int(direction_valid.sum()),
        "覆盖率": _coverage(int(direction_valid.sum()), total_count),
    }
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
    "evaluate_fixed_holdout",
    "evaluate_in_sample_fit",
    "evaluate_rolling_forecast",
    "evaluate_training_rolling",
]
