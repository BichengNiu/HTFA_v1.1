from io import BytesIO
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from dashboard.explore.analysis import lead_lag
from dashboard.explore.analysis.config import LeadLagAnalysisConfig
from dashboard.explore.analysis.dtw_batch import perform_batch_dtw_calculation
from dashboard.explore.core.data_source import load_explore_dataset
from dashboard.explore.core.series_utils import fingerprint_dataframe
from dashboard.explore.metrics.kl_divergence import (
    calculate_kl_divergence_series,
    kl_divergence,
    series_to_distribution,
)
from dashboard.explore.preprocessing.frequency_alignment import (
    resample_series_to_frequency,
)
from dashboard.explore.ui import dataset_context
from dashboard.explore.ui.multivariate_state import (
    build_dtw_backend_options,
    build_dtw_result_signature,
    build_lead_lag_result_signature,
    parse_dtw_alignment_mode,
)


def test_explore_dataset_uses_contract_aware_frequency_tables():
    workbook = Path(__file__).parents[2] / "data" / "阿联酋.xlsx"

    dataset = load_explore_dataset(workbook)

    assert list(dataset.tables) == ["daily", "weekly", "monthly", "quarterly", "yearly"]
    for frame in dataset.tables.values():
        assert not frame.empty
        assert isinstance(frame.index, pd.DatetimeIndex)
        assert frame.index.is_monotonic_increasing
        assert not frame.index.has_duplicates
    assert dataset.file_name == "阿联酋.xlsx"


def test_kl_lag_pairs_preserve_common_timestamps(monkeypatch):
    index = pd.date_range("2025-01-01", periods=12, freq="D")
    target = pd.Series(
        [np.nan, 1, *range(2, 12)],
        index=index,
        name="target",
        dtype=float,
    )
    candidate = pd.Series(
        [0, np.nan, *range(2, 12)],
        index=index,
        name="candidate",
        dtype=float,
    )
    captured = {}

    def capture_distribution(series_a, series_b, bins=None):
        captured["a"] = series_a.tolist()
        captured["b"] = series_b.tolist()
        return np.array([1.0]), np.array([1.0]), np.array([0.0, 1.0])

    monkeypatch.setattr(lead_lag, "series_to_distribution", capture_distribution)

    result = lead_lag.calculate_kl_divergence_optimized(
        target,
        candidate,
        max_lags=0,
        standardize_for_kl=False,
        standardization_method="none",
    )

    assert result["KL_Divergence"].tolist() == [0.0]
    assert captured["a"] == list(range(2, 12))
    assert captured["b"] == list(range(2, 12))


def test_constant_and_varying_series_do_not_have_zero_kl_divergence():
    constant = pd.Series([0.0] * 20)
    varying = pd.Series(np.linspace(0.0, 5.0, 20))

    p, q, _ = series_to_distribution(constant, varying)

    assert len(p) >= 2
    assert kl_divergence(p, q) > 0


def test_empty_kl_series_returns_error_tuple_instead_of_raising():
    value, error = calculate_kl_divergence_series(
        pd.Series(dtype=float),
        pd.Series(dtype=float),
    )

    assert value is None
    assert error == "序列A在移除NaN后为空"


def test_kl_wrapper_does_not_hide_unexpected_programming_errors(monkeypatch):
    kl_module = sys.modules[calculate_kl_divergence_series.__module__]

    def raise_unexpected_error(*args, **kwargs):
        raise RuntimeError("unexpected defect")

    monkeypatch.setattr(
        kl_module,
        "series_to_distribution",
        raise_unexpected_error,
    )

    with pytest.raises(RuntimeError, match="unexpected defect"):
        calculate_kl_divergence_series(
            pd.Series([1.0, 2.0]),
            pd.Series([2.0, 3.0]),
            min_samples=1,
        )


