"""数据概览环节编排：上传 → 数据集缓存 → 选择 → 表与图分栏 → 高级选项。

数据流：
DataSource 上传/工作表 → dataset（指纹缓存，{namespace}.dataset）
  ├─ selectors：变量选择
  ├─ table_panel：筛选 → 预览表 / 统计量
  └─ chart_panel：5-tab 状态 → build_chart_options → Ts plot_series
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

import streamlit as st

from ..core.dataset import OverviewDataset, build_overview_dataset
from ..core.options import build_chart_options, build_table_options
from .chart_options_tabs import render_chart_options_expander
from .chart_panel import draw_series_plot
from .data_source import BuiltinDataSource, DataSource
from .selectors import render_variable_selector
from .table_panel import render_table_options_expander, render_table_panel
from .widget_keys import overview_widget_keys

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
    第二行：工作表选择（左）与变量选择（右）并排；
    预览表与时间序列图都受「数据表高级选项」的筛选条件驱动。
    """
    key_prefix = config.key_prefix
    st_obj.markdown(config.title)
    data_source.render_uploader(st_obj, compact=True)

    data = data_source.current_data()
    if data is None:
        st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
        return

    fingerprint = data_source.current_fingerprint()
    dataset = state.get("dataset")
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
        state.set("dataset", dataset)
        if config.on_dataset_replaced is not None:
            config.on_dataset_replaced(st_obj)

    variables = _numeric_variable_names(dataset)
    if not variables:
        st_obj.error(config.empty_variables_message)
        return

    # 第二行：工作表选择（左）与变量选择（右）并排。工作表选择在
    # dataset 构建之后渲染，避免清理逻辑清掉其选中状态。
    sheets = data_source.sheets()
    if sheets and len(sheets) > 1:
        selection_columns = st_obj.columns(2, vertical_alignment="center")
        with selection_columns[0]:
            sheet_key = f"{key_prefix}_preview_sheet"
            if (
                sheet_key in st.session_state
                and st.session_state[sheet_key] not in sheets
            ):
                st.session_state[sheet_key] = sheets[0]
            current_sheet = data_source.current_sheet()
            st_obj.selectbox(
                "选择工作表",
                options=sheets,
                index=sheets.index(current_sheet)
                if current_sheet in sheets
                else 0,
                key=sheet_key,
                on_change=_make_sheet_callback(data_source, sheet_key),
                help="Excel 文件包含多个工作表时，切换后重新加载该表数据。",
            )
        with selection_columns[1]:
            selected = render_variable_selector(
                st_obj, variables, key_prefix=key_prefix
            )
    else:
        selected = render_variable_selector(st_obj, variables, key_prefix=key_prefix)
    if not selected:
        st_obj.info("请至少选择一个变量。")
        return

    # 表与图左右分栏（表 4 : 图 5，使图渲染高度接近 10 行表格高度）；
    # 表格受数据表高级选项的筛选/视图控制，默认显示前 10 行，
    # 不设固定高度（避免多余空行）。
    table_state = build_table_options(
        st.session_state, dataset, key_prefix=key_prefix
    )
    filtered = dataset.frame.loc[table_state["mask"]]
    overview_columns = st_obj.columns([4, 5])
    with overview_columns[0]:
        render_table_panel(
            st_obj,
            dataset,
            selected,
            filtered,
            table_state,
            key_prefix=key_prefix,
        )
    with overview_columns[1]:
        if filtered.empty:
            st_obj.info("筛选结果为空，暂无数据可绘制。")
        else:
            options, errors = build_chart_options(
                st.session_state, dataset, filtered, key_prefix=key_prefix
            )
            if errors:
                st_obj.warning("；".join(errors))
            draw_series_plot(
                st_obj, dataset, selected, filtered=filtered, **options
            )

    # 表与图下方：数据表高级选项与图形高级选项左右并排。
    # 注意：函数内部必须用全局 st_obj（main DG）调用容器方法，
    # Streamlit 的 with 栈只对 main DG 生效（容器方法忽略 with 栈）。
    option_columns = st_obj.columns(2)
    with option_columns[0]:
        render_table_options_expander(
            st_obj, dataset, selected, key_prefix=key_prefix
        )
    with option_columns[1]:
        render_chart_options_expander(st_obj, dataset, selected, key_prefix=key_prefix)


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


__all__ = [
    "DataOverview",
    "DataOverviewConfig",
    "create_data_overview",
]
