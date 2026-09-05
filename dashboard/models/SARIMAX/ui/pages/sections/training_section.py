"""动态回归工作流的模型训练环节。"""

from __future__ import annotations

import logging

from htfa.workspace import artifact_signature
from dashboard.models.common.model_library import ModelContext
from dashboard.models.common.ui.model_inputs import ModelInputModule
from dashboard.models.common.ui.result_view import render_estimation_result
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.core.adapters import DynamicRegressionAdapter, is_automatic_config
from dashboard.models.SARIMAX.core.data_loader import (
    PREPROCESSING_OPTIONS, dataset_time_index, effective_modeling_date_bounds,
    prepare_modeling_inputs,
)
from dashboard.models.SARIMAX.core.modeling import (
    fit_input_warnings,
    translate_ts_error,
    validate_fit_inputs,
)
from dashboard.models.SARIMAX.ui.model_options import render_model_options
from dashboard.models.SARIMAX.ui.state import ModelPageScope, SARIMAX_SCOPE


logger = logging.getLogger(__name__)
_MODEL_WORKFLOW = ModelWorkflow(DynamicRegressionAdapter())
_MODEL_INPUTS: dict[str, ModelInputModule] = {}


def _model_inputs(scope: ModelPageScope) -> ModelInputModule:
    """按页面范围缓存变量、日期和预处理控件。"""
    module = _MODEL_INPUTS.get(scope.namespace)
    if module is None:
        module = ModelInputModule(
            state=scope.state,
            clear_fit_results=scope.clear_fit_results,
            clear_widget_state=scope.clear_widget_state,
            prepare_inputs=prepare_modeling_inputs,
            effective_date_bounds=effective_modeling_date_bounds,
            dataset_time_index=dataset_time_index,
            preprocessing_options=PREPROCESSING_OPTIONS,
            key_prefix=scope.key_prefix,
            show_exog_log=scope.family == "SARIMAX",
            show_intervention=scope.family == "RDL",
            show_preprocessing=False,
        )
        _MODEL_INPUTS[scope.namespace] = module
    return module


def render_training_section(
    st_obj,
    scope: ModelPageScope = SARIMAX_SCOPE,
) -> ModelContext | None:
    """配置并拟合一个独立 Tab 固定的模型族，返回当前结果上下文。"""
    state = scope.state
    dataset = state.get("dataset")
    if dataset is None:
        st_obj.info(f"请先在上方上传并读取 {scope.family} 的数据文件，再配置并拟合模型。")
        return

    if scope.family == "SARIMAX":
        mode = st_obj.segmented_control(
            "配置方式", options=("手动配置", "自动选阶"), default="手动配置",
            key=scope.key("config_mode"),
        ) or "手动配置"
    else:
        mode = "手动配置"
    selection = (scope.family, mode)
    if selection != state.get("model_selection"):
        state.set("model_selection", selection)
        scope.clear_fit_results()

    dataset_fingerprint = str(getattr(dataset, "fingerprint", "") or "")
    inputs = _model_inputs(scope).render(
        st_obj, dataset, dataset_fingerprint=dataset_fingerprint,
    )
    if inputs is None:
        return
    config = render_model_options(
        st_obj,
        scope.family,
        mode,
        inputs.exog,
        response_log=inputs.response_log,
        exog_log_names=inputs.exog_log_names,
        intervention_analysis=inputs.intervention_analysis,
        model_dates=inputs.index,
        key_prefix=scope.key_prefix, state_manager=state,
    )
    if config is None:
        if scope.family == "RDL":
            state.set("intervention_config", None)
        return
    if scope.family == "RDL":
        state.set("intervention_config", config.intervention)

    problems = validate_fit_inputs(inputs.series, inputs.exog, config)
    for problem in problems:
        st_obj.warning(problem)
    if scope.family == "SARIMAX":
        for warning in fit_input_warnings(inputs.exog):
            st_obj.warning(warning)
    signature = artifact_signature(
        data_fingerprint=dataset_fingerprint,
        parameters={
            "family": scope.family, "mode": mode, "target": inputs.target,
            "exog_variables": inputs.exog_names,
            "time_range": tuple(value.isoformat() for value in inputs.training_range),
            "preprocessing": inputs.preprocessing, "response_log": inputs.response_log,
            "exog_log_names": inputs.exog_log_names,
            "intervention_analysis": inputs.intervention_analysis,
            "config": config.signature(),
        },
        version="dynamic-regression-fit-v2",
    )
    context = ModelContext(
        dataset_fingerprint=inputs.dataset_fingerprint,
        mode=mode,
        target=inputs.target,
        exog_names=inputs.exog_names,
        training_range=inputs.training_range,
        preprocessing=inputs.preprocessing,
        missing_value_method=inputs.missing_value_method,
        response_log=inputs.response_log,
        exog_log_names=inputs.exog_log_names,
    )
    if st_obj.button("拟合模型", type="primary", disabled=bool(problems), key=scope.key("fit_button")):
        if scope.family == "SARIMAX":
            st_obj.session_state.pop(scope.key("auto_selection_model"), None)
        automatic = is_automatic_config(config)
        progress_bar = st_obj.progress(0.0, text="正在准备候选模型评估...") if automatic else None
        progress_state = {"completed": 0, "total": 0}

        def update_progress(completed: int, total: int) -> None:
            progress_state["completed"] = completed
            progress_state["total"] = total
            if progress_bar is not None:
                progress_bar.progress(completed / max(total, 1), text=f"正在评估候选模型：{completed}/{total}")

        with st_obj.spinner("正在调用 Ts 包拟合模型..."):
            try:
                result = _MODEL_WORKFLOW.fit(inputs, config, progress_callback=update_progress if automatic else None)
                if progress_bar is not None:
                    progress_bar.progress(1.0, text="候选模型评估完成，正在整理最优模型结果。")
            except Exception as exc:  # noqa: BLE001 - 用户可读的拟合边界
                if progress_bar is not None and progress_state["total"]:
                    progress_bar.progress(
                        progress_state["completed"] / progress_state["total"],
                        text=f"候选模型评估中断：{progress_state['completed']}/{progress_state['total']}",
                    )
                st_obj.error(translate_ts_error(exc))
                logger.exception("%s 模型拟合失败", scope.family)
                scope.clear_fit_results()
                return
        scope.store_fit_result(result, signature)
        state.set("fit_config", config)

    result = state.get("fitted_result")
    if result is None:
        return
    if state.get("fit_signature") != signature:
        scope.clear_fit_results()
        return
    _render_fit_summary(st_obj, result, scope)
    return context


def _render_fit_summary(
    st_obj,
    result,
    scope: ModelPageScope,
) -> None:
    """通过通用结果视图展示拟合摘要与关键指标。"""
    selected = render_estimation_result(
        st_obj, _MODEL_WORKFLOW.result_view(result),
        selection_key=scope.key("auto_selection_criterion"),
        candidate_selection_key=scope.key("auto_selection_model"),
    )
    if selected is None:
        return
    try:
        result = _MODEL_WORKFLOW.select_result(result, selected)
    except Exception as exc:  # noqa: BLE001 - 用户可读的选阶边界
        st_obj.error(f"重新选择模型失败：{translate_ts_error(exc)}")
        return
    scope.store_fit_result(result, scope.state.get("fit_signature"))
    render_estimation_result(
        st_obj, _MODEL_WORKFLOW.result_view(result),
        selection_key=scope.key("auto_selection_criterion"),
        candidate_selection_key=scope.key("auto_selection_model"), show_selection=False,
    )


__all__ = ["render_training_section"]
