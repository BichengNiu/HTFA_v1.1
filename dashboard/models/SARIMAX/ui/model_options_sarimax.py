"""SARIMAX 及动态回归误差项的参数控件。"""

from __future__ import annotations

import pandas as pd
from Ts.TsModels import TimeSeriesOperator

from dashboard.models.SARIMAX.core.config_shared import SARIMAX_RANGE_LIMITS
from dashboard.models.SARIMAX.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.ui.model_options_shared import (
    parse_sparse_lags,
    render_range_inputs,
    render_sarimax_advanced_settings,
    render_trend_selector,
    restore_table_state,
)
from dashboard.models.SARIMAX.ui.state import state
from dashboard.models.common.state import StateStore

_AUTO_RANGE_DEFAULTS = {
    "p": (0, 3),
    "d": (0, 1),
    "q": (0, 3),
    "P": (0, 1),
    "D": (0, 1),
    "Q": (0, 1),
}
_AUTO_MAX = 200
_AUTO_SELECTION_DEFAULT = "aic"
_AUTO_PARALLEL_NOTICE = (
    "候选模型按规模自动调度：少于 8 个或预计工作量较低时串行；"
    "其余搜索最多使用 4 个单线程数值进程。"
)


def render_sarimax_options(
    st_obj,
    mode: str,
    *,
    exog: pd.DataFrame | None = None,
    response_log: bool = False,
    exog_log_names: tuple[str, ...] = (),
    prefix: str = "sarimax",
    state_manager: StateStore = state,
) -> SARIMAXConfig | AutoSARIMAXConfig | None:
    """渲染 SARIMAX 模型族的手动或自动配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    mode : str
        配置方式，支持 ``手动配置`` 和 ``自动选阶``。
    exog : pandas.DataFrame or None, optional
        当前选择的外生变量；存在时显示逐变量时序算子表。
    response_log : bool, default=False
        通用输入模块提供的目标变量对数变换状态。
    exog_log_names : tuple[str, ...], default=()
        需要对数变换的外生变量名称。

    Returns
    -------
    SARIMAXConfig or AutoSARIMAXConfig or None
        构建好的配置；控件参数无效时返回 ``None``。
    """
    if mode == "手动配置":
        return _render_manual_config(
            st_obj,
            prefix,
            log=response_log,
            exog=exog,
            exog_log_names=exog_log_names,
            state_manager=state_manager,
        )
    return _render_auto_config(
        st_obj,
        f"{prefix}_auto",
        log=response_log,
        exog=exog,
        exog_log_names=exog_log_names,
        state_manager=state_manager,
    )


def render_sarimax_error_options(
    st_obj,
    prefix: str,
    *,
    include_trend: bool = True,
    response_log: bool = False,
    state_manager: StateStore = state,
) -> SARIMAXConfig | None:
    """渲染 RDL/ARDL 使用的手动 SARIMAX 误差结构配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    prefix : str
        控件键前缀。
    include_trend : bool, default=True
        是否显示误差模型趋势项控件。ARDL 已在目标方程中提供趋势项，
        因此其误差模型应传入 ``False``。
    response_log : bool, default=False
        目标变量对数变换状态。

    Returns
    -------
    SARIMAXConfig or None
        动态回归误差项配置。
    """
    return _render_manual_config(
        st_obj,
        prefix,
        log=response_log,
        include_trend=include_trend,
        state_manager=state_manager,
    )


