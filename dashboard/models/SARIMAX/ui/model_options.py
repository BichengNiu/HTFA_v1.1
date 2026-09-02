"""动态回归模型族参数路由 facade。

每个模型族的控件与配置构建位于独立 module；此文件只负责选择相应
的实现，避免训练页面承担模型族分支。
"""

from __future__ import annotations

import pandas as pd

from dashboard.models.common.state import StateStore
from dashboard.models.SARIMAX.ui.state import state

from dashboard.models.SARIMAX.ui.model_options_ardl import render_ardl_options
from dashboard.models.SARIMAX.ui.model_options_rdl import render_rdl_options
from dashboard.models.SARIMAX.ui.model_options_sarimax import (
    render_sarimax_options,
)
from dashboard.models.SARIMAX.ui.model_options_shared import (
    render_trend_selector as _render_trend_selector,
)


def render_model_options(
    st_obj,
    family: str,
    mode: str,
    exog: pd.DataFrame | None,
    *,
    response_log: bool = False,
    exog_log_names: tuple[str, ...] = (),
    intervention_analysis: bool = False,
    model_dates: pd.Index | None = None,
    key_prefix: str = "sarimax",
    state_manager: StateStore = state,
):
    """渲染模型族特有参数并返回模型配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    family : str
        模型族名称，支持 ``SARIMAX``、``RDL`` 和 ``ARDL``。
    mode : str
        SARIMAX 配置方式；RDL/ARDL 始终使用手动配置。
    exog : pandas.DataFrame or None
        当前选择的外生变量表；RDL 需要普通 X 或已启用的干预变量 I，
        ARDL 需要至少一列普通解释变量。
    response_log : bool, default=False
        通用输入模块提供的目标变量对数变换状态。
    exog_log_names : tuple[str, ...], default=()
        需要对数变换的 SARIMAX 外生变量名称。
    intervention_analysis : bool, default=False
        是否为 RDL 启用历史干预变量 I。
    model_dates : pandas.Index or None, optional
        当前训练样本的实际模型观测日期，供 RDL 干预日期选择。

    Returns
    -------
    object or None
        对应模型配置；控件参数无效时返回 ``None``。
    """
    if family == "SARIMAX":
        return render_sarimax_options(
            st_obj,
            mode,
            exog=exog,
            response_log=response_log,
            exog_log_names=exog_log_names,
            prefix=key_prefix,
            state_manager=state_manager,
        )
    if family == "RDL":
        return render_rdl_options(
            st_obj,
            exog,
            response_log=response_log,
            intervention_analysis=intervention_analysis,
            model_dates=model_dates,
            prefix=key_prefix,
            state_manager=state_manager,
        )
    if family == "ARDL":
        return render_ardl_options(
            st_obj,
            exog,
            response_log=response_log,
            key_prefix=key_prefix,
            state_manager=state_manager,
        )
    raise ValueError(f"不支持的模型族：{family}")


__all__ = ["render_model_options"]
