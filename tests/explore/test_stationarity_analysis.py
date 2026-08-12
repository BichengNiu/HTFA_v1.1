from types import SimpleNamespace
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from dashboard.explore.analysis import stationarity
from dashboard.explore.analysis.stationarity import (
    create_correlogram_figure,
    create_time_series_figure,
    prepare_selected_series,
    run_selected_stationarity_tests,
    summarize_series,
    transform_series,
)


@pytest.fixture
def positive_monthly_series() -> pd.Series:
    return pd.Series(
        np.arange(1.0, 25.0),
        index=pd.date_range("2024-01-31", periods=24, freq="ME"),
        name="value",
    )


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("original", lambda series: series),
        ("log", lambda series: np.log(series)),
        ("first_difference", lambda series: series.diff()),
        ("second_difference", lambda series: series.diff().diff()),
        ("year_over_year", lambda series: series.diff(12)),
        ("log_first_difference", lambda series: np.log(series).diff()),
        ("log_second_difference", lambda series: np.log(series).diff().diff()),
        ("log_year_over_year", lambda series: np.log(series).diff(12)),
    ],
)
def test_transform_series_supports_confirmed_methods(
    positive_monthly_series,
    method,
    expected,
):
    result = transform_series(
        positive_monthly_series,
        method,
        frequency="Monthly",
    )

    pd.testing.assert_series_equal(result, expected(positive_monthly_series))


def test_log_transform_rejects_non_positive_values(positive_monthly_series):
    values = positive_monthly_series.copy()
    values.iloc[3] = 0

    with pytest.raises(ValueError, match="严格大于 0"):
        transform_series(values, "log_first_difference", frequency="Monthly")


@pytest.mark.parametrize(
    ("frequency", "lag"),
    [
        ("Monthly", 12),
        ("Quarterly", 4),
        ("Weekly", 52),
        ("Ten_Day", 36),
        ("Annual", 1),
        ("monthly", 12),
        ("quarterly", 4),
    ],
)
def test_year_over_year_uses_frequency_specific_lag(frequency, lag):
    series = pd.Series(np.arange(1.0, 80.0), name="value")

    result = transform_series(series, "year_over_year", frequency=frequency)

    pd.testing.assert_series_equal(result, series.diff(lag))


def test_year_over_year_rejects_unsupported_frequency():
    series = pd.Series(np.arange(1.0, 20.0), name="value")

    with pytest.raises(ValueError, match="不支持同比"):
        transform_series(series, "year_over_year", frequency="Daily")


def test_prepare_selected_series_uses_and_sorts_detected_time_column():
    data = pd.DataFrame(
        {
            "date": ["2025-03-31", "2025-01-31", "2025-02-28"],
            "value": [3.0, 1.0, 2.0],
        }
    )

    series, time_label = prepare_selected_series(data, "value")

    assert time_label == "date"
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.tolist() == [1.0, 2.0, 3.0]