def _render_manual_config(
    st_obj,
    prefix: str = "sarimax",
    *,
    log: bool | None = False,
    exog: pd.DataFrame | None = None,
    exog_log_names: tuple[str, ...] = (),
    include_trend: bool = True,
    state_manager: StateStore = state,
) -> SARIMAXConfig | None:
    """渲染手动 SARIMAX 阶数与高级设置。"""
    order_columns = st_obj.columns(4 if include_trend else 3)
    p = order_columns[0].number_input("p（AR 阶数）", 0, 6, 1, key=f"{prefix}_p")
    d = order_columns[1].number_input("d（差分阶数）", 0, 2, 0, key=f"{prefix}_d")
    q = order_columns[2].number_input("q（MA 阶数）", 0, 6, 1, key=f"{prefix}_q")
    trend = render_trend_selector(order_columns[3], prefix) if include_trend else "n"
    seasonal_columns = st_obj.columns(4)
    P = seasonal_columns[0].number_input("P（季节 AR）", 0, 3, 0, key=f"{prefix}_P")
    D = seasonal_columns[1].number_input("D（季节差分）", 0, 2, 0, key=f"{prefix}_D")
    Q = seasonal_columns[2].number_input("Q（季节 MA）", 0, 3, 0, key=f"{prefix}_Q")
    s = seasonal_columns[3].number_input(
        "s（季节周期）",
        0,
        365,
        0,
        key=f"{prefix}_s",
        help="季节周期长度；0 表示无季节项（日度数据可填 5、21、63 或 252）。",
    )
    with st_obj.expander("高级：活动 AR/MA 滞后", expanded=False):
        st_obj.caption(
            "非空值覆盖上方连续阶数；例如 1,3 表示仅估计第 1 和第 3 阶，"
            "中间滞后固定为零。"
        )
        sparse_columns = st_obj.columns(2)
        ar_lags = sparse_columns[0].text_input(
            "活动 AR 滞后", key=f"{prefix}_ar_lags", placeholder="例如 1,3"
        )
        ma_lags = sparse_columns[1].text_input(
            "活动 MA 滞后", key=f"{prefix}_ma_lags", placeholder="例如 1,3"
        )
        seasonal_ar_lags = sparse_columns[0].text_input(
            "活动季节 AR 滞后", key=f"{prefix}_seasonal_ar_lags", placeholder="例如 1,2"
        )
        seasonal_ma_lags = sparse_columns[1].text_input(
            "活动季节 MA 滞后", key=f"{prefix}_seasonal_ma_lags", placeholder="例如 1,2"
        )
    (
        response_log,
        enforce_stationarity,
        enforce_invertibility,
        method,
        maxiter,
        cov_type,
    ) = render_sarimax_advanced_settings(st_obj, prefix, log=log)
    try:
        return SARIMAXConfig(
            order=(
                _sparse_or_continuous(ar_lags, p, maximum=6),
                int(d),
                _sparse_or_continuous(ma_lags, q, maximum=6),
            ),
            seasonal_order=(
                _sparse_or_continuous(seasonal_ar_lags, P, maximum=3),
                int(D),
                _sparse_or_continuous(seasonal_ma_lags, Q, maximum=3),
                int(s),
            ),
            exog_operators=_render_exog_operators(
                st_obj,
                exog,
                prefix,
                state_manager,
                exog_log_names=exog_log_names,
            ),
            trend=trend,
            log=response_log,
            enforce_stationarity=enforce_stationarity,
            enforce_invertibility=enforce_invertibility,
            fit_method=method,
            maxiter=int(maxiter),
            cov_type=cov_type,
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"SARIMAX 设置有误：{exc}")
        return None


