"""SARIMAX 模型 core 层逻辑测试（纯计算，不依赖 streamlit）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from Ts.TsSims import simulate_sarima

from dashboard.models.SARIMAX.core.data_loader import (
    build_modeling_dataset,
    load_modeling_dataset,
    numeric_variable_names,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.model_config import (
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    RDLConfig,
    RDLInputConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.core.modeling import (
    build_prediction_table,
    fit_ardl,
    fit_auto_ardl,
    fit_auto_rdl,
    fit_auto_sarimax,
    fit_dynamic_model,
    fit_rdl,
    fit_sarimax,
    produce_forecast,
    run_residual_diagnostics,
    translate_ts_error,
    validate_fit_inputs,
)


class FakeUploader:
    def __init__(self, content: bytes, name: str = "data.csv"):
        self._content = content
        self.name = name

    def getvalue(self) -> bytes:
        return self._content


def make_series(n: int = 80, *, dates: bool = False) -> pd.Series:
    simulated = simulate_sarima(n=n, order=(1, 0, 0), ar=[0.6], seed=42)
    if dates:
        index = pd.date_range("2020-01-01", periods=n, freq="MS")
        return pd.Series(simulated.data, index=index)
    return pd.Series(simulated.data)


# ---------- data_loader ----------


def test_load_modeling_dataset_parses_csv_with_date_column():
    content = b"date,value,other\n2024-01-01,1.0,10\n2024-02-01,2.0,20\n"
    dataset = load_modeling_dataset(FakeUploader(content))

    assert dataset.file_name == "data.csv"
    assert dataset.time_column == "date"
    assert numeric_variable_names(dataset.frame) == ["value", "other"]
    assert dataset.fingerprint.startswith("data.csv:")
    assert len(dataset.fingerprint.rsplit(":", 1)[1]) == 64


def test_load_modeling_dataset_falls_back_to_gbk_encoding():
    content = "日期,销售额\n2024-01-01,100\n2024-02-01,200\n".encode("gbk")
    dataset = load_modeling_dataset(FakeUploader(content, "数据.csv"))

    assert dataset.time_column == "日期"
    assert numeric_variable_names(dataset.frame) == ["销售额"]


def test_build_modeling_dataset_treats_numeric_zero_as_missing():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
            "value": [0.0, 2.0, 0.0],
            "zero_only": [0.0, 0.0, 0.0],
            "label": ["0", "x", "0"],
        }
    )

    dataset = build_modeling_dataset(frame, "data.xlsx", "fingerprint")

    assert dataset.frame["value"].isna().tolist() == [True, False, True]
    assert "zero_only" not in dataset.frame.columns
    assert dataset.frame["label"].tolist() == ["0", "x", "0"]


def test_load_modeling_dataset_rejects_empty_or_non_numeric_files():
    with pytest.raises(ValueError, match="没有可分析的列"):
        load_modeling_dataset(FakeUploader(b"a,b\n,\n,\n", "x.csv"))
    with pytest.raises(ValueError, match="没有数值型变量"):
        content = "name,label\nx,甲\ny,乙\n".encode()
        load_modeling_dataset(FakeUploader(content, "x.csv"))


def test_prepare_modeling_inputs_uses_datetime_index():
    content = b"date,value,x\n2024-01-01,1.0,10\n2024-02-01,2.0,20\n"
    dataset = load_modeling_dataset(FakeUploader(content))
    series, exog, index = prepare_modeling_inputs(dataset, "value", ("x",))

    assert isinstance(index, pd.DatetimeIndex)
    assert series.index.equals(index)
    assert series.name == "value"
    assert exog is not None and list(exog.columns) == ["x"]


def test_prepare_modeling_inputs_falls_back_to_range_index():
    content = b"value,x\n1.0,10\n2.0,20\n"
    dataset = load_modeling_dataset(FakeUploader(content))
    series, _exog, index = prepare_modeling_inputs(dataset, "value", ("x",))

    assert isinstance(index, pd.RangeIndex)
    assert series.tolist() == [1.0, 2.0]


def test_prepare_modeling_inputs_rejects_duplicate_dates():
    content = b"date,value\n2024-01-01,1.0\n2024-01-01,2.0\n"
    dataset = load_modeling_dataset(FakeUploader(content))
    with pytest.raises(ValueError, match="重复"):
        prepare_modeling_inputs(dataset, "value")


def test_prepare_modeling_inputs_rejects_unknown_or_target_exog():
    content = b"date,value,x\n2024-01-01,1.0,10\n2024-02-01,2.0,20\n"
    dataset = load_modeling_dataset(FakeUploader(content))
    with pytest.raises(ValueError, match="不存在"):
        prepare_modeling_inputs(dataset, "value", ("missing",))
    with pytest.raises(ValueError, match="不能同时作为外生变量"):
        prepare_modeling_inputs(dataset, "value", ("value",))


# ---------- model_config ----------


def test_sarimax_config_defaults_and_validation():
    config = SARIMAXConfig()
    assert config.order == (1, 0, 0)
    assert config.signature()[0] == "manual"

    with pytest.raises(ValueError, match="trend"):
        SARIMAXConfig(trend="x")
    with pytest.raises(ValueError, match="p 必须"):
        SARIMAXConfig(order=(9, 0, 0))
    with pytest.raises(ValueError, match="fit_method"):
        SARIMAXConfig(fit_method="trust-ncg")
    with pytest.raises(ValueError, match="cov_type"):
        SARIMAXConfig(cov_type="sandwich")
    with pytest.raises(ValueError, match="maxiter"):
        SARIMAXConfig(maxiter=0)


def test_auto_sarimax_config_candidate_count_and_validation():
    config = AutoSARIMAXConfig(p=(0, 1), d=(0, 0), q=(0, 1))
    assert config.candidate_count() == 4

    seasonal = AutoSARIMAXConfig(
        p=(0, 0), d=(0, 0), q=(0, 0), P=(0, 1), D=(0, 0), Q=(0, 1), s=4
    )
    assert seasonal.candidate_count() == 4

    with pytest.raises(ValueError, match="criterion"):
        AutoSARIMAXConfig(criterion="mdl")
    with pytest.raises(ValueError, match="下限不能大于上限"):
        AutoSARIMAXConfig(p=(3, 1))
    with pytest.raises(TypeError, match="enforce_stationarity"):
        AutoSARIMAXConfig(enforce_stationarity=1)

    unconstrained = AutoSARIMAXConfig(
        p=(0, 0), d=(0, 0), q=(0, 0),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    assert unconstrained.signature()[-2:] == (False, False)


def test_dynamic_regression_configs_capture_all_lag_structure():
    rdl_input = RDLInputConfig(
        "price", numerator_order=2, denominator_order=1, delay=1,
        numerator_lags=(0, 2), denominator_lags=(1,), initialization="zero",
    )
    rdl = RDLConfig(inputs=(rdl_input,))
    assert rdl_input.specification() == ((0, 2), (1,), 1, "zero")
    assert rdl.signature()[0] == "rdl-manual"

    ardl = ARDLConfig(lags=(1, 3), input_orders=(("price", 2),))
    auto = AutoARDLConfig(maxlag=2, max_input_orders=(("price", 3),))
    assert ardl.order_mapping() == {"price": 2}
    assert auto.maxorder_mapping() == {"price": 3}
    with pytest.raises(ValueError, match="至少需要"):
        RDLConfig(inputs=())
    with pytest.raises(ValueError, match="至少需要"):
        ARDLConfig(input_orders=())
    with pytest.raises(TypeError, match="不能为 None"):
        ARDLConfig(input_orders=(("price", None),))
    with pytest.raises(TypeError, match="正整数"):
        SARIMAXConfig(maxiter=1.5)


# ---------- modeling ----------


def test_fit_sarimax_manual_order():
    series = make_series()
    result = fit_sarimax(series, None, SARIMAXConfig(order=(1, 0, 0)))

    assert result.model_type == "SARIMAX"
    assert result.nobs == 80
    assert result.converged
    assert np.isfinite(result.aic)
    assert len(result.params) >= 2  # ar.L1 + sigma2（含常数）
    assert len(result.fitted_values) == 80


def test_fit_sarimax_masks_state_initialization_fitted_values():
    """差分模型初始化期的拟合值应为 NaN，而非 statsmodels 的占位 0。"""
    simulated = simulate_sarima(
        n=60,
        order=(0, 1, 0),
        seed=42,
    )
    series = pd.Series(simulated.data)
    result = fit_sarimax(
        series,
        None,
        SARIMAXConfig(order=(0, 1, 0), trend="n"),
    )

    burn = result.likelihood_burn
    assert burn >= 1
    assert np.isnan(result.fitted_values[0])
    assert np.all(np.isnan(result.fitted_values[:burn]))
    assert np.all(np.isfinite(result.fitted_values[burn:]))
    assert len(result.fitted_values) == result.nobs


def test_fit_sarimax_with_exog():
    series = make_series()
    rng = np.random.default_rng(7)
    exog = pd.DataFrame({"x": rng.normal(size=80)})
    result = fit_sarimax(
        series,
        exog,
        SARIMAXConfig(order=(0, 0, 0), trend="n"),
    )

    assert result.exog_names == ("x",)
    assert "x" in result.params


def test_fit_sarimax_seasonal_order():
    simulated = simulate_sarima(
        n=120,
        order=(1, 0, 0),
        seasonal_order=(1, 0, 0, 4),
        ar=[0.5],
        seasonal_ar=[0.4],
        seed=42,
    )
    series = pd.Series(simulated.data)
    result = fit_sarimax(
        series,
        None,
        SARIMAXConfig(order=(1, 0, 0), seasonal_order=(1, 0, 0, 4)),
    )

    assert result.converged
    assert "Seasonal Order: (1, 0, 0, 4)" in result.summary()
    assert any("ar.S.L4" in name for name in result.params)


def test_fit_sarimax_rejects_too_few_observations():
    series = pd.Series(np.arange(5.0))
    with pytest.raises(ValueError, match="Need at least 10 observations"):
        fit_sarimax(series, None, SARIMAXConfig())


def test_fit_sarimax_rejects_log_with_non_positive_data():
    series = pd.Series([0.0, 1.0, 2.0, 3.0] * 20)
    with pytest.raises(ValueError, match="strictly positive"):
        fit_sarimax(series, None, SARIMAXConfig(log=True))


def test_fit_auto_sarimax_small_grid():
    series = make_series()
    config = AutoSARIMAXConfig(
        p=(0, 1),
        d=(0, 0),
        q=(0, 1),
        P=(0, 0),
        D=(0, 0),
        Q=(0, 0),
    )
    result = fit_auto_sarimax(series, None, config)

    assert len(result.candidate_orders) == config.candidate_count() == 4
    assert result.best_result is not None
    assert len(result.best_order) == 3
    assert len(result.criterion_values) == 4


def test_fit_auto_sarimax_passes_stationarity_constraints():
    config = AutoSARIMAXConfig(
        p=(0, 0), d=(0, 0), q=(0, 0),
        enforce_stationarity=False,
        enforce_invertibility=False,
        trend="n",
    )
    result = fit_auto_sarimax(make_series(), None, config)
    fitted_model = result.best_result._statsmodels_result.model
    assert fitted_model.enforce_stationarity is False
    assert fitted_model.enforce_invertibility is False


def test_fit_rdl_and_auto_rdl_keep_transfer_function_fixed():
    series = make_series()
    exog = pd.DataFrame({"policy": np.linspace(1.0, 3.0, len(series))})
    inputs = (RDLInputConfig("policy", numerator_order=0),)
    manual = fit_rdl(
        series,
        exog,
        RDLConfig(
            inputs=inputs,
            error=SARIMAXConfig(order=(0, 0, 0), trend="n"),
        ),
    )
    assert tuple(manual.distributed_lags) == ("policy",)
    automatic = fit_auto_rdl(
        series,
        exog,
        AutoRDLConfig(
            inputs=inputs,
            error=AutoSARIMAXConfig(
                p=(0, 1), d=(0, 0), q=(0, 0),
                P=(0, 0), D=(0, 0), Q=(0, 0), trend="n",
            ),
        ),
    )
    assert tuple(automatic.best_result.distributed_lags) == ("policy",)


def test_fit_standard_ardl_manual_auto_and_future_input_path():
    series = make_series(dates=True) + 10.0
    exog = pd.DataFrame(
        {"policy": np.linspace(1.0, 3.0, len(series))}, index=series.index
    )
    manual = fit_ardl(
        series,
        exog,
        ARDLConfig(lags=1, input_orders=(("policy", 1),), trend="n"),
    )
    assert manual.ardl_order == (1, 1)
    forecast = produce_forecast(
        manual,
        steps=3,
        future_exog=pd.DataFrame({"policy": [3.1, 3.2, 3.3]}),
    )
    assert len(forecast["mean"]) == 3

    automatic = fit_auto_ardl(
        series,
        exog,
        AutoARDLConfig(
            maxlag=1, max_input_orders=(("policy", 1),), trend="n"
        ),
    )
    assert automatic.best_result is not None
    assert not automatic.criterion_table.empty
    assert fit_dynamic_model(
        series, exog, ARDLConfig(lags=1, input_orders=(("policy", 0),), trend="n")
    ).model_type == "ARDL"


def test_run_residual_diagnostics_table():
    result = fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0)))
    table = run_residual_diagnostics(result, lags=4)

    assert list(table.columns) == ["检验", "统计量", "P值", "结论"]
    assert len(table) == 4
    assert "Ljung-Box" in table.iloc[0]["检验"]
    assert table["P值"].between(0, 1).all()


def test_produce_forecast_with_and_without_dates():
    result = fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0)))
    forecast = produce_forecast(result, steps=5)

    assert len(forecast["mean"]) == 5
    assert forecast["dates"] is None
    assert np.all(forecast["lower"] <= forecast["mean"])
    assert np.all(forecast["mean"] <= forecast["upper"])

    dated = fit_sarimax(
        make_series(dates=True),
        None,
        SARIMAXConfig(order=(1, 0, 0)),
    )
    dated_forecast = produce_forecast(dated, steps=3)
    assert len(dated_forecast["dates"]) == 3
    assert dated_forecast["dates"][0] == pd.Timestamp("2026-09-01")


def test_produce_forecast_requires_positive_steps():
    result = fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0)))
    with pytest.raises(ValueError, match="预测期数"):
        produce_forecast(result, steps=0)
    with pytest.raises(TypeError, match="正整数"):
        produce_forecast(result, steps=1.5)


def test_produce_forecast_rejects_wrong_future_exog_columns():
    series = make_series()
    rng = np.random.default_rng(7)
    exog = pd.DataFrame({"x": rng.normal(size=80)})
    result = fit_sarimax(
        series,
        exog,
        SARIMAXConfig(order=(0, 0, 0), trend="n"),
    )
    wrong = pd.DataFrame({"y": rng.normal(size=5)})
    with pytest.raises(ValueError, match="columns"):
        produce_forecast(result, steps=5, future_exog=wrong)


def test_produce_forecast_accepts_one_based_future_exog_index():
    """无日期模型允许未来外生变量使用第 1 期起的 RangeIndex 标签。"""
    series = make_series()
    rng = np.random.default_rng(7)
    exog = pd.DataFrame({"x": rng.normal(size=80)})
    result = fit_sarimax(
        series,
        exog,
        SARIMAXConfig(order=(0, 0, 0), trend="n"),
    )
    future = pd.DataFrame(
        {"x": rng.normal(size=5)},
        index=pd.RangeIndex(1, 6),
    )
    forecast = produce_forecast(result, steps=5, future_exog=future)

    assert len(forecast["mean"]) == 5
    assert np.all(forecast["lower"] <= forecast["mean"])


def test_build_prediction_table():
    result = fit_sarimax(make_series(dates=True), None, SARIMAXConfig(order=(1, 0, 0)))
    forecast = produce_forecast(result, steps=4)
    table = build_prediction_table(forecast)

    assert table.shape == (4, 3)
    assert list(table.columns) == ["预测值", "下界", "上界"]
    assert table.index.name == "日期"

    undated = produce_forecast(
        fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0))),
        steps=3,
    )
    assert build_prediction_table(undated).index.name == "期数"


def test_translate_ts_error_maps_known_fragments():
    message = translate_ts_error(
        ValueError(
            "SARIMAX optimization failed to converge with method='bfgs' "
            "within maxiter=50"
        )
    )
    assert "未收敛" in message

    assert translate_ts_error(ValueError("unknown failure")) == "unknown failure"


def test_validate_fit_inputs_reports_user_problems():
    config = SARIMAXConfig(log=True)
    short = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    problems = validate_fit_inputs(short, None, config)
    assert any("样本量不足" in problem for problem in problems)

    non_positive = pd.Series(np.arange(20.0))
    problems = validate_fit_inputs(non_positive, None, config)
    assert any("非正值" in problem for problem in problems)

    seasonal = SARIMAXConfig(seasonal_order=(0, 0, 0, 12))
    problems = validate_fit_inputs(short, None, seasonal)
    assert any("季节周期" in problem for problem in problems)

    series = make_series()
    shifted = pd.DataFrame({"x": np.arange(80.0)}, index=pd.RangeIndex(1, 81))
    problems = validate_fit_inputs(series, shifted, SARIMAXConfig())
    assert any("索引不一致" in problem for problem in problems)

    assert validate_fit_inputs(series, None, SARIMAXConfig()) == []


def test_dynamic_regression_validation_rejects_missing_and_no_input():
    series = make_series()
    config = ARDLConfig(lags=1, input_orders=(("x", 0),))
    missing = pd.DataFrame({"x": np.arange(len(series), dtype=float)})
    missing.iloc[5, 0] = np.nan
    problems = validate_fit_inputs(series, missing, config)
    assert any("非连续" in problem for problem in problems)
    assert any("至少需要" in problem for problem in validate_fit_inputs(series, None, config))
