"""单变量分析的数据概览页与 ACF/PACF 诊断。"""

from __future__ import annotations

import logging
from copy import deepcopy

import pandas as pd
from data_overview import create_data_overview
from data_overview.core.dataset import OverviewDataset, build_overview_dataset
from data_overview.ui.widget_keys import (
    overview_widget_keys,
    read_widget_keys,
    selector_widget_keys,
)
from Ts.TsUtils import hurst_exponent

from htfa.app.state.shared_dataset import (
    get_shared_dataset_fingerprint,
    get_shared_dataset_sheet,
)
from htfa.app.state.session_state import NamespacedStateManager
from htfa.exploration.analysis.stationarity import (
    numeric_variable_names,
    prepare_selected_series,
    resolve_correlation_lags,
    transform_series,
)
from htfa.exploration.ui.chart_controls import (
    chart_scope,
    render_correlogram_chart,
)
from htfa.exploration.ui.shared_dataset_source import SharedDatasetSource

logger = logging.getLogger(__name__)

_DATA_OVERVIEW_STATE = NamespacedStateManager(
    "data_exploration.univariate.overview"
)
_DATA_OVERVIEW_KEY_PREFIX = "univariate_overview"
CORRELOGRAM_VARIABLES_KEY = "univariate_overview_correlogram_vars"
CORRELOGRAM_TRANSFORMATION_PREFIX = (
    "univariate_overview_correlogram_transformation_"
)
SERIES_STYLE_WIDGET_PREFIX = "univariate_overview_preview_series_style_"
CORRELOGRAM_WIDGET_KEYS = (CORRELOGRAM_VARIABLES_KEY,)
_PRESERVED_DATA_OVERVIEW_KEYS = set(
    selector_widget_keys(_DATA_OVERVIEW_KEY_PREFIX)
    + read_widget_keys(_DATA_OVERVIEW_KEY_PREFIX)
    + ("univariate_overview_preview_sheet",)
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
_CORRELOGRAM_SOURCE_VARIABLES_KEY = "univariate_overview_correlogram_source_vars"
_HANDOFF_RESTORE_GUARD_KEY = (
    "data_exploration.univariate.overview.handoff_restore"
)
_CHART_CONFIG_STATE_PREFIX = "tools.analysis.chart_config."
DATA_OVERVIEW_HANDOFF_WIDGET_KEYS = (
    overview_widget_keys(_DATA_OVERVIEW_KEY_PREFIX)
    + ("univariate_overview_preview_sheet",)
    + CORRELOGRAM_WIDGET_KEYS
)
HURST_RESULT_COLUMNS = (
    "变量",
    "赫斯特指数",
    "有效观测数",
    "参考解释",
)


def _build_univariate_overview_dataset(
    frame: pd.DataFrame,
    file_name: str,
    fingerprint: str,
) -> OverviewDataset:
    """按单变量概览的历史口径构建数据集。

    原始共享数据仍保留 0；这里只在单变量概览的本地数据集里把数值 0
    视为尚未开始/缺失观测，使图表和统计从第一个有效值开始。该边界
    不影响共享数据，也不影响其他模型页面的数据输入。
    """

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
    """换数据读取设置时清理本页图表与相关分析控件。"""
    session = getattr(st_obj, "session_state", None)
    if session is None:
        return
    for key in tuple(session):
        if (
            str(key).startswith("univariate_overview_")
            and key not in _PRESERVED_DATA_OVERVIEW_KEYS
        ):
            session.pop(key, None)


def _on_data_overview_dataset_replaced(st_obj) -> None:
    """数据读取设置变化后只清理单变量数据概览的下游控件。"""

    if st_obj.session_state.pop(_HANDOFF_RESTORE_GUARD_KEY, False):
        return
    _clear_data_overview_dependent_widgets(st_obj)


_render_shared_data_overview = create_data_overview(
    key_prefix=_DATA_OVERVIEW_KEY_PREFIX,
    state_namespace="data_exploration.univariate.overview",
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
        except (TypeError, ValueError):
            continue
        maxima.append(maximum)
    return min(maxima) if maxima else None


def _hurst_interpretation(value: float) -> str:
    """将赫斯特指数转换为不带检验含义的描述性提示。"""
    if value < 0.5:
        return "反持续（H < 0.5）"
    if value > 0.5:
        return "持续性（H > 0.5）"
    return "弱依赖/随机性（H ≈ 0.5）"


def _calculate_hurst_result(series: pd.Series, variable: str) -> dict[str, object]:
    """调用 TsUtils 赫斯特接口并构建单变量概览表的一行。"""
    n_valid = int(series.notna().sum())
    try:
        value = hurst_exponent(series, missing="drop")
    except Exception as exc:  # noqa: BLE001 - user-facing diagnostic boundary
        return {
            "变量": variable,
            "赫斯特指数": None,
            "有效观测数": n_valid,
            "参考解释": f"无法计算：{exc}",
        }
    return {
        "变量": variable,
        "赫斯特指数": round(float(value), 4),
        "有效观测数": n_valid,
        "参考解释": _hurst_interpretation(float(value)),
    }


def _render_hurst_results(st_obj, results: list[dict[str, object]]) -> None:
    """在 ACF/PACF 图组下方渲染赫斯特指数结果表。"""
    if not results:
        return
    st_obj.markdown("---")
    st_obj.markdown("**赫斯特指数**")
    st_obj.caption(
        "基于原始序列的经典 R/S 方法；计算时删除缺失值，至少需要 20 个有效观测。"
        " H<0.5、H≈0.5、H>0.5 仅作描述性参考。"
    )
    st_obj.dataframe(
        pd.DataFrame(results, columns=HURST_RESULT_COLUMNS),
        use_container_width=True,
        hide_index=True,
    )


def _correlogram_chart_config_prefixes(session) -> tuple[str, ...]:
    """返回当前单变量概览 ACF/PACF 配置的会话键前缀。"""

    variables = session.get(CORRELOGRAM_VARIABLES_KEY)
    if variables is None:
        variables = session.get(
            f"{_DATA_OVERVIEW_KEY_PREFIX}_preview_vars", ()
        )
    if isinstance(variables, str):
        variables = (variables,)
    if not variables:
        return ()
    return tuple(
        f"{_CHART_CONFIG_STATE_PREFIX}"
        f"{chart_scope('data_overview', variable, 'correlogram')}."
        for variable in variables
    )


def export_data_overview_widget_state(st_obj) -> dict[str, object]:
    """导出独立数据概览页可恢复的白名单控件状态。"""

    session = st_obj.session_state
    keys = list(DATA_OVERVIEW_HANDOFF_WIDGET_KEYS)
    config_prefixes = _correlogram_chart_config_prefixes(session)
    keys.extend(
        str(key)
        for key in session
        if str(key).startswith(
            (
                CORRELOGRAM_TRANSFORMATION_PREFIX,
                SERIES_STYLE_WIDGET_PREFIX,
            )
            + config_prefixes
        )
    )
    return {
        key: deepcopy(session[key])
        for key in keys
        if key in session
    }


def restore_data_overview_widget_state(
    st_obj, widget_state: dict[str, object]
) -> None:
    """恢复已校验白名单中的数据概览控件状态。"""

    allowed = set(DATA_OVERVIEW_HANDOFF_WIDGET_KEYS)
    config_prefixes = _correlogram_chart_config_prefixes(widget_state)
    for key, value in widget_state.items():
        if key in allowed or key.startswith(
            (
                CORRELOGRAM_TRANSFORMATION_PREFIX,
                SERIES_STYLE_WIDGET_PREFIX,
            )
            + config_prefixes
        ):
            st_obj.session_state[key] = deepcopy(value)


def mark_data_overview_handoff_restore(st_obj) -> None:
    """标记下一次数据集建立来自页面交接，保留已恢复的控件状态。"""

    # ``create_data_overview`` 会在首次看到文件指纹时清理变量名行、
    # 数据开始行和时间列控件。交接快照已经恢复了这些值，先同步内部
    # 指纹即可避免首次渲染把它们重置为默认值。
    fingerprint = get_shared_dataset_fingerprint()
    if fingerprint:
        _DATA_OVERVIEW_STATE.set("source_fingerprint", fingerprint)
        # 首次渲染还会依据原始行和读取设置建立时间列选项签名；若不
        # 预先建立该签名，组件会把交接过来的时间列再次清空。
        try:
            variable_name_row = int(
                st_obj.session_state.get(
                    f"{_DATA_OVERVIEW_KEY_PREFIX}_preview_variable_name_row",
                    1,
                )
            )
            data_start_row = int(
                st_obj.session_state.get(
                    f"{_DATA_OVERVIEW_KEY_PREFIX}_preview_data_start_row",
                    variable_name_row + 1,
                )
            )
            raw_data = SharedDatasetSource(uploader_enabled=False).load_data(
                variable_name_row=variable_name_row - 1,
                data_start_row=data_start_row - 1,
                time_column=None,
            )
            if raw_data is not None:
                _DATA_OVERVIEW_STATE.set(
                    "time_options_signature",
                    (
                        fingerprint,
                        get_shared_dataset_sheet() or "none",
                        variable_name_row,
                        data_start_row,
                        ("无", *[str(column) for column in raw_data.columns]),
                    ),
                )
        except Exception:
            logger.debug(
                "无法预先建立交接页面的时间列选项签名",
                exc_info=True,
            )
    st_obj.session_state[_HANDOFF_RESTORE_GUARD_KEY] = True


def render_data_overview(st_obj) -> None:
    """渲染单变量数据预览，并提供可选预处理的 ACF/PACF 分析。"""
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
        for variable in st_obj.session_state.get(
            f"{_DATA_OVERVIEW_KEY_PREFIX}_preview_vars", []
        )
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

    hurst_results = []
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
            hurst_results.append(_calculate_hurst_result(series, variable))
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
        hurst_results.append(_calculate_hurst_result(series, variable))

    _render_hurst_results(st_obj, hurst_results)


__all__ = [
    "CORRELOGRAM_TRANSFORMATION_LABELS",
    "CORRELOGRAM_TRANSFORMATION_OPTIONS",
    "CORRELOGRAM_TRANSFORMATION_PREFIX",
    "CORRELOGRAM_VARIABLES_KEY",
    "CORRELOGRAM_WIDGET_KEYS",
    "DATA_OVERVIEW_HANDOFF_WIDGET_KEYS",
    "HURST_RESULT_COLUMNS",
    "SERIES_STYLE_WIDGET_PREFIX",
    "export_data_overview_widget_state",
    "mark_data_overview_handoff_restore",
    "render_data_overview",
    "restore_data_overview_widget_state",
]
