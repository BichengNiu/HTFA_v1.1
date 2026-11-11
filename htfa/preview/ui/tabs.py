# -*- coding: utf-8 -*-
"""
Preview模块统一Tab组件
通过配置驱动,一个函数支持所有频率的数据展示
包含时间序列Tab和数据概览Tab
"""

from htfa.preview.processing.statistics import calculate_indicator_statistics
import pandas as pd
from datetime import datetime
import io

from htfa.preview.processing.config import FREQUENCY_CONFIGS, UI_TEXT
from htfa.preview.processing.calculators import calculate_summary
from htfa.preview.ui.plotting import plot_indicator
from htfa.preview.ui.components import create_filter_ui, display_summary_table
from htfa.ui_shared.session_state import get_economic_workbook_state
from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom


def calculate_indicator_statistics_cached(all_data_dict, indicator_maps):
    """缓存版本的统计计算（简化版：使用Streamlit自动缓存）

    优化：移除手动MD5缓存键，Streamlit会自动基于参数生成缓存键

    Args:
        all_data_dict: {频率名: DataFrame}字典
        indicator_maps: 包含industry、type、clean_industry的映射字典

    Returns:
        dict: 统计结果字典
    """
    # 调用原始的统计计算函数
    return calculate_indicator_statistics(all_data_dict, indicator_maps)






def _create_summary_dataframe(stats_dict, column_names):
    """创建统计摘要DataFrame（私有辅助函数）"""
    df = pd.DataFrame(
        list(stats_dict.items()),
        columns=column_names
    )
    df = df.sort_values(column_names[1], ascending=False)

    # 添加合计行
    total_row = pd.DataFrame(
        [['合计', df[column_names[1]].sum()]],
        columns=column_names
    )
    df = pd.concat([df, total_row], ignore_index=True)

    return df


def render_statistics_summary(stats, st_module):
    """渲染统计摘要（行业、类型、频率统计）

    Args:
        stats: calculate_indicator_statistics返回的统计字典
        st_module: streamlit模块
    """
    col1, col2, col3 = st_module.columns(3)

    # 渲染行业统计
    with col1:
        st_module.markdown("**行业统计**")
        industry_df = _create_summary_dataframe(
            stats['industry_stats'],
            ['行业名称', '指标数量']
        )
        st_module.dataframe(industry_df, width='stretch', hide_index=True)

    # 渲染类型统计
    with col2:
        st_module.markdown("**类型统计**")
        type_df = _create_summary_dataframe(
            stats['type_stats'],
            ['指标类型', '指标数量']
        )
        st_module.dataframe(type_df, width='stretch', hide_index=True)

    # 渲染频率统计
    with col3:
        st_module.markdown("**频率统计**")
        if stats['frequency_stats']:
            frequency_df = _create_summary_dataframe(
                stats['frequency_stats'],
                ['数据频率', '指标数量']
            )
            st_module.dataframe(frequency_df, width='stretch', hide_index=True)
        else:
            st_module.warning("无频率数据")


def render_indicator_details(indicator_details, st_module):
    """渲染指标详情表格及下载功能

    Args:
        indicator_details: 指标详情列表
        st_module: streamlit模块
    """
    if not indicator_details:
        st_module.warning("未找到有效的指标数据")
        return

    # 转换为DataFrame
    detailed_df = pd.DataFrame(indicator_details)

    # 添加缺失率数值列用于排序（将"5.2%"转换为5.2）
    detailed_df['缺失率_数值'] = detailed_df['缺失率'].str.replace('%', '').astype(float)

    # 排序：按缺失率（由低到高）、行业、类型、频率
    detailed_df = detailed_df.sort_values(
        by=['缺失率_数值', '行业', '类型', '频率'],
        ascending=[True, True, True, True]
    )

    # 删除临时排序列
    detailed_df = detailed_df.drop(columns=['缺失率_数值'])

    # 重置索引并添加序号列（从1开始）
    detailed_df = detailed_df.reset_index(drop=True)
    detailed_df.insert(0, '序号', range(1, len(detailed_df) + 1))

    # 显示表格（隐藏默认index）
    st_module.dataframe(detailed_df, width='stretch', hide_index=True)

    # 下载指标详情按钮
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        detailed_df.to_excel(writer, sheet_name='指标详情', index=False)

        # 设置列宽自适应
        worksheet = writer.sheets['指标详情']
        for column in worksheet.columns:
            max_length = max(len(str(cell.value)) for cell in column if cell.value)
            worksheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 50)

    st_module.download_button(
        label="下载指标详情",
        data=buffer.getvalue(),
        file_name=f"指标详情_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type = "primary"
    )


