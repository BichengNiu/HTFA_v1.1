"""模型库的保存控件与侧边栏展示。"""

from __future__ import annotations

from datetime import datetime

from dashboard.models.common.model_library import (
    ModelContext,
    ModelLibrary,
    ModelRecord,
    ensure_model_library,
)


_NOTICE_KEY = "model_library.notice"
_CLEAR_CONFIRM_KEY = "model_library.clear_confirm"


def render_model_library_sidebar(st_obj) -> None:
    """在当前页面侧边栏展示共享模型库及其管理操作。"""

    _, library = ensure_model_library(st_obj.session_state)
    st_obj.markdown("### 模型库")
    notice = st_obj.session_state.pop(_NOTICE_KEY, None)
    if notice:
        st_obj.toast(notice)

    records = library.records
    if not records:
        st_obj.session_state.pop(_CLEAR_CONFIRM_KEY, None)
        st_obj.caption("暂无已保存模型。模型拟合后可手动加入模型库。")
        return

    st_obj.caption(f"已保存 {len(records)} 个模型；服务重启后清空。")
    for record in records:
        _render_record(st_obj, library, record)

    confirmed = st_obj.checkbox(
        "确认清空模型库",
        key=_CLEAR_CONFIRM_KEY,
        help="清空只影响模型库中的保存记录，不会删除当前页面的拟合、诊断或预测结果。",
    )
    if st_obj.button(
        "清空模型库",
        key="model_library_clear_button",
        disabled=not confirmed,
        type="secondary",
        width="stretch",
    ):
        count = library.clear()
        st_obj.session_state.pop(_CLEAR_CONFIRM_KEY, None)
        st_obj.session_state[_NOTICE_KEY] = f"已清空模型库（{count} 个模型）。"
        st_obj.rerun()


def render_model_library_save_control(
    st_obj,
    model_object,
    *,
    family: str,
    signature: str,
    context: ModelContext,
) -> None:
    """在当前拟合结果下提供一个显式的模型库保存入口。"""

    _, library = ensure_model_library(st_obj.session_state)
    existing = _record_for_signature(library, signature)
    label_key = _label_key(family, signature)
    if label_key not in st_obj.session_state:
        st_obj.session_state[label_key] = existing.label if existing else ""

    clicked = st_obj.button(
        "加入模型库",
        key=_save_key(family, signature),
        type="secondary",
        width="stretch",
    )
    label = st_obj.text_input(
        "模型库名称（可选）",
        key=label_key,
        placeholder=f"留空则自动命名：{family} | {context.target} | 保存时间",
        help=(
            "仅新记录使用此名称；同一模型签名再次保存时保留原名称。"
        ),
    )
    if existing is not None:
        st_obj.caption(
            "再次保存会更新模型对象和保存时间，并保留记录编号与名称。"
        )
    if clicked:
        try:
            record = library.save(
                model_object,
                family=family,
                signature=signature,
                context=context,
                label=label,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的保存边界
            st_obj.error(f"加入模型库失败：{exc}")
            return
        action = "更新" if existing is not None else "保存"
        st_obj.session_state[_NOTICE_KEY] = (
            f"已{action}模型：{record.label}。"
        )
        st_obj.rerun()


def _render_record(st_obj, library: ModelLibrary, record: ModelRecord) -> None:
    """展示单条模型记录和删除操作。"""

    with st_obj.expander(f"{record.label} · {record.family}", expanded=False):
        st_obj.caption(f"记录编号：{record.record_id}")
        st_obj.caption(f"保存时间：{_format_datetime(record.saved_at)}")
        st_obj.caption(
            f"数据集：{_short_value(record.context.dataset_fingerprint)}；"
            f"配置：{record.context.mode}"
        )
        st_obj.caption(f"目标变量：{record.context.target}")
        if record.context.exog_names:
            st_obj.caption(f"外生变量：{', '.join(record.context.exog_names)}")
        if record.context.training_range is not None:
            start, end = record.context.training_range
            st_obj.caption(f"训练范围：{start} 至 {end}")
        preprocessing = record.context.preprocessing or ("无",)
        st_obj.caption(
            f"预处理：{', '.join(preprocessing)}；"
            f"缺失值：{record.context.missing_value_method}"
        )
        log_names = ", ".join(record.context.exog_log_names) or "无"
        st_obj.caption(
            f"目标取对数：{'是' if record.context.response_log else '否'}；"
            f"外生取对数：{log_names}"
        )
        if st_obj.button(
            "删除",
            key=f"model_library_delete_{record.record_id}",
            type="secondary",
        ):
            library.delete(record.record_id)
            st_obj.session_state.pop(_CLEAR_CONFIRM_KEY, None)
            st_obj.session_state[_NOTICE_KEY] = f"已删除模型：{record.label}。"
            st_obj.rerun()


def _record_for_signature(
    library: ModelLibrary,
    signature: str,
) -> ModelRecord | None:
    return next(
        (record for record in library.records if record.signature == signature),
        None,
    )


def _format_datetime(value: datetime) -> str:
    local_value = value.astimezone().replace(microsecond=0)
    return local_value.strftime("%Y-%m-%d %H:%M")


def _short_value(value: str) -> str:
    return value if len(value) <= 16 else f"{value[:16]}…"


def _label_key(family: str, signature: str) -> str:
    return f"model_library_label_{family}_{signature}"


def _save_key(family: str, signature: str) -> str:
    return f"model_library_save_{family}_{signature}"


__all__ = [
    "render_model_library_save_control",
    "render_model_library_sidebar",
]
