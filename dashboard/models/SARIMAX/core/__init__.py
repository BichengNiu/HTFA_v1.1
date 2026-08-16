"""SARIMAX 模型核心逻辑（纯计算，不依赖 streamlit 渲染）。"""

from dashboard.models.SARIMAX.core.data_loader import (
    ModelingDataset,
    load_modeling_dataset,
    numeric_variable_names,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.model_config import (
    AUTO_CRITERIA,
    AutoSARIMAXConfig,
    SARIMAXConfig,
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    TREND_LABELS,
    TREND_OPTIONS,
)
from dashboard.models.SARIMAX.core.modeling import (
    MIN_OBSERVATIONS,
    build_prediction_table,
    fit_auto_sarimax,
    fit_sarimax,
    future_dates,
    produce_forecast,
    run_residual_diagnostics,
    translate_ts_error,
    validate_fit_inputs,
)

__all__ = [
    "AUTO_CRITERIA",
    "AutoSARIMAXConfig",
    "MIN_OBSERVATIONS",
    "ModelingDataset",
    "SARIMAXConfig",
    "SARIMAX_COV_TYPES",
    "SARIMAX_OPTIMIZERS",
    "TREND_LABELS",
    "TREND_OPTIONS",
    "build_prediction_table",
    "fit_auto_sarimax",
    "fit_sarimax",
    "future_dates",
    "load_modeling_dataset",
    "numeric_variable_names",
    "prepare_modeling_inputs",
    "produce_forecast",
    "run_residual_diagnostics",
    "translate_ts_error",
    "validate_fit_inputs",
]
