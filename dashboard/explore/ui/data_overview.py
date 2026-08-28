"""单变量分析的数据概览页。

动态回归模型的数据读取、数据表和时间序列预览在这里统一渲染；本页原有
的单变量诊断只保留 ACF/PACF 相关结构分析。
"""

from __future__ import annotations

import pandas as pd

from data_overview import create_data_overview
from data_overview.core.dataset import OverviewDataset, build_overview_dataset
from data_overview.ui.widget_keys import (
    read_widget_keys,
    selector_widget_keys,
)

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager
from dashboard.explore.analysis.stationarity import (
    numeric_variable_names,
    prepare_selected_series,
    resolve_correlation_lags,
    transform_series,
)
from dashboard.explore.ui.chart_controls import (
    chart_scope,
    render_correlogram_chart,
)
from dashboard.explore.ui.shared_dataset_source import SharedDatasetSource

_DATA_OVERVIEW_STATE = NamespacedStateManager("model_analysis.sarimax")
_DATA_OVERVIEW_KEY_PREFIX = "sarimax"
CORRELOGRAM_VARIABLES_KEY = "sarimax_correlogram_vars"
CORRELOGRAM_TRANSFORMATION_PREFIX = "sarimax_correlogram_transformation_"
CORRELOGRAM_WIDGET_KEYS = (CORRELOGRAM_VARIABLES_KEY,)
_PRESERVED_DATA_OVERVIEW_KEYS = set(
    selector_widget_keys(_DATA_OVERVIEW_KEY_PREFIX)
    + read_widget_keys(_DATA_OVERVIEW_KEY_PREFIX)
    + ("sarimax_preview_sheet",)
)

CORRELOGRAM_TRANSFORMATION_OPTIONS = (
    "original",
    "log",
    "first_difference",
    "log_first_difference",
)
CORRELOGRAM_TRANSFORMATION_LABELS = {
    "original": "原始变量",
    "log": "对数",
    "first_difference": "差分",
    "log_first_difference": "对数差分",
}
_CORRELOGRAM_SOURCE_VARIABLES_KEY = "sarimax_correlogram_source_vars"


def _build_univariate_overview_dataset(
    frame: pd.DataFrame,
    file_name: str,
    fingerprint: str,
) -> OverviewDataset:
    """构建单变量概览数据，并保留预览中的零值缺失约定。"""
    cleaned = frame.replace(r"^\s*$", pd.NA, regex=True).copy()
    for column in cleaned.columns:
        series = cleaned[column]
        if (
            pd.api.types.is_datetime64_any_dtype(series)
            or pd.api.types.is_bool_dtype(series)
            or not pd.api.types.is_numeric_dtype(series)
        ):
            continue
        cleaned[column] = series.mask(series.eq(0))
    return build_overview_dataset(cleaned, file_name, fingerprint)


def _clear_data_overview_dependent_widgets(st_obj) -> None:
    """换数据读取设置时清理图表、模型和相关分析控件。"""
    session = getattr(st_obj, "session_state", None)
    if session is None:
        return
    for key in tuple(session):
        if (
            str(key).startswith("sarimax_")
            and key not in _PRESERVED_DATA_OVERVIEW_KEYS
        ):
            session.pop(key, None)


def _on_data_overview_dataset_replaced(st_obj) -> None:
    """数据读取设置变化后清理共享模型状态和下游控件。"""
    for key, value in {
        "target_variable": None,
        "exog_variables": (),
        "training_time_range": None,
        "response_log": False,
        "future_exog_editor_signature": None,
        "fitted_result": None,
        "fit_signature": None,
        "diagnostics_table": None,
        "diagnostics_signature": None,
        "forecast": None,
        "forecast_signature": None,
    }.items():
        _DATA_OVERVIEW_STATE.set(key, value)
    _clear_data_overview_dependent_widgets(st_obj)


_render_shared_data_overview = create_data_overview(
    key_prefix=_DATA_OVERVIEW_KEY_PREFIX,
    state_namespace="model_analysis.sarimax",
    data_source=SharedDatasetSource(uploader_enabled=False),
    dataset_builder=_build_univariate_overview_dataset,
    on_dataset_replaced=_on_data_overview_dataset_replaced,
    title="",
)


def _render_correlogram_controls(
    st_obj,
    available_variables: list[str],
    default_variables: list[str],
) -> list[str]:
    """渲染占整行的 ACF/PACF 变量多选。"""
    st_obj.markdown("---")
    st_obj.markdown("**自相关与偏自相关**")

    session = st_obj.session_state
    current_variables = session.get(CORRELOGRAM_VARIABLES_KEY)
    previous_default = session.get(_CORRELOGRAM_SOURCE_VARIABLES_KEY)
    if (
        current_variables is None
        or (
            previous_default is not None
            and list(current_variables) == list(previous_default)
        )
    ):
        session[CORRELOGRAM_VARIABLES_KEY] = list(default_variables)
    else:
        session[CORRELOGRAM_VARIABLES_KEY] = [
            value
            for value in current_variables
            if value in available_variables
        ]
    session[_CORRELOGRAM_SOURCE_VARIABLES_KEY] = list(default_variables)
    variables = st_obj.multiselect(
        "选择变量",
        options=available_variables,
        key=CORRELOGRAM_VARIABLES_KEY,
        help="选择一个或多个变量，生成对应的 ACF/PACF 图。",
    )
    return list(variables)


