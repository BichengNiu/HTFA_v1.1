"""SARIMAX 模型 core 层逻辑测试（纯计算，不依赖 streamlit）。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from data_overview.core.dataset import OverviewDataset, build_overview_dataset
from data_overview.core.file_parsing import load_dataframe
from statsmodels.tsa.statespace.sarimax import SARIMAX as StatsmodelsSARIMAX
from Ts.TsModels import TimeSeriesOperator
from Ts.TsSims import simulate_sarima

from dashboard.core.workspace import stable_signature
from dashboard.models.SARIMAX.core.data_loader import (
    MISSING_VALUE_OPTIONS,
    dataset_time_index,
    effective_modeling_date_bounds,
    forecast_sample_dates,
    preprocess_modeling_frame,
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
    build_auto_sarimax_criterion_table,
    build_prediction_table,
    fit_ardl,
    fit_auto_ardl,
    fit_auto_rdl,
    fit_auto_sarimax,
    fit_dynamic_model,
    fit_input_warnings,
    fit_rdl,
    fit_sarimax,
    format_sarimax_order,
    produce_forecast,
    recommended_residual_diagnostic_lags,
    run_residual_diagnostics,
    select_auto_sarimax_candidate,
    select_auto_sarimax_result,
    translate_ts_error,
    validate_fit_inputs,
)
from dashboard.models.SARIMAX.core.forecast_planning import (
    build_forecast_calendar,
    build_future_exog,
    normalise_date_window,
    resolve_prediction_positions,
    serialise_frame,
)
def make_series(n: int = 80, *, dates: bool = False) -> pd.Series:
    simulated = simulate_sarima(n=n, order=(1, 0, 0), ar=[0.6], seed=42)
    if dates:
        index = pd.date_range("2020-01-01", periods=n, freq="MS")
        return pd.Series(simulated.data, index=index)
    return pd.Series(simulated.data)


def dataset_from_csv(content: bytes) -> OverviewDataset:
    frame = load_dataframe(content, "data.csv")
    return build_overview_dataset(frame, "data.csv", "fingerprint")


def test_prepare_modeling_inputs_uses_datetime_index():
    content = b"date,value,x\n2024-01-01,1.0,10\n2024-02-01,2.0,20\n"
    dataset = dataset_from_csv(content)
    series, exog, index = prepare_modeling_inputs(dataset, "value", ("x",))

    assert isinstance(index, pd.DatetimeIndex)
    assert series.index.equals(index)
    assert series.name == "value"
    assert exog is not None and list(exog.columns) == ["x"]


def test_forecast_sample_dates_stays_inside_dataset_boundary():
    """预测样本只返回训练结束日之后的数据集日期，不生成外推日期。"""
    dataset = dataset_from_csv(
        b"date,value\n"
        b"2024-03-01,3.0\n"
        b"2024-01-01,1.0\n"
        b"2024-02-01,2.0\n"
    )

    assert dataset_time_index(dataset).equals(
        pd.DatetimeIndex(["2024-01-01", "2024-02-01", "2024-03-01"])
    )
    assert forecast_sample_dates(dataset, pd.Timestamp("2024-01-15")).equals(
        pd.DatetimeIndex(["2024-02-01", "2024-03-01"])
    )


def test_forecast_planning_builds_calendar_and_normalises_window():
    dates = pd.date_range("2020-01-01", periods=5, freq="MS")
    dataset = build_overview_dataset(
        pd.DataFrame(
            {
                "date": dates,
                "target": [10, 11, 12, 13, 14],
            }
        ),
        "planning.csv",
        "fingerprint",
    )
    result = SimpleNamespace(nobs=3, dates=dates[:3])

    calendar = build_forecast_calendar(
        dataset,
        result.dates,
        dates[2],
        extension_periods=2,
    )
    assert calendar.model_dates.equals(dates[:3])
    assert calendar.base_dates.equals(dates)
    assert calendar.dates.equals(
        pd.date_range("2020-01-01", periods=7, freq="MS")
    )

    options = tuple(value.date() for value in calendar.dates)
    window = normalise_date_window((options[1], options[5]), options)
    assert window == (options[1], options[5])
    assert resolve_prediction_positions(calendar.dates, window) == (1, 5)

    frame = pd.DataFrame({"x": [1.0, np.nan]})
    assert serialise_frame(frame) == {
        "columns": ["x"],
        "values": [[1.0], [None]],
    }


def test_forecast_chart_date_adapter_preserves_ts_actual_values(monkeypatch):
    """Date adaptation must not replace Ts' model-aligned Actual y values."""
    import matplotlib.pyplot as plt
    from Ts.TsModels._base import PredictResult

    import dashboard.models.SARIMAX.ui.pages.sections.forecast_chart as chart
    from dashboard.models.common.contracts import ForecastResult

    calendar = pd.DatetimeIndex(["2024-01-01", "2024-02-01", "2024-03-01"])
    prediction = PredictResult(
        mean=np.array([10.0, 20.0, 30.0]),
        lower=np.array([9.0, 19.0, 29.0]),
        upper=np.array([11.0, 21.0, 31.0]),
        is_oos=np.array([False, False, False]),
        _full_data=np.array([10.0, 20.0, 30.0]),
        _full_fitted=np.array([10.5, 19.5, 30.5]),
        _start=0,
    )
    captured = {}
    monkeypatch.setattr(
        chart,
        "render_pyplot_figure",
        lambda _st_obj, figure, **_kwargs: captured.setdefault("figure", figure),
    )

    chart.render_forecast_chart(
        SimpleNamespace(warning=lambda _message: None),
        calendar,
        ForecastResult(
            dates=calendar,
            mean=np.array([10.0, 20.0, 30.0]),
            lower=np.array([9.0, 19.0, 29.0]),
            upper=np.array([11.0, 21.0, 31.0]),
            alpha=0.05,
            steps=3,
            start=0,
            end=2,
            prediction=prediction,
        ),
        target="sales",
    )

    axis = captured["figure"].axes[0]
    actual = next(line for line in axis.lines if line.get_label() == "Actual")
    assert np.array_equal(actual.get_ydata(), np.array([10.0, 20.0, 30.0]))
    assert len(actual.get_xdata()) == len(calendar)
    plt.close(actual.figure)


