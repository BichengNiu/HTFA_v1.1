"""标准 ARDL 模型族的参数控件。"""

from __future__ import annotations

import pandas as pd

from htfa.models.univariate.sarimax.core.ardl_config import ARDLConfig
from htfa.models.univariate.sarimax.ui.model_options_shared import (
    render_trend_selector,
    restore_table_state,
)
from htfa.models.univariate.sarimax.ui.model_options_sarimax import (
    render_sarimax_error_options,
)
from htfa.models.univariate.sarimax.ui.state import state
from htfa.models.univariate.common.state import StateStore


def render_ardl_options(
    st_obj,
    exog: pd.DataFrame | None,
    *,
    response_log: bool,
    key_prefix: str = "sarimax_ardl",
    state_manager: StateStore = state,
) -> ARDLConfig | None:
    """渲染标准 ARDL 的手动滞后与 SARIMA 误差设置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    exog : pandas.DataFrame or None
        当前选择的外生变量表。
    response_log : bool
        目标变量对数变换状态。

    Returns
    -------
    ARDLConfig or None
        构建好的 ARDL 配置；控件参数无效时返回 ``None``。
    """
    if exog is None or exog.empty:
        st_obj.warning("ARDL 需要至少一个解释变量；请在上方变量选择中添加。")
        return None
    prefix = key_prefix
    with st_obj.container(border=True):
        st_obj.markdown("**误差 SARIMA 结构**")
        error = render_sarimax_error_options(
            st_obj,
            f"{prefix}_error",
            include_trend=False,
            response_log=response_log,
            state_manager=state_manager,
        )
    if error is None:
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**响应结构**")
        response_columns = st_obj.columns(3)
        target_lag = response_columns[0].number_input(
            "目标变量滞后",
            0,
            12,
            1,
            key=f"{prefix}_target_lag",
        )
        trend = render_trend_selector(response_columns[1], prefix)
        causal = response_columns[2].checkbox(
            "仅使用滞后输入（不含当期）", key=f"{prefix}_causal"
        )
        seasonal = st_obj.checkbox("加入季节虚拟项", key=f"{prefix}_seasonal")
        period = None
        if seasonal:
            period = st_obj.number_input(
                "季节周期", 2, 365, 12, key=f"{prefix}_period"
            )
    with st_obj.container(border=True):
        st_obj.markdown("**输入动态**")
        label = "输入滞后"
        orders = st_obj.data_editor(
            restore_table_state(
                f"{prefix}_input_table",
                pd.DataFrame({"变量": list(exog.columns), label: 0}),
                list(exog.columns),
                state_manager=state_manager,
            ),
            key=f"{prefix}_input_table",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state_manager.set(f"{prefix}_input_table", orders.copy())
    with st_obj.container(border=True):
        st_obj.markdown("**估计设置**")
        hold_back_value = st_obj.number_input(
            "统一预留期（0=自动）", 0, 1000, 0, key=f"{prefix}_hold_back"
        )
    try:
        pairs = tuple(
            (str(row["变量"]), int(row[label])) for _, row in orders.iterrows()
        )
        common = {
            "trend": trend,
            "causal": bool(causal),
            "seasonal": bool(seasonal),
            "period": None if period is None else int(period),
            "hold_back": (
                None if int(hold_back_value) == 0 else int(hold_back_value)
            ),
            "log": bool(response_log),
            "cov_type": "nonrobust",
        }
        return ARDLConfig(
            lags=int(target_lag),
            input_orders=pairs,
            error=error,
            **common,
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"ARDL 设置有误：{exc}")
        return None


__all__ = ["render_ardl_options"]
