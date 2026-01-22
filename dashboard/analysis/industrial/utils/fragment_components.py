"""
统一的Fragment组件
Unified Fragment Components

目标：消除6个几乎完全相同的fragment函数（约240行重复）
遵循DRY原则：提取通用的fragment逻辑
"""

import streamlit as st
import pandas as pd
from typing import Tuple, Optional, List, Callable, Dict, Any

from dashboard.analysis.industrial.utils.chart_config import TIME_RANGE_OPTIONS, get_time_range_index


def render_time_range_selector(
    st_obj,
    key_prefix: str,
    default_value: str = "3年",
    label_visibility: str = "collapsed"
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    渲染时间范围选择器（不带fragment装饰器）

    Args:
        st_obj: Streamlit对象
        key_prefix: 控件key前缀（用于确保唯一性）
        default_value: 默认时间范围
        label_visibility: 标签可见性

    Returns:
        (time_range, custom_start_date, custom_end_date) 元组
    """
    # 时间范围选择
    default_index = get_time_range_index(default_value)

    time_range = st_obj.radio(
        "时间范围",
        TIME_RANGE_OPTIONS,
        index=default_index,
        horizontal=True,
        key=f"{key_prefix}_time_range_selector",
        label_visibility=label_visibility
    )

    # 自定义日期范围输入
    custom_start_date = None
    custom_end_date = None

    if time_range == "自定义":
        col_start, col_end = st_obj.columns([1, 1])
        with col_start:
            custom_start_date = st_obj.text_input(
                "开始年月",
                placeholder="2020-01",
                key=f"{key_prefix}_custom_start_date"
            )
        with col_end:
            custom_end_date = st_obj.text_input(
                "结束年月",
                placeholder="2024-12",
                key=f"{key_prefix}_custom_end_date"
            )

    return time_range, custom_start_date, custom_end_date


def create_chart_with_time_selector_fragment(
    st_obj,
    chart_id: str,
    state_namespace: str,
    chart_title: Optional[str],
    chart_creator_func: Callable,
    chart_data: pd.DataFrame,
    chart_variables: List[str],
    get_state_func: Callable[[str, Any], Any],
    set_state_func: Callable[[str, Any], None],
    additional_chart_kwargs: Optional[Dict[str, Any]] = None,
    variable_selector_config: Optional[Dict[str, Any]] = None
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    创建带时间选择器的图表Fragment

    这个函数统一了以下重复代码：
    - macro_operations.py 中的3个fragment（约120行）
    - enterprise_operations.py 中的3个fragment（约120行）

    Args:
        st_obj: Streamlit对象
        chart_id: 图表唯一ID
        state_namespace: 状态管理命名空间
        chart_title: 图表标题（Markdown格式，如 "#### 图表标题"）
        chart_creator_func: 图表创建函数
        chart_data: 图表数据
        chart_variables: 图表变量列表
        get_state_func: 获取状态函数
        set_state_func: 设置状态函数
        additional_chart_kwargs: 传递给图表创建函数的额外参数

    Returns:
        (time_range, custom_start_date, custom_end_date) 元组
    """
    @st_obj.fragment
    def render():
        # 显示图表标题（如果提供）
        if chart_title:
            st_obj.markdown(chart_title)

        # 创建两行布局（如果需要变量选择器）
        if variable_selector_config:
            # 第一行：左侧时间选择器，右侧线条选择器标题和复选框在同一行
            col_time, col_vars = st_obj.columns([1, 1])

            # 左列：时间选择器
            with col_time:
                # 获取当前时间范围状态
                state_key = f'{state_namespace}.time_range_{chart_id}'
                current_time_range = get_state_func(state_key, "3年")

                # 渲染时间范围选择器
                time_range, custom_start, custom_end = render_time_range_selector(
                    st_obj,
                    key_prefix=f"{chart_id}_fragment",
                    default_value=current_time_range
                )

                # 更新状态（仅在值改变时）
                if time_range != current_time_range:
                    set_state_func(state_key, time_range)

            # 右列：变量复选框
            selected_variables = []
            with col_vars:
                var_options = variable_selector_config['options']
                var_mapping = variable_selector_config.get('name_mapping', {})
                default_values = variable_selector_config.get('default_values', var_options)

                # 创建水平排列的复选框
                var_cols = st_obj.columns(len(var_options))

                # 显示复选框
                for idx, var in enumerate(var_options):
                    with var_cols[idx]:
                        if st_obj.checkbox(
                            var_mapping.get(var, var),
                            value=(var in default_values),
                            key=f"{chart_id}_var_checkbox_{idx}"
                        ):
                            selected_variables.append(var)
        else:
            # 没有变量选择器，只显示时间选择器
            # 获取当前时间范围状态
            state_key = f'{state_namespace}.time_range_{chart_id}'
            current_time_range = get_state_func(state_key, "3年")

            # 渲染时间范围选择器
            time_range, custom_start, custom_end = render_time_range_selector(
                st_obj,
                key_prefix=f"{chart_id}_fragment",
                default_value=current_time_range
            )

            # 更新状态（仅在值改变时）
            if time_range != current_time_range:
                set_state_func(state_key, time_range)

            selected_variables = chart_variables

        # 检查是否有选中的变量
        if not selected_variables:
            st_obj.warning("至少选择一个指标")
        else:
            # 准备图表创建函数的参数（使用选中的变量）
            chart_kwargs = {
                'df': chart_data,
                'variables': selected_variables,
                'time_range': time_range,
                'custom_start_date': custom_start,
                'custom_end_date': custom_end
            }

            # 添加额外参数
            if additional_chart_kwargs:
                chart_kwargs.update(additional_chart_kwargs)

            # 创建并显示图表
            try:
                fig = chart_creator_func(**chart_kwargs)
                if fig:
                    st_obj.plotly_chart(
                        fig,
                        width='stretch',
                        key=f"{chart_id}_chart_fragment"
                    )
                else:
                    st_obj.warning("图表数据不足或不可用，无法生成图表")
            except Exception as e:
                st_obj.error(f"创建图表时出错: {e}")
                import traceback
                st_obj.code(traceback.format_exc())

        return time_range, custom_start, custom_end

    return render()


def render_chart_group_with_download(
    st_obj,
    chart_id: str,
    state_namespace: str,
    chart_title: Optional[str],
    chart_creator_func: Callable,
    chart_data: pd.DataFrame,
    chart_variables: List[str],
    get_state_func: Callable,
    set_state_func: Callable,
    download_data_func: Callable,
    download_file_prefix: str,
    additional_chart_kwargs: Optional[Dict[str, Any]] = None
) -> None:
    """
    渲染完整的图表组（图表 + 时间选择器 + 下载按钮）

    Args:
        st_obj: Streamlit对象
        chart_id: 图表唯一ID
        state_namespace: 状态管理命名空间
        chart_title: 图表标题
        chart_creator_func: 图表创建函数
        chart_data: 图表数据
        chart_variables: 图表变量列表
        get_state_func: 获取状态函数
        set_state_func: 设置状态函数
        download_data_func: 下载数据处理函数（接收filtered_df和time_range，返回要下载的数据）
        download_file_prefix: 下载文件名前缀
        additional_chart_kwargs: 传递给图表创建函数的额外参数
    """
    # 渲染图表和时间选择器
    time_range, custom_start, custom_end = create_chart_with_time_selector_fragment(
        st_obj=st_obj,
        chart_id=chart_id,
        state_namespace=state_namespace,
        chart_title=chart_title,
        chart_creator_func=chart_creator_func,
        chart_data=chart_data,
        chart_variables=chart_variables,
        get_state_func=get_state_func,
        set_state_func=set_state_func,
        additional_chart_kwargs=additional_chart_kwargs
    )

    # 准备下载数据
    from dashboard.analysis.industrial.utils.time_filter import filter_data_by_time_range

    filtered_df = filter_data_by_time_range(
        chart_data[chart_variables] if chart_variables else chart_data,
        time_range,
        custom_start,
        custom_end
    )

    if not filtered_df.empty and download_data_func:
        try:
            download_data = download_data_func(filtered_df, time_range)

            if download_data:
                # 导入下载工具（延迟导入避免循环依赖）
                from dashboard.analysis.industrial.utils.download_utils import create_excel_download_button

                create_excel_download_button(
                    st_obj=st_obj,
                    data=download_data if isinstance(download_data, pd.DataFrame) else filtered_df,
                    file_name=f"{download_file_prefix}_{time_range}",
                    button_key=f"download_{chart_id}"
                )
        except Exception as e:
            st_obj.warning(f"准备下载数据时出错: {e}")


def render_multiple_charts_with_separators(
    st_obj,
    chart_configs: List[Dict[str, Any]],
    separator: str = "---"
) -> None:
    """
    渲染多个图表，并在它们之间添加分隔符

    Args:
        st_obj: Streamlit对象
        chart_configs: 图表配置列表，每个配置是一个字典，包含render_chart_group_with_download的参数
        separator: 分隔符（Markdown格式）
    """
    for i, config in enumerate(chart_configs):
        # 渲染图表
        render_chart_group_with_download(st_obj=st_obj, **config)

        # 添加分隔符（最后一个图表后不加）
        if i < len(chart_configs) - 1 and separator:
            st_obj.markdown(separator)
