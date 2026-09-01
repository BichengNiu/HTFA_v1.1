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
    candidate_selection_key: str | None = None,
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
    candidate_selection_key : str or None, optional
        其他候选模型控件的 Streamlit 键；省略时根据 ``selection_key`` 生成。
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
    selected_candidate = view.candidate_value
    if show_selection and view.selection_options:
        options = list(view.selection_options)
        current = (
            view.selection_value
            if view.selection_value in options
            else options[0]
        )
        # Use a content-sized horizontal row so the second control follows the
        # criterion selector immediately instead of inheriting page-width gaps.
        selection_row = (
            st_obj.container(
                horizontal=True,
                horizontal_alignment="left",
                gap="xxsmall",
                width="content",
            )
            if view.candidate_options
            else st_obj
        )
        candidate_key = candidate_selection_key or f"{selection_key}_model"
        radio_kwargs = {}
        if view.candidate_options:
            radio_kwargs = {
                "on_change": _reset_candidate_selection,
                "args": (st_obj.session_state, candidate_key),
            }
        selected = selection_row.radio(
            "最终采用模型",
            options=options,
            index=options.index(current),
            format_func=str.upper,
            horizontal=True,
            key=selection_key,
            help=view.selection_help,
            **radio_kwargs,
        )
        if view.candidate_options:
            candidate_options = (None, *view.candidate_options)
            candidate_value = (
                view.candidate_value
                if view.candidate_value in candidate_options
                else None
            )
            selected_candidate = selection_row.selectbox(
                "其他模型",
                options=candidate_options,
                index=candidate_options.index(candidate_value),
                format_func=(
                    lambda value: (
                        "按左侧准则选择" if value is None else str(value)
                    )
                ),
                key=candidate_key,
                help=view.candidate_help,
                width=320,
            )
        if selected != view.selection_value:
            if on_selection_changed is not None:
                on_selection_changed(selected)
            return ("criterion", selected)
        if selected_candidate != view.candidate_value:
            return (
                ("criterion", selected)
                if selected_candidate is None
                else ("candidate", selected_candidate)
            )
    st_obj.divider()
    st_obj.markdown("**参数估计结果**")
    st_obj.code(view.summary)
    return None


def _reset_candidate_selection(session_state, candidate_key: str) -> None:
    """radio 改变时清除右侧候选覆盖，避免两个控件互相覆盖。"""
    session_state[candidate_key] = None


__all__ = ["render_estimation_result"]
