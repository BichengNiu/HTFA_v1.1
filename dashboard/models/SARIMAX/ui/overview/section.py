"""数据概览环节编排：上传 → 数据集缓存 → 选择 → 表与图分栏 → 高级选项。

数据流：
shared_dataset 上传/工作表 → ModelingDataset（指纹缓存）
  ├─ selectors：变量选择
  ├─ table_panel：筛选 → 预览表 / 统计量
  └─ chart_panel：5-tab 状态 → build_chart_options → Ts plot_series
"""

from __future__ import annotations

import streamlit as st

from dashboard.core.ui.utils.shared_dataset import (
    get_shared_dataset_data,
    get_shared_dataset_fingerprint,
    get_shared_dataset_name,
    get_shared_dataset_sheet,
    get_shared_dataset_sheets,
    render_shared_dataset_uploader,
)
from dashboard.models.SARIMAX.core.data_loader import (
    build_modeling_dataset,
    numeric_variable_names,
)
from dashboard.models.SARIMAX.core.overview.options import (
    build_chart_options,
    build_table_options,
)
from dashboard.models.SARIMAX.ui.overview.chart_options_tabs import (
    render_chart_options_expander,
)
from dashboard.models.SARIMAX.ui.overview.chart_panel import draw_series_plot
from dashboard.models.SARIMAX.ui.overview.selectors import (
    on_sheet_change,
    render_variable_selector,
)
from dashboard.models.SARIMAX.ui.overview.table_panel import (
    render_table_options_expander,
    render_table_panel,
)
from dashboard.models.SARIMAX.ui.state import (
    WIDGET_KEYS,
    clear_fit_results,
    clear_widget_state,
    state,
)


def render_data_overview_section(st_obj) -> None:
    """展示共享数据集并绘制所选变量的时间序列预览图。

    第一行：数据上传组件独占一行；
    第二行：工作表选择（左）与变量选择（右）并排；
    预览表与时间序列图都受「数据表高级选项」的筛选条件驱动。
    """
    st_obj.markdown("#### ① 数据概览")
    render_shared_dataset_uploader(st_obj, compact=True)

    data = get_shared_dataset_data()
    if data is None:
        st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
        return

    fingerprint = get_shared_dataset_fingerprint()
    dataset = state.get("dataset")
    if dataset is None or dataset.fingerprint != fingerprint:
        try:
            dataset = build_modeling_dataset(
                data,
                get_shared_dataset_name(),
                fingerprint,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据解析边界
            st_obj.error(f"数据集校验失败：{exc}")
            return
        state.set("dataset", dataset)
        state.set("target_variable", None)
        state.set("exog_variables", ())
        clear_fit_results()
        clear_widget_state(st_obj, WIDGET_KEYS[1:])

    variables = numeric_variable_names(dataset.frame)
    if not variables:
        st_obj.error("数据中没有可用的数值型变量。")
        return

    # 第二行：工作表选择（左）与变量选择（右）并排。工作表选择在
    # dataset 构建之后渲染，避免 clear_widget_state 清掉其选中状态。
    sheets = get_shared_dataset_sheets()
    if sheets and len(sheets) > 1:
        selection_columns = st_obj.columns(2, vertical_alignment="center")
        with selection_columns[0]:
            if (
                "sarimax_preview_sheet" in st.session_state
                and st.session_state["sarimax_preview_sheet"] not in sheets
            ):
                st.session_state["sarimax_preview_sheet"] = sheets[0]
            current_sheet = get_shared_dataset_sheet()
            st_obj.selectbox(
                "选择工作表",
                options=sheets,
                index=sheets.index(current_sheet)
                if current_sheet in sheets
                else 0,
                key="sarimax_preview_sheet",
                on_change=on_sheet_change,
                help="Excel 文件包含多个工作表时，切换后重新加载该表数据。",
            )
        with selection_columns[1]:
            selected = render_variable_selector(st_obj, variables)
    else:
        selected = render_variable_selector(st_obj, variables)
    if not selected:
        st_obj.info("请至少选择一个变量。")
        return

    # 表与图左右分栏（表 4 : 图 5，使图渲染高度接近 10 行表格高度）；
    # 表格受数据表高级选项的筛选/视图控制，默认显示前 10 行，
    # 不设固定高度（避免多余空行）。
    table_state = build_table_options(st.session_state, dataset)
    filtered = dataset.frame.loc[table_state["mask"]]
    overview_columns = st_obj.columns([4, 5])
    with overview_columns[0]:
        render_table_panel(st_obj, dataset, selected, filtered, table_state)
    with overview_columns[1]:
        if filtered.empty:
            st_obj.info("筛选结果为空，暂无数据可绘制。")
        else:
            options, errors = build_chart_options(st.session_state, dataset, filtered)
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
        render_table_options_expander(st_obj, dataset, selected)
    with option_columns[1]:
        render_chart_options_expander(st_obj, dataset, selected)


__all__ = ["render_data_overview_section"]