def _render_auto_config(
    st_obj,
    prefix: str = "sarimax_auto",
    *,
    log: bool | None = False,
    exog: pd.DataFrame | None = None,
    exog_log_names: tuple[str, ...] = (),
    state_manager: StateStore = state,
) -> AutoSARIMAXConfig | None:
    """渲染 AutoSARIMAX 搜索范围；范围非法时提示并返回 None。"""
    layout_columns = st_obj.columns([2, 1])
    with layout_columns[0]:
        ranges: dict[str, tuple[int, int]] = {}
        range_columns = st_obj.columns(3)
        for column, name in zip(range_columns, ("p", "d", "q")):
            ranges[name] = render_range_inputs(
                column,
                name,
                _AUTO_RANGE_DEFAULTS[name],
                prefix,
                SARIMAX_RANGE_LIMITS[name],
            )
        seasonal_columns = st_obj.columns(3)
        for column, name in zip(seasonal_columns, ("P", "D", "Q")):
            ranges[name] = render_range_inputs(
                column,
                name,
                _AUTO_RANGE_DEFAULTS[name],
                prefix,
                SARIMAX_RANGE_LIMITS[name],
            )
    with layout_columns[1]:
        trend = render_trend_selector(st_obj, prefix)
        s = st_obj.number_input(
            "s（季节周期）",
            0,
            365,
            0,
            key=f"{prefix}_s",
            help="0 表示不搜索季节项；输入 5、21、63 或 252 可搜索对应交易日周期。",
        )
    (
        response_log,
        enforce_stationarity,
        enforce_invertibility,
        method,
        maxiter,
        cov_type,
    ) = render_sarimax_advanced_settings(st_obj, prefix, log=log)
    try:
        config = AutoSARIMAXConfig(
            p=ranges["p"],
            d=ranges["d"],
            q=ranges["q"],
            P=ranges["P"],
            D=ranges["D"],
            Q=ranges["Q"],
            s=int(s),
            exog_operators=_render_exog_operators(
                st_obj,
                exog,
                prefix,
                state_manager,
                exog_log_names=exog_log_names,
            ),
            trend=trend,
            criterion=_AUTO_SELECTION_DEFAULT,
            log=response_log,
            fit_method=method,
            maxiter=int(maxiter),
            cov_type=cov_type,
            enforce_stationarity=enforce_stationarity,
            enforce_invertibility=enforce_invertibility,
        )
    except ValueError as exc:
        st_obj.error(f"搜索范围设置有误：{exc}")
        return None
    count = config.candidate_count()
    st_obj.caption(_AUTO_PARALLEL_NOTICE)
    st_obj.caption(f"网格搜索将尝试 {count} 个模型组合。")
    if count > _AUTO_MAX:
        st_obj.warning(
            f"组合数超过 {_AUTO_MAX}，拟合耗时可能很长，建议缩小搜索范围。"
        )
    return config


def _sparse_or_continuous(
    text: object,
    fallback: int,
    *,
    maximum: int,
) -> int | tuple[int, ...]:
    """优先使用用户填写的稀疏活动滞后，并保持 UI 上限。"""
    lags = parse_sparse_lags(text, minimum=1)
    if lags is None:
        return int(fallback)
    if any(lag > maximum for lag in lags):
        raise ValueError(f"活动滞后必须不大于 {maximum}")
    return lags


def _render_exog_operators(
    st_obj,
    exog: pd.DataFrame | None,
    prefix: str,
    state_manager: StateStore,
    *,
    exog_log_names: tuple[str, ...] = (),
) -> dict[str, TimeSeriesOperator]:
    """渲染逐变量时序算子，并返回非恒等映射。"""
    if exog is None or exog.empty:
        return {}
    names = [str(name) for name in exog.columns]
    with st_obj.expander("外生变量时序算子", expanded=False):
        st_obj.caption(
            "算子按季节差分、普通差分、滞后依次作用；未来外生变量仍应填写原始路径。"
        )
        defaults = pd.DataFrame(
            {
                "变量": names,
                "滞后 L": 0,
                "普通差分 d": 0,
                "季节差分 D": 0,
                "季节周期 s": 0,
            }
        )
        table_key = f"{prefix}_exog_operators_table"
        edited = st_obj.data_editor(
            restore_table_state(table_key, defaults, names, state_manager=state_manager),
            key=f"{prefix}_exog_operators",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state_manager.set(table_key, edited.copy())
    operators: dict[str, TimeSeriesOperator] = {}
    for _, row in edited.iterrows():
        seasonal_difference = int(row["季节差分 D"])
        seasonal_period = int(row["季节周期 s"])
        operator = TimeSeriesOperator(
            lag=int(row["滞后 L"]),
            difference=int(row["普通差分 d"]),
            seasonal_difference=seasonal_difference,
            seasonal_period=(seasonal_period if seasonal_difference else None),
            log=str(row["变量"]) in exog_log_names,
        )
        if not operator.is_identity:
            operators[str(row["变量"])] = operator
    return operators


__all__ = ["render_sarimax_error_options", "render_sarimax_options"]
