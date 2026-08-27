"""SARIMAX 工作流 - ② 模型训练环节（手动配置与自动选阶）。"""

from __future__ import annotations

import logging

import pandas as pd
from Ts.TsModels import AutoARDLResult, AutoModelResult

from dashboard.models.SARIMAX.core.data_loader import (
    numeric_variable_names,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.model_config import (
    ARDL_CRITERIA,
    ARDL_SEARCH_METHODS,
    AUTO_CRITERIA,
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
from dashboard.core.workspace import artifact_signature
from dashboard.models.SARIMAX.core.modeling import (
    build_auto_sarimax_criterion_table,
    fit_dynamic_model,
    select_auto_sarimax_result,
    translate_ts_error,
    validate_fit_inputs,
)
from dashboard.models.SARIMAX.ui.state import (
    clear_downstream_results,
    clear_fit_results,
    clear_widget_state,
    state,
)

logger = logging.getLogger(__name__)

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
_TREND_COMPONENTS = ("常数项", "线性趋势")


def _render_trend_selector(st_obj, prefix: str) -> str:
    """渲染常数项/线性趋势多选并映射为 Ts 的趋势代码。"""
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


def render_training_section(st_obj) -> None:
    """配置并拟合 SARIMAX、RDL 或标准 ARDL 模型。"""
    st_obj.markdown("#### ② 模型训练")
    dataset = state.get("dataset")
    if dataset is None:
        st_obj.info("完成「① 数据预览」（在上方上传数据）后可配置并拟合模型。")
        return

    variables = numeric_variable_names(dataset.frame)
    if not variables:
        st_obj.error("数据中没有可用的数值型变量。")
        return

    control_columns = st_obj.columns([1, 1, 2])
    with control_columns[0]:
        family = st_obj.segmented_control(
            "模型族",
            options=("SARIMAX", "RDL", "ARDL"),
            default="SARIMAX",
            key="sarimax_model_family",
            help="SARIMAX 使用静态外生变量；RDL 使用传递函数；ARDL 显式估计目标和输入滞后。",
        )
    with control_columns[1]:
        mode = st_obj.segmented_control(
            "配置方式",
            options=("手动配置", "自动选阶"),
            default="手动配置",
            key="sarimax_config_mode",
        )
    family = family or "SARIMAX"
    mode = mode or "手动配置"
    if (family, mode) != state.get("model_selection"):
        state.set("model_selection", (family, mode))
        clear_fit_results()

    select_columns = st_obj.columns(4)
    with select_columns[0]:
        target = st_obj.selectbox(
            "目标变量",
            options=variables,
            index=variables.index(state.get("target_variable"))
            if state.get("target_variable") in variables
            else 0,
            key="sarimax_target_select",
        )
    if target != state.get("target_variable"):
        state.set("target_variable", target)
        state.set("exog_variables", ())
        clear_fit_results()
        clear_widget_state(st_obj, ("sarimax_exog_select",))

    with select_columns[1]:
        exog_options = [name for name in variables if name != target]
        exog = st_obj.multiselect(
            "外生变量",
            options=exog_options,
            key="sarimax_exog_select",
            help="外生变量的观测日期必须与目标变量完全对齐。",
        )
    if tuple(exog) != state.get("exog_variables", ()):
        state.set("exog_variables", tuple(exog))
        clear_fit_results()

    time_range = None
    if dataset.time_column is not None:
        time_values = pd.to_datetime(dataset.frame[dataset.time_column])
        date_min = time_values.min().date()
        date_max = time_values.max().date()
        with select_columns[2]:
            selected_range = st_obj.date_input(
                "训练时间范围",
                value=(date_min, date_max),
                min_value=date_min,
                max_value=date_max,
                key="sarimax_training_time_range",
                help="仅使用该闭区间内的观测值拟合模型。",
            )
        if not isinstance(selected_range, (tuple, list)) or len(selected_range) != 2:
            st_obj.warning("请选择完整的训练起始日期和结束日期。")
            return
        time_range = tuple(pd.Timestamp(value) for value in selected_range)
        if time_range != state.get("training_time_range"):
            state.set("training_time_range", time_range)
            clear_fit_results()

    sarimax_family = family == "SARIMAX"
    if sarimax_family:
        response_log = bool(
            st_obj.session_state.get("sarimax_response_log", False)
        )
    else:
        with select_columns[3]:
            response_log = st_obj.checkbox(
                "目标变量取对数",
                key="sarimax_response_log",
                help="勾选时要求目标变量严格为正，预测结果将回到原始刻度。",
            )

    try:
        series, exog, _ = prepare_modeling_inputs(
            dataset,
            target,
            tuple(exog),
            time_range=time_range,
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
        st_obj.error(f"数据准备失败：{exc}")
        return

    if family == "SARIMAX":
        config = (
            _render_manual_config(st_obj, log=None)
            if mode == "手动配置"
            else _render_auto_config(st_obj, log=None)
        )
    elif family == "RDL":
        config = _render_rdl_config(
            st_obj, exog, automatic=mode == "自动选阶", log=response_log
        )
    else:
        config = _render_ardl_config(
            st_obj, exog, automatic=mode == "自动选阶", log=response_log
        )
    if sarimax_family:
        response_log = bool(
            st_obj.session_state.get("sarimax_response_log", False)
        )
    if response_log != state.get("response_log"):
        state.set("response_log", response_log)
        clear_fit_results()
    if config is None:
        return

    problems = validate_fit_inputs(
        series,
        exog,
        config,
    )
    for problem in problems:
        st_obj.warning(problem)

    signature = artifact_signature(
        data_fingerprint=str(state.get("file_fingerprint") or ""),
        parameters={
            "family": family,
            "mode": mode,
            "target": target,
            "exog_variables": tuple(state.get("exog_variables", ())),
            "time_range": (
                tuple(value.isoformat() for value in time_range)
                if time_range is not None
                else None
            ),
            "response_log": response_log,
            "config": config.signature(),
        },
        version="sarimax-fit-v1",
    )
    if st_obj.button(
        "拟合模型",
        type="primary",
        disabled=bool(problems),
        key="sarimax_fit_button",
    ):
        with st_obj.spinner("正在调用 Ts 包拟合模型..."):
            try:
                result = fit_dynamic_model(series, exog, config)
            except Exception as exc:
                st_obj.error(translate_ts_error(exc))
                logger.exception("SARIMAX 模型拟合失败")
                clear_fit_results()
                return
        state.set("fitted_result", result)
        state.set("fit_signature", signature)
        state.set("diagnostics_table", None)
        state.set("diagnostics_signature", None)
        state.set("forecast", None)
        state.set("forecast_signature", None)

    result = state.get("fitted_result")
    if result is None or state.get("fit_signature") != signature:
        return
    _render_fit_summary(st_obj, result)


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
        12,
        0,
        key=f"{prefix}_s",
        help="季节周期长度；0 表示无季节项（如月度数据可填 12）。",
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
                session_state=st_obj.session_state,
            )
        seasonal_columns = st_obj.columns(3)
        for column, name in zip(seasonal_columns, ("P", "D", "Q")):
            ranges[name] = _render_range_inputs(
                column,
                name,
                _AUTO_RANGE_DEFAULTS[name],
                prefix,
                SARIMAX_RANGE_LIMITS[name],
                session_state=st_obj.session_state,
            )

    with layout_columns[1]:
        trend = _render_trend_selector(st_obj, prefix)
        s = st_obj.number_input(
            "s（季节周期）", 0, 12, 0,
            key=f"{prefix}_s",
            help="0 表示不搜索季节项。",
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
    st_obj.caption(f"网格搜索将尝试 {count} 个模型组合。")
    if count > _AUTO_MAX:
        st_obj.warning(
            f"组合数超过 {_AUTO_MAX}，拟合耗时可能很长，建议缩小搜索范围。"
        )
    return config


def _render_sarimax_advanced_settings(
    st_obj, prefix: str, *, log: bool | None
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

        constraint_columns = st_obj.columns(3)
        response_log = (
            constraint_columns[0].checkbox(
                "目标变量取对数",
                key="sarimax_response_log",
                help="勾选时要求目标变量严格为正，预测结果将回到原始刻度。",
            )
            if log is None
            else bool(log)
        )
        enforce_stationarity = constraint_columns[1].checkbox(
            "强制 AR 多项式平稳",
            value=False,
            key=f"{prefix}_enforce_stationarity",
        )
        enforce_invertibility = constraint_columns[2].checkbox(
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
    *,
    session_state,
) -> tuple[int, int]:
    """渲染单个阶数的双端整数滑块。"""
    minimum, maximum = limits
    old_low = session_state.get(f"{prefix}_{name}_min", default[0])
    old_high = session_state.get(f"{prefix}_{name}_max", default[1])
    try:
        value = (int(old_low), int(old_high))
    except (TypeError, ValueError):
        value = default
    value = (
        max(minimum, min(maximum, value[0])),
        max(minimum, min(maximum, value[1])),
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


def _render_rdl_inputs(st_obj, exog: pd.DataFrame) -> tuple[RDLInputConfig, ...] | None:
    """渲染固定行的 RDL 传递函数参数表与可选稀疏滞后设置。"""
    names = list(exog.columns)
    basic = pd.DataFrame(
        {
            "变量": names,
            "分子阶数": 0,
            "分母阶数": 0,
            "延迟": 0,
        }
    )
    basic = _restore_table_state("rdl_input_table", basic, names)
    edited = st_obj.data_editor(
        basic,
        key="sarimax_rdl_input_table",
        num_rows="fixed",
        disabled=("变量",),
        width="stretch",
    )
    state.set("rdl_input_table", edited.copy())
    advanced = None
    with st_obj.expander("高级：稀疏滞后与初始化策略", expanded=False):
        st_obj.caption("留空即采用上表连续阶数；分母稀疏滞后从 1 开始。")
        advanced_defaults = _restore_table_state(
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
        )
        advanced = st_obj.data_editor(
            advanced_defaults,
            key="sarimax_rdl_advanced_table",
            num_rows="fixed",
            disabled=("变量",),
            width="stretch",
        )
        state.set("rdl_advanced_table", advanced.copy())
    try:
        inputs = []
        for index, name in enumerate(names):
            advanced_row = advanced.iloc[index]
            inputs.append(
                RDLInputConfig(
                    name=str(name),
                    numerator_order=int(edited.iloc[index]["分子阶数"]),
                    denominator_order=int(edited.iloc[index]["分母阶数"]),
                    delay=int(edited.iloc[index]["延迟"]),
                    numerator_lags=_parse_sparse_lags(
                        advanced_row["分子稀疏滞后"], minimum=0
                    ),
                    denominator_lags=_parse_sparse_lags(
                        advanced_row["分母稀疏滞后"], minimum=1
                    ),
                    initialization=str(advanced_row["初始化"]),
                )
            )
        return tuple(inputs)
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
        if automatic:
            return AutoRDLConfig(
                inputs=inputs,
                error=error,
                enforce_distributed_lag_stability=stable,
            )
        return RDLConfig(
            inputs=inputs,
            error=error,
            enforce_distributed_lag_stability=stable,
        )
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
            0, 12, 3 if automatic else 1,
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
                "搜索方式", ARDL_SEARCH_METHODS, key=f"{prefix}_search_method",
                format_func=lambda value: "分层搜索" if value == "hierarchical" else "全局搜索",
            )
            if search_method == "global":
                st_obj.warning("全局搜索会枚举滞后子集，变量较多或上限较高时计算量会迅速增加。")
    try:
        pairs = tuple(
            (str(row["变量"]), int(row[label]))
            for _, row in orders.iterrows()
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
                maxlag=int(target_lag), max_input_orders=pairs,
                criterion=criterion, search_method=search_method, **common,
            )
        return ARDLConfig(lags=int(target_lag), input_orders=pairs, **common)
    except (TypeError, ValueError) as exc:
        st_obj.error(f"ARDL 设置有误：{exc}")
        return None


def _restore_table_state(
    state_key: str,
    defaults: pd.DataFrame,
    variable_names: list[str],
) -> pd.DataFrame:
    """仅在变量结构仍兼容时，以模块影子状态恢复 data_editor 内容。"""
    saved = state.get(state_key)
    if not isinstance(saved, pd.DataFrame):
        return defaults
    if list(saved.columns) != list(defaults.columns):
        return defaults
    if saved["变量"].tolist() != variable_names:
        return defaults
    return saved.copy()


def _render_fit_summary(st_obj, result) -> None:
    """展示拟合摘要与关键指标。"""
    if isinstance(result, AutoModelResult):
        st_obj.markdown("**自动选阶结果**")
        table = build_auto_sarimax_criterion_table(result)
        st_obj.dataframe(table, width="stretch")
        current_criterion = (
            result.selection_criterion
            if result.selection_criterion in AUTO_CRITERIA
            else _AUTO_SELECTION_DEFAULT
        )
        if "sarimax_auto_selection_criterion" not in st_obj.session_state:
            st_obj.session_state["sarimax_auto_selection_criterion"] = (
                current_criterion
            )
        selected_criterion = st_obj.selectbox(
            "最终采用的最小准则",
            options=list(AUTO_CRITERIA),
            index=list(AUTO_CRITERIA).index(current_criterion),
            format_func=str.upper,
            key="sarimax_auto_selection_criterion",
            help="从上方结果表中选择一个信息准则，采用该列最小值对应的模型。",
        )
        if selected_criterion != current_criterion:
            result = select_auto_sarimax_result(result, selected_criterion)
            state.set("fitted_result", result)
            clear_downstream_results()
        st_obj.markdown(
            f"最终采用模型：SARIMAX{result.best_order}"
            + (
                f" × {result.best_seasonal_order}"
                if result.best_seasonal_order
                else ""
            )
            + f"（{result.selection_criterion.upper()} 最小）"
        )
    elif isinstance(result, AutoARDLResult):
        st_obj.markdown("**自动选阶结果**")
        st_obj.markdown(
            f"最优 ARDL：目标滞后 {result.ar_lags}；"
            f"输入滞后 {result.distributed_lags}"
            f"（准则：{result.selection_criterion.upper()}，"
            f"{('全局' if result.search_method == 'global' else '分层')}搜索）"
        )
        table = result.criterion_table.copy()
        table = table.rename(
            columns={"criterion": result.selection_criterion.upper(), "target_lags": "目标滞后", "input_lags": "输入滞后"}
        )
        st_obj.dataframe(table, width="stretch")

    best = (
        result.best_result
        if isinstance(result, (AutoModelResult, AutoARDLResult))
        else result
    )

    status = "已收敛" if best.converged else "未收敛"
    st_obj.success(
        f"模型优化状态：{status} · 有效样本量 {best.effective_nobs}"
        f" · 优化器 {best.optimizer or '未知'}"
    )

    metric_columns = st_obj.columns(3)
    metric_columns[0].metric("AIC", f"{result.aic:.4f}")
    metric_columns[1].metric("BIC", f"{result.bic:.4f}")
    metric_columns[2].metric("对数似然", f"{result.log_likelihood:.4f}")

    with st_obj.expander("参数摘要", expanded=False):
        st_obj.code(result.summary())


__all__ = ["render_training_section"]
