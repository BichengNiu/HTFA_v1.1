"""解析层测试：频率推断、时间掩码、参考线/阴影解析。"""

from __future__ import annotations

import pandas as pd

from data_overview.core.dataset import build_overview_dataset
from data_overview.core.parsing import (
    detect_frequency,
    parse_float,
    parse_shade,
    parse_vlines,
    period_bounds,
    resolve_position,
    time_mask,
)


def _frame():
    index = pd.date_range("2020-01-01", periods=30, freq="MS")
    return build_overview_dataset(
        pd.DataFrame({"date": index, "a": range(30)}), "sample.csv", "fp"
    )


def test_detect_frequency():
    monthly = pd.date_range("2020-01-01", periods=12, freq="MS")
    assert detect_frequency(monthly) == "month"
    daily = pd.date_range("2020-01-01", periods=12, freq="D")
    assert detect_frequency(daily) == "day"
    yearly = pd.date_range("2020-01-01", periods=5, freq="YS")
    assert detect_frequency(yearly) == "year"
    assert detect_frequency(monthly[:1]) == "day"


def test_period_bounds():
    start, end = period_bounds("2020-03", "month")
    assert start == pd.Timestamp("2020-03-01")
    # Period.end_time 为当月最后一刻（纳秒前）；行为与日期比较兼容。
    assert end.date() == pd.Timestamp("2020-03-31").date()
    assert end >= pd.Timestamp("2020-03-31")
    start, end = period_bounds("2020", "year")
    assert start == pd.Timestamp("2020-01-01")
    assert end.date() == pd.Timestamp("2020-12-31").date()
    start, end = period_bounds("2020-01-05", "day")
    assert start == end == pd.Timestamp("2020-01-05")


def test_time_mask_preset():
    dataset = _frame()
    # 未设置预设 = 不过滤。
    mask = time_mask(dataset, {})
    assert mask.all()
    # 过去3个月：取最后 3 个数据点。
    mask = time_mask(dataset, {"sarimax_table_time_preset": "过去3个月"})
    assert mask.sum() == 3
    assert dataset.frame.loc[mask, "date"].max() == dataset.frame["date"].max()
    # 全部。
    mask = time_mask(dataset, {"sarimax_table_time_preset": "全部"})
    assert mask.all()


def test_time_mask_custom():
    dataset = _frame()
    mask = time_mask(
        dataset,
        {
            "sarimax_table_time_preset": "自定义",
            "sarimax_table_time_start": "2020-03",
            "sarimax_table_time_end": "2020-05",
        },
    )
    assert mask.sum() == 3
    # 自定义但缺起止 = 不过滤。
    mask = time_mask(dataset, {"sarimax_table_time_preset": "自定义"})
    assert mask.all()


def test_time_mask_key_prefix():
    """不同 key_prefix 读取不同键。"""
    dataset = _frame()
    state = {"dfm_table_time_preset": "过去3个月"}
    mask = time_mask(dataset, state, key_prefix="dfm")
    assert mask.sum() == 3
    # 默认前缀读不到 dfm 键 → 不过滤。
    mask = time_mask(dataset, state)
    assert mask.all()


def test_parse_float():
    assert parse_float("") is None
    assert parse_float("  ") is None
    assert parse_float("12.5") == 12.5
    assert parse_float("abc") is None


def _x_values():
    """真实路径的类型：filtered[time_column] 是 pd.Series。"""
    return pd.Series(pd.date_range("2020-01-01", periods=10, freq="MS"))


def test_resolve_position_row_and_date():
    x_values = _x_values()
    value, error = resolve_position("3", x_values, "参考线")
    assert error is None
    assert value == x_values[3]
    value, error = resolve_position("2020-04", x_values, "参考线")
    assert error is None
    assert value == x_values[3]
    value, error = resolve_position("2020-04-15", x_values, "参考线")
    assert error is None
    assert value == x_values[4]  # 取第一个不早于目标的数据点
    value, error = resolve_position("99", x_values, "参考线")
    assert value is None
    assert "行号超出数据范围" in error
    value, error = resolve_position("2019-01", x_values, "参考线")
    assert value is None
    assert "早于数据起点" in error
    value, error = resolve_position("2021-01", x_values, "参考线")
    assert value is None
    assert "晚于数据终点" in error


def test_resolve_position_non_date_axis():
    x_values = pd.Series(range(10))
    value, error = resolve_position("2", x_values, "参考线")
    assert value == 2
    value, error = resolve_position("2020-01", x_values, "参考线")
    assert value is None
    assert "请填写行号" in error


def test_parse_vlines():
    x_values = _x_values()
    assert parse_vlines("", x_values) == (None, None)
    lines, error = parse_vlines("0,3,7", x_values)
    assert error is None
    assert lines == [x_values[0], x_values[3], x_values[7]]
    lines, error = parse_vlines("2020-01,2020-05", x_values)
    assert error is None
    assert lines == [x_values[0], x_values[4]]
    lines, error = parse_vlines("99", x_values)
    assert lines is None
    assert error is not None


def test_parse_shade():
    x_values = _x_values()
    assert parse_shade("", x_values) == (None, None)
    intervals, error = parse_shade("2,5,8,9", x_values)
    assert error is None
    assert intervals == [(x_values[2], x_values[5]), (x_values[8], x_values[9])]
    intervals, error = parse_shade("2020-02,2020-06", x_values)
    assert error is None
    assert intervals == [(x_values[1], x_values[5])]
    intervals, error = parse_shade("2,5,8", x_values)
    assert intervals is None
    assert "两两一组" in error
    intervals, error = parse_shade("5,3", x_values)
    assert intervals is None
    assert "起点不能大于终点" in error


def test_parse_shade_date_order():
    x_values = _x_values()
    intervals, error = parse_shade("2020-06,2020-02", x_values)
    assert intervals is None
    assert "起点不能大于终点" in error
