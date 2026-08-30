"""SARIMAX 及 RDL 误差项的参数控件。"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.config_shared import (
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    SARIMAX_RANGE_LIMITS,
)
from dashboard.models.SARIMAX.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.ui.model_options_shared import (
    render_range_inputs,
    render_sarimax_advanced_settings,
    render_trend_selector,
)

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
    response_log: bool = False,
) -> SARIMAXConfig | AutoSARIMAXConfig | None:
    """渲染 SARIMAX 模型族的手动或自动配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    mode : str
        配置方式，支持 ``手动配置`` 和 ``自动选阶``。
    response_log : bool, default=False
        通用输入模块提供的目标变量对数变换状态。

    Returns
    -------
    SARIMAXConfig or AutoSARIMAXConfig or None
        构建好的配置；控件参数无效时返回 ``None``。
    """
    if mode == "手动配置":
        return _render_manual_config(st_obj, log=response_log)
    return _render_auto_config(st_obj, log=response_log)


def render_sarimax_error_options(
    st_obj,
    prefix: str,
    *,
    automatic: bool,
    response_log: bool = False,
) -> SARIMAXConfig | AutoSARIMAXConfig | None:
    """渲染 RDL 使用的 SARIMAX 误差结构配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    prefix : str
        控件键前缀。
    automatic : bool
        是否使用自动 SARIMAX 误差阶数搜索。
    response_log : bool, default=False
        目标变量对数变换状态。

    Returns
    -------
    SARIMAXConfig or AutoSARIMAXConfig or None
        RDL 误差项配置。
    """
    return (
        _render_auto_config(st_obj, prefix, log=response_log)
        if automatic
        else _render_manual_config(st_obj, prefix, log=response_log)
    )


def _render_manual_config(
    st_obj,
    prefix: str = "sarimax",
    *,
    log: bool | None = False,
) -> SARIMAXConfig:
    """渲染手动 SARIMAX 阶数与高级设置。"""
    order_columns = st_obj.columns(4)
    p = order_columns[0].number_input("p（AR 阶数）", 0, 6, 1, key=f"{prefix}_p")
    d = order_columns[1].number_input("d（差分阶数）", 0, 2, 0, key=f"{prefix}_d")
    q = order_columns[2].number_input("q（MA 阶数）", 0, 6, 1, key=f"{prefix}_q")
    trend = render_trend_selector(order_columns[3], prefix)
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
    (
        response_log,
        enforce_stationarity,
        enforce_invertibility,
        method,
        maxiter,
        cov_type,
    ) = render_sarimax_advanced_settings(st_obj, prefix, log=log)
    return SARIMAXConfig(
        order=(int(p), int(d), int(q)),
        seasonal_order=(int(P), int(D), int(Q), int(s)),
        trend=trend,
        log=response_log,
        enforce_stationarity=enforce_stationarity,
        enforce_invertibility=enforce_invertibility,
        fit_method=method,
        maxiter=int(maxiter),
        cov_type=cov_type,
    )


def _render_auto_config(
    st_obj,
    prefix: str = "sarimax_auto",
    *,
    log: bool | None = False,
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


__all__ = ["render_sarimax_error_options", "render_sarimax_options"]
