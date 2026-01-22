"""
Industrial Macro Operations Analysis Module
工业宏观运行分析模块 - 主入口文件
"""

# 导出本模块定义的函数
__all__ = ['render_macro_operations_analysis_with_data']

# 导入必要的模块
import streamlit as st
import pandas as pd
from typing import Any, Optional, List
import plotly.graph_objects as go
import logging

# 设置日志
logger = logging.getLogger(__name__)

# 导入统一的工具函数
from dashboard.analysis.industrial.utils import (
    get_weight_for_year,
    filter_data_from_2012,
    load_macro_data,
    load_weights_data,
    load_overall_industrial_data,
    filter_data_by_time_range,
    create_grouping_mappings,
    # 新增：优化的加权计算
    calculate_weighted_groups_optimized,
    # 新增：统一Fragment组件
    create_chart_with_time_selector_fragment,
    # 新增：统一下载工具
    create_excel_download_button,
    create_download_with_annotation,
    prepare_grouping_annotation_data,
    # 新增：统一图表创建器
    create_time_series_chart
)

# 导入拉动率计算模块
from dashboard.analysis.industrial.utils.contribution_calculator import calculate_all_contributions
from dashboard.analysis.industrial.utils.weighted_calculation import (
    build_weights_mapping,
    categorize_indicators
)
# 导入统一状态管理
from dashboard.analysis.industrial.utils import IndustrialStateManager
from dashboard.core.ui.utils.debug_helpers import debug_log
from dashboard.analysis.industrial.validation import validate_data_format, display_validation_result
from dashboard.analysis.industrial.constants import (
    TOTAL_INDUSTRIAL_GROWTH_COLUMN,
    STATE_NAMESPACE_INDUSTRIAL,
    STATE_KEY_MACRO_DATA,
    STATE_KEY_WEIGHTS_DATA,
    STATE_KEY_FILE_NAME,
    STATE_KEY_CONTRIBUTION_EXPORT,
    STATE_KEY_CONTRIBUTION_STREAM,
    STATE_KEY_CONTRIBUTION_INDUSTRY,
    STATE_KEY_CONTRIBUTION_INDIVIDUAL,
    STATE_KEY_TOTAL_GROWTH,
    STATE_KEY_VALIDATION_RESULT
)


