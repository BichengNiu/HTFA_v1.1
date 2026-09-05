import pandas as pd

from htfa.data.economic_workbook.shared.plotting import plot_indicator


def _trace(figure, name):
    return next(trace for trace in figure.data if trace.name == name)


def test_plot_preserves_legitimate_zero_values():
    series = pd.Series(
        [0.0, 1.0],
        index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
    )

    figure = plot_indicator(series, "指标", "daily", 2025, 2024)

    assert list(_trace(figure, "2025年").y) == [0.0, 1.0]


def test_weekly_plot_uses_iso_year_with_iso_week():
    series = pd.Series(
        [7.0],
        index=pd.to_datetime(["2021-01-01"]),
    )

    figure = plot_indicator(series, "指标", "weekly", 2020, 2019)
    current_trace = _trace(figure, "2020年")

    assert 53 in list(current_trace.x)
    assert current_trace.y[list(current_trace.x).index(53)] == 7.0


def test_daily_plot_aligns_same_calendar_day_across_leap_years():
    series = pd.Series(
        [10.0, 20.0],
        index=pd.to_datetime(["2023-03-01", "2024-03-01"]),
    )

    figure = plot_indicator(series, "指标", "daily", 2024, 2023)

    assert list(_trace(figure, "2024年").x) == [61]
    assert list(_trace(figure, "2023年").x) == [61]


def test_daily_historical_statistics_do_not_fill_unobserved_days():
    series = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.to_datetime(["2022-01-01", "2023-01-01", "2025-01-01"]),
    )

    figure = plot_indicator(series, "指标", "daily", 2025, 2024)
    historical_mean = _trace(figure, "均值")

    assert pd.notna(historical_mean.y[0])
    assert pd.isna(historical_mean.y[1])
