# -*- coding: utf-8 -*-
"""三个数据模块共用的会话级数据集状态。"""

from __future__ import annotations

import hashlib
import io
from typing import Optional

import pandas as pd
import streamlit as st


STATE_PREFIX = "dashboard.shared_dataset"
SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]


def _state_key(name: str) -> str:
    return f"{STATE_PREFIX}.{name}"


def fingerprint_file(uploaded_file) -> str:
    """返回文件名与内容共同决定的稳定指纹。"""
    content = uploaded_file.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    return f"{uploaded_file.name}:{len(content)}:{digest}"


def load_shared_dataframe(uploaded_file) -> pd.DataFrame:
    """以通用时序表格式读取共享文件，第一列优先解析为时间列。"""
    content = uploaded_file.getvalue()
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension == "csv":
        last_error = None
        for encoding in ("utf-8", "gbk", "gb2312"):
            try:
                return pd.read_csv(io.StringIO(content.decode(encoding)), parse_dates=[0])
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError("无法解码 CSV 文件，请使用 UTF-8、GBK 或 GB2312 编码") from last_error
    if extension in {"xlsx", "xls"}:
        return pd.read_excel(io.BytesIO(content), parse_dates=[0])
    raise ValueError(f"不支持的文件格式：{extension}")


def get_shared_dataset_file():
    """获取当前会话的原始上传文件。"""
    return st.session_state.get(_state_key("file"))


def get_shared_dataset_data() -> Optional[pd.DataFrame]:
    """获取当前会话的通用 DataFrame。"""
    return st.session_state.get(_state_key("data"))


def get_shared_dataset_name() -> str:
    """获取当前会话数据集名称。"""
    return st.session_state.get(_state_key("file_name"), "")


def get_shared_dataset_fingerprint() -> str:
    """获取当前会话数据集指纹。"""
    return st.session_state.get(_state_key("fingerprint"), "")


def _clear_dependent_analysis_state() -> None:
    """新文件进入后移除依赖旧数据的探索结果。"""
    prefixes = (
        "tools.analysis.",
        "exploration.time_lag_corr.",
        "exploration.lead_lag.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]


def clear_shared_dataset() -> None:
    """清除共享数据集及其派生的探索结果。"""
    for key in list(st.session_state):
        if str(key).startswith(f"{STATE_PREFIX}."):
            del st.session_state[key]
    _clear_dependent_analysis_state()


def render_shared_dataset_uploader(st_obj) -> dict:
    """在侧边栏渲染唯一上传器，并在文件变更时更新共享状态。"""
    st_obj.markdown("### 共享数据集")
    uploaded_file = st_obj.file_uploader(
        "选择数据文件",
        type=SUPPORTED_FILE_TYPES,
        key="dashboard_shared_dataset_uploader",
        help="数据预览、监测分析和数据探索会共同使用此文件。",
    )

    if uploaded_file is None:
        if get_shared_dataset_file() is not None:
            clear_shared_dataset()
        st_obj.caption("支持 CSV、XLS、XLSX；更换文件会清除数据探索的历史结果。")
        return {"show_upload": True, "has_data": False}

    fingerprint = fingerprint_file(uploaded_file)
    if fingerprint != get_shared_dataset_fingerprint():
        try:
            data = load_shared_dataframe(uploaded_file)
            data = data.dropna(how="all").dropna(axis=1, how="all")
            if data.empty:
                raise ValueError("文件清理后为空")
        except Exception as exc:
            clear_shared_dataset()
            st_obj.error(f"共享数据集读取失败：{exc}")
            return {"show_upload": True, "has_data": False, "error": str(exc)}

        _clear_dependent_analysis_state()
        st.session_state[_state_key("file")] = uploaded_file
        st.session_state[_state_key("data")] = data
        st.session_state[_state_key("file_name")] = uploaded_file.name
        st.session_state[_state_key("fingerprint")] = fingerprint

    data = get_shared_dataset_data()
    st_obj.success(f"已加载：{uploaded_file.name}")
    st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
    return {"show_upload": True, "has_data": True, "file_name": uploaded_file.name}


__all__ = [
    "clear_shared_dataset",
    "fingerprint_file",
    "get_shared_dataset_data",
    "get_shared_dataset_file",
    "get_shared_dataset_fingerprint",
    "get_shared_dataset_name",
    "render_shared_dataset_uploader",
]
