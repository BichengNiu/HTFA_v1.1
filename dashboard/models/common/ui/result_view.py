"""通用估计结果展示模块。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dashboard.models.common.contracts import EstimationResultView


def render_estimation_result(
    st_obj,
    view: EstimationResultView,
    *,
    on_selection_changed: Callable[[Any], None] | None = None,
    selection_key: str = "model_selection_criterion",
    show_selection: bool = True,
) -> Any | None:
    """展示通用拟合结果，并返回用户新选择的模型选项。

    Parameters
    ----------
    st_obj : object
        具有 Streamlit 展示方法的对象。
    view : EstimationResultView
        模型适配器生成的稳定结果视图。
    on_selection_changed : callable or None
        自动选阶选项变化时的可选回调。
    selection_key : str, default="model_selection_criterion"
        选阶控件的 Streamlit 键。
    show_selection : bool, default=True
        是否显示模型候选选择区域；重新选择后可关闭以避免重复渲染。

    Returns
    -------
    object or None
        新选择的选项；没有可选项或选项未变化时返回 ``None``。
    """
    if show_selection and view.selection_title:
        st_obj.divider()
        st_obj.markdown(f"**{view.selection_title}**")
    if show_selection and view.selection_message:
        st_obj.info(view.selection_message)
    if show_selection and view.selection_table is not None:
        st_obj.dataframe(view.selection_table, width="stretch")

    selected = None
    if show_selection and view.selection_options:
        options = list(view.selection_options)
        current = (
            view.selection_value
            if view.selection_value in options
            else options[0]
        )
        selected = st_obj.selectbox(
            "最终采用的最小准则",
            options=options,
            index=options.index(current),
            format_func=str.upper,
            key=selection_key,
            help=view.selection_help,
        )
        if selected != view.selection_value:
            if on_selection_changed is not None:
                on_selection_changed(selected)
            return selected

    if view.selected_label:
        criterion = view.metadata.get("selection_criterion")
        suffix = f"（{str(criterion).upper()} 最小）" if criterion else ""
        st_obj.markdown(f"最终采用模型：{view.selected_label}{suffix}")

    _render_search_metadata(st_obj, view.metadata.get("search_metadata"))

    status = "已收敛" if view.converged else "未收敛"
    st_obj.success(
        f"模型优化状态：{status} · 有效样本量 {view.effective_nobs}"
        f" · 优化器 {view.optimizer or '未知'}"
    )
    metric_columns = st_obj.columns(3)
    metric_columns[0].metric("AIC", f"{view.aic:.4f}")
    metric_columns[1].metric("BIC", f"{view.bic:.4f}")
    metric_columns[2].metric("对数似然", f"{view.log_likelihood:.4f}")
    with st_obj.expander("参数摘要", expanded=False):
        st_obj.code(view.summary)
    return None


def _render_search_metadata(st_obj, metadata: Any) -> None:
    """展示适配器提供的候选搜索调度审计信息。"""
    if not isinstance(metadata, dict) or not metadata:
        return
    mode = {"parallel": "并行", "serial": "串行"}.get(
        metadata.get("mode"), "未知"
    )
    reasons = {
        "bounded_process_parallelism": "满足并行阈值",
        "candidate_count_below_threshold": "候选数低于并行阈值",
        "estimated_work_below_threshold": "预计工作量低于并行阈值",
        "explicit_serial_request": "显式串行请求",
        "single_available_worker": "仅有一个可用工作进程",
    }
    reason = reasons.get(metadata.get("reason"), "未提供")
    elapsed = metadata.get("elapsed_seconds")
    elapsed_text = (
        f"{elapsed:.2f} 秒" if isinstance(elapsed, (int, float)) else "未提供"
    )
    st_obj.caption(
        "本次候选调度："
        f"{mode} · {metadata.get('worker_count', '未知')} 个工作进程"
        f" · {metadata.get('candidate_count', '未知')} 个候选"
        f" · 耗时 {elapsed_text} · {reason}。"
    )


__all__ = ["render_estimation_result"]