@pytest.mark.parametrize(
    ("target_frequency", "aggregation", "expected_error"),
    [
        ("Bogus", "mean", "不支持的目标频率"),
        ("Daily", "bogus", "不支持的聚合方法"),
    ],
)
def test_resampling_rejects_unknown_statistical_configuration(
    target_frequency,
    aggregation,
    expected_error,
):
    frame = pd.DataFrame(
        {"value": range(6)},
        index=pd.date_range("2024-01-01", periods=6, freq="D"),
    )

    result, report = resample_series_to_frequency(
        frame,
        target_frequency,
        aggregation,
    )

    assert result.equals(frame)
    assert report["status"] == "error"
    assert expected_error in report["error"]


def test_lead_lag_config_is_validated_on_construction():
    with pytest.raises(ValueError, match="max_lags必须大于0"):
        LeadLagAnalysisConfig(max_lags=0)


def test_lead_lag_config_rejects_non_integer_lags_and_accepts_ten_day():
    with pytest.raises(ValueError, match="max_lags必须大于0"):
        LeadLagAnalysisConfig(max_lags="12")

    config = LeadLagAnalysisConfig(max_lags=12, target_frequency="Ten_Day")

    assert config.target_frequency == "Ten_Day"


def test_detailed_lag_data_does_not_ignore_alignment_failure():
    frame = pd.DataFrame(
        {
            "target": range(20),
            "candidate": range(1, 21),
        }
    )

    with pytest.raises(ValueError, match="频率对齐失败"):
        lead_lag.get_detailed_lag_data_for_candidate(
            frame,
            "target",
            "candidate",
            {
                "max_lags": 1,
                "enable_frequency_alignment": True,
            },
        )


def test_dataframe_fingerprint_changes_when_values_change():
    first = pd.DataFrame({"value": [1.0, 2.0, 3.0]})
    second = pd.DataFrame({"value": [10.0, 20.0, 30.0]})

    assert fingerprint_dataframe(first) != fingerprint_dataframe(second)


def test_multivariate_parameter_contracts_are_complete_and_strict():
    frame = pd.DataFrame({"target": [1.0, 2.0], "candidate": [2.0, 3.0]})
    dtw_params = {
        "target_series": "target",
        "comparison_series": ["candidate"],
        "enable_window_constraint": True,
        "radius": 3,
        "enable_alignment": True,
        "strict_alignment": True,
        "agg_method": "mean",
        "standardization_method": "zscore",
    }
    lead_lag_config = {
        "max_lags": 5,
        "standardize_for_kl": True,
        "standardization_method": "zscore",
        "enable_frequency_alignment": True,
        "target_frequency": None,
        "freq_agg_method": "mean",
    }

    assert parse_dtw_alignment_mode("freq_align_strict") == (True, True)
    assert build_dtw_backend_options(dtw_params) == {
        "window_type_param": "固定大小窗口 (Radius约束)",
        "window_size_param": 3,
        "dist_metric_display_param": "欧氏距离",
        "enable_freq_alignment": True,
        "freq_agg_method": "mean",
        "strict_alignment": True,
        "standardization_method": "zscore",
    }
    assert build_dtw_result_signature(frame, dtw_params) != (
        build_dtw_result_signature(
            frame,
            {**dtw_params, "standardization_method": "none"},
        )
    )
    assert build_lead_lag_result_signature(
        frame,
        "target",
        ["candidate"],
        lead_lag_config,
    ) != build_lead_lag_result_signature(
        frame,
        "target",
        ["candidate"],
        {**lead_lag_config, "standardize_for_kl": False},
    )

    with pytest.raises(ValueError, match="不支持的 DTW 对齐模式"):
        parse_dtw_alignment_mode("unknown")
    with pytest.raises(ValueError, match="必须提供 radius"):
        build_dtw_backend_options({**dtw_params, "radius": None})


def test_explore_dataset_supports_flat_csv():
    uploaded = BytesIO(b"date,value\n2026-01-01,1\n")
    uploaded.name = "series.csv"

    dataset = load_explore_dataset(uploaded)

    assert list(dataset.tables) == ["table"]
    assert dataset.tables["table"].shape == (1, 2)


