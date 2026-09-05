"""
Industrial Macro Operations Analysis Module
工业宏观运行分析模块 - 主入口文件
"""

# 导出本模块定义的函数
__all__ = ['render_macro_operations_analysis_with_data']

# 导入必要的模块
import pandas as pd
import plotly.graph_objects as go
import logging

from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom
# 设置日志
logger = logging.getLogger(__name__)

# 导入统一的工具函数
from htfa.monitoring.industrial.utils import (
    filter_data_from_2012,
    load_overall_industrial_data,
    create_grouping_mappings,
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
from htfa.monitoring.industrial.utils.contribution_calculator import calculate_all_contributions
from htfa.monitoring.industrial.utils.weighted_calculation import (
    build_weights_mapping,
    categorize_indicators
)
# 导入统一状态管理
from htfa.monitoring.industrial.utils.state_manager import industrial_state
from htfa.ui_shared.debug_helpers import debug_log
from htfa.monitoring.industrial.constants import (
    TOTAL_INDUSTRIAL_GROWTH_COLUMN,
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


def _compute_contributions(df_macro, df_weights, target_columns, uploaded_file):
    """计算拉动率并保存到状态"""
    if not target_columns:
        return

    debug_log("开始计算拉动率", "INFO")
    try:
        if uploaded_file is None:
            debug_log("未找到上传文件，无法加载总体增速", "WARNING")
            _clear_contribution_states()
            return

        df_overall = load_overall_industrial_data(uploaded_file)
        if df_overall is None or len(df_overall.columns) == 0:
            debug_log("总体增速数据加载失败或为空", "WARNING")
            _clear_contribution_states()
            return

        if TOTAL_INDUSTRIAL_GROWTH_COLUMN not in df_overall.columns:
            debug_log(f"总体增速列 '{TOTAL_INDUSTRIAL_GROWTH_COLUMN}' 未找到", "WARNING")
            _clear_contribution_states()
            return

        debug_log(f"使用标准列名: {TOTAL_INDUSTRIAL_GROWTH_COLUMN}", "INFO")
        total_growth_series = df_overall[TOTAL_INDUSTRIAL_GROWTH_COLUMN]
        df_with_total = pd.concat([total_growth_series, df_macro], axis=1).dropna(how='all')

        df_macro_filtered = filter_data_from_2012(df_with_total)
        df_overall_filtered = filter_data_from_2012(df_overall)

        contribution_results = calculate_all_contributions(
            df_macro_filtered, df_weights, df_overall_growth=df_overall_filtered
        )

        industrial_state.set(STATE_KEY_CONTRIBUTION_EXPORT, contribution_results['export_groups'])
        industrial_state.set(STATE_KEY_CONTRIBUTION_STREAM, contribution_results['stream_groups'])
        industrial_state.set(STATE_KEY_CONTRIBUTION_INDUSTRY, contribution_results['industry_groups'])
        industrial_state.set(STATE_KEY_CONTRIBUTION_INDIVIDUAL, contribution_results['individual'])
        industrial_state.set(STATE_KEY_TOTAL_GROWTH, contribution_results['total_growth'])
        industrial_state.set(STATE_KEY_VALIDATION_RESULT, contribution_results['validation'])

        debug_log(f"拉动率计算完成，验证结果: {contribution_results['validation']['passed']}", "INFO")

    except Exception as e:
        debug_log(f"拉动率计算失败: {e}", "ERROR")
        import traceback
        debug_log(f"错误详情: {traceback.format_exc()}", "ERROR")
        _clear_contribution_states()


def _clear_contribution_states():
    """清除拉动率状态"""
    industrial_state.set(STATE_KEY_CONTRIBUTION_EXPORT, None)
    industrial_state.set(STATE_KEY_CONTRIBUTION_STREAM, None)
    industrial_state.set(STATE_KEY_CONTRIBUTION_INDUSTRY, None)


def _render_contribution_chart(st_obj, state_key, prefix, chart_id, chart_title, grouping_label, df_weights):
    """渲染单个拉动率图表区块（三大产业/出口依赖/上中下游）"""
    contribution_data = industrial_state.get(state_key)
    if contribution_data is None or contribution_data.empty:
        st_obj.warning(f"{grouping_label}拉动率数据未计算")
        return

    chart_vars = [col for col in contribution_data.columns if col.startswith(prefix)]
    if not chart_vars:
        return

    var_name_mapping = {var: var.replace(prefix, '') for var in chart_vars}

    def _create_chart(df, variables, time_range, custom_start_date, custom_end_date, var_mapping=None):
        return create_time_series_chart(
            df=df, variables=variables,
            title=chart_title, time_range=time_range,
            custom_start_date=custom_start_date, custom_end_date=custom_end_date,
            var_name_mapping=var_mapping or var_name_mapping,
            y_axis_title="拉动率(%)", height=500, bottom_margin=120
        )

    create_chart_with_time_selector_fragment(
        st_obj=st_obj, chart_id=chart_id,
        state_namespace="monitoring.industrial.macro",
        chart_title=None, chart_creator_func=_create_chart,
        chart_data=contribution_data, chart_variables=chart_vars,
        get_state_func=industrial_state.get,
        set_state_func=industrial_state.set,
        additional_chart_kwargs={'var_mapping': var_name_mapping},
        variable_selector_config={'options': chart_vars, 'name_mapping': var_name_mapping}
    )

    # 下载功能
    download_df = contribution_data[chart_vars].copy()
    total_growth = industrial_state.get(STATE_KEY_TOTAL_GROWTH)
    if total_growth is not None:
        total_growth_aligned = total_growth.reindex(download_df.index)
        download_df.insert(0, '规模以上工业增加值:当月同比', total_growth_aligned)
    download_df.index = download_df.index.strftime('%Y-%m-%d')

    if df_weights is not None:
        from htfa.monitoring.industrial.utils.weighted_calculation import build_weights_mapping, categorize_indicators
        column_names = download_df.columns.tolist()
        target_cols = [col for col in column_names[1:] if pd.notna(col)] if len(column_names) > 1 else []
        if target_cols:
            weights_mapping = build_weights_mapping(df_weights, target_cols)
            if grouping_label == '三大产业':
                _, _, groups = categorize_indicators(weights_mapping)
            elif grouping_label == '出口依赖':
                groups, _ = create_grouping_mappings(df_weights)
            else:
                _, groups = create_grouping_mappings(df_weights)
            annotation_df = prepare_grouping_annotation_data(df_weights, groups)
            create_download_with_annotation(
                st_obj=st_obj, data=download_df,
                file_name=f"{grouping_label}分组_拉动率_全部",
                annotation_data=annotation_df, button_key=f"download_{chart_id}"
            )
            return

    create_excel_download_button(
        st_obj=st_obj, data=download_df,
        file_name=f"{grouping_label}_拉动率_全部.xlsx",
        button_key=f"download_{chart_id}", column_ratio=(1, 4)
    )
def render_macro_operations_analysis_with_data(st_obj, df_macro: pd.DataFrame, df_weights: pd.DataFrame, uploaded_file=None):
    """使用预加载数据渲染分行业工业增加值同比增速分析"""
    if df_macro is None or df_weights is None:
        st_obj.error("数据未正确加载，无法进行分行业工业增加值同比增速分析")
        return

    industrial_state.set(STATE_KEY_MACRO_DATA, df_macro)
    industrial_state.set(STATE_KEY_WEIGHTS_DATA, df_weights)
    industrial_state.set(STATE_KEY_FILE_NAME, 'shared_data')

    column_names = df_macro.columns.tolist()
    target_columns = [col for col in column_names[1:] if pd.notna(col)] if len(column_names) > 1 else []

    _compute_contributions(df_macro, df_weights, target_columns, uploaded_file)

    # 三大产业拉动率图表
    _render_contribution_chart(
        st_obj, STATE_KEY_CONTRIBUTION_INDUSTRY, '三大产业_', 'macro_chart1',
        "工业增加值同比增速拉动率:三大产业", '三大产业', df_weights
    )
    st_obj.markdown("---")

    # 出口依赖拉动率图表
    _render_contribution_chart(
        st_obj, STATE_KEY_CONTRIBUTION_EXPORT, '出口依赖_', 'macro_chart2',
        "工业增加值同比增速拉动率:分出口依赖行业", '出口依赖', df_weights
    )
    st_obj.markdown("---")

    # 上中下游拉动率图表
    _render_contribution_chart(
        st_obj, STATE_KEY_CONTRIBUTION_STREAM, '上中下游_', 'macro_chart3',
        "工业增加值同比增速拉动率:分上中下游行业", '上中下游', df_weights
    )
    st_obj.markdown("---")

    # 个体行业拉动率分析
    _render_individual_contribution_analysis(st_obj, df_weights)

def _render_individual_contribution_analysis(st_obj, df_weights):
    """渲染个体行业拉动率分析（月度变化+历史分析）"""
    contribution_individual = industrial_state.get(STATE_KEY_CONTRIBUTION_INDIVIDUAL)

    if contribution_individual is None or contribution_individual.empty:
        st_obj.info("拉动率数据未计算，请确保已上传数据文件")
        return

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
        st_obj.plotly_chart(
            place_chart_legend_at_bottom(fig_change),
            width='stretch',
        )

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
            st_obj.plotly_chart(
                place_chart_legend_at_bottom(fig),
                width='stretch',
            )

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
            st_obj.plotly_chart(
                place_chart_legend_at_bottom(fig),
                width='stretch',
            )
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
        file_name="工业指标拉动率_全部指标",
        sheet_name="拉动率",
        additional_sheets={"拉动率排名": download_df_rank_with_date},
        button_label="下载数据",
        button_key="download_selected_contributions",
        column_ratio=(1, 3),
        type="primary"
    )
