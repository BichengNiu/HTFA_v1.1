"""单变量预测精度评估的纯逻辑回归测试。"""

import numpy as np
import pandas as pd
import pytest

from dashboard.models.common.forecast_evaluation import (
    evaluate_current_forecast,
    evaluate_rolling_forecast,
)
from dashboard.models.SARIMAX.core.model_config import (
    ARDLConfig,
    RDLConfig,
    RDLInputConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.core.modeling import (
    fit_dynamic_model,
    run_historical_rolling_evaluation,
)
from Ts.TsMetrics import RollingOrigin


def test_current_forecast_is_split_into_fit_and_oos_metrics():
    calendar = pd.date_range("2020-01-01", periods=7, freq="D")
    report = evaluate_current_forecast(
        actual=[3.0, 4.0, np.nan],
        predicted=[3.2, 3.5, 4.8],
        dates=calendar[2:5],
        calendar_actual=[1, 2, 3, 4, 5, 6, 7],
        calendar=calendar,
        training_end=calendar[3],
    )

    assert report.error_table["对象"].tolist() == ["拟合表现", "样本外表现"]
    assert report.error_table.columns.tolist()[:6] == [
        "对象", "MAE", "RMSE", "MPE", "MAPE", "sMAPE"
    ]
    assert report.error_table.loc[0, "有效样本数"] == 2
    assert report.error_table.loc[1, "有效样本数"] == 0
    assert np.isnan(report.error_table.loc[1, "RMSE"])
    assert report.direction_table.loc[0, "相对基准胜率"] == pytest.approx(1.0)
    assert report.point_table["方向命中"].notna().sum() == 2


def test_current_forecast_reports_zero_oos_coverage_without_scoring():
    calendar = pd.date_range("2020-01-01", periods=4, freq="D")
    report = evaluate_current_forecast(
        actual=[np.nan, np.nan],
        predicted=[1.0, 1.1],
        dates=calendar[2:],
        calendar_actual=[1, 2, np.nan, np.nan],
        calendar=calendar,
        training_end=calendar[1],
    )

    assert report.error_table.loc[1, "覆盖率"] == 0.0
    assert report.error_table.loc[1, "有效样本数"] == 0
    assert any("尚无真实值" in note for note in report.notes)


def test_rolling_forecast_includes_naive_baseline_and_direction_metrics():
    full_actual = np.arange(1.0, 15.0)
    splits = RollingOrigin(initial_window=10, horizon=1).split(len(full_actual))
    actual = np.array([[full_actual[split.target_indices[0]]] for split in splits])
    predicted = actual.copy()
    report = evaluate_rolling_forecast(
        actual,
        predicted,
        splits,
        full_actual,
        pd.date_range("2020-01-01", periods=len(full_actual), freq="D"),
    )

    assert report.error_table["对象"].tolist() == ["模型", "朴素基准"]
    assert report.error_table.loc[0, "MAE"] == 0.0
    assert report.error_table.loc[0, "有效样本数"] == 4
    assert report.direction_table.loc[0, "相对基准胜率"] == 1.0
    assert report.direction_table.loc[0, "方向命中率"] == 1.0
    assert len(report.point_table) == 4


def test_all_univariate_model_families_can_run_historical_backtest():
    dates = pd.date_range("2020-01-01", periods=32, freq="MS")
    exog = pd.DataFrame({"x": np.arange(32, dtype=float)}, index=dates)
    series = pd.Series(
        5.0 + 0.5 * np.arange(32) + np.sin(np.arange(32)),
        index=dates,
        name="y",
    )
    cases = (
        (SARIMAXConfig(order=(0, 0, 0), trend="c", maxiter=20), None),
        (
            RDLConfig(
                inputs=(RDLInputConfig("x", numerator_order=1),),
                error=SARIMAXConfig(order=(0, 0, 0), trend="c", maxiter=20),
            ),
            exog,
        ),
        (
            ARDLConfig(lags=1, input_orders=(("x", 1),), trend="c"),
            exog,
        ),
    )

    for config, model_exog in cases:
        fitted = fit_dynamic_model(series, model_exog, config)
        comparison = run_historical_rolling_evaluation(
            series,
            model_exog,
            config,
            fitted,
            initial_window=20,
            horizon=1,
        )
        result = next(iter(comparison.results.values()))
        assert result.splits
        assert not result.failures