def test_prepare_selected_series_rejects_duplicate_timestamps():
    data = pd.DataFrame(
        {
            "date": ["2025-01-31", "2025-01-31"],
            "value": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="重复日期"):
        prepare_selected_series(data, "value")


def test_summary_uses_ts_summary_without_implicit_plot(monkeypatch):
    calls = {}

    class FakeSummary:
        def __init__(self, data, *, alpha):
            calls["data"] = data
            calls["alpha"] = alpha

        def summary(self, *, plot):
            calls["plot"] = plot
            return "\n".join(
                [
                    "Time Series Summary",
                    "==================================================",
                    "Name               : value",
                    "Observations       : 3",
                    "Valid observations : 2",
                    "Frequency          : ME",
                    "Missing timestamps : None",
                    "Mean               : 2",
                ]
            )

    monkeypatch.setattr(stationarity, "TimeSeriesSummary", FakeSummary)
    series = pd.Series([1.0, np.nan, 3.0], name="value")

    result = summarize_series(series, alpha=0.1)

    assert "时间序列统计摘要" in result
    assert "名称：value" in result
    assert "总观测数：3" in result
    assert "有效观测数：2" in result
    assert "频率：月度" in result
    assert "缺失时间点：无" in result
    assert "均值：2" in result
    assert "Time Series Summary" not in result
    pd.testing.assert_series_equal(calls["data"], series)
    assert calls["alpha"] == 0.1
    assert calls["plot"] is False


def test_summary_uses_explicit_frequency_over_ts_inference(monkeypatch):
    class FakeSummary:
        def __init__(self, data, *, alpha):
            pass

        def summary(self, *, plot):
            return "Time Series Summary\nFrequency          : ME"

    monkeypatch.setattr(stationarity, "TimeSeriesSummary", FakeSummary)

    result = summarize_series(
        pd.Series([1.0, 2.0, 3.0]),
        frequency="Daily",
    )

    assert "频率：日度" in result
    assert "频率：月度" not in result


def test_time_series_figure_handles_matplotlib_date_deprecation(
    positive_monthly_series,
):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        figure = create_time_series_figure(
            positive_monthly_series,
            x_start=positive_monthly_series.index.min().date(),
        )

    plt.close(figure)


def test_correlogram_uses_ts_plots_and_drops_missing_values(monkeypatch):
    calls = {}

    def record_acf(data, **kwargs):
        calls["acf"] = (data.copy(), kwargs)
        return kwargs["ax"].figure, kwargs["ax"]

    def record_pacf(data, **kwargs):
        calls["pacf"] = (data.copy(), kwargs)
        return kwargs["ax"].figure, kwargs["ax"]

    monkeypatch.setattr(stationarity, "plot_acf", record_acf)
    monkeypatch.setattr(stationarity, "plot_pacf", record_pacf)
    series = pd.Series([1.0, np.nan, 2.0, 3.0, 5.0, 8.0], name="value")

    figure = create_correlogram_figure(
        series,
        nlags=1,
        alpha=0.05,
        acf_title="自定义 ACF",
        pacf_title="自定义 PACF",
        acf_x_title="ACF 横轴",
        acf_y_title="ACF 纵轴",
        pacf_x_title="PACF 横轴",
        pacf_y_title="PACF 纵轴",
        grid=False,
        pacf_method="ols",
    )

    assert set(calls) == {"acf", "pacf"}
    assert all(call[0].isna().sum() == 0 for call in calls.values())
    assert all(call[1]["nlags"] == 1 for call in calls.values())
    assert calls["acf"][1]["zero_lag"] is False
    assert "zero_lag" not in calls["pacf"][1]
    assert calls["acf"][1]["title"] == "自定义 ACF"
    assert calls["acf"][1]["xtitle"] == "ACF 横轴"
    assert calls["acf"][1]["ytitle"] == "ACF 纵轴"
    assert calls["acf"][1]["grid"] is False
    assert calls["pacf"][1]["title"] == "自定义 PACF"
    assert calls["pacf"][1]["method"] == "ols"
    plt.close(figure)


def test_correlogram_caps_lags_for_pacf():
    series = pd.Series(np.arange(10.0), name="value")

    with pytest.raises(ValueError, match="最大允许值为 4"):
        create_correlogram_figure(series, nlags=5)


class _FakeTest:
    result = None

    def __init__(self, data, **kwargs):
        self.data = data
        self.kwargs = kwargs

    def fit(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _test_class(result):
    return type("ConfiguredFakeTest", (_FakeTest,), {"result": result})


def test_selected_tests_respect_opposite_null_hypotheses(monkeypatch):
    monkeypatch.setattr(
        stationarity,
        "ADFTest",
        _test_class(
            SimpleNamespace(
                statistic=-4.0,
                pvalue=0.01,
                lags=1,
                nobs=98,
                critical_values={"5%": -2.9},
            )
        ),
    )
    monkeypatch.setattr(
        stationarity,
        "KPSSTest",
        _test_class(
            SimpleNamespace(
                statistic=0.1,
                pvalue=0.10,
                lags=3,
                nobs=100,
                critical_values={"5%": 0.463},
            )
        ),
    )
    monkeypatch.setattr(
        stationarity,
        "PhillipsPerronTest",
        _test_class(
            SimpleNamespace(
                statistic=-4.5,
                pvalue=0.02,
                lags=4,
                nobs=99,
                critical_values={"5%": -2.9},
            )
        ),
    )
    series = pd.Series(
        np.arange(100.0),
        index=pd.date_range("2020-01-31", periods=100, freq="ME"),
        name="value",
    )

    result = run_selected_stationarity_tests(
        series,
        ["adf", "kpss", "pp"],
        alpha=0.05,
        trend="c",
    ).set_index("检验代码")

    assert result.loc["adf", "判定"] == "拒绝原假设"
    assert result.loc["kpss", "判定"] == "不能拒绝原假设"
    assert result.loc["pp", "平稳性解释"] == "支持平稳"
    assert result["平稳性解释"].eq("支持平稳").all()


def test_selected_test_failure_is_reported_without_aborting_other_tests(
    monkeypatch,
):
    monkeypatch.setattr(
        stationarity,
        "ADFTest",
        _test_class(ValueError("bad adf input")),
    )
    monkeypatch.setattr(
        stationarity,
        "KPSSTest",
        _test_class(
            SimpleNamespace(
                statistic=0.1,
                pvalue=0.10,
                lags=3,
                nobs=20,
                critical_values={"5%": 0.463},
            )
        ),
    )

    result = run_selected_stationarity_tests(
        pd.Series(np.arange(20.0), name="value"),
        ["adf", "kpss"],
    ).set_index("检验代码")

    assert "bad adf input" in result.loc["adf", "错误"]
    assert result.loc["kpss", "错误"] == ""


def test_each_test_uses_its_own_ts_trend_contract(monkeypatch):
    constructor_options = {}
    result = SimpleNamespace(
        statistic=-4.0,
        pvalue=0.01,
        lags=1,
        nobs=40,
        critical_values={"5%": -2.9},
    )

    def configured_class(test_key):
        class ConfiguredTest:
            def __init__(self, data, **kwargs):
                constructor_options[test_key] = kwargs

            def fit(self):
                return result

        return ConfiguredTest

    monkeypatch.setattr(stationarity, "ADFTest", configured_class("adf"))
    monkeypatch.setattr(stationarity, "KPSSTest", configured_class("kpss"))
    monkeypatch.setattr(
        stationarity,
        "PhillipsPerronTest",
        configured_class("pp"),
    )

    outcomes = run_selected_stationarity_tests(
        pd.Series(np.arange(40.0), name="value"),
        ["adf", "kpss", "pp"],
        test_trends={"adf": "n", "kpss": "ct", "pp": "ct"},
    ).set_index("检验代码")

    assert constructor_options["adf"]["trend"] == "n"
    assert constructor_options["kpss"]["trend"] == "ct"
    assert constructor_options["pp"]["trend"] == "ct"
    assert outcomes.loc["adf", "确定性项"] == "无常数项"
    assert outcomes.loc["kpss", "确定性项"] == "趋势平稳（常数项 + 线性趋势）"


def test_kpss_rejects_unsupported_no_constant_option():
    with pytest.raises(ValueError, match="KPSS"):
        run_selected_stationarity_tests(
            pd.Series(np.arange(40.0), name="value"),
            ["kpss"],
            test_trends={"kpss": "n"},
        )


def test_selected_tests_require_at_least_one_method():
    with pytest.raises(ValueError, match="至少选择一种"):
        run_selected_stationarity_tests(
            pd.Series(np.arange(20.0), name="value"),
            [],
        )


def test_real_ts_package_runs_all_supported_tests_end_to_end():
    rng = np.random.default_rng(42)
    values = np.zeros(120)
    for index in range(1, len(values)):
        values[index] = 0.5 * values[index - 1] + rng.normal()
    series = pd.Series(
        values,
        index=pd.date_range("2016-01-31", periods=120, freq="ME"),
        name="ar1",
    )

    result = run_selected_stationarity_tests(
        series,
        ["adf", "kpss", "pp"],
        alpha=0.05,
        trend="c",
    )

    assert result["错误"].eq("").all()
    assert result["统计量"].notna().all()
    assert set(result["平稳性解释"]) <= {"支持平稳", "支持非平稳"}
