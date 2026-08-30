"""统一动态回归工作流的公共协议测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace

from dashboard.models.common.contracts import (
    EstimationResultView,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
)
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.common.ui.data_input import create_data_input_module
from dashboard.models.SARIMAX.core import adapters
from dashboard.models.SARIMAX.core.adapters import (
    ARDLAdapter,
    SARIMAXAdapter,
)
from dashboard.models.SARIMAX.core.model_config import ARDLConfig, SARIMAXConfig
from data_overview.ui.data_source import BuiltinDataSource
from dashboard.models.common.ui.forecast_view import build_forecast_table


def test_modeling_input_copies_and_normalises_public_fields():
    dates = pd.date_range("2024-01-01", periods=3, freq="MS")
    series = pd.Series([1.0, 2.0, 3.0], index=dates, name="target")
    exog = pd.DataFrame({"x": [4.0, 5.0, 6.0]}, index=dates)

    inputs = ModelingInput(
        series=series,
        exog=exog,
        index=dates,
        target="target",
        exog_names=("x",),
        training_range=(dates[0], dates[-1]),
        dataset_fingerprint="fingerprint",
        preprocessing=("去零",),
        response_log=False,
    )

    assert inputs.series is not series
    assert inputs.exog is not exog
    assert inputs.index.equals(dates)
    assert inputs.target == "target"
    assert inputs.exog_names == ("x",)
    assert inputs.training_range == (dates[0], dates[-1])


def test_forecast_request_requires_a_closed_window_and_valid_alpha():
    with pytest.raises(ValueError, match="alpha"):
        ForecastRequest(start=0, end=2, alpha=0.0)
    with pytest.raises(ValueError, match="结束"):
        ForecastRequest(start=3, end=2)


def test_forecast_result_requires_aligned_finite_arrays():
    dates = pd.date_range("2024-01-01", periods=2, freq="MS")
    result = ForecastResult(
        dates=dates,
        mean=np.array([1.0, 2.0]),
        lower=np.array([0.5, 1.5]),
        upper=np.array([1.5, 2.5]),
        alpha=0.05,
        steps=2,
        start=0,
        end=1,
        prediction=object(),
    )

    assert result.steps == len(result.mean) == len(result.dates)
    assert np.array_equal(result.mean, [1.0, 2.0])

    with pytest.raises(ValueError, match="非有限"):
        ForecastResult(
            dates=dates,
            mean=np.array([1.0, np.inf]),
            lower=np.array([0.5, 1.5]),
            upper=np.array([1.5, 2.5]),
            alpha=0.05,
            steps=2,
            start=0,
            end=1,
            prediction=object(),
        )


def test_estimation_result_view_exposes_common_summary_without_ts_type():
    view = EstimationResultView(
        model_name="SARIMAX",
        result=object(),
        converged=True,
        effective_nobs=30,
        optimizer="bfgs",
        aic=10.0,
        bic=12.0,
        log_likelihood=-3.0,
        summary="summary",
    )

    assert view.model_name == "SARIMAX"
    assert view.converged is True
    assert view.effective_nobs == 30
    assert view.summary == "summary"


def _inputs() -> ModelingInput:
    dates = pd.date_range("2024-01-01", periods=3, freq="MS")
    return ModelingInput(
        series=pd.Series([1.0, 2.0, 3.0], index=dates, name="target"),
        exog=None,
        index=dates,
        target="target",
    )


def test_sarimax_adapter_is_the_workflow_fit_seam(monkeypatch):
    calls = {}

    def fake_fit(series, exog, config, *, progress_callback=None):
        calls.update(
            series=series,
            exog=exog,
            config=config,
            progress_callback=progress_callback,
        )
        return "fitted"

    monkeypatch.setattr(adapters, "fit_dynamic_model", fake_fit)
    workflow = ModelWorkflow(SARIMAXAdapter())
    config = SARIMAXConfig(order=(1, 0, 0))

    assert workflow.fit(_inputs(), config) == "fitted"
    assert calls["series"].name == "target"
    assert calls["exog"] is None
    assert calls["config"] is config


def test_sarimax_adapter_surfaces_fit_and_result_conversion_failures(monkeypatch):
    def failing_fit(*_args, **_kwargs):
        raise RuntimeError("fit failed")

    monkeypatch.setattr(adapters, "fit_dynamic_model", failing_fit)
    adapter = SARIMAXAdapter()
    with pytest.raises(RuntimeError, match="fit failed"):
        adapter.fit(_inputs(), SARIMAXConfig(order=(1, 0, 0)))

    def failing_summary():
        raise RuntimeError("summary failed")

    result = SimpleNamespace(
        model_type="SARIMAX",
        summary=failing_summary,
    )
    with pytest.raises(RuntimeError, match="summary failed"):
        adapter.result_view(result)


def test_sarimax_adapter_converts_result_and_forecast_to_neutral_views(monkeypatch):
    best = SimpleNamespace(
        model_type="SARIMAX",
        converged=True,
        effective_nobs=3,
        optimizer="bfgs",
        aic=1.0,
        bic=2.0,
        log_likelihood=-0.5,
        summary=lambda: "summary",
    )
    result = SimpleNamespace(best_result=best)
    adapter = SARIMAXAdapter()
    view = adapter.result_view(result)

    assert view.model_name == "SARIMAX"
    assert view.result is result
    assert view.aic == 1.0

    monkeypatch.setattr(
        adapters,
        "produce_forecast",
        lambda *args, **kwargs: {
            "dates": None,
            "mean": np.array([1.0, 2.0]),
            "lower": np.array([0.5, 1.5]),
            "upper": np.array([1.5, 2.5]),
            "alpha": 0.05,
            "steps": 2,
            "start": 3,
            "end": 4,
            "prediction": "prediction",
        },
    )
    forecast = adapter.forecast(
        result,
        ForecastRequest(start=3, end=4),
    )
    assert forecast.steps == 2
    assert forecast.prediction == "prediction"


def test_ardl_adapter_is_a_separate_model_seam(monkeypatch):
    calls = []

    def fake_fit(series, exog, config, *, progress_callback=None):
        calls.append(config)
        return "ardl-fitted"

    monkeypatch.setattr(adapters, "fit_dynamic_model", fake_fit)
    adapter = ARDLAdapter()
    config = ARDLConfig(lags=1, input_orders=(("x", 1),), trend="n")

    assert adapter.fit(_inputs(), config) == "ardl-fitted"
    assert calls == [config]
    with pytest.raises(TypeError, match="ARDL 适配器"):
        adapter.fit(_inputs(), SARIMAXConfig(order=(1, 0, 0)))


def test_ardl_adapter_reuses_the_neutral_forecast_contract(monkeypatch):
    monkeypatch.setattr(
        adapters,
        "produce_forecast",
        lambda *args, **kwargs: {
            "dates": None,
            "mean": np.array([1.0]),
            "lower": np.array([0.5]),
            "upper": np.array([1.5]),
            "alpha": 0.05,
            "steps": 1,
            "start": 3,
            "end": 3,
            "prediction": "ardl-prediction",
        },
    )

    forecast = ARDLAdapter().forecast(
        SimpleNamespace(best_result=object()),
        ForecastRequest(start=3, end=3),
    )

    assert forecast.prediction == "ardl-prediction"
    assert forecast.mean.tolist() == [1.0]


def test_data_input_module_is_configurable_without_sarimax_imports():
    module = create_data_input_module(
        key_prefix="other_model",
        state_namespace="model_analysis.other",
        data_source=BuiltinDataSource("model_analysis.other"),
    )

    assert module.key_prefix == "other_model"
    assert module.state_namespace == "model_analysis.other"
    assert callable(module.render)


def test_common_forecast_table_uses_the_neutral_result_arrays():
    result = ForecastResult(
        dates=pd.date_range("2024-01-01", periods=2, freq="MS"),
        mean=np.array([1.0, 2.0]),
        lower=np.array([0.5, 1.5]),
        upper=np.array([1.5, 2.5]),
        alpha=0.05,
        steps=2,
        start=3,
        end=4,
        prediction=object(),
    )

    table = build_forecast_table(result, actual_values=np.array([0.9, 1.9]))

    assert list(table.columns) == ["真实值", "预测值", "下界", "上界"]
    assert table.index.name == "日期"
    assert table["预测值"].tolist() == [1.0, 2.0]