def _group_indicators_by_industry_and_type(indicators, industry_map, type_map):
    """按行业和类型分组指标，并按数量降序排序

    Args:
        indicators: 指标列表
        industry_map: 指标->行业映射
        type_map: 指标->类型映射

    Returns:
        dict: {行业名: {类型名: [指标列表]}}，行业和类型都按指标数量降序排列
    """
    from collections import defaultdict

    # Step 1: 按行业分组
    industry_groups = defaultdict(list)
    for ind in indicators:
        industry = industry_map.get(ind, "未分类")
        industry_groups[industry].append(ind)

    # Step 2: 行业按指标数量降序排序
    sorted_industries = sorted(
        industry_groups.keys(),
        key=lambda x: len(industry_groups[x]),
        reverse=True
    )

    # Step 3: 每个行业内按类型分组，类型按数量降序
    result = {}
    for industry in sorted_industries:
        type_groups = defaultdict(list)
        for ind in industry_groups[industry]:
            ind_type = type_map.get(ind, "未分类")
            type_groups[ind_type].append(ind)

        # 类型按指标数量降序
        sorted_types = sorted(
            type_groups.keys(),
            key=lambda x: len(type_groups[x]),
            reverse=True
        )

        result[industry] = {t: sorted(type_groups[t]) for t in sorted_types}

    return result


def display_time_series_tab(
    st_module,
    frequency,
    *,
    state_namespace: str = "economic_workbook",
):
    """通用的时间序列数据Tab

    通过频率参数和配置驱动,支持周度/月度/日度/旬度/年度所有频率

    Args:
        st_module: Streamlit模块
        frequency: 数据频率 ('weekly'/'monthly'/'daily'/'ten_day'/'yearly')
    """
    # 1. 获取配置
    config = FREQUENCY_CONFIGS[frequency]

    # 2. 获取数据（直接从session_state获取）
    df = get_economic_workbook_state(config.df_key, namespace=state_namespace)

    if df is None or df.empty:
        st_module.info(config.empty_message)
        return

    # 3. 获取行业和映射数据（直接从session_state获取）
    industries = get_economic_workbook_state(
        config.industries_key,
        [],
        namespace=state_namespace,
    )
    indicator_type_map = get_economic_workbook_state(
        'indicator_type_map',
        {},
        namespace=state_namespace,
    )
    indicator_industry_map = get_economic_workbook_state(
        'indicator_industry_map',
        {},
        namespace=state_namespace,
    )

    # 4. 创建筛选UI
    selected_industry, selected_type, filtered_indicators, display_name = \
        create_filter_ui(
            st=st_module,
            industries=industries,
            df=df,
            indicator_type_map=indicator_type_map,
            indicator_industry_map=indicator_industry_map,
            key_prefix=f"{state_namespace}.{config.english_name}"
        )

    if not filtered_indicators:
        st_module.warning(UI_TEXT['no_data_warning'].format(display_name))
        return

    # 5. 显示摘要表
    st_module.markdown(f"**{display_name} - {config.display_name}数据摘要**")

    # 计算摘要（使用Streamlit内置缓存，自动处理缓存逻辑）
    with st_module.spinner(f"正在计算 '{display_name}' 的{config.display_name}摘要..."):
        filtered_df = df[filtered_indicators]
        try:
            # 获取单位、类型和行业映射
            indicator_unit_map = get_economic_workbook_state(
                'indicator_unit_map',
                {},
                namespace=state_namespace,
            )
            # 调用calculate_summary时传入映射字典
            summary_table = calculate_summary(
                filtered_df,
                frequency,
                indicator_unit_map,
                indicator_type_map,
                indicator_industry_map
            )
        except Exception as e:
            st_module.error(f"计算{config.display_name}摘要时出错 ({display_name}): {e}")
            summary_table = pd.DataFrame()

    # 显示摘要表
    if not summary_table.empty:
        display_summary_table(
            st=st_module,
            summary_table=summary_table,
            sort_column=config.sort_column,
            highlight_columns=config.highlight_columns,
            percentage_columns=config.percentage_columns,
            download_prefix=config.download_prefix,
        )

    # 6. 绑制图表（按行业和类型分组）
    indicator_unit_map = get_economic_workbook_state(
        'indicator_unit_map',
        {},
        namespace=state_namespace,
    )
    indicator_type_map = get_economic_workbook_state(
        'indicator_type_map',
        {},
        namespace=state_namespace,
    )
    indicator_industry_map = get_economic_workbook_state(
        'indicator_industry_map',
        {},
        namespace=state_namespace,
    )

    # 图表是页面最重的部分。摘要始终保留完整指标，首屏只绘制有限数量，
    # 用户可显式选择全部图表以保持原有查看能力。
    max_initial_charts = min(12, len(filtered_indicators))
    show_all_charts = st_module.checkbox(
        "显示全部指标图表",
        value=False,
        key=f"{state_namespace}.{config.english_name}.show_all_charts",
        help="全部图表会显著增加页面加载时间。",
    )
    chart_indicators = (
        filtered_indicators
        if show_all_charts
        else filtered_indicators[:max_initial_charts]
    )
    if len(chart_indicators) < len(filtered_indicators):
        st_module.caption(
            f"当前展示前 {len(chart_indicators)} 项，共 {len(filtered_indicators)} 项；"
            "如需全部图表，请勾选上方选项。"
        )

    # 按行业和类型分组指标
    grouped = _group_indicators_by_industry_and_type(
        chart_indicators,
        indicator_industry_map,
        indicator_type_map
    )

    for industry, types_dict in grouped.items():
        # 分隔线和行业标题
        st_module.markdown("---")
        st_module.markdown(f"### {industry}")

        # 创建两列布局
        col1, col2 = st_module.columns(2)
        col_idx = 0

        for indicators in types_dict.values():
            for indicator in indicators:
                series = df[indicator].dropna()
                if not series.empty:
                    latest_date = pd.Timestamp(series.index.max())
                    current_year = (
                        int(latest_date.isocalendar().year)
                        if frequency == "weekly"
                        else latest_date.year
                    )
                    previous_year = current_year - 1
                    current_col = col1 if col_idx % 2 == 0 else col2
                    with current_col:
                        with st_module.spinner(UI_TEXT['loading_message'].format(indicator)):
                            try:
                                unit = indicator_unit_map.get(indicator, None)
                                ind_type = indicator_type_map.get(indicator, None)
                                fig = plot_indicator(
                                    series=series,
                                    name=indicator,
                                    frequency=frequency,
                                    current_year=current_year,
                                    previous_year=previous_year,
                                    unit=unit,
                                    indicator_type=ind_type
                                )
                                st_module.plotly_chart(
                                    place_chart_legend_at_bottom(fig),
                                    width='stretch',
                                )
                            except Exception as e:
                                st_module.error(f"为指标 '{indicator}' 生成图表时出错: {e}")
                    col_idx += 1




