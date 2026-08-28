"""数据概览环节编排：上传 → 数据集缓存 → 选择 → 表 → 图 → 高级选项。

数据流：
DataSource 上传/工作表 → dataset（指纹缓存，{namespace}.dataset）
  ├─ selectors：变量选择
  ├─ table_panel：筛选 → 预览表 / 统计量
  └─ chart_panel：5-tab 状态 → build_chart_options → Ts plot_series
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
from typing import Any, Callable

import pandas as pd
import streamlit as st

from ..core.dataset import OverviewDataset, build_overview_dataset
from ..core.options import build_chart_options, build_table_options
from .chart_options_tabs import render_chart_options_expander
from .chart_panel import draw_series_plot
from .data_source import BuiltinDataSource, DataSource
from .selectors import render_variable_selector
from .table_panel import render_table_options_expander, render_table_panel
from .widget_keys import overview_widget_keys, preview_key

# 数据集构建器签名：``(frame, file_name, fingerprint) -> dataset``。
DatasetBuilder = Callable[[Any, str, str], Any]


@dataclass(frozen=True)
class DataOverviewConfig:
    """数据概览组件的实例配置。

    不同实例必须使用不同的 key_prefix 与 state_namespace，
    以避免 widget 键与数据集缓存互相覆盖。
    """

    key_prefix: str = "sarimax"
    state_namespace: str = "model_analysis.sarimax"
    data_source: DataSource | None = None
    dataset_builder: DatasetBuilder = build_overview_dataset
    on_dataset_replaced: Callable[[Any], None] | None = None
    title: str = "#### ① 数据概览"
    empty_variables_message: str = "数据中没有可用的数值型变量。"
    widget_keys: tuple[str, ...] | None = None


class DataOverview:
    """数据概览组件（类式入口）。

    用法::

        overview = DataOverview(key_prefix="dfm", state_namespace="model_analysis.dfm")
        overview.render(st_obj)
    """

    def __init__(self, config: DataOverviewConfig | None = None, **overrides):
        base = config if config is not None else DataOverviewConfig()
        self.config = replace(base, **overrides)
        self.state = _StateManager(self.config.state_namespace)
        self.data_source = self.config.data_source or BuiltinDataSource(
            self.config.state_namespace
        )
        self.widget_keys = self.config.widget_keys or overview_widget_keys(
            self.config.key_prefix
        )

    def render(self, st_obj) -> None:
        render_data_overview(self.config, self.state, self.data_source, st_obj)


def create_data_overview(
    *,
    key_prefix: str = "sarimax",
    state_namespace: str = "model_analysis.sarimax",
    data_source: DataSource | None = None,
    dataset_builder: DatasetBuilder = build_overview_dataset,
    on_dataset_replaced: Callable[[Any], None] | None = None,
    title: str = "#### ① 数据概览",
    empty_variables_message: str = "数据中没有可用的数值型变量。",
    widget_keys: tuple[str, ...] | None = None,
) -> Callable[[Any], None]:
    """创建数据概览渲染函数（工厂式入口）。

    用法::

        overview = create_data_overview(
            key_prefix="dfm",
            state_namespace="model_analysis.dfm",
            data_source=my_source,          # None=内置上传器
            on_dataset_replaced=clear_model,  # 换文件时清理模型结果
        )
        overview(st_obj)   # 渲染整段
    """
    component = DataOverview(
        key_prefix=key_prefix,
        state_namespace=state_namespace,
        data_source=data_source,
        dataset_builder=dataset_builder,
        on_dataset_replaced=on_dataset_replaced,
        title=title,
        empty_variables_message=empty_variables_message,
        widget_keys=widget_keys,
    )
    return component.render


class _StateManager:
    """轻量命名空间状态：``{namespace}.{key}``。"""

    def __init__(self, namespace: str):
        self.namespace = namespace

    def get(self, key: str, default: Any = None) -> Any:
        return st.session_state.get(f"{self.namespace}.{key}", default)

    def set(self, key: str, value: Any) -> None:
        st.session_state[f"{self.namespace}.{key}"] = value


def render_data_overview(
    config: DataOverviewConfig, state: _StateManager, data_source: DataSource, st_obj
) -> None:
    """展示数据集并绘制所选变量的时间序列预览图。

    第一行：数据上传组件独占一行；
    第二行：工作表、变量名行、时间列和数据开始行；
    第三行：选择变量独占一行；
    预览表与时间序列图都受「数据表高级选项」的筛选条件驱动。
    """
    key_prefix = config.key_prefix
    if config.title:
        st_obj.markdown(config.title)
    data_source.render_uploader(st_obj, compact=True)

    source_fingerprint = data_source.current_fingerprint()
    if not source_fingerprint:
        st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
        return

    row_count = data_source.row_count()
    if row_count < 2:
        st_obj.error("文件中至少需要一行变量名和一行数据。")
        return

    # 工作表、变量名行、时间列和数据开始行在同一排。
    sheets = data_source.sheets()
    has_sheet_selector = bool(sheets and len(sheets) > 1)
    selection_columns = st_obj.columns(4 if has_sheet_selector else 3)
    column_index = 0
    if has_sheet_selector:
        with selection_columns[column_index]:
            sheet_key = f"{key_prefix}_preview_sheet"
            if (
                sheet_key in st.session_state
                and st.session_state[sheet_key] not in sheets
            ):
                st.session_state[sheet_key] = sheets[0]
            current_sheet = data_source.current_sheet()
            selection_columns[column_index].selectbox(
                "选择工作表",
                options=sheets,
                index=sheets.index(current_sheet)
                if current_sheet in sheets
                else 0,
                key=sheet_key,
                on_change=_make_sheet_callback(data_source, sheet_key),
                help="Excel 文件包含多个工作表时，切换后重新加载该表数据。",
            )
        column_index += 1

    time_key = preview_key(key_prefix, "time_column")
    variable_name_key = preview_key(key_prefix, "variable_name_row")
    data_start_key = preview_key(key_prefix, "data_start_row")
    if state.get("source_fingerprint") != source_fingerprint:
        st.session_state.pop(variable_name_key, None)
        st.session_state.pop(data_start_key, None)
        st.session_state.pop(time_key, None)
        state.set("source_fingerprint", source_fingerprint)

    variable_name_default = st.session_state.get(variable_name_key, 1)
    if not 1 <= int(variable_name_default) < row_count:
        variable_name_default = 1
    st.session_state[variable_name_key] = int(variable_name_default)
    variable_name_row = selection_columns[column_index].number_input(
        "变量名行",
        min_value=1,
        max_value=row_count - 1,
        step=1,
        key=variable_name_key,
        help="输入包含变量名称的原始行号，行号从 1 开始。",
    )

    data_start_min = int(variable_name_row) + 1
    data_start_default = st.session_state.get(data_start_key, data_start_min)
    if not data_start_min <= int(data_start_default) <= row_count:
        data_start_default = data_start_min
    st.session_state[data_start_key] = int(data_start_default)
    data_start_row = selection_columns[column_index + 2].number_input(
        "数据开始行",
        min_value=data_start_min,
        max_value=row_count,
        step=1,
        key=data_start_key,
        help="输入第一行数据的行号，必须晚于变量名行。行号从 1 开始。",
    )

    dataset = state.get("dataset")
    settings_fingerprint = (
        f"{source_fingerprint}::variable_name_row={variable_name_row}"
        f"::data_start_row={data_start_row}"
    )
    dataset_changed = dataset is not None and not str(
        dataset.fingerprint
    ).startswith(settings_fingerprint)
    if dataset_changed:
        state.set("dataset", None)
        if config.on_dataset_replaced is not None:
            config.on_dataset_replaced(st_obj)
        dataset = None

    try:
        raw_data = data_source.load_data(
            variable_name_row=int(variable_name_row) - 1,
            data_start_row=int(data_start_row) - 1,
            time_column=None,
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据读取边界
        st_obj.error(f"数据读取失败：{exc}")
        return
    if raw_data is None:
        st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
        return

    time_options = ["无", *[str(column) for column in raw_data.columns]]
    time_options_signature = (
        source_fingerprint,
        int(variable_name_row),
        int(data_start_row),
        tuple(time_options),
    )
    if state.get("time_options_signature") != time_options_signature:
        # 变量名行或数据开始行变化后，旧时间列选择不能沿用；否则
        # Streamlit 会优先恢复旧 widget 值，页面可能继续显示旧表头。
        st.session_state.pop(time_key, None)
        state.set("time_options_signature", time_options_signature)
    time_default = st.session_state.get(
        time_key, _suggest_time_column(raw_data)
    )
    if time_default not in time_options:
        time_default = "无"
    st.session_state[time_key] = time_default
    time_selection = selection_columns[column_index + 1].selectbox(
        "选择时间列",
        options=time_options,
        key=time_key,
        help="选择用于识别时间索引的列；选择“无”则按观测顺序处理。",
    )

    time_column = None if time_selection == "无" else str(time_selection)
    fingerprint = (
        f"{source_fingerprint}::variable_name_row={variable_name_row}"
        f"::data_start_row={data_start_row}::time_column={time_column or 'none'}"
    )
    try:
        data = data_source.load_data(
            variable_name_row=int(variable_name_row) - 1,
            data_start_row=int(data_start_row) - 1,
            time_column=time_column,
        )
        if data is None:
            st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
            return
    except Exception as exc:  # noqa: BLE001 - 用户可读的数据读取边界
        st_obj.error(f"数据读取失败：{exc}")
        return

    if dataset is None or dataset.fingerprint != fingerprint:
        try:
            dataset = config.dataset_builder(
                data,
                data_source.current_name(),
                fingerprint,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据解析边界
            st_obj.error(f"数据集校验失败：{exc}")
            return
        if is_dataclass(dataset) and hasattr(dataset, "time_column"):
            dataset = replace(dataset, time_column=time_column)
        state.set("dataset", dataset)
        if not dataset_changed and config.on_dataset_replaced is not None:
            config.on_dataset_replaced(st_obj)

    variables = _numeric_variable_names(dataset)
    if not variables:
        st_obj.error(config.empty_variables_message)
        return

    # 变量选择独占一整排，选项来自当前变量名行。
    variable_row = st_obj.columns(1)
    selected = render_variable_selector(
        variable_row[0], variables, key_prefix=key_prefix
    )
    if not selected:
        st_obj.info("请至少选择一个变量。")
        return

    # 页面纵向顺序固定为：整排表格 → 表格高级选项 → 整排图表 → 图形高级选项。
    # 表格受数据表高级选项的筛选/视图控制，默认显示前 10 行，
    # 不设固定高度（避免多余空行）。
    table_state = build_table_options(
        st.session_state, dataset, key_prefix=key_prefix
    )
    filtered = dataset.frame.loc[table_state["mask"]]
    render_table_panel(
        st_obj,
        dataset,
        selected,
        filtered,
        table_state,
        key_prefix=key_prefix,
    )
    render_table_options_expander(
        st_obj, dataset, selected, key_prefix=key_prefix
    )

    if filtered.empty:
        st_obj.info("筛选结果为空，暂无数据可绘制。")
    else:
        options, errors = build_chart_options(
            st.session_state,
            dataset,
            filtered,
            variables=selected,
            key_prefix=key_prefix,
        )
        if errors:
            st_obj.warning("；".join(errors))
        _render_series_charts(
            st_obj, dataset, selected, filtered=filtered, options=options
        )

    render_chart_options_expander(
        st_obj, dataset, selected, key_prefix=key_prefix
    )


def _render_series_charts(st_obj, dataset, selected, *, filtered, options) -> None:
    """渲染单图或页面级分面图。"""
    if not options.get("facet") or len(selected) < 2:
        draw_series_plot(st_obj, dataset, selected, filtered=filtered, **options)
        return

    _, cols = _resolve_page_facet_grid(
        len(selected), options.get("facet_rows"), options.get("facet_cols")
    )
    if options.get("facet_rows") and options.get("facet_cols"):
        requested = options["facet_rows"] * options["facet_cols"]
        if requested < len(selected):
            st_obj.warning(
                f"分面布局 {options['facet_rows']}×{options['facet_cols']} "
                f"不足以容纳 {len(selected)} 个指标，已自动增加行数。"
            )

    for start in range(0, len(selected), cols):
        row_columns = st_obj.columns(cols)
        for column, variable in zip(row_columns, selected[start : start + cols]):
            with column:
                chart_options = _page_facet_chart_options(
                    options, selected, variable
                )
                draw_series_plot(
                    st_obj,
                    dataset,
                    [variable],
                    filtered=filtered,
                    **chart_options,
                )


def _page_facet_chart_options(
    options: dict, selected: list[str], variable: str
) -> dict:
    """为页面级独立分面生成单变量绘图参数。

    页面级分面不是 Ts 的原生多面板 Figure，而是每个变量一个独立
    Streamlit 图。因此共享坐标轴与多纵轴参数在这里不适用；legend
    必须显式传入当前变量名，否则 Ts 会按单序列冗余图例规则跳过它。
    """
    chart_options = dict(options)
    variable_index = selected.index(variable)
    colors = options.get("colors")
    series_styles = options.get("series_styles")
    legend_labels = options.get("legend_labels")
    units = options.get("units")

    chart_options.update(
        {
            "facet": False,
            "facet_rows": None,
            "facet_cols": None,
            "sharex": False,
            "sharey": False,
            "auto_dual_y": False,
            "axis_groups": None,
            "max_y_axes": 1,
            "second_axis_vars": None,
            "third_axis_vars": None,
            "second_axis_title": None,
            "third_axis_title": None,
            "legend_bbox": None,
            "legend_cols": 1,
            "colors": [colors[variable_index]] if colors else None,
            "series_styles": (
                {variable: dict(series_styles[variable])}
                if series_styles and variable in series_styles
                else None
            ),
            "legend_labels": (
                [legend_labels[variable_index]]
                if options.get("show_legend", True) and legend_labels
                else [variable]
                if options.get("show_legend", True)
                else None
            ),
            "units": {variable: units[variable]}
            if units and variable in units
            else None,
            "log_vars": (
                [variable] if variable in options.get("log_vars", []) else []
            ),
        }
    )
    return chart_options


def _resolve_page_facet_grid(
    count: int, rows: int | None, cols: int | None
) -> tuple[int, int]:
    """将分面行列选项解析为可容纳所有指标的页面网格。"""
    if rows is None and cols is None:
        cols = min(2, count)
        rows = (count + cols - 1) // cols
    elif rows is None:
        rows = (count + cols - 1) // cols
    elif cols is None:
        cols = (count + rows - 1) // rows
    elif rows * cols < count:
        rows = (count + cols - 1) // cols
    return rows, cols


def _make_sheet_callback(data_source: DataSource, sheet_key: str):
    """工作表切换回调：重载对应 sheet 的数据。"""

    def _callback() -> None:
        sheet = st.session_state.get(sheet_key)
        if sheet:
            data_source.select_sheet(sheet)

    return _callback


def _numeric_variable_names(dataset) -> list[str]:
    """数值变量名（兼容 OverviewDataset 与自定义数据集对象）。"""
    from ..core.dataset import numeric_variable_names

    return numeric_variable_names(dataset.frame)


def _suggest_time_column(frame: pd.DataFrame) -> str:
    """建议可解析的首列为时间列，否则默认不使用时间列。"""
    if frame.shape[1] == 0:
        return "无"
    first = frame.iloc[:, 0]
    if pd.api.types.is_datetime64_any_dtype(first):
        return str(frame.columns[0])
    if pd.api.types.is_numeric_dtype(first):
        return "无"
    nonblank = first.notna() & first.astype(str).str.strip().ne("")
    parsed = pd.to_datetime(first, errors="coerce", format="mixed")
    if nonblank.any() and parsed.loc[nonblank].notna().all():
        return str(frame.columns[0])
    return "无"


__all__ = [
    "DataOverview",
    "DataOverviewConfig",
    "create_data_overview",
]