def _prepare_correlogram(
    st_obj,
    series: pd.Series,
    variable: str,
    *,
    chart_type: str,
) -> tuple[pd.Series, str] | None:
    """渲染变换单选，并返回对应的序列与标题前缀。"""
    transformation_key = (
        f"{CORRELOGRAM_TRANSFORMATION_PREFIX}"
        f"{chart_scope('data_overview', variable, chart_type)}"
    )
    transformation = st_obj.radio(
        chart_type,
        options=list(CORRELOGRAM_TRANSFORMATION_OPTIONS),
        format_func=lambda key: CORRELOGRAM_TRANSFORMATION_LABELS[key],
        horizontal=True,
        label_visibility="collapsed",
        key=transformation_key,
    )
    label = CORRELOGRAM_TRANSFORMATION_LABELS[transformation]
    try:
        processed = (
            series
            if transformation == "original"
            else transform_series(series, transformation)
        )
    except Exception as exc:  # noqa: BLE001 - user-facing processing boundary
        st_obj.error(f"变量“{variable}”的{chart_type}处理失败：{exc}")
        return None
    return processed, f"{variable} · {label}"


def _shared_correlogram_maximum(
    results: tuple[pd.Series, str] | None,
    other_results: tuple[pd.Series, str] | None,
) -> int | None:
    """返回 ACF/PACF 两张图共同可用的最大滞后阶数。"""
    maxima = []
    for result in (results, other_results):
        if result is None:
            continue
        try:
            _, maximum = resolve_correlation_lags(result[0])
        except Exception:  # noqa: BLE001 - 单图绘制边界会报告具体错误
            continue
        maxima.append(maximum)
    return min(maxima) if maxima else None


def render_data_overview(st_obj) -> None:
    """渲染动态回归数据预览，并提供可选预处理的 ACF/PACF 分析。"""
    _render_shared_data_overview(st_obj)

    overview_dataset = _DATA_OVERVIEW_STATE.get("dataset")
    if overview_dataset is None:
        return

    available_variables = [
        str(variable)
        for variable in numeric_variable_names(overview_dataset.frame)
    ]
    if not available_variables:
        return

    selected_above = [
        str(variable)
        for variable in st_obj.session_state.get("sarimax_preview_vars", [])
        if str(variable) in available_variables
    ]
    variables = _render_correlogram_controls(
        st_obj,
        available_variables,
        selected_above or available_variables[:1],
    )
    if not variables:
        st_obj.info("请至少选择一个变量。")
        return

    for variable in variables:
        try:
            series, _ = prepare_selected_series(overview_dataset.frame, variable)
        except Exception as exc:  # noqa: BLE001 - user-facing processing boundary
            st_obj.error(f"变量“{variable}”处理失败：{exc}")
            continue
        acf_column, pacf_column = st_obj.columns(2)
        acf_result = _prepare_correlogram(
            acf_column,
            series,
            variable,
            chart_type="ACF",
        )
        pacf_result = _prepare_correlogram(
            pacf_column,
            series,
            variable,
            chart_type="PACF",
        )
        if acf_result is None and pacf_result is None:
            continue

        scope = chart_scope("data_overview", variable, "correlogram")
        config_defaults = {}
        if acf_result is not None:
            config_defaults["acf_title"] = f"{acf_result[1]} · ACF"
        if pacf_result is not None:
            config_defaults["pacf_title"] = f"{pacf_result[1]} · PACF"
        maximum_lags = _shared_correlogram_maximum(acf_result, pacf_result)

        if acf_result is not None:
            render_correlogram_chart(
                acf_column,
                acf_result[0],
                title_prefix=acf_result[1],
                include_acf=True,
                include_pacf=False,
                alpha=0.05,
                scope=scope,
                config_defaults=config_defaults,
                maximum_lags=maximum_lags,
                show_config=pacf_result is None,
                config_container=st_obj,
            )
        if pacf_result is not None:
            render_correlogram_chart(
                pacf_column,
                pacf_result[0],
                title_prefix=pacf_result[1],
                include_acf=False,
                include_pacf=True,
                alpha=0.05,
                scope=scope,
                config_defaults=config_defaults,
                maximum_lags=maximum_lags,
                config_container=st_obj,
            )


__all__ = [
    "CORRELOGRAM_TRANSFORMATION_OPTIONS",
    "CORRELOGRAM_TRANSFORMATION_LABELS",
    "CORRELOGRAM_TRANSFORMATION_PREFIX",
    "CORRELOGRAM_VARIABLES_KEY",
    "CORRELOGRAM_WIDGET_KEYS",
    "render_data_overview",
]