def test_forecast_chart_uses_target_ylabel_without_titles(monkeypatch):
    """Forecast chart labels use the target variable and omit both titles."""
    import matplotlib.pyplot as plt
    from Ts.TsModels._base import PredictResult

    import dashboard.models.SARIMAX.ui.pages.sections.forecast_chart as chart
    from dashboard.models.common.contracts import ForecastResult

    calendar = pd.DatetimeIndex(["2024-01-01", "2024-02-01", "2024-03-01"])
    prediction = PredictResult(
        mean=np.array([10.0, 20.0, 30.0]),
        lower=np.array([9.0, 19.0, 29.0]),
        upper=np.array([11.0, 21.0, 31.0]),
        is_oos=np.array([False, False, False]),
        _full_data=np.array([10.0, 20.0, 30.0]),
        _full_fitted=np.array([10.5, 19.5, 30.5]),
        _start=0,
    )
    captured = {}
    monkeypatch.setattr(
        chart,
        "render_pyplot_figure",
        lambda _st_obj, figure, **_kwargs: captured.setdefault("figure", figure),
    )

    chart.render_forecast_chart(
        SimpleNamespace(warning=lambda _message: None),
        calendar,
        ForecastResult(
            dates=calendar,
            mean=np.array([10.0, 20.0, 30.0]),
            lower=np.array([9.0, 19.0, 29.0]),
            upper=np.array([11.0, 21.0, 31.0]),
            alpha=0.05,
            steps=3,
            start=0,
            end=2,
            prediction=prediction,
        ),
        target="sales",
    )

    axis = captured["figure"].axes[0]
    assert axis.get_title() == ""
    assert axis.get_xlabel() == ""
    assert axis.get_ylabel() == "sales"
    plt.close(axis.figure)


