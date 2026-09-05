"""RDL 模型族的参数控件。"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.rdl_config import (
    RDLConfig,
    RDLInputConfig,
    RDLInterventionConfig,
    RDL_INTERVENTION_NAME,
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
    intervention_analysis: bool = False,
    model_dates: pd.Index | None = None,
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
    intervention_analysis : bool, default=False
        是否启用历史干预变量 I。
    model_dates : pandas.Index or None, optional
        当前训练样本的实际模型观测日期。

    Returns
    -------
    RDLConfig or None
        构建好的 RDL 配置；控件参数无效时返回 ``None``。
    """
    if not intervention_analysis and (exog is None or exog.empty):
        st_obj.warning("RDL 需要至少一个解释变量；请在上方变量选择中添加。")
        return None
    intervention = None
    if intervention_analysis:
        dates = _normalise_model_dates(model_dates)
        if dates is None:
            st_obj.error("干预分析需要至少一个有效的历史模型观测日期。")
            return None
        with st_obj.container(border=True):
            st_obj.markdown("**干预冲击定义**")
            intervention = _render_intervention_controls(
                st_obj,
                dates,
                prefix=prefix,
            )
        if intervention is None:
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
        inputs = _render_rdl_inputs(
            st_obj,
            exog,
            intervention=intervention,
            prefix=prefix,
            state_manager=state_manager,
        )
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
            intervention=intervention,
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"RDL 设置有误：{exc}")
        return None


def _render_rdl_inputs(
    st_obj,
    exog: pd.DataFrame | None,
    *,
    intervention: RDLInterventionConfig | None,
    prefix: str,
    state_manager: StateStore,
) -> tuple[RDLInputConfig, ...] | None:
    """渲染固定行的 RDL 传递函数参数表与可选稀疏滞后设置。"""
    ordinary_names = [] if exog is None else [str(name) for name in exog.columns]
    names = ordinary_names + (
        [RDL_INTERVENTION_NAME] if intervention is not None else []
    )
    display_names = ordinary_names + (
        ["I（干预变量）"] if intervention is not None else []
    )
    basic = restore_table_state(
        f"{prefix}_input_table",
        pd.DataFrame(
            {
                "变量": display_names,
                "分子阶数": 0,
                "分母阶数": 0,
                "延迟": 0,
            }
        ),
        display_names,
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
                        "变量": display_names,
                        "分子稀疏滞后": "",
                        "分母稀疏滞后": "",
                        "初始化": "auto",
                    }
                ),
                display_names,
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


_INTERVENTION_KIND_LABELS = {
    "单期冲击（pulse）": "pulse",
    "持续冲击（step）": "step",
    "区间冲击（interval）": "temporary",
}


def _normalise_model_dates(model_dates: pd.Index | None) -> pd.DatetimeIndex | None:
    """规范化 RDL 干预控件使用的实际模型观测日期。"""
    if model_dates is None:
        return None
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(model_dates))
    except (TypeError, ValueError):
        return None
    if len(dates) == 0 or dates.hasnans or dates.has_duplicates:
        return None
    if not dates.is_monotonic_increasing:
        return None
    return dates


def _render_intervention_controls(
    st_obj,
    model_dates: pd.DatetimeIndex,
    *,
    prefix: str,
) -> RDLInterventionConfig | None:
    """渲染冲击类型和历史观测日期控件。"""
    labels = tuple(_INTERVENTION_KIND_LABELS)
    selected_label = st_obj.selectbox(
        "冲击类型",
        options=labels,
        key=f"{prefix}_intervention_kind",
        help="I 为 0/1 虚拟变量；冲击幅度由 I 的 RDL 参数估计，不单独设置。",
    )
    kind = _INTERVENTION_KIND_LABELS[str(selected_label)]
    dates = tuple(pd.Timestamp(value) for value in model_dates)
    timestamp_formatter = _build_intervention_timestamp_formatter(dates)
    middle = len(dates) // 2
    default_start = dates[middle]
    if kind == "pulse":
        start_date = st_obj.selectbox(
            "冲击发生日期",
            options=list(dates),
            index=middle,
            format_func=timestamp_formatter,
            key=f"{prefix}_intervention_pulse_date",
        )
        end_date = None
    elif kind == "temporary":
        default_end = dates[min(middle + 1, len(dates) - 1)]
        selected_window = st_obj.select_slider(
            "冲击起止日期（包含端点）",
            options=list(dates),
            value=(default_start, default_end),
            format_func=timestamp_formatter,
            key=f"{prefix}_intervention_window",
        )
        if (
            not isinstance(selected_window, (tuple, list))
            or len(selected_window) != 2
        ):
            st_obj.warning("请选择完整的干预起止日期。")
            return None
        start_date, end_date = selected_window
    else:
        step_key = f"{prefix}_intervention_start"
        has_step_state = _pin_step_intervention_window(
            st_obj,
            step_key,
            dates,
            default_start,
        )
        step_slider_kwargs = {
            "options": list(dates),
            "format_func": timestamp_formatter,
            "key": step_key,
        }
        if not has_step_state:
            step_slider_kwargs["value"] = (default_start, dates[-1])
        selected_window = st_obj.select_slider(
            "冲击起始日期（之后持续）",
            **step_slider_kwargs,
        )
        if (
            not isinstance(selected_window, (tuple, list))
            or len(selected_window) != 2
        ):
            st_obj.warning("请选择完整的持续干预起始范围。")
            return None
        start_date = selected_window[0]
        end_date = None
    try:
        return RDLInterventionConfig(
            start_date=pd.Timestamp(start_date),
            kind=kind,
            end_date=None if end_date is None else pd.Timestamp(end_date),
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"干预冲击设置有误：{exc}")
    return None


def _pin_step_intervention_window(
    st_obj,
    key: str,
    dates: tuple[pd.Timestamp, ...],
    default_start: pd.Timestamp,
) -> bool:
    """固定持续冲击范围的上端点为最后一个模型日期。"""
    session = getattr(st_obj, "session_state", None)
    if session is None or key not in session:
        return False

    start_date = default_start
    current = session[key]
    if isinstance(current, (tuple, list)) and len(current) == 2:
        try:
            candidate = pd.Timestamp(current[0])
        except (TypeError, ValueError):
            candidate = default_start
        if candidate in dates:
            start_date = candidate
    session[key] = (start_date, dates[-1])
    return True


def _build_intervention_timestamp_formatter(model_dates: pd.Index):
    """按模型日期中实际存在的最小时间粒度构造显示格式化器。"""
    dates = tuple(pd.Timestamp(value) for value in model_dates)
    if all(
        value.hour == 0
        and value.minute == 0
        and value.second == 0
        and value.microsecond == 0
        and value.nanosecond == 0
        for value in dates
    ):
        date_format = "%Y-%m-%d"
    elif all(
        value.minute == 0
        and value.second == 0
        and value.microsecond == 0
        and value.nanosecond == 0
        for value in dates
    ):
        date_format = "%Y-%m-%d %H"
    elif all(
        value.second == 0
        and value.microsecond == 0
        and value.nanosecond == 0
        for value in dates
    ):
        date_format = "%Y-%m-%d %H:%M"
    else:
        date_format = "%Y-%m-%d %H:%M:%S"

    def format_timestamp(value) -> str:
        return pd.Timestamp(value).strftime(date_format)

    return format_timestamp


__all__ = ["render_rdl_options"]
