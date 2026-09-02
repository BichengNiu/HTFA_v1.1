"""RDL 模型族的参数控件。"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.rdl_config import (
    RDLConfig,
    RDLInputConfig,
)
from dashboard.models.SARIMAX.ui.model_options_shared import (
    parse_sparse_lags,
    restore_table_state,
)
from dashboard.models.SARIMAX.ui.model_options_sarimax import (
    render_sarimax_error_options,
)
from dashboard.models.SARIMAX.ui.state import state
from dashboard.models.common.state import StateStore


def render_rdl_options(
    st_obj,
    exog: pd.DataFrame | None,
    *,
    response_log: bool,
    prefix: str = "sarimax_rdl",
    state_manager: StateStore = state,
) -> RDLConfig | None:
    """渲染 RDL 的误差结构、输入动态与估计设置。

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
    RDLConfig or None
        构建好的 RDL 配置；控件参数无效时返回 ``None``。
    """
    if exog is None or exog.empty:
        st_obj.warning("RDL 需要至少一个解释变量；请在上方变量选择中添加。")
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**响应 / 误差结构**")
        error = render_sarimax_error_options(
            st_obj,
            f"{prefix}_error",
            response_log=response_log,
            state_manager=state_manager,
        )
    if error is None:
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**输入动态**")
        inputs = _render_rdl_inputs(st_obj, exog, prefix=prefix, state_manager=state_manager)
    if inputs is None:
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**估计设置**")
        stable = st_obj.checkbox(
            "强制传递函数分母稳定",
            value=True,
            key=f"{prefix}_enforce_stability",
        )
    try:
        return RDLConfig(
            inputs=inputs,
            error=error,
            enforce_distributed_lag_stability=stable,
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"RDL 设置有误：{exc}")
        return None


def _render_rdl_inputs(
    st_obj,
    exog: pd.DataFrame,
    *,
    prefix: str,
    state_manager: StateStore,
) -> tuple[RDLInputConfig, ...] | None:
    """渲染固定行的 RDL 传递函数参数表与可选稀疏滞后设置。"""
    names = list(exog.columns)
    basic = restore_table_state(
        f"{prefix}_input_table",
        pd.DataFrame(
            {"变量": names, "分子阶数": 0, "分母阶数": 0, "延迟": 0}
        ),
        names,
        state_manager=state_manager,
    )
    edited = st_obj.data_editor(
        basic,
        key=f"{prefix}_input_table",
        num_rows="fixed",
        disabled=("变量",),
        width="stretch",
    )
    state_manager.set(f"{prefix}_input_table", edited.copy())
    with st_obj.expander("高级：稀疏滞后与初始化策略", expanded=False):
        st_obj.caption("留空即采用上表连续阶数；分母稀疏滞后从 1 开始。")
        advanced = st_obj.data_editor(
            restore_table_state(
                f"{prefix}_advanced_table",
                pd.DataFrame(
                    {
                        "变量": names,
                        "分子稀疏滞后": "",
                        "分母稀疏滞后": "",
                        "初始化": "auto",
                    }
                ),
                names,
                state_manager=state_manager,
            ),
            key=f"{prefix}_advanced_table",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state_manager.set(f"{prefix}_advanced_table", advanced.copy())
    try:
        return tuple(
            RDLInputConfig(
                name=str(name),
                numerator_order=int(edited.iloc[index]["分子阶数"]),
                denominator_order=int(edited.iloc[index]["分母阶数"]),
                delay=int(edited.iloc[index]["延迟"]),
                numerator_lags=parse_sparse_lags(
                    advanced.iloc[index]["分子稀疏滞后"], minimum=0
                ),
                denominator_lags=parse_sparse_lags(
                    advanced.iloc[index]["分母稀疏滞后"], minimum=1
                ),
                initialization=str(advanced.iloc[index]["初始化"]),
            )
            for index, name in enumerate(names)
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"RDL 输入动态设置有误：{exc}")
        return None


__all__ = ["render_rdl_options"]