def test_forecast_chart_autoscales_y_to_selected_date_window(monkeypatch):
    """Date-window adaptation keeps the forecast y-axis local to the window."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    from Ts.TsModels._base import PredictResult
    from Ts.TsPlots.style import GRAY

    import dashboard.models.SARIMAX.ui.pages.sections.forecast_chart as chart
    from dashboard.models.common.contracts import ForecastResult

    calendar = pd.date_range("2024-01-01", periods=4, freq="MS")
    prediction = PredictResult(
        mean=np.array([10.0, 11.0]),
        lower=np.array([9.0, 10.0]),
        upper=np.array([11.0, 12.0]),
        is_oos=np.array([False, True]),
        _full_data=np.array([1000.0, 10.0, 11.0, 2000.0]),
        _full_fitted=np.array([900.0, 10.5, 11.5, 1900.0]),
        _full_lower=np.array([800.0, 9.5, 10.5, 1800.0]),
        _full_upper=np.array([1000.0, 11.5, 12.5, 2000.0]),
        _start=1,
    )
    captured = {}
    monkeypatch.setattr(
        chart,
        "render_pyplot_figure",
        lambda _st_obj, figure, **_kwargs: captured.setdefault("figure", figure),
    )

    chart.render_forecast_chart(
        SimpleNamespace(warning=lambda _message: None),
        calendar,
        ForecastResult(
            dates=calendar[1:3],
            mean=np.array([10.0, 11.0]),
            lower=np.array([9.0, 10.0]),
            upper=np.array([11.0, 12.0]),
            alpha=0.05,
            steps=2,
            start=1,
            end=2,
            prediction=prediction,
        ),
        target="sales",
        show_confidence_interval=True,
    )

    axis = captured["figure"].axes[0]
    lower, upper = axis.get_ylim()
    assert lower < 10.0
    assert upper > 11.5
    assert upper < 100.0
    assert len(axis.collections) == 1
    collection = axis.collections[0]
    assert np.allclose(collection.get_facecolor()[0][:3], to_rgb(GRAY))
    vertices = collection.get_paths()[0].vertices
    x_min, x_max = axis.get_xlim()
    assert np.all((vertices[:, 0] >= x_min) & (vertices[:, 0] <= x_max))
    legend_labels = [text.get_text() for text in axis.get_legend().get_texts()]
    assert "Fitted 95% CI" not in legend_labels
    assert "Forecast 95% CI" in legend_labels
    plt.close(axis.figure)


def test_prepare_modeling_inputs_sorts_dates_and_keeps_exog_aligned():
    content = (
        b"date,value,x\n"
        b"2024-03-01,3.0,30\n"
        b"2024-01-01,1.0,10\n"
        b"2024-02-01,2.0,20\n"
    )
    dataset = dataset_from_csv(content)

    series, exog, index = prepare_modeling_inputs(dataset, "value", ("x",))

    expected = pd.DatetimeIndex(
        ["2024-01-01", "2024-02-01", "2024-03-01"]
    )
    assert index.equals(expected)
    assert series.index.equals(expected)
    assert series.tolist() == [1.0, 2.0, 3.0]
    assert exog is not None and exog.index.equals(expected)
    assert exog["x"].tolist() == [10.0, 20.0, 30.0]


def test_prepare_modeling_inputs_filters_datetime_range_inclusively():
    content = (
        b"date,value,x\n"
        b"2024-01-01,1.0,10\n"
        b"2024-02-01,2.0,20\n"
        b"2024-03-01,3.0,30\n"
        b"2024-04-01,4.0,40\n"
    )
    dataset = dataset_from_csv(content)

    series, exog, index = prepare_modeling_inputs(
        dataset,
        "value",
        ("x",),
        time_range=(pd.Timestamp("2024-02-01"), pd.Timestamp("2024-03-01")),
    )

    expected = pd.DatetimeIndex(["2024-02-01", "2024-03-01"])
    assert index.equals(expected)
    assert series.index.equals(expected)
    assert series.tolist() == [2.0, 3.0]
    assert exog is not None and exog.index.equals(expected)
    assert exog["x"].tolist() == [20.0, 30.0]


@pytest.mark.parametrize(
    ("preprocessing", "expected_target", "expected_exog"),
    [
        (("去零",), [np.nan, -1.0, 2.0], [10.0, np.nan, -2.0]),
        (("去负",), [0.0, np.nan, 2.0], [10.0, 0.0, np.nan]),
        (("去零", "去负"), [np.nan, np.nan, 2.0], [10.0, np.nan, np.nan]),
    ],
)
def test_prepare_modeling_inputs_applies_preprocessing(
    preprocessing, expected_target, expected_exog
):
    """数据预处理将选定的 0/负值转换为缺失并保持目标外生对齐。"""
    dataset = dataset_from_csv(
        b"date,value,x\n"
        b"2024-01-01,0,10\n"
        b"2024-02-01,-1,0\n"
        b"2024-03-01,2,-2\n"
    )
    original = dataset.frame.copy(deep=True)

    series, exog, index = prepare_modeling_inputs(
        dataset,
        "value",
        ("x",),
        preprocessing=preprocessing,
    )

    assert index.equals(series.index)
    assert series.tolist() == pytest.approx(expected_target, nan_ok=True)
    assert exog is not None
    assert exog.index.equals(index)
    assert exog["x"].tolist() == pytest.approx(expected_exog, nan_ok=True)
    pd.testing.assert_frame_equal(dataset.frame, original)


def test_prepare_modeling_inputs_rejects_unknown_preprocessing():
    """数据预处理选项必须来自受支持的固定集合。"""
    dataset = dataset_from_csv(b"value,x\n1,2\n2,3\n")

    with pytest.raises(ValueError, match="数据预处理"):
        prepare_modeling_inputs(dataset, "value", ("x",), preprocessing=("未知",))


@pytest.mark.parametrize("method", MISSING_VALUE_OPTIONS)
def test_prepare_modeling_inputs_applies_missing_value_method(method):
    """缺失值处理规则同时作用于目标和外生变量且不修改源数据。"""
    dataset = dataset_from_csv(
        b"date,value,x\n"
        b"2024-01-01,1,10\n"
        b"2024-02-01,,20\n"
        b"2024-03-01,3,\n"
        b"2024-04-01,,40\n"
        b"2024-05-01,5,50\n"
        b"2024-06-01,6,60\n"
    )
    original = dataset.frame.copy(deep=True)

    series, exog, index = prepare_modeling_inputs(
        dataset,
        "value",
        ("x",),
        missing_value_method=method,
    )

    assert series.index.equals(index)
    assert exog is not None and exog.index.equals(index)
    if method == "无":
        assert series.isna().sum() == 2
        assert exog.isna().sum().sum() == 1
    else:
        assert series.notna().all()
        assert exog.notna().all().all()
    pd.testing.assert_frame_equal(dataset.frame, original)


def test_prepare_modeling_inputs_rejects_unknown_missing_value_method():
    """缺失值处理方式必须来自固定选项集合。"""
    dataset = dataset_from_csv(b"value,x\n1,2\n2,3\n")

    with pytest.raises(ValueError, match="缺失值处理"):
        prepare_modeling_inputs(
            dataset,
            "value",
            ("x",),
            missing_value_method="未知",
        )


def test_preprocess_modeling_frame_applies_rules_before_model_selection():
    """数据输入阶段处理整张数值表，且不修改原始数据框。"""
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3, freq="MS"),
            "value": [0.0, 2.0, 4.0],
            "x": [1.0, np.nan, 3.0],
            "label": ["a", "b", "c"],
        }
    )
    original = frame.copy(deep=True)

    processed = preprocess_modeling_frame(
        frame,
        preprocessing=("去零",),
        missing_value_method="线性内插",
    )

    assert pd.isna(processed.loc[0, "value"])
    assert processed["x"].tolist() == [1.0, 2.0, 3.0]
    assert processed["label"].tolist() == ["a", "b", "c"]
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("method", MISSING_VALUE_OPTIONS)
def test_preprocess_modeling_frame_keeps_missing_values_outside_valid_span(method):
    """缺失值处理只覆盖替换后的首末有效值之间。"""
    frame = pd.DataFrame(
        {
            "value": [
                0.0,
                1.0,
                np.nan,
                3.0,
                -1.0,
                5.0,
                np.nan,
                7.0,
                np.nan,
                0.0,
            ],
            "x": [
                np.nan,
                10.0,
                np.nan,
                30.0,
                np.nan,
                50.0,
                np.nan,
                70.0,
                np.nan,
                0.0,
            ],
        }
    )

    processed = preprocess_modeling_frame(
        frame,
        preprocessing=("去零", "去负"),
        missing_value_method=method,
    )

    # 去零/去负发生在前，替换后首个有效值为第 2 行，最后一个有效值为第 8 行。
    assert processed["value"].iloc[[0, 8, 9]].isna().all()
    assert processed["x"].iloc[[0, 8, 9]].isna().all()
    if method == "无":
        assert processed["value"].iloc[[2, 4, 6]].isna().all()
        assert processed["x"].iloc[[2, 4, 6]].isna().all()
    else:
        assert processed["value"].iloc[[2, 4, 6]].notna().all()
        assert processed["x"].iloc[[2, 4, 6]].notna().all()


def test_effective_modeling_date_bounds_use_common_preprocessed_dates():
    """训练范围按目标和外生变量预处理后的共同有效日期确定。"""
    dataset = dataset_from_csv(
        b"date,value,x\n"
        b"2024-01-01,0,1\n"
        b"2024-02-01,10,2\n"
        b"2024-03-01,11,0\n"
        b"2024-04-01,12,3\n"
        b"2024-05-01,-1,4\n"
        b"2024-06-01,14,5\n"
    )

    bounds = effective_modeling_date_bounds(
        dataset,
        "value",
        ("x",),
        preprocessing=("去零", "去负"),
    )

    assert bounds == (pd.Timestamp("2024-02-01"), pd.Timestamp("2024-06-01"))


def test_prepare_modeling_inputs_falls_back_to_range_index():
    content = b"value,x\n1.0,10\n2.0,20\n"
    dataset = dataset_from_csv(content)
    series, _exog, index = prepare_modeling_inputs(dataset, "value", ("x",))

    assert isinstance(index, pd.RangeIndex)
    assert series.tolist() == [1.0, 2.0]


def test_prepare_modeling_inputs_rejects_invalid_time_range():
    dated = dataset_from_csv(
        b"date,value\n2024-01-01,1.0\n2024-02-01,2.0\n"
    )
    with pytest.raises(ValueError, match="起始日期不能晚于结束日期"):
        prepare_modeling_inputs(
            dated,
            "value",
            time_range=(pd.Timestamp("2024-02-01"), pd.Timestamp("2024-01-01")),
        )

    undated = dataset_from_csv(b"value\n1.0\n2.0\n")
    with pytest.raises(ValueError, match="没有日期列"):
        prepare_modeling_inputs(
            undated,
            "value",
            time_range=(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")),
        )


def test_prepare_modeling_inputs_rejects_duplicate_dates():
    content = b"date,value\n2024-01-01,1.0\n2024-01-01,2.0\n"
    dataset = dataset_from_csv(content)
    with pytest.raises(ValueError, match="重复"):
        prepare_modeling_inputs(dataset, "value")


def test_prepare_modeling_inputs_rejects_unknown_or_target_exog():
    content = b"date,value,x\n2024-01-01,1.0,10\n2024-02-01,2.0,20\n"
    dataset = dataset_from_csv(content)
    with pytest.raises(ValueError, match="不存在"):
        prepare_modeling_inputs(dataset, "value", ("missing",))
    with pytest.raises(ValueError, match="不能同时作为外生变量"):
        prepare_modeling_inputs(dataset, "value", ("value",))


# ---------- model_config ----------


def test_sarimax_config_defaults_and_validation():
    config = SARIMAXConfig()
    assert config.order == (1, 0, 0)
    assert config.enforce_stationarity is False
    assert config.enforce_invertibility is False
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


def test_sarimax_config_supports_sparse_orders_and_exog_operators():
    """手动配置保留 Ts 的稀疏 ARMA 语义与逐变量算子。"""
    config = SARIMAXConfig(
        order=((1, 3), 0, (1, 3)),
        seasonal_order=((1, 2), 0, (1,), 12),
        exog_operators={"x": TimeSeriesOperator(lag=1, difference=1)},
    )

    assert config.order == ((1, 3), 0, (1, 3))
    assert config.seasonal_order == ((1, 2), 0, (1,), 12)
    assert config.operator_mapping() == {
        "x": TimeSeriesOperator(lag=1, difference=1)
    }
    assert config.signature() != SARIMAXConfig().signature()
    with pytest.raises(ValueError, match="p 必须"):
        SARIMAXConfig(order=((0, 3), 0, 0))
    with pytest.raises(ValueError, match="Q 必须"):
        SARIMAXConfig(seasonal_order=(0, 0, (4,), 12))


@pytest.mark.parametrize("config_type", [SARIMAXConfig, AutoSARIMAXConfig])
def test_sarimax_config_signature_serializes_exog_operators(config_type):
    """外生变量算子签名必须可被会话缓存签名稳定序列化。"""
    config = config_type(
        exog_operators={"x": TimeSeriesOperator(lag=1, difference=1)}
    )

    signature = stable_signature(config.signature())
    changed = stable_signature(
        config_type(
            exog_operators={"x": TimeSeriesOperator(lag=2, difference=1)}
        ).signature()
    )
    logged = stable_signature(
        config_type(
            exog_operators={"x": TimeSeriesOperator(lag=1, difference=1, log=True)}
        ).signature()
    )

    assert signature != changed
    assert signature != logged


def test_auto_sarimax_config_candidate_count_and_validation():
    config = AutoSARIMAXConfig(p=(0, 1), d=(0, 0), q=(0, 1))
    assert config.candidate_count() == 4
    assert config.enforce_stationarity is False
    assert config.enforce_invertibility is False

    seasonal = AutoSARIMAXConfig(
        p=(0, 0), d=(0, 0), q=(0, 0), P=(0, 1), D=(0, 0), Q=(0, 1), s=252
    )
    assert seasonal.candidate_count() == 4
    manual_seasonal = SARIMAXConfig(seasonal_order=(1, 0, 1, 252))
    assert manual_seasonal.seasonal_order == (1, 0, 1, 252)

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


def test_format_sarimax_order_includes_complete_seasonal_order():
    """SARIMAX 结果标签同时显示非季节和季节四元组。"""
    assert format_sarimax_order((2, 0, 1), (1, 0, 1, 252)) == (
        "SARIMAX(2, 0, 1)(1, 0, 1, 252)"
    )
    assert format_sarimax_order((2, 0, 1)) == (
        "SARIMAX(2, 0, 1)(0, 0, 0, 0)"
    )


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


def test_htfa_sarimax_matches_direct_statsmodels_for_same_data_and_config():
    """相同输入和设置下，HTFA 不得改变 statsmodels 的 SARIMAX 结果。"""
    rng = np.random.default_rng(20260831)
    log_data = np.log(1000.0) + np.cumsum(
        0.001 + rng.normal(0.0, 0.01, size=100)
    )
    series = pd.Series(np.exp(log_data))
    config = SARIMAXConfig(
        order=(1, 1, 1),
        trend="c",
        log=True,
        enforce_stationarity=False,
        enforce_invertibility=False,
        fit_method="bfgs",
        maxiter=500,
        cov_type="oim",
    )

    htfa = fit_sarimax(series, None, config)
    direct = StatsmodelsSARIMAX(
        np.log(series.to_numpy(dtype=float)),
        order=config.order,
        seasonal_order=config.seasonal_order,
        trend=config.trend,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
        missing="drop",
    ).fit(
        method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
        disp=False,
    )
    htfa_raw = htfa._statsmodels_result

    assert htfa_raw.param_names == direct.param_names
    np.testing.assert_array_equal(htfa_raw.params, direct.params)
    np.testing.assert_array_equal(htfa_raw.fittedvalues, direct.fittedvalues)
    np.testing.assert_array_equal(htfa_raw.resid, direct.resid)
    assert htfa_raw.llf == direct.llf
    assert htfa_raw.aic == direct.aic
    assert htfa_raw.bic == direct.bic
    assert htfa.likelihood_burn == direct.loglikelihood_burn

    start = htfa.likelihood_burn
    end = htfa.nobs + 4
    forecast = produce_forecast(htfa, start=start, end=end, alpha=0.05)
    direct_prediction = direct.get_prediction(start=start, end=end)
    direct_frame = direct_prediction.summary_frame(alpha=0.05)
    direct_mean = np.asarray(direct_frame["mean"], dtype=float)
    direct_variance = np.asarray(direct_prediction.var_pred_mean, dtype=float)
    expected_mean = np.exp(direct_mean + 0.5 * direct_variance)
    expected_lower = np.exp(
        np.asarray(direct_frame["mean_ci_lower"], dtype=float)
    )
    expected_upper = np.exp(
        np.asarray(direct_frame["mean_ci_upper"], dtype=float)
    )
    np.testing.assert_array_equal(forecast["mean"], expected_mean)
    np.testing.assert_array_equal(forecast["lower"], expected_lower)
    np.testing.assert_array_equal(forecast["upper"], expected_upper)


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


def test_fit_sarimax_passes_exog_time_operators_to_ts():
    """HTFA 只传递原始路径，实际变换由 Ts 统一完成。"""
    series = make_series()
    exog = pd.DataFrame({"x": np.arange(len(series), dtype=float)})
    config = SARIMAXConfig(
        order=(0, 0, 0),
        trend="n",
        exog_operators={"x": TimeSeriesOperator(lag=1)},
    )

    result = fit_sarimax(series, exog, config)

    assert result.exog_operators == {"x": TimeSeriesOperator(lag=1)}
    assert result.nobs == len(series) - 1


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


def test_fit_auto_sarimax_passes_exog_time_operators_to_ts():
    series = make_series()
    exog = pd.DataFrame({"x": np.arange(len(series), dtype=float)})
    config = AutoSARIMAXConfig(
        p=(0, 0),
        d=(0, 0),
        q=(0, 0),
        P=(0, 0),
        D=(0, 0),
        Q=(0, 0),
        trend="n",
        exog_operators={"x": TimeSeriesOperator(difference=1)},
    )

    result = fit_auto_sarimax(series, exog, config)

    assert result.best_result.exog_operators == {
        "x": TimeSeriesOperator(difference=1)
    }


def test_fit_auto_sarimax_searches_all_seasonal_orders_when_period_is_set():
    """设置 S 后，P/D/Q 的每个组合都进入自动搜索。"""
    config = AutoSARIMAXConfig(
        p=(0, 0),
        d=(0, 0),
        q=(0, 0),
        P=(0, 1),
        D=(0, 1),
        Q=(0, 1),
        s=4,
        trend="n",
    )
    result = fit_auto_sarimax(make_series(n=100), None, config)

    assert config.candidate_count() == 8
    assert result.n_attempted == 8
    assert len(result.candidate_seasonal_orders) == 8
    assert set(result.candidate_seasonal_orders) == {
        (P, D, Q, 4)
        for P in range(2)
        for D in range(2)
        for Q in range(2)
    }


def test_auto_sarimax_criterion_table_and_post_selection():
    result = fit_auto_sarimax(
        make_series(),
        None,
        AutoSARIMAXConfig(
            p=(0, 1),
            d=(0, 0),
            q=(0, 1),
            P=(0, 0),
            D=(0, 0),
            Q=(0, 0),
        ),
    )

    table = build_auto_sarimax_criterion_table(result)
    assert list(table.columns) == ["模型", "AIC", "BIC", "HQIC", "AICC"]
    assert len(table) == len(result.candidate_results)

    selected = select_auto_sarimax_result(result, "bic")
    expected_index = int(table["BIC"].idxmin())
    assert selected.selection_criterion == "bic"
    assert selected.best_order == result.candidate_orders[expected_index]
    assert selected.search_metadata == result.search_metadata
    assert selected.search_metadata["mode"] == "serial"

    selected_candidate = select_auto_sarimax_candidate(result, 0)
    assert selected_candidate.best_order == result.candidate_orders[0]
    assert selected_candidate.selection_criterion == result.selection_criterion


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
    assert automatic.search_metadata["mode"] == "serial"


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
        start=manual.nobs,
        end=manual.nobs + 2,
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


def test_recommended_residual_diagnostic_lags_uses_effective_residual_count():
    assert recommended_residual_diagnostic_lags(30) == 6
    assert recommended_residual_diagnostic_lags(80) == 10


def test_produce_forecast_with_and_without_dates():
    result = fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0)))
    forecast = produce_forecast(result, start=result.nobs, end=result.nobs + 4)

    assert len(forecast["mean"]) == 5
    assert forecast["dates"] is None
    assert np.all(forecast["lower"] <= forecast["mean"])
    assert np.all(forecast["mean"] <= forecast["upper"])

    dated = fit_sarimax(
        make_series(dates=True),
        None,
        SARIMAXConfig(order=(1, 0, 0)),
    )
    dated_forecast = produce_forecast(dated, start=dated.nobs, end=dated.nobs + 2)
    assert len(dated_forecast["dates"]) == 3
    assert dated_forecast["dates"][0] == pd.Timestamp("2026-09-01")


def test_produce_forecast_supports_explicit_window_without_steps_compatibility():
    result = fit_sarimax(
        make_series(dates=True),
        None,
        SARIMAXConfig(order=(1, 0, 0)),
    )
    forecast = produce_forecast(
        result,
        start=result.nobs + 2,
        end=result.nobs + 4,
    )

    assert forecast["steps"] == 3
    assert list(forecast["dates"]) == [
        pd.Timestamp("2026-11-01"),
        pd.Timestamp("2026-12-01"),
        pd.Timestamp("2027-01-01"),
    ]


def test_produce_forecast_accepts_explicit_dates_for_irregular_model_dates():
    """缺失值导致日期不连续时，预测可使用外部推断出的未来日历。"""
    dates = pd.date_range("2020-01-01", periods=20, freq="MS")
    values = np.arange(20.0)
    values[[2, 5, 9]] = np.nan
    result = fit_sarimax(
        pd.Series(values, index=dates),
        None,
        SARIMAXConfig(order=(1, 0, 0), trend="n"),
    )
    forecast_dates = pd.date_range("2021-09-01", periods=3, freq="MS")

    forecast = produce_forecast(
        result,
        start=result.nobs,
        end=result.nobs + 2,
        future_dates=forecast_dates,
    )

    assert list(forecast["dates"]) == list(forecast_dates)


def test_future_exog_path_is_prefilled_from_dataset():
    dates = pd.date_range("2020-01-01", periods=5, freq="MS")
    dataset = build_overview_dataset(
        pd.DataFrame(
            {
                "date": dates,
                "target": [10, 11, 12, 13, 14],
                "policy": [1, 2, 3, 4, 5],
            }
        ),
        "future.csv",
        "fingerprint",
    )
    best = SimpleNamespace(nobs=3, dates=dates[:3])

    future = build_future_exog(
        dataset,
        best.nobs,
        best.dates,
        total_steps=2,
        source_columns=("policy",),
        exog_names=("policy",),
    )

    assert list(future.index) == list(dates[3:5])
    assert future["policy"].tolist() == [4.0, 5.0]


def test_produce_forecast_requires_valid_window():
    result = fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0)))
    with pytest.raises(ValueError):
        produce_forecast(result, start=result.nobs + 1, end=result.nobs)
    with pytest.raises(TypeError):
        produce_forecast(result, steps=3)


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
        produce_forecast(
            result,
            start=result.nobs,
            end=result.nobs + 4,
            future_exog=wrong,
        )


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
    forecast = produce_forecast(
        result,
        start=result.nobs,
        end=result.nobs + 4,
        future_exog=future,
    )

    assert len(forecast["mean"]) == 5
    assert np.all(forecast["lower"] <= forecast["mean"])


def test_build_prediction_table():
    result = fit_sarimax(make_series(dates=True), None, SARIMAXConfig(order=(1, 0, 0)))
    forecast = produce_forecast(result, start=result.nobs, end=result.nobs + 3)
    table = build_prediction_table(forecast)

    assert table.shape == (4, 3)
    assert list(table.columns) == ["预测值", "下界", "上界"]
    assert table.index.name == "日期"

    undated = produce_forecast(
        fit_sarimax(make_series(), None, SARIMAXConfig(order=(1, 0, 0))),
        start=result.nobs,
        end=result.nobs + 2,
    )
    undated_table = build_prediction_table(undated)
    assert undated_table.index.name == "期数"
    assert list(undated_table.index) == [81, 82, 83]


def test_translate_ts_error_maps_known_fragments():
    message = translate_ts_error(
        ValueError(
            "SARIMAX optimization failed to converge with method='bfgs' "
            "within maxiter=50"
        )
    )
    assert "未收敛" in message

    assert translate_ts_error(ValueError("unknown failure")) == "unknown failure"


def test_translate_ts_error_never_returns_an_empty_message():
    """无消息异常也必须给 UI 返回可读的失败原因。"""
    message = translate_ts_error(MemoryError())

    assert "MemoryError" in message
    assert message


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


def test_sarimax_missing_exog_is_a_warning_not_a_blocking_problem():
    """SARIMAX 缺失外生变量时允许由 Ts 按 missing='drop' 继续拟合。"""
    series = make_series()
    exog = pd.DataFrame({"x": np.arange(len(series), dtype=float)})
    exog.iloc[5, 0] = np.nan

    problems = validate_fit_inputs(series, exog, SARIMAXConfig())

    assert not any("外生变量存在" in problem for problem in problems)
    assert any(
        "外生变量存在 1 个缺失值" in warning
        for warning in fit_input_warnings(exog)
    )


def test_dynamic_regression_validation_rejects_missing_and_no_input():
    series = make_series()
    config = ARDLConfig(lags=1, input_orders=(("x", 0),))
    missing = pd.DataFrame({"x": np.arange(len(series), dtype=float)})
    missing.iloc[5, 0] = np.nan
    problems = validate_fit_inputs(series, missing, config)
    assert any("非连续" in problem for problem in problems)
    assert any("至少需要" in problem for problem in validate_fit_inputs(series, None, config))
