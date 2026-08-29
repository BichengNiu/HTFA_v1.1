"""数据概览的纯解析逻辑：频率推断、时间掩码、参考线/阴影解析。

全部函数不依赖 streamlit（状态以 Mapping 传入），可独立单测。
"""

from __future__ import annotations

import pandas as pd

from .constants import FREQ_PERIOD, TIME_PRESETS


def detect_frequency(dates) -> str:
    """按时间间隔中位数推断数据频率：year/quarter/month/week/day。"""
    series = pd.to_datetime(pd.Series(dates)).sort_values()
    if len(series) < 2:
        return "day"
    diffs = series.diff().dropna()
    if diffs.empty:
        return "day"
    median = diffs.median()
    if median >= pd.Timedelta(days=330):
        return "year"
    if median >= pd.Timedelta(days=85):
        return "quarter"
    if median >= pd.Timedelta(days=25):
        return "month"
    if median >= pd.Timedelta(days=5):
        return "week"
    return "day"


def period_bounds(text: str, freq: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """把按频率粒度的选择文本转换为 (起始, 结束) 时间戳。"""
    if freq in ("day", "week"):
        ts = pd.Timestamp(text)
        return ts, ts
    period = pd.Period(text, FREQ_PERIOD[freq])
    return period.start_time, period.end_time


def time_mask(dataset, state, *, key_prefix: str = "sarimax") -> pd.Series:
    """按时间筛选预设/自定义起止构造布尔掩码（频率匹配数据粒度）。

    state：会话状态映射（如 st.session_state），缺失键回退不筛选。
    key_prefix：widget 键前缀，默认 "sarimax"（读 {prefix}_table_* 键）。
    """
    time_series = pd.to_datetime(dataset.frame[dataset.time_column])
    mask = pd.Series(True, index=dataset.frame.index)
    freq = detect_frequency(time_series)
    preset_label = state.get(f"{key_prefix}_table_time_preset")
    if preset_label is None:
        return mask
    preset_value = dict(TIME_PRESETS[freq]).get(preset_label, "all")
    if preset_value == "all":
        return mask
    last = time_series.max()
    if preset_value == "custom":
        start = state.get(f"{key_prefix}_table_time_start")
        end = state.get(f"{key_prefix}_table_time_end")
        if start is None or end is None:
            return mask
        start_ts, _ = period_bounds(str(start), freq)
        _, end_ts = period_bounds(str(end), freq)
    else:
        # 按数据实际点位取最近 N 期（如月度数据「过去3个月」= 最后 3 个
        # 数据点），与数据频率和实际范围精确匹配。
        periods = int(preset_value)
        sorted_dates = time_series.sort_values().unique()
        if len(sorted_dates) <= periods:
            return mask
        start_ts = pd.Timestamp(sorted_dates[-periods])
        end_ts = last
    return mask & (time_series >= start_ts) & (time_series <= end_ts)


def parse_float(text: str) -> float | None:
    """解析可空的数值输入；空或非法时返回 None。"""
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_csv_items(
    text: str,
    label: str,
    *,
    expected_count: int | None = None,
) -> tuple[list[str] | None, str | None]:
    """解析逗号分隔的非空文本项，并可校验项目数。"""
    text = str(text or "").strip()
    if not text:
        return None, None
    items = [item.strip() for item in text.split(",")]
    if any(not item for item in items):
        return None, f"{label}不能包含空项目"
    if expected_count is not None and len(items) != expected_count:
        return None, f"{label}应填写 {expected_count} 项，实际为 {len(items)} 项"
    return items, None


def parse_key_value_mapping(
    text: str,
    label: str,
    *,
    allowed_keys=None,
) -> tuple[dict[str, str] | None, str | None]:
    """解析 ``键=值,键=值`` 文本为字典，并校验键唯一性。"""
    text = str(text or "").strip()
    if not text:
        return None, None
    mapping: dict[str, str] = {}
    allowed = set(allowed_keys) if allowed_keys is not None else None
    for item in text.split(","):
        item = item.strip()
        if not item or "=" not in item:
            return None, f"{label}格式应为 键=值,键=值：{item or text}"
        key, value = (part.strip() for part in item.split("=", 1))
        if not key or not value:
            return None, f"{label}的键和值都不能为空：{item}"
        if key in mapping:
            return None, f"{label}存在重复键：{key}"
        if allowed is not None and key not in allowed:
            return None, f"{label}包含未选择变量：{key}"
        mapping[key] = value
    return mapping, None


def resolve_position(text: str, x_values, label: str):
    """把输入解析为 X 轴位置：纯数字=行号；否则按日期解析（取第一个
    不早于该日期的数据点）。返回 (位置, 错误)；出错时位置为 None。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        count = len(x_values)
        if index >= count:
            return None, f"{label}行号超出数据范围（0~{count - 1}）：{index}"
        value = x_values.iloc[index] if hasattr(x_values, "iloc") else x_values[index]
        return value, None

    if not pd.api.types.is_datetime64_any_dtype(x_values):
        return None, f"{label}无法解析（数据时间列不是日期类型，请填写行号）：{text}"
    try:
        target = pd.to_datetime(text)
    except (ValueError, TypeError):
        return None, f"{label}无法解析（应为行号或日期，如 1987-07）：{text}"
    if target < pd.Timestamp(x_values.iloc[0]):
        return None, f"{label}日期早于数据起点：{text}"
    candidates = x_values[x_values >= target]
    if not len(candidates):
        return None, f"{label}日期晚于数据终点：{text}"
    return candidates.iloc[0], None


def parse_vlines(text: str, x_values) -> tuple[list | None, str | None]:
    """解析垂直参考线：逗号分隔，每项为行号或日期（如 1987-07）。"""
    text = text.strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None, None
    resolved = []
    for part in parts:
        position, error = resolve_position(part, x_values, "参考线")
        if error:
            return None, error
        resolved.append(position)
    return resolved, None


def parse_hlines(text: str) -> tuple[list[float] | None, str | None]:
    """解析水平参考线：逗号分隔的数值 Y 轴位置。"""
    text = text.strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None, None
    resolved = []
    for part in parts:
        value = parse_float(part)
        if value is None:
            return None, f"水平参考线必须填写数字：{part}"
        resolved.append(value)
    return resolved, None


def parse_shade(text: str, x_values) -> tuple[list[tuple] | None, str | None]:
    """解析阴影区间：逗号分隔两两一组（起,止,起,止…），行为行号或日期。"""
    text = text.strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None, None
    if len(parts) % 2:
        return None, f"阴影区间应为两两一组（起,止）：{parts[-1]}"
    intervals = []
    for i in range(0, len(parts), 2):
        start, error = resolve_position(parts[i], x_values, "阴影起点")
        if error:
            return None, error
        end, error = resolve_position(parts[i + 1], x_values, "阴影终点")
        if error:
            return None, error
        if start > end:
            return None, f"阴影区间起点不能大于终点：{parts[i]}, {parts[i + 1]}"
        intervals.append((start, end))
    return intervals or None, None


__all__ = [
    "detect_frequency",
    "parse_csv_items",
    "parse_float",
    "parse_hlines",
    "parse_key_value_mapping",
    "parse_shade",
    "parse_vlines",
    "period_bounds",
    "resolve_position",
    "time_mask",
]