def test_explore_dataset_is_parsed_once_per_file_fingerprint(monkeypatch):
    uploaded = BytesIO(b"date,value\n2026-01-01,1\n")
    uploaded.name = "series.csv"
    state_owner = type(
        "StateOwner",
        (),
        {
            "session_state": {
                "data_overview_table_select": "old",
                "bivariate_table_select": "old",
            }
        },
    )()
    calls = 0
    real_loader = dataset_context.load_explore_dataset

    def counted_loader(file_input):
        nonlocal calls
        calls += 1
        return real_loader(file_input)

    monkeypatch.setattr(dataset_context, "load_explore_dataset", counted_loader)

    first = dataset_context.get_explore_dataset(state_owner, uploaded)
    second = dataset_context.get_explore_dataset(state_owner, uploaded)

    assert first is second
    assert calls == 1
    assert "data_overview_table_select" not in state_owner.session_state
    assert "bivariate_table_select" not in state_owner.session_state


def test_importing_core_constants_does_not_load_heavy_analysis_dependencies():
    command = (
        "import sys; "
        "import dashboard.explore.core.constants; "
        "print(int('Ts' in sys.modules), "
        "int('matplotlib.pyplot' in sys.modules), "
        "int('dtaidistance.dtw' in sys.modules))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "0 0 0"


def test_public_objects_are_imported_from_owning_modules():
    command = (
        "from dashboard.explore.core.validation import validate_series; "
        "from dashboard.explore.analysis import perform_batch_dtw_calculation; "
        "from dashboard.explore.ui import DTWAnalysisComponent; "
        "print(int(callable(validate_series)), "
        "int(callable(perform_batch_dtw_calculation)), "
        "DTWAnalysisComponent.__name__)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "1 1 DTWAnalysisComponent"


def test_dtw_accepts_lowercase_date_column_and_returns_path():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="D"),
            "target": np.arange(12, dtype=float),
            "candidate": np.arange(12, dtype=float) + 1,
        }
    )

    results, paths, errors, warnings = perform_batch_dtw_calculation(
        df_input=frame,
        target_series_name="target",
        comparison_series_names=["candidate"],
        window_type_param="无限制",
        window_size_param=None,
        dist_metric_display_param="欧氏距离",
        enable_freq_alignment=False,
        strict_alignment=True,
        standardization_method="zscore",
    )

    assert not errors
    assert not warnings
    assert len(results) == 1
    assert np.isfinite(results[0]["DTW距离"])
    assert paths["candidate"]["path"]
    assert isinstance(paths["candidate"]["target_index"], pd.DatetimeIndex)


def test_dtw_rejects_invalid_configuration_before_calculation():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="D"),
            "target": np.arange(12, dtype=float),
            "candidate": np.arange(12, dtype=float) + 1,
        }
    )

    _, _, errors, _ = perform_batch_dtw_calculation(
        df_input=frame,
        target_series_name="target",
        comparison_series_names=["candidate"],
        window_type_param="无限制",
        window_size_param=None,
        dist_metric_display_param="欧氏距离",
        enable_freq_alignment=True,
        freq_agg_method="bogus",
    )

    assert errors == ["不支持的聚合方法: bogus"]


def test_dtw_rejects_columns_that_collide_after_cleaning():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=12, freq="D"),
            "first": np.arange(12, dtype=float),
            "second": np.arange(12, dtype=float) + 1,
        }
    )
    frame.columns = ["date", "value ", "value"]

    _, _, errors, _ = perform_batch_dtw_calculation(
        df_input=frame,
        target_series_name="value",
        comparison_series_names=["value"],
        window_type_param="无限制",
        window_size_param=None,
        dist_metric_display_param="欧氏距离",
    )

    assert errors == ["清理后存在重复列名: ['value']"]
