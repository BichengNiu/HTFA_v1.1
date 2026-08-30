"""动态回归模型族参数路由 facade。

每个模型族的控件与配置构建位于独立 module；此文件只负责选择相应
的实现，避免训练页面承担模型族分支。
"""

from __future__ import annotations

import pandas as pd

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
):
    """渲染模型族特有参数并返回模型配置。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 控件方法的对象。
    family : str
        模型族名称，支持 ``SARIMAX``、``RDL`` 和 ``ARDL``。
    mode : str
        配置方式，支持 ``手动配置`` 和 ``自动选阶``。
    exog : pandas.DataFrame or None
        当前选择的外生变量表；RDL/ARDL 需要至少一列。
    response_log : bool, default=False
        通用输入模块提供的目标变量对数变换状态。

    Returns
    -------
    object or None
        对应模型配置；控件参数无效时返回 ``None``。
    """
    if family == "SARIMAX":
        return render_sarimax_options(st_obj, mode, response_log=response_log)
    if family == "RDL":
        return render_rdl_options(
            st_obj,
            exog,
            automatic=mode == "自动选阶",
            response_log=response_log,
        )
    if family == "ARDL":
        return render_ardl_options(
            st_obj,
            exog,
            automatic=mode == "自动选阶",
            response_log=response_log,
        )
    raise ValueError(f"不支持的模型族：{family}")


__all__ = ["render_model_options"]
