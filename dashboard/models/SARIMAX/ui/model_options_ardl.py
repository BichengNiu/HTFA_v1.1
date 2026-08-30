"""标准 ARDL 模型族的参数控件。"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.ardl_config import (
    ARDLConfig,
    AutoARDLConfig,
)
from dashboard.models.SARIMAX.core.config_shared import (
    ARDL_CRITERIA,
    ARDL_SEARCH_METHODS,
)
from dashboard.models.SARIMAX.ui.model_options_shared import (
    render_trend_selector,
    restore_table_state,
)
from dashboard.models.SARIMAX.ui.state import state

_AUTO_PARALLEL_NOTICE = (
    "候选模型按规模自动调度：少于 8 个或预计工作量较低时串行；"
    "其余搜索最多使用 4 个单线程数值进程。"
)


def render_ardl_options(
    st_obj,
    exog: pd.DataFrame | None,
    *,
    automatic: bool,
    response_log: bool,
) -> ARDLConfig | AutoARDLConfig | None:
    """渲染标准 ARDL 的目标/输入滞后与自动选阶设置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    exog : pandas.DataFrame or None
        当前选择的外生变量表。
    automatic : bool
        是否使用自动 ARDL 选阶。
    response_log : bool
        目标变量对数变换状态。

    Returns
    -------
    ARDLConfig or AutoARDLConfig or None
        构建好的 ARDL 配置；控件参数无效时返回 ``None``。
    """
    if exog is None or exog.empty:
        st_obj.warning("ARDL 需要至少一个解释变量；请在上方变量选择中添加。")
        return None
    prefix = "sarimax_auto_ardl" if automatic else "sarimax_ardl"
    with st_obj.container(border=True):
        st_obj.markdown("**响应 / 误差结构**")
        response_columns = st_obj.columns(3)
        target_lag = response_columns[0].number_input(
            "最大目标滞后" if automatic else "目标变量滞后",
            0,
            12,
            3 if automatic else 1,
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
        label = "最大输入滞后" if automatic else "输入滞后"
        orders = st_obj.data_editor(
            restore_table_state(
                f"{prefix}_input_table",
                pd.DataFrame({"变量": list(exog.columns), label: 0}),
                list(exog.columns),
            ),
            key=f"{prefix}_input_table",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state.set(f"{prefix}_input_table", orders.copy())
    with st_obj.container(border=True):
        st_obj.markdown("**估计设置**")
        settings = st_obj.columns(2)
        hold_back_value = settings[0].number_input(
            "统一预留期（0=自动）", 0, 1000, 0, key=f"{prefix}_hold_back"
        )
        cov_type = settings[1].selectbox(
            "协方差估计",
            ("nonrobust", "HC0", "HC1", "HC2", "HC3"),
            key=f"{prefix}_cov_type",
        )
        criterion = "bic"
        search_method = "hierarchical"
        if automatic:
            choice = st_obj.columns(2)
            criterion = choice[0].selectbox(
                "选阶准则", ARDL_CRITERIA, index=1, key=f"{prefix}_criterion"
            )
            search_method = choice[1].selectbox(
                "搜索方式",
                ARDL_SEARCH_METHODS,
                key=f"{prefix}_search_method",
                format_func=lambda value: (
                    "分层搜索" if value == "hierarchical" else "全局搜索"
                ),
            )
            if search_method == "global":
                st_obj.warning(
                    "全局搜索会枚举滞后子集，变量较多或上限较高时计算量会迅速增加。"
                )
            st_obj.caption(_AUTO_PARALLEL_NOTICE)
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
            "cov_type": cov_type,
        }
        if automatic:
            return AutoARDLConfig(
                maxlag=int(target_lag),
                max_input_orders=pairs,
                criterion=criterion,
                search_method=search_method,
                **common,
            )
        return ARDLConfig(lags=int(target_lag), input_orders=pairs, **common)
    except (TypeError, ValueError) as exc:
        st_obj.error(f"ARDL 设置有误：{exc}")
        return None


__all__ = ["render_ardl_options"]
