"""SARIMAX 工作流 - ② 模型训练环节（手动配置与自动选阶）。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from Ts.TsModels import AutoModelResult

from dashboard.models.SARIMAX.core.data_loader import (
    numeric_variable_names,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.model_config import (
    AUTO_CRITERIA,
    AutoSARIMAXConfig,
    SARIMAXConfig,
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    TREND_LABELS,
    TREND_OPTIONS,
)
from dashboard.models.SARIMAX.core.modeling import (
    fit_auto_sarimax,
    fit_sarimax,
    translate_ts_error,
    validate_fit_inputs,
)
from dashboard.models.SARIMAX.ui.state import (
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


def render_training_section(st_obj) -> None:
    """配置并拟合 SARIMAX 模型。"""
    st_obj.markdown("#### ② 模型训练")
    dataset = state.get("dataset")
    if dataset is None:
        st_obj.info("完成「① 数据概览」（在上方上传数据）后可配置并拟合模型。")
        return

    variables = numeric_variable_names(dataset.frame)
    if not variables:
        st_obj.error("数据中没有可用的数值型变量。")
        return

    st_obj.markdown("**变量选择**")
    select_columns = st_obj.columns(2)
    with select_columns[0]:
        target = st_obj.selectbox(
            "目标变量（因变量，将被建模的序列）",
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
            "外生变量（可选，作为回归输入参与建模）",
            options=exog_options,
            key="sarimax_exog_select",
            help="外生变量的观测日期必须与目标变量完全对齐。",
        )
    if tuple(exog) != state.get("exog_variables", ()):
        state.set("exog_variables", tuple(exog))
        clear_fit_results()

    st_obj.caption(
        f"当前配置：目标变量「{target}」，外生变量 "
        + (f"「{'、'.join(exog)}」" if exog else "无")
    )

    try:
        series, exog, index = prepare_modeling_inputs(
            dataset,
            target,
            tuple(exog),
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
        st_obj.error(f"数据准备失败：{exc}")
        return

    scope_text = (
        f"建模对象：目标「{target}」 · 有效观测 {len(series.dropna()):,} 行"
    )
    if isinstance(index, pd.DatetimeIndex):
        scope_text += f" · 时间范围 {index.min():%Y-%m-%d} ~ {index.max():%Y-%m-%d}"
    else:
        scope_text += " · 未识别时间索引（按观测顺序建模）"
    st_obj.caption(scope_text)

    mode = st_obj.radio(
        "模型配置方式",
        options=("手动配置", "自动选阶（AutoSARIMAX）"),
        horizontal=True,
        key="sarimax_mode_radio",
        help=(
            "手动配置：自行指定 (p,d,q)×(P,D,Q,s) 阶数；"
            "自动选阶：在指定范围内按信息准则搜索最优阶数。"
        ),
    )
    if mode == "手动配置":
        config = _render_manual_config(st_obj)
    else:
        config = _render_auto_config(st_obj)
        if config is None:
            return

    problems = validate_fit_inputs(
        series,
        exog,
        config,
    )
    for problem in problems:
        st_obj.warning(problem)

    signature = (
        state.get("file_fingerprint"),
        target,
        tuple(state.get("exog_variables", ())),
        config.signature(),
    )
    if st_obj.button(
        "拟合模型",
        type="primary",
        disabled=bool(problems),
        key="sarimax_fit_button",
    ):
        with st_obj.spinner("正在调用 Ts 包拟合模型..."):
            try:
                if isinstance(config, AutoSARIMAXConfig):
                    result = fit_auto_sarimax(series, exog, config)
                else:
                    result = fit_sarimax(series, exog, config)
            except Exception as exc:  # noqa: BLE001 - 统计拟合失败边界
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


def _render_manual_config(st_obj) -> SARIMAXConfig:
    """渲染手动 SARIMAX 阶数与高级设置。"""
    st_obj.markdown("**非季节阶数 (p, d, q)**")
    order_columns = st_obj.columns(3)
    p = order_columns[0].number_input("p（AR 阶数）", 0, 6, 1, key="sarimax_p")
    d = order_columns[1].number_input("d（差分阶数）", 0, 2, 0, key="sarimax_d")
    q = order_columns[2].number_input("q（MA 阶数）", 0, 6, 1, key="sarimax_q")

    st_obj.markdown("**季节阶数 (P, D, Q, s)**")
    seasonal_columns = st_obj.columns(4)
    P = seasonal_columns[0].number_input("P（季节 AR）", 0, 3, 0, key="sarimax_P")
    D = seasonal_columns[1].number_input("D（季节差分）", 0, 2, 0, key="sarimax_D")
    Q = seasonal_columns[2].number_input("Q（季节 MA）", 0, 3, 0, key="sarimax_Q")
    s = seasonal_columns[3].number_input(
        "s（季节周期）",
        0,
        12,
        0,
        key="sarimax_s",
        help="季节周期长度；0 表示无季节项（如月度数据可填 12）。",
    )

    common_columns = st_obj.columns(2)
    trend = common_columns[0].selectbox(
        "趋势项",
        options=list(TREND_OPTIONS),
        index=list(TREND_OPTIONS).index("c"),
        format_func=lambda value: TREND_LABELS[value],
        key="sarimax_trend",
    )
    log = common_columns[1].checkbox(
        "对响应取自然对数（log 变换）",
        key="sarimax_log",
        help="要求数据严格为正；预测结果将回到原始刻度。",
    )

    with st_obj.expander("高级设置（优化器与协方差）"):
        advanced_columns = st_obj.columns(3)
        method = advanced_columns[0].selectbox(
            "优化器",
            options=list(SARIMAX_OPTIMIZERS),
            index=list(SARIMAX_OPTIMIZERS).index("bfgs"),
            key="sarimax_method",
        )
        maxiter = advanced_columns[1].number_input(
            "最大迭代次数",
            10,
            10000,
            500,
            step=50,
            key="sarimax_maxiter",
        )
        cov_type = advanced_columns[2].selectbox(
            "协方差估计",
            options=list(SARIMAX_COV_TYPES),
            index=list(SARIMAX_COV_TYPES).index("oim"),
            key="sarimax_cov_type",
        )
        enforce_columns = st_obj.columns(2)
        enforce_stationarity = enforce_columns[0].checkbox(
            "强制 AR 多项式平稳",
            value=True,
            key="sarimax_enforce_stationarity",
        )
        enforce_invertibility = enforce_columns[1].checkbox(
            "强制 MA 多项式可逆",
            value=True,
            key="sarimax_enforce_invertibility",
        )

    return SARIMAXConfig(
        order=(int(p), int(d), int(q)),
        seasonal_order=(int(P), int(D), int(Q), int(s)),
        trend=trend,
        log=log,
        enforce_stationarity=enforce_stationarity,
        enforce_invertibility=enforce_invertibility,
        fit_method=method,
        maxiter=int(maxiter),
        cov_type=cov_type,
    )


def _render_auto_config(st_obj) -> AutoSARIMAXConfig | None:
    """渲染 AutoSARIMAX 搜索范围；范围非法时提示并返回 None。"""
    st_obj.markdown("**搜索范围**")
    range_columns = st_obj.columns(3)
    ranges: dict[str, tuple[int, int]] = {}
    for column, name in zip(range_columns, ("p", "d", "q")):
        ranges[name] = _render_range_inputs(
            column,
            name,
            _AUTO_RANGE_DEFAULTS[name],
        )
    seasonal_columns = st_obj.columns(3)
    for column, name in zip(seasonal_columns, ("P", "D", "Q")):
        ranges[name] = _render_range_inputs(
            column,
            name,
            _AUTO_RANGE_DEFAULTS[name],
        )

    options_columns = st_obj.columns(3)
    s = options_columns[0].number_input(
        "s（季节周期）",
        0,
        12,
        0,
        key="sarimax_auto_s",
        help="0 表示不搜索季节项。",
    )
    trend = options_columns[1].selectbox(
        "趋势项",
        options=list(TREND_OPTIONS),
        index=list(TREND_OPTIONS).index("c"),
        format_func=lambda value: TREND_LABELS[value],
        key="sarimax_auto_trend",
    )
    criterion = options_columns[2].selectbox(
        "选阶准则",
        options=list(AUTO_CRITERIA),
        index=list(AUTO_CRITERIA).index("aic"),
        key="sarimax_auto_criterion",
    )
    log = st_obj.checkbox(
        "对响应取自然对数（log 变换）",
        key="sarimax_auto_log",
        help="要求数据严格为正。",
    )

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
            criterion=criterion,
            log=log,
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


def _render_range_inputs(
    container,
    name: str,
    default: tuple[int, int],
) -> tuple[int, int]:
    """渲染单个阶数的 (最小值, 最大值) 两个输入框。"""
    container.markdown(f"**{name}**")
    low = container.number_input(
        "最小值",
        0,
        6,
        int(default[0]),
        key=f"sarimax_auto_{name}_min",
    )
    high = container.number_input(
        "最大值",
        0,
        6,
        int(default[1]),
        key=f"sarimax_auto_{name}_max",
    )
    return (int(low), int(high))


def _render_fit_summary(st_obj, result) -> None:
    """展示拟合摘要与关键指标。"""
    best = result.best_result if isinstance(result, AutoModelResult) else result

    if isinstance(result, AutoModelResult):
        st_obj.markdown("**自动选阶结果**")
        st_obj.markdown(
            f"最优模型：SARIMAX{result.best_order}"
            + (
                f" × {result.best_seasonal_order}"
                if result.best_seasonal_order
                else ""
            )
            + f"（准则：{result.selection_criterion.upper()}）"
        )
        candidate_rows = []
        for index, order in enumerate(result.candidate_orders):
            seasonal = (
                result.candidate_seasonal_orders[index]
                if index < len(result.candidate_seasonal_orders)
                else None
            )
            label = f"SARIMAX{order}" + (f" × {seasonal}" if seasonal else "")
            candidate_rows.append(
                {
                    "模型": label,
                    f"{result.selection_criterion.upper()}": round(
                        float(result.criterion_values[index]),
                        6,
                    ),
                }
            )
        st_obj.dataframe(pd.DataFrame(candidate_rows), width="stretch")

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
