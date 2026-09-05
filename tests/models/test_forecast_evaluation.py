"""单变量预测精度评估的纯逻辑回归测试。"""

from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from htfa.models.univariate.common.forecast_evaluation import (
    build_accuracy_workbook,
    evaluate_current_forecast,
    evaluate_fixed_holdout,
    evaluate_in_sample_fit,
    evaluate_rolling_forecast,
    evaluate_training_rolling,
)
from htfa.models.univariate.sarimax.core.model_config import (
    ARDLConfig,
    RDLConfig,
    RDLInputConfig,
    SARIMAXConfig,
)
from htfa.models.univariate.sarimax.core.modeling import (
    fit_dynamic_model,
    run_fixed_holdout_evaluation,
    run_historical_rolling_evaluation,
    run_training_rolling_evaluation,
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


def test_accuracy_workbook_contains_metric_tables_and_detail_sheet():
    calendar = pd.date_range("2020-01-01", periods=7, freq="D")
    report = evaluate_current_forecast(
        actual=[3.0, 4.0, np.nan],
        predicted=[3.2, 3.5, 4.8],
        dates=calendar[2:5],
        calendar_actual=[1, 2, 3, 4, 5, 6, 7],
        calendar=calendar,
        training_end=calendar[3],
    )

    workbook = build_accuracy_workbook(report)
    with pd.ExcelFile(BytesIO(workbook)) as excel:
        assert excel.sheet_names == ["误差指标", "方向性指标", "评估明细"]
        error_table = pd.read_excel(excel, sheet_name="误差指标")
        direction_table = pd.read_excel(excel, sheet_name="方向性指标")
        detail = pd.read_excel(excel, sheet_name="评估明细")

    assert {"MAE", "RMSE", "MPE", "MAPE", "sMAPE"}.issubset(
        error_table.columns
    )
    assert {"方向命中率", "相对基准胜率", "趋势相关系数"}.issubset(
        direction_table.columns
    )
    assert {"日期", "实际值", "预测值", "误差"}.issubset(detail.columns)
    assert "方向参考" not in detail.columns


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


def test_rolling_report_contains_overall_and_by_horizon_tables():
    full_actual = np.arange(1.0, 21.0)
    dates = pd.date_range("2020-01-01", periods=len(full_actual), freq="D")
    splits = RollingOrigin(initial_window=10, horizon=3).split(len(full_actual))
    actual = np.array(
        [[full_actual[index] for index in split.target_indices] for split in splits]
    )
    predicted = actual + 0.25

    report = evaluate_rolling_forecast(
        actual,
        predicted,
        splits,
        full_actual,
        dates,
    )

    assert report.horizon_error_table is not None
    assert report.horizon_direction_table is not None
    assert report.horizon_error_table["步长"].unique().tolist() == [1, 2, 3]
    assert report.horizon_direction_table["步长"].unique().tolist() == [1, 2, 3]
    assert report.horizon_error_table.groupby("步长").size().tolist() == [2, 2, 2]


def test_training_rolling_uses_two_horizon_initial_window():
    full_actual = np.arange(1.0, 31.0)
    dates = pd.date_range("2020-01-01", periods=len(full_actual), freq="D")
    horizon = 3
    splits = RollingOrigin(initial_window=10, horizon=horizon).split(
        len(full_actual)
    )
    actual = np.array(
        [[full_actual[index] for index in split.target_indices] for split in splits]
    )
    predicted = actual.copy()

    report = evaluate_training_rolling(
        actual,
        predicted,
        splits,
        full_actual,
        dates,
        horizon=horizon,
    )

    assert len(report.point_table) == len(splits) * horizon
    assert report.horizon_error_table.groupby("步长").size().tolist() == [2, 2, 2]
    assert any("训练期" in note for note in report.notes)


def test_training_rolling_rejects_an_incomplete_horizon_window():
    full_actual = np.arange(1.0, 12.0)
    dates = pd.date_range("2020-01-01", periods=len(full_actual), freq="D")

    report = evaluate_training_rolling(
        np.empty((0, 3)),
        np.empty((0, 3)),
        (),
        full_actual,
        dates,
        horizon=3,
    )

    assert report.point_table.empty
    assert report.error_table.loc[0, "有效样本数"] == 0
    assert any("完整" in note for note in report.notes)


def test_training_rolling_accepts_a_larger_initial_window():
    full_actual = np.arange(1.0, 31.0)
    dates = pd.date_range("2020-01-01", periods=len(full_actual), freq="D")
    horizon = 1
    splits = RollingOrigin(initial_window=20, horizon=horizon).split(
        len(full_actual)
    )
    actual = np.array(
        [[full_actual[index] for index in split.target_indices] for split in splits]
    )
    predicted = actual.copy()

    report = evaluate_training_rolling(
        actual,
        predicted,
        splits,
        full_actual,
        dates,
        horizon=horizon,
    )

    assert len(report.point_table) == len(splits) * horizon


def test_in_sample_and_fixed_holdout_reports_share_baseline_metrics():
    full_actual = np.arange(1.0, 16.0)
    dates = pd.date_range("2020-01-01", periods=len(full_actual), freq="D")
    fit = full_actual[:10] + 0.5
    in_sample = evaluate_in_sample_fit(
        full_actual[:10],
        fit,
        dates[:10],
    )
    holdout = evaluate_fixed_holdout(
        full_actual[10:],
        full_actual[10:] + 0.5,
        dates[10:],
        full_actual,
        dates,
        dates[9],
    )

    assert in_sample.error_table["对象"].tolist() == ["模型", "朴素基准"]
    assert holdout.error_table["对象"].tolist() == ["模型", "朴素基准"]
    assert in_sample.direction_table.loc[1, "相对基准胜率"] != in_sample.direction_table.loc[1, "相对基准胜率"]
    assert holdout.point_table["阶段"].unique().tolist() == ["完整样本外验证"]


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


def test_fixed_holdout_evaluation_reuses_fitted_result(monkeypatch):
    from htfa.models.univariate.sarimax.core import modeling

    calls = {}

    def fake_produce_forecast(result, **kwargs):
        calls["result"] = result
        calls.update(kwargs)
        return {"mean": np.array([1.0, 2.0])}

    monkeypatch.setattr(modeling, "produce_forecast", fake_produce_forecast)
    fitted = object()
    future_dates = pd.date_range("2024-01-01", periods=2, freq="MS")

    output = run_fixed_holdout_evaluation(
        fitted,
        start=10,
        end=11,
        future_dates=future_dates,
    )

    assert output["mean"].tolist() == [1.0, 2.0]
    assert calls["result"] is fitted
    assert calls["start"] == 10
    assert calls["end"] == 11
    assert calls["dynamic"] is False
    assert calls["future_dates"].equals(future_dates)


def test_training_rolling_model_entry_uses_two_horizon_initial_window(monkeypatch):
    from htfa.models.univariate.sarimax.core import modeling

    calls = {}

    def fake_historical(*args, **kwargs):
        calls.update(kwargs)
        return "comparison"

    monkeypatch.setattr(
        modeling,
        "run_historical_rolling_evaluation",
        fake_historical,
    )
    result = run_training_rolling_evaluation(
        pd.Series([1.0] * 30),
        None,
        SARIMAXConfig(order=(0, 0, 0)),
        object(),
        horizon=6,
    )

    assert result == "comparison"
    assert calls == {"initial_window": 12, "horizon": 6}


def test_historical_rolling_model_entry_caps_large_sample_to_recent_origins(
    monkeypatch,
):
    from htfa.models.univariate.sarimax.core import modeling

    calls = {}

    def fake_evaluate(*args, **kwargs):
        calls.update(kwargs)
        return "comparison"

    monkeypatch.setattr(
        modeling,
        "build_evaluation_model",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        modeling,
        "evaluate_forecasts",
        fake_evaluate,
    )
    result = run_historical_rolling_evaluation(
        pd.Series([1.0] * 5000),
        None,
        SARIMAXConfig(order=(0, 0, 0)),
        object(),
        initial_window=10,
        horizon=1,
    )

    assert result == "comparison"
    scheme = calls["scheme"]
    assert scheme.max_origins == modeling.MAX_ROLLING_ORIGINS
    assert len(scheme.split(5000)) == modeling.MAX_ROLLING_ORIGINS
    assert scheme.split(5000)[0].target_indices[0] == (
        5000 - modeling.MAX_ROLLING_ORIGINS
    )
