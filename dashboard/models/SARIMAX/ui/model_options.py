"""动态回归模型族的特有参数设置。

通用训练工作流只负责数据和生命周期；本模块负责 SARIMAX、RDL、ARDL
各自的参数控件和配置对象构建。
"""

from __future__ import annotations

import pandas as pd

from dashboard.models.SARIMAX.core.model_config import (
    ARDL_CRITERIA,
    ARDL_SEARCH_METHODS,
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    SARIMAX_RANGE_LIMITS,
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    RDLConfig,
    RDLInputConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.ui.state import state

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
_TREND_COMPONENTS = ("常数项", "线性趋势")


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
        return (
            _render_manual_config(st_obj, log=response_log)
            if mode == "手动配置"
            else _render_auto_config(st_obj, log=response_log)
        )
    if family == "RDL":
        return _render_rdl_config(
            st_obj, exog, automatic=mode == "自动选阶", log=response_log
        )
    if family == "ARDL":
        return _render_ardl_config(
            st_obj, exog, automatic=mode == "自动选阶", log=response_log
        )
    raise ValueError(f"不支持的模型族：{family}")


def _render_trend_selector(st_obj, prefix: str) -> str:
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


def _render_manual_config(
    st_obj, prefix: str = "sarimax", *, log: bool | None = False
) -> SARIMAXConfig:
    """渲染手动 SARIMAX 阶数与高级设置。"""
    order_columns = st_obj.columns(4)
    p = order_columns[0].number_input("p（AR 阶数）", 0, 6, 1, key=f"{prefix}_p")
    d = order_columns[1].number_input("d（差分阶数）", 0, 2, 0, key=f"{prefix}_d")
    q = order_columns[2].number_input("q（MA 阶数）", 0, 6, 1, key=f"{prefix}_q")
    trend = _render_trend_selector(order_columns[3], prefix)
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
    ) = _render_sarimax_advanced_settings(st_obj, prefix, log=log)
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
    st_obj, prefix: str = "sarimax_auto", *, log: bool | None = False
) -> AutoSARIMAXConfig | None:
    """渲染 AutoSARIMAX 搜索范围；范围非法时提示并返回 None。"""
    layout_columns = st_obj.columns([2, 1])
    with layout_columns[0]:
        ranges: dict[str, tuple[int, int]] = {}
        range_columns = st_obj.columns(3)
        for column, name in zip(range_columns, ("p", "d", "q")):
            ranges[name] = _render_range_inputs(
                column,
                name,
                _AUTO_RANGE_DEFAULTS[name],
                prefix,
                SARIMAX_RANGE_LIMITS[name],
            )
        seasonal_columns = st_obj.columns(3)
        for column, name in zip(seasonal_columns, ("P", "D", "Q")):
            ranges[name] = _render_range_inputs(
                column,
                name,
                _AUTO_RANGE_DEFAULTS[name],
                prefix,
                SARIMAX_RANGE_LIMITS[name],
            )
    with layout_columns[1]:
        trend = _render_trend_selector(st_obj, prefix)
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
    ) = _render_sarimax_advanced_settings(st_obj, prefix, log=log)
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