def render_macro_operations_analysis_with_data(st_obj, df_macro: pd.DataFrame, df_weights: pd.DataFrame, uploaded_file=None):
    """
    使用预加载数据渲染分行业工业增加值同比增速分析

    Args:
        st_obj: Streamlit对象
        df_macro: 分行业工业增加值同比增速数据
        df_weights: 权重数据
        uploaded_file: 数据文件路径（用于加载总体工业增加值数据）
    """
    if df_macro is None or df_weights is None:
        st_obj.error("数据未正确加载，无法进行分行业工业增加值同比增速分析")
        return

    # Store the data in state
    IndustrialStateManager.set(STATE_KEY_MACRO_DATA, df_macro)
    IndustrialStateManager.set(STATE_KEY_WEIGHTS_DATA, df_weights)
    IndustrialStateManager.set(STATE_KEY_FILE_NAME, 'shared_data')

    # 定义目标列范围（第二列到最后一列）
    column_names = df_macro.columns.tolist()
    target_columns = []
    if len(column_names) > 1:
        target_columns = column_names[1:]
        target_columns = [col for col in target_columns if pd.notna(col)]

    # 计算拉动率（必须在显示图表之前完成）
    if target_columns:
        debug_log("开始计算拉动率", "INFO")
        try:
            # 使用传入的文件路径加载总体增速数据
            if uploaded_file is not None:
                df_overall = load_overall_industrial_data(uploaded_file)
                if df_overall is not None and len(df_overall.columns) > 0:
                    # 使用标准列名
                    if TOTAL_INDUSTRIAL_GROWTH_COLUMN in df_overall.columns:
                        debug_log(f"使用标准列名: {TOTAL_INDUSTRIAL_GROWTH_COLUMN}", "INFO")

                        # 合并总体增速到分行业数据
                        total_growth_series = df_overall[TOTAL_INDUSTRIAL_GROWTH_COLUMN]
                        df_with_total = pd.concat([total_growth_series, df_macro], axis=1)
                        df_with_total = df_with_total.dropna(how='all')

                        # 过滤2012年及以后
                        df_macro_filtered = filter_data_from_2012(df_with_total)
                        df_overall_filtered = filter_data_from_2012(df_overall)

                        # 计算拉动率（传入总体增速数据用于三大产业拉动率计算）
                        contribution_results = calculate_all_contributions(
                            df_macro_filtered, df_weights, df_overall_growth=df_overall_filtered
                        )

                        # 保存拉动率结果到状态
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_EXPORT, contribution_results['export_groups'])
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_STREAM, contribution_results['stream_groups'])
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDUSTRY, contribution_results['industry_groups'])
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDIVIDUAL, contribution_results['individual'])
                        IndustrialStateManager.set(STATE_KEY_TOTAL_GROWTH, contribution_results['total_growth'])
                        IndustrialStateManager.set(STATE_KEY_VALIDATION_RESULT, contribution_results['validation'])

                        debug_log(
                            f"拉动率计算完成，验证结果: {contribution_results['validation']['passed']}",
                            "INFO"
                        )
                    else:
                        debug_log(f"总体增速列 '{TOTAL_INDUSTRIAL_GROWTH_COLUMN}' 未找到", "WARNING")
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_EXPORT, None)
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_STREAM, None)
                        IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDUSTRY, None)
                else:
                    debug_log("总体增速数据加载失败或为空", "WARNING")
                    IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_EXPORT, None)
                    IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_STREAM, None)
                    IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDUSTRY, None)
            else:
                debug_log("未找到上传文件，无法加载总体增速", "WARNING")
                IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_EXPORT, None)
                IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_STREAM, None)
                IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDUSTRY, None)

        except Exception as e:
            debug_log(f"拉动率计算失败: {e}", "ERROR")
            import traceback
            debug_log(f"错误详情: {traceback.format_exc()}", "ERROR")
            # 即使拉动率计算失败，也不影响其他功能
            IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_EXPORT, None)
            IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_STREAM, None)
            IndustrialStateManager.set(STATE_KEY_CONTRIBUTION_INDUSTRY, None)

    # 添加标题

    # First chart - Three major industries contribution rate (拉动率)
    contribution_industry = IndustrialStateManager.get(STATE_KEY_CONTRIBUTION_INDUSTRY)
    if contribution_industry is not None and not contribution_industry.empty:
        chart1_data = contribution_industry
        chart1_vars = [col for col in contribution_industry.columns if col.startswith('三大产业_')]

        if chart1_vars:
            # 创建变量名映射，去掉"三大产业_"前缀
            var_name_mapping_1 = {var: var.replace('三大产业_', '') for var in chart1_vars}

            # 定义图表创建函数 - 使用统一的图表创建器
            def create_chart1(df, variables, time_range, custom_start_date, custom_end_date, var_mapping=None):
                return create_time_series_chart(
                    df=df,
                    variables=variables,
                    title="工业增加值同比增速拉动率:三大产业",
                    time_range=time_range,
                    custom_start_date=custom_start_date,
                    custom_end_date=custom_end_date,
                    var_name_mapping=var_mapping or {},
                    y_axis_title="拉动率(%)",
                    height=500,
                    bottom_margin=120
                )

            # 使用统一Fragment组件
            current_time_range_1, custom_start_1, custom_end_1 = create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="macro_chart1",
                state_namespace="monitoring.industrial.macro",
                chart_title=None,
                chart_creator_func=create_chart1,
                chart_data=chart1_data,
                chart_variables=chart1_vars,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set,
                additional_chart_kwargs={'var_mapping': var_name_mapping_1},
                variable_selector_config={
                    'options': chart1_vars,
                    'name_mapping': var_name_mapping_1
                }
            )

            # 数据下载功能 - 使用统一下载工具
            # 下载全部数据，不进行时间过滤
            download_df1 = chart1_data[chart1_vars].copy()

            # 重命名列，去掉前缀
            download_df1_renamed = download_df1.rename(columns=var_name_mapping_1)

            # 添加总体增速列作为第一列
            total_growth = IndustrialStateManager.get(STATE_KEY_TOTAL_GROWTH)
            if total_growth is not None:
                # 对齐索引并插入到第一列
                total_growth_aligned = total_growth.reindex(download_df1_renamed.index)
                download_df1_renamed.insert(0, '规模以上工业增加值:当月同比', total_growth_aligned)

            # 格式化索引为年-月-日格式
            download_df1_renamed.index = download_df1_renamed.index.strftime('%Y-%m-%d')

            # 获取权重数据用于分组注释
            df_weights = IndustrialStateManager.get(STATE_KEY_WEIGHTS_DATA)
            if df_weights is not None:
                # 创建三大产业分组映射
                from dashboard.analysis.industrial.utils.weighted_calculation import build_weights_mapping, categorize_indicators
                column_names = download_df1_renamed.columns.tolist()
                if len(column_names) > 1:
                    target_columns = [col for col in column_names[1:] if pd.notna(col)]
                    weights_mapping = build_weights_mapping(df_weights, target_columns)
                    _, _, industry_groups = categorize_indicators(weights_mapping)
                    annotation_df = prepare_grouping_annotation_data(df_weights, industry_groups, '三大产业')
                    create_download_with_annotation(
                        st_obj=st_obj,
                        data=download_df1_renamed,
                        file_name=f"三大产业分组_拉动率_全部",
                        annotation_data=annotation_df,
                        button_key="download_chart1"
                    )
            else:
                # 如果没有权重数据，提供简单下载
                create_excel_download_button(
                    st_obj=st_obj,
                    data=download_df1_renamed,
                    file_name=f"三大产业_拉动率_全部.xlsx",
                    button_key="download_chart1",
                    column_ratio=(1, 4)
                )
    else:
        st_obj.warning("三大产业拉动率数据未计算，请检查数据文件")

    # 添加横线分隔符
    st_obj.markdown("---")

    # Second chart - Export dependency groups (contribution mode only)
    contribution_export = IndustrialStateManager.get(STATE_KEY_CONTRIBUTION_EXPORT)
    if contribution_export is not None and not contribution_export.empty:
        chart2_data = contribution_export
        chart2_vars = [col for col in contribution_export.columns if col.startswith('出口依赖_')]

        if chart2_vars:
            # 创建变量名映射，去掉"出口依赖_"前缀
            var_name_mapping_2 = {var: var.replace('出口依赖_', '') for var in chart2_vars}

            # 定义图表创建函数 - 使用统一的图表创建器
            def create_chart2(df, variables, time_range, custom_start_date, custom_end_date):
                return create_time_series_chart(
                    df=df,
                    variables=variables,
                    title="工业增加值同比增速拉动率:分出口依赖行业",
                    time_range=time_range,
                    custom_start_date=custom_start_date,
                    custom_end_date=custom_end_date,
                    y_axis_title="拉动率(%)",
                    height=500,
                    bottom_margin=120
                )

            # 使用统一Fragment组件
            current_time_range_2, custom_start_2, custom_end_2 = create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="macro_chart2",
                state_namespace="monitoring.industrial.macro",
                chart_title=None,
                chart_creator_func=create_chart2,
                chart_data=chart2_data,
                chart_variables=chart2_vars,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set,
                variable_selector_config={
                    'options': chart2_vars,
                    'name_mapping': var_name_mapping_2
                }
            )

            # 数据下载功能 - 使用统一下载工具
            # 下载全部数据，不进行时间过滤
            download_df2 = chart2_data[chart2_vars].copy()

            # 添加总体增速列作为第一列
            total_growth = IndustrialStateManager.get(STATE_KEY_TOTAL_GROWTH)
            if total_growth is not None:
                # 对齐索引并插入到第一列
                total_growth_aligned = total_growth.reindex(download_df2.index)
                download_df2.insert(0, '规模以上工业增加值:当月同比', total_growth_aligned)

            # 格式化索引为年-月-日格式
            download_df2.index = download_df2.index.strftime('%Y-%m-%d')

            export_groups, _ = create_grouping_mappings(df_weights)
            annotation_df = prepare_grouping_annotation_data(df_weights, export_groups, '出口依赖')
            create_download_with_annotation(
                st_obj=st_obj,
                data=download_df2,
                file_name=f"出口依赖分组_拉动率_全部",
                annotation_data=annotation_df,
                button_key="download_chart2"
            )
    else:
        st_obj.warning("出口依赖拉动率数据未计算")

    # 添加横线分隔符
    st_obj.markdown("---")

    # Third chart - Upstream/downstream groups (contribution mode only)
    contribution_stream = IndustrialStateManager.get(STATE_KEY_CONTRIBUTION_STREAM)
    if contribution_stream is not None and not contribution_stream.empty:
        chart3_vars = [col for col in contribution_stream.columns if col.startswith('上中下游_')]

        # 按照指定顺序排序图例：上游XX、中游XX、下游XX
        def get_sort_key(col):
            # 提取列名中的行业类型
            industry_type = col.replace('上中下游_', '')

            # 按照上游、中游、下游的顺序排序
            if industry_type.startswith('上游'):
                return (0, industry_type)  # 上游排在最前
            elif industry_type.startswith('中游'):
                return (1, industry_type)  # 中游排在中间
            elif industry_type.startswith('下游'):
                return (2, industry_type)  # 下游排在最后
            else:
                return (3, industry_type)  # 未知类型排在最后

        chart3_vars = sorted(chart3_vars, key=get_sort_key)

        if chart3_vars:
            chart3_data = contribution_stream

            # 创建变量名映射，去掉"上中下游_"前缀
            var_name_mapping_3 = {var: var.replace('上中下游_', '') for var in chart3_vars}

            # 定义图表创建函数 - 使用统一的图表创建器
            def create_chart3(df, variables, time_range, custom_start_date, custom_end_date):
                return create_time_series_chart(
                    df=df,
                    variables=variables,
                    title="工业增加值同比增速拉动率:分上中下游行业",
                    time_range=time_range,
                    custom_start_date=custom_start_date,
                    custom_end_date=custom_end_date,
                    y_axis_title="拉动率(%)",
                    height=500,
                    bottom_margin=120
                )

            # 使用统一Fragment组件
            current_time_range_3, custom_start_3, custom_end_3 = create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="macro_chart3",
                state_namespace="monitoring.industrial.macro",
                chart_title=None,
                chart_creator_func=create_chart3,
                chart_data=chart3_data,
                chart_variables=chart3_vars,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set,
                variable_selector_config={
                    'options': chart3_vars,
                    'name_mapping': var_name_mapping_3
                }
            )

            # 数据下载功能 - 使用统一下载工具
            # 下载全部数据，不进行时间过滤
            download_df3 = chart3_data[chart3_vars].copy()

            # 添加总体增速列作为第一列
            total_growth = IndustrialStateManager.get(STATE_KEY_TOTAL_GROWTH)
            if total_growth is not None:
                # 对齐索引并插入到第一列
                total_growth_aligned = total_growth.reindex(download_df3.index)
                download_df3.insert(0, '规模以上工业增加值:当月同比', total_growth_aligned)

            # 格式化索引为年-月-日格式
            download_df3.index = download_df3.index.strftime('%Y-%m-%d')

            _, stream_groups = create_grouping_mappings(df_weights)
            annotation_df = prepare_grouping_annotation_data(df_weights, stream_groups, '上中下游')
            create_download_with_annotation(
                st_obj=st_obj,
                data=download_df3,
                file_name=f"上中下游分组_拉动率_全部",
                annotation_data=annotation_df,
                button_key="download_chart3"
            )
    else:
        st_obj.warning("上中下游拉动率数据未计算")

    # 添加横线分隔符
    st_obj.markdown("---")

    # 获取个体行业拉动率数据
    contribution_individual = IndustrialStateManager.get(STATE_KEY_CONTRIBUTION_INDIVIDUAL)

    if contribution_individual is not None and not contribution_individual.empty:
        # 获取权重数据
        df_weights = IndustrialStateManager.get(STATE_KEY_WEIGHTS_DATA)

        # 获取所有指标列表
        all_indicators = list(contribution_individual.columns)

        # 按三大产业分组排序指标
        weights_mapping = build_weights_mapping(df_weights, all_indicators)
        _, _, industry_groups = categorize_indicators(weights_mapping)

        # 按顺序：采矿业、制造业、电力热力燃气及水生产和供应业
        industry_order = ['采矿业', '制造业', '电力、热力、燃气及水生产和供应业']
        sorted_indicators = []
        for industry in industry_order:
            if industry in industry_groups:
                sorted_indicators.extend(industry_groups[industry])

        # 如果有指标未分类，添加到末尾
        for indicator in all_indicators:
            if indicator not in sorted_indicators:
                sorted_indicators.append(indicator)

        # 创建指标名称简化函数
        def simplify_indicator_name(name):
            """简化指标名称：去掉'规模以上工业增加值:'前缀和':当月同比'后缀"""
            simplified = name
            if simplified.startswith('规模以上工业增加值:'):
                simplified = simplified.replace('规模以上工业增加值:', '', 1)
            if simplified.endswith(':当月同比'):
                simplified = simplified.replace(':当月同比', '')
            return simplified

        # ==================== 月度变化分析 ====================
        # 检查数据是否足够（至少需要2个月）
        if len(contribution_individual.index) >= 2:
            # 获取最新月份和上个月的数据（兼容升序/降序排列）
            sorted_index = contribution_individual.index.sort_values(ascending=False)
            latest_month = sorted_index[0]  # 最新月份
            previous_month = sorted_index[1]  # 上个月

            # 显示动态标题
            st_obj.subheader(f"行业拉动率月度变化分析（{previous_month.strftime('%Y-%m')} -> {latest_month.strftime('%Y-%m')}）")

            # 最新月份和上个月的拉动率
            latest_contribution = contribution_individual.loc[latest_month]
            previous_contribution = contribution_individual.loc[previous_month]

            # 计算变化（最新月 - 上月）
            change_contribution = latest_contribution - previous_contribution

            # 生成统计表：按出口依赖类型和上中下游类型统计正负变化
            export_groups, stream_groups, _ = categorize_indicators(weights_mapping)

            # 统计出口依赖类型
            export_stats = []
            for category, indicators in export_groups.items():
                positive_count = sum(1 for ind in indicators if ind in change_contribution.index and change_contribution[ind] > 0)
                negative_count = sum(1 for ind in indicators if ind in change_contribution.index and change_contribution[ind] < 0)
                export_stats.append({
                    '类型': category,
                    '上拉行业数': positive_count,
                    '下拉行业数': negative_count
                })

            # 统计上中下游类型
            stream_stats = []
            for category, indicators in stream_groups.items():
                positive_count = sum(1 for ind in indicators if ind in change_contribution.index and change_contribution[ind] > 0)
                negative_count = sum(1 for ind in indicators if ind in change_contribution.index and change_contribution[ind] < 0)
                stream_stats.append({
                    '类型': category,
                    '上拉行业数': positive_count,
                    '下拉行业数': negative_count
                })

            # 创建DataFrame并显示
            if export_stats:
                st_obj.markdown("**按出口依赖类型统计**")
                export_stats_df = pd.DataFrame(export_stats)
                st_obj.dataframe(export_stats_df, width='stretch', hide_index=True)

            if stream_stats:
                st_obj.markdown("**按上中下游类型统计**")
                stream_stats_df = pd.DataFrame(stream_stats)
                st_obj.dataframe(stream_stats_df, width='stretch', hide_index=True)

            # 添加间距
            st_obj.markdown("")

            # 按变化值从大到小排序（横向图从上到下显示）
            change_contribution_sorted = change_contribution.sort_values(ascending=True)

            # 简化指标名称
            simplified_names = [simplify_indicator_name(name) for name in change_contribution_sorted.index]

            # 创建柱状图数据（横向）
            y_data = simplified_names  # Y轴为指标名称
            x_data = change_contribution_sorted.values.tolist()  # X轴为变化值

            # 设置柱子颜色：正值为红色，负值为绿色
            colors = ['red' if val > 0 else 'green' for val in x_data]

            # 创建横向柱状图
            fig_change = go.Figure()
            fig_change.add_trace(go.Bar(
                y=y_data,  # Y轴为指标名称
                x=x_data,  # X轴为变化值
                orientation='h',  # 横向柱状图
                marker_color=colors,
                name='拉动率变化',
                hovertemplate='%{y}<br>变化: %{x:.4f}百分点<extra></extra>'
            ))

            # 更新布局
            fig_change.update_layout(
                title=f"行业动率月度变化（{previous_month.strftime('%Y-%m')} -> {latest_month.strftime('%Y-%m')}）",
                xaxis_title="拉动率变化(%)",
                yaxis_title="",  # 不显示Y轴标题
                height=max(500, len(y_data) * 20),  # 根据指标数量动态调整高度
                hovermode='y',
                margin={'l': 250, 'r': 50, 't': 80, 'b': 50},  # 增加左边距以显示完整指标名
                yaxis={
                    'tickfont': {'size': 10}
                },
                showlegend=False
            )

            # 添加零线（横向图用vline）
            fig_change.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)

            # 显示图表
            st_obj.plotly_chart(fig_change, width='stretch')

            # 准备下载数据
            download_change_df = pd.DataFrame({
                '指标名称': change_contribution_sorted.index,
                f'{previous_month.strftime("%Y-%m")}拉动率': previous_contribution[change_contribution_sorted.index].values,
                f'{latest_month.strftime("%Y-%m")}拉动率': latest_contribution[change_contribution_sorted.index].values,
                '变化值': change_contribution_sorted.values
            })

            # 设置索引，转换为Excel友好格式
            download_change_df.set_index('指标名称', inplace=True)

            # 使用统一的Excel下载函数
            create_excel_download_button(
                st_obj=st_obj,
                data=download_change_df,
                file_name=f"行业拉动率月度变化_{latest_month.strftime('%Y%m')}",
                sheet_name="月度变化",
                button_label="下载数据",
                button_key="download_monthly_change",
                column_ratio=(1, 3),
                type="primary"
            )
        else:
            st_obj.info("数据不足，至少需要两个月的数据才能计算月度变化")

        # 添加横线分隔符
        st_obj.markdown("---")

        # ==================== 工业指标拉动率分析 ====================
        st_obj.subheader("行业拉动率历史分析")

        # 创建两列布局
        col1, col2 = st_obj.columns([3, 1])

        with col1:
            # 多选框：选择指标
            selected_indicators = st_obj.multiselect(
                "选择工业指标",
                options=sorted_indicators,
                default=sorted_indicators[:3] if len(sorted_indicators) >= 3 else sorted_indicators,
                key="indicator_selector",
                format_func=simplify_indicator_name  # 使用简化名称显示
            )

        with col2:
            # 单选下拉菜单：选择显示模式
            display_mode = st_obj.selectbox(
                "显示模式",
                options=["拉动率", "拉动率排名"],
                key="display_mode"
            )

        # 根据选择绘制图表
        if selected_indicators:
            if display_mode == "拉动率":
                # 绘制拉动率时间序列图
                chart_data = contribution_individual[selected_indicators]

                # 创建变量名映射（简化显示）
                var_name_mapping = {ind: simplify_indicator_name(ind) for ind in selected_indicators}

                fig = create_time_series_chart(
                    df=chart_data,
                    variables=selected_indicators,
                    title="行业拉动率历史分析",
                    time_range="全部",
                    y_axis_title="拉动率(%)",
                    height=500,
                    bottom_margin=150,
                    var_name_mapping=var_name_mapping  # 使用简化名称
                )
                st_obj.plotly_chart(fig, width='stretch')

            else:  # 拉动率排名
                # 计算排名（按绝对值排名：ascending=False表示绝对值从大到小排序，绝对值最大排名1）
                rank_df = contribution_individual.abs().rank(axis=1, method='min', ascending=False)
                chart_data = rank_df[selected_indicators]

                # 创建变量名映射（简化显示）
                var_name_mapping = {ind: simplify_indicator_name(ind) for ind in selected_indicators}

                fig = create_time_series_chart(
                    df=chart_data,
                    variables=selected_indicators,
                    title="工业指标拉动率排名时间序列",
                    time_range="全部",
                    y_axis_title="排名（1=拉动率绝对值最大）",
                    height=500,
                    bottom_margin=150,
                    var_name_mapping=var_name_mapping  # 使用简化名称
                )

                # 排名图需要倒置Y轴（1在上，41在下）
                fig.update_yaxes(autorange='reversed')
                st_obj.plotly_chart(fig, width='stretch')
        else:
            st_obj.info("请至少选择一个工业指标")

        # 添加下载按钮（下载所有指标的拉动率和排名，不受多选框筛选限制）
        # 准备拉动率数据（所有指标，主sheet，保留索引）
        download_df_contribution = contribution_individual.copy()
        download_df_contribution.index = download_df_contribution.index.strftime('%Y-%m-%d')
        download_df_contribution.index.name = '日期'  # 设置索引名，保存时会作为列名

        # 准备拉动率排名数据（按绝对值排名，所有指标，额外sheet，需要reset_index将日期转为列）
        rank_df = contribution_individual.abs().rank(axis=1, method='min', ascending=False)
        download_df_rank = rank_df.copy()
        download_df_rank.index = download_df_rank.index.strftime('%Y-%m-%d')
        download_df_rank.index.name = '日期'

        # 将排名数据的索引转为普通列（因为additional_sheets使用index=False）
        download_df_rank_with_date = download_df_rank.reset_index()

        # 使用统一的Excel下载函数（包含两个sheet）
        create_excel_download_button(
            st_obj=st_obj,
            data=download_df_contribution,
            file_name=f"工业指标拉动率_全部指标",
            sheet_name="拉动率",
            additional_sheets={"拉动率排名": download_df_rank_with_date},
            button_label="下载数据",
            button_key="download_selected_contributions",
            column_ratio=(1, 3),
            type="primary"
        )

    else:
        st_obj.info("拉动率数据未计算，请确保已上传数据文件")