def display_overview_tab(
    st_module,
    *,
    state_namespace: str = "economic_workbook",
):
    """数据概览Tab（重构后）

    显示所有频率数据的统计概览、指标详情、数据下载功能
    重构后的版本：
    - 单次遍历替代5次遍历
    - 职责清晰的子函数
    - 减少约70%代码量

    Args:
        st_module: Streamlit模块
    """
    # 1. 获取数据并创建统一结构（直接从session_state获取）
    # 使用工具函数创建频率到DataFrame的字典
    all_data_dict = {
        config.display_name: get_economic_workbook_state(
            config.df_key,
            pd.DataFrame(),
            namespace=state_namespace,
        )
        for config in FREQUENCY_CONFIGS.values()
    }

    indicator_maps = {
        'industry': get_economic_workbook_state(
            'indicator_industry_map',
            {},
            namespace=state_namespace,
        ),
        'type': get_economic_workbook_state(
            'indicator_type_map',
            {},
            namespace=state_namespace,
        ),
        'clean_industry': get_economic_workbook_state(
            'clean_industry_map',
            {},
            namespace=state_namespace,
        ),
    }

    # 2. 计算统计（一次遍历完成所有统计）- 使用缓存版本
    stats = calculate_indicator_statistics_cached(all_data_dict, indicator_maps)

    # 3. 第一部分：指标概览
    st_module.markdown("#### 指标概览")
    render_statistics_summary(stats, st_module)
    st_module.markdown("---")

    # 4. 第二部分：指标详情
    st_module.markdown("#### 指标详情")
    render_indicator_details(stats['indicator_details'], st_module)