def _render_sarimax_advanced_settings(
    st_obj, prefix: str, *, log: bool
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


def _render_range_inputs(
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


def _parse_sparse_lags(value: object, *, minimum: int) -> tuple[int, ...] | None:
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


def _restore_table_state(
    state_key: str,
    defaults: pd.DataFrame,
    variable_names: list[str],
) -> pd.DataFrame:
    """仅在变量结构仍兼容时恢复 data_editor 内容。"""
    saved = state.get(state_key)
    if not isinstance(saved, pd.DataFrame):
        return defaults
    if list(saved.columns) != list(defaults.columns):
        return defaults
    if saved["变量"].tolist() != variable_names:
        return defaults
    return saved.copy()


def _render_rdl_inputs(st_obj, exog: pd.DataFrame) -> tuple[RDLInputConfig, ...] | None:
    """渲染固定行的 RDL 传递函数参数表与可选稀疏滞后设置。"""
    names = list(exog.columns)
    basic = _restore_table_state(
        "rdl_input_table",
        pd.DataFrame(
            {"变量": names, "分子阶数": 0, "分母阶数": 0, "延迟": 0}
        ),
        names,
    )
    edited = st_obj.data_editor(
        basic,
        key="sarimax_rdl_input_table",
        num_rows="fixed",
        disabled=("变量",),
        width="stretch",
    )
    state.set("rdl_input_table", edited.copy())
    with st_obj.expander("高级：稀疏滞后与初始化策略", expanded=False):
        st_obj.caption("留空即采用上表连续阶数；分母稀疏滞后从 1 开始。")
        advanced = st_obj.data_editor(
            _restore_table_state(
                "rdl_advanced_table",
                pd.DataFrame(
                    {
                        "变量": names,
                        "分子稀疏滞后": "",
                        "分母稀疏滞后": "",
                        "初始化": "auto",
                    }
                ),
                names,
            ),
            key="sarimax_rdl_advanced_table",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state.set("rdl_advanced_table", advanced.copy())
    try:
        return tuple(
            RDLInputConfig(
                name=str(name),
                numerator_order=int(edited.iloc[index]["分子阶数"]),
                denominator_order=int(edited.iloc[index]["分母阶数"]),
                delay=int(edited.iloc[index]["延迟"]),
                numerator_lags=_parse_sparse_lags(
                    advanced.iloc[index]["分子稀疏滞后"], minimum=0
                ),
                denominator_lags=_parse_sparse_lags(
                    advanced.iloc[index]["分母稀疏滞后"], minimum=1
                ),
                initialization=str(advanced.iloc[index]["初始化"]),
            )
            for index, name in enumerate(names)
        )
    except (TypeError, ValueError) as exc:
        st_obj.error(f"RDL 输入动态设置有误：{exc}")
        return None


def _render_rdl_config(
    st_obj, exog: pd.DataFrame | None, *, automatic: bool, log: bool
):
    """渲染 RDL 的误差结构、输入动态与估计设置区块。"""
    if exog is None or exog.empty:
        st_obj.warning("RDL 需要至少一个解释变量；请在上方变量选择中添加。")
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**响应 / 误差结构**")
        error = (
            _render_auto_config(st_obj, "sarimax_rdl_auto_error", log=log)
            if automatic
            else _render_manual_config(st_obj, "sarimax_rdl_error", log=log)
        )
    if error is None:
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**输入动态**")
        inputs = _render_rdl_inputs(st_obj, exog)
    if inputs is None:
        return None
    with st_obj.container(border=True):
        st_obj.markdown("**估计设置**")
        stable = st_obj.checkbox(
            "强制传递函数分母稳定",
            value=True,
            key="sarimax_rdl_enforce_stability",
        )
        st_obj.caption("自动 RDL 只搜索 SARIMAX 误差阶数，以上传递函数结构保持固定。")
    try:
        config_type = AutoRDLConfig if automatic else RDLConfig
        kwargs = {
            "inputs": inputs,
            "error": error,
            "enforce_distributed_lag_stability": stable,
        }
        return config_type(**kwargs)
    except (TypeError, ValueError) as exc:
        st_obj.error(f"RDL 设置有误：{exc}")
        return None


def _render_ardl_config(
    st_obj, exog: pd.DataFrame | None, *, automatic: bool, log: bool
):
    """渲染标准 ARDL 的目标/输入滞后与自动选阶设置。"""
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
        trend = _render_trend_selector(response_columns[1], prefix)
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
            _restore_table_state(
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
            "协方差估计", ("nonrobust", "HC0", "HC1", "HC2", "HC3"),
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
            "hold_back": None if int(hold_back_value) == 0 else int(hold_back_value),
            "log": bool(log),
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


__all__ = ["render_model_options"]
