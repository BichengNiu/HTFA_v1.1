"""SARIMAX 工作流 - ① 模型训练环节（手动配置与自动选阶）。"""

from __future__ import annotations

import logging

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import artifact_signature, stable_signature
from dashboard.models.common.ui.model_inputs import ModelInputModule
from dashboard.models.common.ui.result_view import render_estimation_result
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.core.adapters import (
    DynamicRegressionAdapter,
    best_result,
    is_automatic_config,
)
from dashboard.models.SARIMAX.core.data_loader import (
    PREPROCESSING_OPTIONS,
    dataset_time_index,
    effective_modeling_date_bounds,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.modeling import (
    translate_ts_error,
    validate_fit_inputs,
)
from dashboard.models.SARIMAX.core.simulation import (
    build_sarimax_acf_comparison_table,
    build_sarimax_simulation_comparison,
    build_sarimax_simulation_summary,
    plot_sarimax_simulation_comparison,
)
from dashboard.models.SARIMAX.ui.model_options import render_model_options
from dashboard.models.SARIMAX.ui.state import (
    clear_downstream_results,
    clear_fit_results,
    clear_widget_state,
    state,
)

logger = logging.getLogger(__name__)
_MODEL_ADAPTER = DynamicRegressionAdapter()
_MODEL_WORKFLOW = ModelWorkflow(_MODEL_ADAPTER)
_SIMULATION_SEED = 42
_SIMULATION_PATHS_DEFAULT = 500
_SIMULATION_PATHS_MIN = 50
_SIMULATION_PATHS_MAX = 2000
_SIMULATION_CONFIDENCE_LEVEL = 0.95
_SIMULATION_ACF_LAGS = 10
_MODEL_INPUTS = ModelInputModule(
    state=state,
    clear_fit_results=clear_fit_results,
    clear_widget_state=clear_widget_state,
    prepare_inputs=prepare_modeling_inputs,
    effective_date_bounds=effective_modeling_date_bounds,
    dataset_time_index=dataset_time_index,
    preprocessing_options=PREPROCESSING_OPTIONS,
    key_prefix="sarimax",
)


def render_training_section(st_obj) -> None:
    """配置并拟合 SARIMAX、RDL 或标准 ARDL 模型。"""
    dataset = state.get("dataset")
    if dataset is None:
        st_obj.info(
            "请先在上方上传并读取 SARIMAX 的数据文件，再配置并拟合模型。"
        )
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

    inputs = _MODEL_INPUTS.render(
        st_obj,
        dataset,
        dataset_fingerprint=str(state.get("file_fingerprint") or ""),
    )
    if inputs is None:
        return

    config = render_model_options(
        st_obj,
        family,
        mode,
        inputs.exog,
        response_log=inputs.response_log,
    )
    if config is None:
        return

    problems = validate_fit_inputs(
        inputs.series,
        inputs.exog,
        config,
    )
    for problem in problems:
        st_obj.warning(problem)

    signature = artifact_signature(
        data_fingerprint=str(state.get("file_fingerprint") or ""),
        parameters={
            "family": family,
            "mode": mode,
            "target": inputs.target,
            "exog_variables": inputs.exog_names,
            "time_range": (
                tuple(value.isoformat() for value in inputs.training_range)
                if inputs.training_range is not None
                else None
            ),
            "preprocessing": inputs.preprocessing,
            "response_log": inputs.response_log,
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
        st_obj.session_state.pop("sarimax_auto_selection_model", None)
        is_automatic = is_automatic_config(config)
        progress_bar = (
            st_obj.progress(0.0, text="正在准备候选模型评估...")
            if is_automatic
            else None
        )
        progress_state = {"completed": 0, "total": 0}

        def update_progress(completed: int, total: int) -> None:
            """在主进程中更新自动选阶进度，不进入候选 worker。"""
            progress_state["completed"] = completed
            progress_state["total"] = total
            if progress_bar is not None:
                progress_bar.progress(
                    completed / max(total, 1),
                    text=f"正在评估候选模型：{completed}/{total}",
                )

        with st_obj.spinner("正在调用 Ts 包拟合模型..."):
            try:
                result = _MODEL_WORKFLOW.fit(
                    inputs,
                    config,
                    progress_callback=update_progress if is_automatic else None,
                )
                if progress_bar is not None:
                    progress_bar.progress(
                        1.0,
                        text=(
                            "候选模型评估完成，正在整理最优模型结果。"
                        ),
                    )
            except Exception as exc:
                if progress_bar is not None and progress_state["total"]:
                    progress_bar.progress(
                        progress_state["completed"] / progress_state["total"],
                        text=(
                            "候选模型评估中断："
                            f"{progress_state['completed']}/{progress_state['total']}"
                        ),
                    )
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
        state.set("simulation_comparison", None)
        state.set("simulation_signature", None)

    result = state.get("fitted_result")
    if result is None or state.get("fit_signature") != signature:
        return
    _render_fit_summary(st_obj, result, model_family=family)


def _render_fit_summary(st_obj, result, *, model_family: str) -> None:
    """通过通用结果视图展示拟合摘要与关键指标。"""
    view = _MODEL_WORKFLOW.result_view(result)
    selected = render_estimation_result(
        st_obj,
        view,
        selection_key="sarimax_auto_selection_criterion",
        candidate_selection_key="sarimax_auto_selection_model",
    )
    if selected is not None:
        try:
            result = _MODEL_ADAPTER.select_result(result, selected)
        except Exception as exc:  # noqa: BLE001 - 用户可读的选阶边界
            st_obj.error(f"重新选择模型失败：{translate_ts_error(exc)}")
            return
        state.set("fitted_result", result)
        clear_downstream_results()
        render_estimation_result(
            st_obj,
            _MODEL_WORKFLOW.result_view(result),
            selection_key="sarimax_auto_selection_criterion",
            candidate_selection_key="sarimax_auto_selection_model",
            show_selection=False,
        )
        if model_family == "SARIMAX":
            _render_sarimax_simulation_chart(st_obj, result)
        return
    if model_family == "SARIMAX":
        _render_sarimax_simulation_chart(st_obj, result)


def _render_sarimax_simulation_chart(st_obj, result) -> None:
    """展示实际序列与多条 TsSims 模拟路径的分布比较。"""
    best = best_result(result)
    st_obj.markdown("**实际序列与模拟路径分布**")
    n_paths = int(
        st_obj.number_input(
            "模拟路径数",
            min_value=_SIMULATION_PATHS_MIN,
            max_value=_SIMULATION_PATHS_MAX,
            value=_SIMULATION_PATHS_DEFAULT,
            step=50,
            key="sarimax_simulation_paths",
            help=(
                "每条路径均由估计的 SARIMAX 参数独立生成；增加路径数会使模拟区间"
                "更稳定，但会增加计算时间。"
            ),
        )
    )
    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "order": getattr(best, "order", None),
            "seasonal_order": getattr(best, "seasonal_order", None),
            "n_paths": n_paths,
            "seed": _SIMULATION_SEED,
            "confidence_level": _SIMULATION_CONFIDENCE_LEVEL,
            "acf_lags": _SIMULATION_ACF_LAGS,
        }
    )
    comparison = state.get("simulation_comparison")
    if comparison is None or state.get("simulation_signature") != signature:
        try:
            with st_obj.spinner(
                f"正在调用 TsSims 生成 {n_paths} 条模拟路径..."
            ):
                comparison = build_sarimax_simulation_comparison(
                    best,
                    n_paths=n_paths,
                    seed=_SIMULATION_SEED,
                    confidence_level=_SIMULATION_CONFIDENCE_LEVEL,
                    acf_lags=_SIMULATION_ACF_LAGS,
                )
        except Exception as exc:
            st_obj.warning(f"模拟路径比较无法绘制：{translate_ts_error(exc)}")
            logger.warning("SARIMAX 模拟路径比较生成失败", exc_info=True)
            state.set("simulation_comparison", None)
            state.set("simulation_signature", None)
            return
        state.set("simulation_comparison", comparison)
        state.set("simulation_signature", signature)

    try:
        with matplotlib_date_compatibility():
            figure, _ = plot_sarimax_simulation_comparison(comparison)
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:
        st_obj.warning(f"模拟路径比较无法绘制：{translate_ts_error(exc)}")
        logger.warning("SARIMAX 模拟路径比较绘制失败", exc_info=True)
        return

    st_obj.caption(
        f"{comparison.n_paths} 条独立模拟路径（seed={comparison.seed}）；"
        f"阴影为模拟{comparison.confidence_level:.0%}区间；"
        f"实际序列逐时覆盖率={comparison.pointwise_coverage:.1%}；"
        f"ACF（滞后1–{comparison.acf_lags}）覆盖率={comparison.acf_coverage:.1%}。"
    )
    st_obj.markdown("**统计量比较**")
    st_obj.dataframe(
        build_sarimax_simulation_summary(comparison),
        hide_index=True,
        use_container_width=True,
    )
    st_obj.markdown("**ACF 比较明细**")
    st_obj.dataframe(
        build_sarimax_acf_comparison_table(comparison),
        hide_index=True,
        use_container_width=True,
    )


__all__ = ["render_training_section"]
