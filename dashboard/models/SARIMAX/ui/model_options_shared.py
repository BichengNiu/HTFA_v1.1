"""动态回归参数控件共用的 UI 小 module。"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.config_shared import (
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
)
from dashboard.models.common.state import StateStore
from dashboard.models.SARIMAX.ui.state import state

_TREND_COMPONENTS = ("常数项", "线性趋势")


def render_trend_selector(st_obj, prefix: str) -> str:
    """渲染常数项/线性趋势多选并映射为 Ts 趋势代码。"""
    selected = st_obj.multiselect(
        "常数/趋势项（可多选）",
        options=_TREND_COMPONENTS,
        default=["常数项"],
        key=f"{prefix}_trend_components",
        help="不选表示无常数项、无线性趋势；两项都选表示同时包含二者。",
    )
    has_constant = "常数项" in selected
    has_trend = "线性趋势" in selected
    if has_constant and has_trend:
        return "ct"
    if has_constant:
        return "c"
    if has_trend:
        return "t"
    return "n"


def render_sarimax_advanced_settings(
    st_obj,
    prefix: str,
    *,
    log: bool,
) -> tuple[bool, bool, bool, str, int, str]:
    """渲染手动与自动 SARIMAX 共用的高级设置。"""
    with st_obj.expander("高级设置（优化器、协方差与约束）"):
        optimizer_columns = st_obj.columns(3)
        method = optimizer_columns[0].selectbox(
            "优化器",
            options=list(SARIMAX_OPTIMIZERS),
            index=list(SARIMAX_OPTIMIZERS).index("bfgs"),
            key=f"{prefix}_method",
        )
        maxiter = optimizer_columns[1].number_input(
            "最大迭代次数",
            10,
            10000,
            500,
            step=50,
            key=f"{prefix}_maxiter",
        )
        cov_type = optimizer_columns[2].selectbox(
            "协方差估计",
            options=list(SARIMAX_COV_TYPES),
            index=list(SARIMAX_COV_TYPES).index("oim"),
            key=f"{prefix}_cov_type",
        )
        constraint_columns = st_obj.columns(2)
        response_log = bool(log)
        enforce_stationarity = constraint_columns[0].checkbox(
            "强制 AR 多项式平稳",
            value=False,
            key=f"{prefix}_enforce_stationarity",
        )
        enforce_invertibility = constraint_columns[1].checkbox(
            "强制 MA 多项式可逆",
            value=False,
            key=f"{prefix}_enforce_invertibility",
        )
    return (
        bool(response_log),
        bool(enforce_stationarity),
        bool(enforce_invertibility),
        str(method),
        int(maxiter),
        str(cov_type),
    )


def render_range_inputs(
    container,
    name: str,
    default: tuple[int, int],
    prefix: str,
    limits: tuple[int, int],
) -> tuple[int, int]:
    """渲染单个阶数的双端整数滑块。"""
    minimum, maximum = limits
    value = (
        max(minimum, min(maximum, default[0])),
        max(minimum, min(maximum, default[1])),
    )
    if value[0] > value[1]:
        value = default
    return tuple(
        int(item)
        for item in container.slider(
            f"{name} 搜索范围",
            min_value=minimum,
            max_value=maximum,
            value=value,
            step=1,
            key=f"{prefix}_{name}_range",
        )
    )


def parse_sparse_lags(value: object, *, minimum: int) -> tuple[int, ...] | None:
    """将高级表格中的逗号分隔滞后转换为规范化元组。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        lags = tuple(sorted({int(token.strip()) for token in text.split(",")}))
    except ValueError as exc:
        raise ValueError("稀疏滞后请用逗号分隔的整数，例如 0,2,4") from exc
    if any(lag < minimum for lag in lags):
        raise ValueError(f"稀疏滞后必须不小于 {minimum}")
    return lags


def restore_table_state(
    state_key: str,
    defaults: pd.DataFrame,
    variable_names: list[str],
    *,
    state_manager: StateStore = state,
) -> pd.DataFrame:
    """仅在变量结构仍兼容时恢复 data_editor 内容。"""
    saved = state_manager.get(state_key)
    if not isinstance(saved, pd.DataFrame):
        return defaults
    if list(saved.columns) != list(defaults.columns):
        return defaults
    if saved["变量"].tolist() != variable_names:
        return defaults
    return saved.copy()


__all__ = [
    "parse_sparse_lags",
    "render_range_inputs",
    "render_sarimax_advanced_settings",
    "render_trend_selector",
    "restore_table_state",
]
