# -*- coding: utf-8 -*-
"""三个数据模块共用的会话级数据集状态。"""

from __future__ import annotations

import csv
import io
from typing import Optional

import pandas as pd
import streamlit as st

from dashboard.core.workspace import SessionWorkspace


STATE_PREFIX = "dashboard.shared_dataset"
SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]
_AUTO_TIME_COLUMN = object()


def _state_key(name: str) -> str:
    return f"{STATE_PREFIX}.{name}"


def _workspace() -> SessionWorkspace:
    return SessionWorkspace(st.session_state)


def fingerprint_file(uploaded_file) -> str:
    """返回只由文件内容决定的稳定 SHA-256 指纹。"""
    content = uploaded_file.getvalue()
    from hashlib import sha256

    return sha256(content).hexdigest()


def _parse_first_column_as_time(frame: pd.DataFrame) -> pd.DataFrame:
    """仅当第一列的全部有效值都是日期时才转换该列。"""

    if frame.empty or frame.shape[1] == 0:
        return frame

    first_column = frame.iloc[:, 0]
    if pd.api.types.is_datetime64_any_dtype(first_column):
        return frame
    if pd.api.types.is_numeric_dtype(first_column):
        return frame

    nonblank = first_column.notna() & first_column.astype(str).str.strip().ne("")
    if not nonblank.any():
        return frame

    parsed = pd.to_datetime(first_column, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        return frame

    result = frame.copy()
    result[result.columns[0]] = parsed
    return result


def list_excel_sheets(uploaded_file) -> Optional[list[str]]:
    """Excel 文件返回工作表名列表；非 Excel 文件返回 None。"""
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension not in {"xlsx", "xls"}:
        return None
    with pd.ExcelFile(io.BytesIO(uploaded_file.getvalue())) as excel:
        return list(excel.sheet_names)


def _read_raw_rows(
    uploaded_file, sheet_name: Optional[str] = None
) -> list[list[object]]:
    """读取原始行，不预设表头，保留前置说明行。"""
    content = uploaded_file.getvalue()
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension == "csv":
        last_error = None
        for encoding in ("utf-8", "gbk", "gb2312"):
            try:
                return [
                    list(row)
                    for row in csv.reader(
                        io.StringIO(content.decode(encoding), newline="")
                    )
                ]
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError(
            "无法解码 CSV 文件，请使用 UTF-8、GBK 或 GB2312 编码"
        ) from last_error
    if extension in {"xlsx", "xls"}:
        if sheet_name is None:
            with pd.ExcelFile(io.BytesIO(content)) as excel:
                sheet_name = excel.sheet_names[0]
        frame = pd.read_excel(
            io.BytesIO(content),
            sheet_name=sheet_name,
            header=None,
        )
        return frame.where(pd.notna(frame), None).values.tolist()
    raise ValueError(f"不支持的文件格式：{extension}")


def _is_blank(value: object) -> bool:
    """判断原始单元格是否为空。"""
    return value is None or (isinstance(value, float) and pd.isna(value)) or (
        isinstance(value, str) and not value.strip()
    )


def _infer_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """把完全由数字组成的文本列恢复为数值列。"""
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            continue
        converted = pd.to_numeric(result[column], errors="coerce")
        nonblank = result[column].notna()
        if converted[nonblank].notna().all():
            result[column] = converted
    return result


def _make_unique_column_names(names: list[str]) -> list[str]:
    """保留首个表头，重复表头按出现顺序追加 ``__2``、``__3``。"""
    used = set()
    occurrence: dict[str, int] = {}
    unique_names = []
    for base_name in names:
        occurrence[base_name] = occurrence.get(base_name, 0) + 1
        suffix_number = occurrence[base_name]
        candidate = (
            base_name
            if suffix_number == 1
            else f"{base_name}__{suffix_number}"
        )
        while candidate in used:
            occurrence[base_name] += 1
            suffix_number = occurrence[base_name]
            candidate = f"{base_name}__{suffix_number}"
        used.add(candidate)
        unique_names.append(candidate)
    return unique_names


def _parse_time_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """把用户指定列解析为时间列，无法完整解析时提示用户。"""
    if column not in frame.columns:
        raise ValueError(f"时间列不存在：{column}")
    values = frame[column]
    if pd.api.types.is_datetime64_any_dtype(values):
        return frame
    nonblank = values.notna() & values.astype(str).str.strip().ne("")
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        raise ValueError(f"时间列“{column}”存在无法解析的值")
    result = frame.copy()
    result[column] = parsed
    return result


def _build_dataframe_from_rows(
    rows: list[list[object]],
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
) -> pd.DataFrame:
    """按 0-based 行号从原始行构建带变量名的数据框。"""
    if not isinstance(variable_name_row, int) or isinstance(variable_name_row, bool):
        raise ValueError("变量名行必须是整数")
    if not isinstance(data_start_row, int) or isinstance(data_start_row, bool):
        raise ValueError("数据开始行必须是整数")
    if variable_name_row < 0 or data_start_row <= variable_name_row:
        raise ValueError("数据开始行必须晚于变量名行")
    if variable_name_row >= len(rows) or data_start_row >= len(rows):
        raise ValueError("选择的行号超出数据范围")

    header = list(rows[variable_name_row])
    while header and _is_blank(header[-1]):
        header.pop()
    if not header:
        raise ValueError("变量名行为空")
    names = []
    for index, value in enumerate(header, start=1):
        if _is_blank(value):
            raise ValueError(f"变量名行第 {index} 列为空")
        names.append(str(value).strip())
    names = _make_unique_column_names(names)

    width = len(names)
    data_rows = []
    for row_number, row in enumerate(rows[data_start_row:], start=data_start_row + 1):
        values = list(row)
        if len(values) > width and any(
            not _is_blank(value) for value in values[width:]
        ):
            raise ValueError(f"第 {row_number} 行超过变量名行的列数")
        data_rows.append(values[:width] + [None] * max(0, width - len(values)))
    frame = pd.DataFrame(data_rows, columns=names)
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("数据开始行之后没有可读取的数据")
    frame = _infer_numeric_columns(frame)
    if time_column is _AUTO_TIME_COLUMN:
        return _parse_first_column_as_time(frame)
    if time_column is None:
        return frame
    return _parse_time_column(frame, time_column)


def load_shared_dataframe(
    uploaded_file,
    sheet_name: Optional[str] = None,
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
    raw_rows: list[list[object]] | None = None,
) -> pd.DataFrame:
    """按变量名行和数据开始行读取共享文件。

    ``raw_rows`` 用于调用方已经读取并校验当前工作表时复用原始行，
    避免在同一页面重跑中重复打开 Excel。未提供时保持原有文件读取行为。
    """
    rows = (
        _read_raw_rows(uploaded_file, sheet_name=sheet_name)
        if raw_rows is None
        else raw_rows
    )
    return _build_dataframe_from_rows(
        rows,
        variable_name_row=variable_name_row,
        data_start_row=data_start_row,
        time_column=time_column,
    )


def get_shared_dataset_row_count() -> int:
    """返回当前工作表的原始行数。"""
    return len(st.session_state.get(_state_key("raw_rows"), []))


def get_shared_dataset_raw_rows() -> list[list[object]] | None:
    """返回当前工作表已缓存的原始行；没有缓存时返回 ``None``。"""
    return st.session_state.get(_state_key("raw_rows"))


def get_shared_dataset_file():
    """获取当前会话的原始上传文件内存视图。"""
    return _workspace().open_asset("shared")


def get_shared_dataset_data() -> Optional[pd.DataFrame]:
    """获取当前会话的通用 DataFrame。"""
    return st.session_state.get(_state_key("data"))


def get_shared_dataset_name() -> str:
    """获取当前会话数据集名称。"""
    asset = _workspace().get_asset("shared")
    return asset.name if asset is not None else ""


def get_shared_dataset_fingerprint() -> str:
    """获取当前会话数据集指纹。"""
    return st.session_state.get(_state_key("fingerprint"), "")


def get_shared_dataset_sheets() -> Optional[list[str]]:
    """获取当前会话上传文件的工作表名列表（非 Excel 为 None）。"""
    return st.session_state.get(_state_key("sheets"))


def get_shared_dataset_sheet() -> Optional[str]:
    """获取当前会话选中的工作表名。"""
    return st.session_state.get(_state_key("sheet"))


def select_shared_dataset_sheet(
    sheet: str, *, allow_unparsed: bool = False
) -> bool:
    """切换到指定工作表并重载共享数据；成功返回 True。"""
    uploaded_file = get_shared_dataset_file()
    if uploaded_file is None:
        return False
    raw_rows = []
    try:
        raw_rows = _read_raw_rows(uploaded_file, sheet_name=sheet)
        data = _build_dataframe_from_rows(raw_rows)
    except Exception:
        if not allow_unparsed:
            return False
        _clear_dependent_analysis_state()
        st.session_state.pop(_state_key("data"), None)
        st.session_state[_state_key("raw_rows")] = raw_rows
        st.session_state[_state_key("file_name")] = uploaded_file.name
        st.session_state[_state_key("fingerprint")] = (
            f"{fingerprint_file(uploaded_file)}::{sheet}"
        )
        st.session_state[_state_key("sheet")] = sheet
        return True
    _clear_dependent_analysis_state()
    st.session_state[_state_key("data")] = data
    st.session_state[_state_key("raw_rows")] = raw_rows
    st.session_state[_state_key("file_name")] = uploaded_file.name
    st.session_state[_state_key("fingerprint")] = (
        f"{fingerprint_file(uploaded_file)}::{sheet}"
    )
    st.session_state[_state_key("sheet")] = sheet
    return True


def _clear_dependent_analysis_state() -> None:
    """新文件进入后移除依赖旧数据的探索与模型分析结果。"""
    prefixes = (
        "exploration.dataset.",
        "tools.analysis.",
        "exploration.lead_lag.",
        "model_analysis.sarimax.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]
    # SARIMAX 的数据概览和训练控件是共享文件的直接消费者；文件内容
    # 改变时必须清除，避免旧变量名被 Streamlit 重新注入新数据集。
    for key in list(st.session_state):
        if str(key).startswith("sarimax_"):
            del st.session_state[key]


def _clear_shared_page_snapshots() -> None:
    """清理依赖共享文件的页面输入快照。"""
    prefixes = (
        "workspace.pages.exploration.",
        "workspace.pages.model_analysis.sarimax.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]


def _clear_shared_derived_state() -> None:
    """保留文件资产，移除共享文件衍生状态与分析结果。"""
    for key in list(st.session_state):
        if str(key).startswith(f"{STATE_PREFIX}."):
            del st.session_state[key]
    _clear_shared_page_snapshots()
    _clear_dependent_analysis_state()


def clear_shared_dataset() -> None:
    """明确清除共享文件及其衍生的页面和分析状态。"""
    _workspace().clear_asset("shared")
    _clear_shared_derived_state()


def _fingerprint_matches(file_fingerprint: str, current: str) -> bool:
    """当前指纹是否属于该文件（兼容“文件指纹::工作表名”形式）。"""
    return current == file_fingerprint or current.startswith(
        f"{file_fingerprint}::"
    )


def render_shared_dataset_uploader(
    st_obj, *, compact: bool = False, allow_unparsed: bool = False
) -> dict:
    """渲染共享数据集上传器，并在文件变更时更新共享状态。

    compact=True 时隐藏「共享数据集」标题、已加载提示与行数列数
    小字（用于页面主区域内嵌场景，如模型分析的数据概览）。
    """
    if not compact:
        st_obj.markdown("### 共享数据集")
    uploaded_file = st_obj.file_uploader(
        "选择数据文件",
        type=SUPPORTED_FILE_TYPES,
        key="dashboard_shared_dataset_uploader",
        help="数据预览、监测分析、数据探索和模型分析会共同使用此文件。",
    )

    if uploaded_file is None:
        asset = _workspace().get_asset("shared")
        if asset is not None:
            st_obj.caption(f"当前会话文件：{asset.name}")
            if st_obj.button("清除当前文件", key="dashboard_shared_dataset_clear"):
                clear_shared_dataset()
                return {"show_upload": True, "has_data": False}
            return {
                "show_upload": True,
                "has_data": True,
                "file_name": asset.name,
            }
        if not compact:
            st_obj.caption(
                "支持 CSV、XLS、XLSX；更换文件会清除数据探索与模型分析的历史结果。"
            )
        return {"show_upload": True, "has_data": False}

    update = _workspace().put_asset("shared", uploaded_file)
    active_file = _workspace().open_asset("shared")
    if active_file is None:  # pragma: no cover - put_asset 成功后的防御边界
        raise RuntimeError("共享文件资产未能保存")
    fingerprint = update.asset.fingerprint
    if update.changed or not _fingerprint_matches(
        fingerprint, get_shared_dataset_fingerprint()
    ):
        sheets = None
        sheet = None
        raw_rows = []
        try:
            _clear_shared_derived_state()
            sheets = list_excel_sheets(active_file)
            sheet = sheets[0] if sheets else None
            raw_rows = _read_raw_rows(active_file, sheet_name=sheet)
            data = _build_dataframe_from_rows(raw_rows)
        except Exception as exc:
            if not allow_unparsed:
                st_obj.error(f"共享数据集读取失败：{exc}")
                return {"show_upload": True, "has_data": False, "error": str(exc)}
            st.session_state[_state_key("data")] = None
            st.session_state[_state_key("raw_rows")] = raw_rows
            st.session_state[_state_key("fingerprint")] = fingerprint
            st.session_state[_state_key("sheets")] = sheets
            st.session_state[_state_key("sheet")] = sheet
            st_obj.warning(
                "默认读取失败；请在数据预览中输入变量名行和数据开始行后重试。"
            )
            return {
                "show_upload": True,
                "has_data": True,
                "file_name": active_file.name,
                "error": str(exc),
            }

        st.session_state[_state_key("data")] = data
        st.session_state[_state_key("raw_rows")] = raw_rows
        st.session_state[_state_key("fingerprint")] = fingerprint
        st.session_state[_state_key("sheets")] = sheets
        st.session_state[_state_key("sheet")] = sheet

    if not compact:
        st_obj.success(f"已加载：{active_file.name}")
        data = get_shared_dataset_data()
        if data is not None:
            st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
    return {"show_upload": True, "has_data": True, "file_name": active_file.name}


__all__ = [
    "clear_shared_dataset",
    "fingerprint_file",
    "get_shared_dataset_data",
    "get_shared_dataset_file",
    "get_shared_dataset_fingerprint",
    "get_shared_dataset_name",
    "get_shared_dataset_raw_rows",
    "get_shared_dataset_row_count",
    "get_shared_dataset_sheet",
    "get_shared_dataset_sheets",
    "list_excel_sheets",
    "render_shared_dataset_uploader",
    "select_shared_dataset_sheet",
]
