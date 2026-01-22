"""
Industrial Enterprise Operations Analysis Module
工业企业经营分析模块（重构版）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Optional
import logging

# 设置日志
logger = logging.getLogger(__name__)

# 导入统一的工具函数
from dashboard.analysis.industrial.utils import (
    convert_cumulative_to_yoy,
    filter_data_by_time_range,
    load_enterprise_profit_data,
    create_excel_download_button
)

# 导入新的图表组件
from dashboard.analysis.industrial.charts import (
    ProfitContributionChart,
    OperationsIndicatorsChart,
    EfficiencyMetricsChart,
    EnterpriseIndicatorsChart
)


# ============================================================================
# 图表创建函数（向后兼容封装）
# ============================================================================


def create_profit_contribution_chart(
    df_contribution: pd.DataFrame,
    total_growth: pd.Series,
    time_range: str = "3年",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None
) -> Optional[go.Figure]:
    """
    创建工业企业利润分行业拉动率图表（堆叠柱状图+折线图）

    Args:
        df_contribution: 上中下游拉动率DataFrame
        total_growth: 总体增速Series
        time_range: 时间范围选择
        custom_start_date: 自定义开始日期
        custom_end_date: 自定义结束日期

    Returns:
        plotly Figure对象
    """
    chart = ProfitContributionChart(total_growth=total_growth)
    return chart.create(df_contribution, time_range, custom_start_date, custom_end_date)


def create_enterprise_operations_indicators_chart(
    df_operations: pd.DataFrame,
    time_range: str = "3年",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None
) -> Optional[go.Figure]:
    """
    创建企业经营指标图表（四个子图：ROE、利润率、周转率、权益乘数）

    Args:
        df_operations: 包含企业经营数据的DataFrame
        time_range: 时间范围选择
        custom_start_date: 自定义开始日期
        custom_end_date: 自定义结束日期

    Returns:
        plotly Figure对象（包含4个子图）
    """
    chart = OperationsIndicatorsChart()
    return chart.create(df_operations, time_range, custom_start_date, custom_end_date)


def create_enterprise_efficiency_metrics_chart(
    df_efficiency: pd.DataFrame,
    time_range: str = "3年",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None
) -> Optional[go.Figure]:
    """
    创建企业经营效率指标图表（六个子图）

    Args:
        df_efficiency: 包含企业经营效率数据的DataFrame
        time_range: 时间范围选择
        custom_start_date: 自定义开始日期
        custom_end_date: 自定义结束日期

    Returns:
        plotly Figure对象（包含6个子图）
    """
    chart = EfficiencyMetricsChart()
    return chart.create(df_efficiency, time_range, custom_start_date, custom_end_date)


def create_enterprise_indicators_chart(
    df_data: pd.DataFrame,
    time_range: str = "3年",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None
) -> Optional[go.Figure]:
    """
    创建企业经营四个指标的时间序列线图

    Args:
        df_data: 包含指标数据的DataFrame
        time_range: 时间范围选择
        custom_start_date: 自定义开始日期
        custom_end_date: 自定义结束日期

    Returns:
        plotly Figure对象
    """
    chart = EnterpriseIndicatorsChart()
    return chart.create(df_data, time_range, custom_start_date, custom_end_date)


# ============================================================================
# 渲染函数（保持原有API）
# ============================================================================


def render_enterprise_operations_analysis_with_data(
    st_obj,
    df_macro: Optional[pd.DataFrame],
    df_weights: Optional[pd.DataFrame],
    uploaded_file=None
):
    """
    使用预加载数据渲染企业经营分析（用于统一模块）

    Args:
        st_obj: Streamlit对象
        df_macro: 宏观运行数据
        df_weights: 权重数据
        uploaded_file: 上传的Excel文件对象
    """
    # 如果没有传入上传的文件，尝试从统一状态管理器获取
    if uploaded_file is None:
        uploaded_file = st.session_state.get("analysis.industrial.unified_file_uploader")

    if uploaded_file is None:
        return

    # 读取企业利润拆解数据
    df_profit = load_enterprise_profit_data(uploaded_file)

    if df_profit is None:
        logger.error("无法加载企业利润数据")
        st_obj.error("错误：无法加载企业利润数据")
        return

    # 处理营业收入利润率：累计值转换为年同比
    profit_margin_col = None
    for col in df_profit.columns:
        if '营业收入利润率' in str(col) and '累计值' in str(col):
            profit_margin_col = col
            break

    if profit_margin_col:
        yoy_data = convert_cumulative_to_yoy(df_profit[profit_margin_col])
        yoy_col_name = profit_margin_col.replace('累计值', '累计同比')
        df_profit[yoy_col_name] = yoy_data

    # 过滤掉所有1月和2月的数据
    jan_feb_mask = df_profit.index.month.isin([1, 2])
    df_profit = df_profit[~jan_feb_mask]

    if len(df_profit) == 0:
        logger.error("过滤1月2月后数据为空")
        st_obj.error("错误：过滤1月2月后，数据为空！请检查上传的Excel文件。")
        return

    # 图表1：工业企业利润拆解
    from dashboard.analysis.industrial.utils import (
        create_chart_with_time_selector_fragment,
        IndustrialStateManager
    )
    from dashboard.analysis.industrial.constants import (
        PROFIT_TOTAL_COLUMN,
        CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
        PPI_COLUMN,
        PROFIT_MARGIN_COLUMN_YOY
    )

    chart1_variables = [
        PROFIT_TOTAL_COLUMN,
        CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
        PPI_COLUMN,
        PROFIT_MARGIN_COLUMN_YOY
    ]

    available_vars = [var for var in chart1_variables if var in df_profit.columns]

    if not available_vars:
        st_obj.error(f"错误：未找到任何必需的指标列！")
        return

    def create_chart1(df, variables, time_range, custom_start_date, custom_end_date):
        return create_enterprise_indicators_chart(
            df_data=df,
            time_range=time_range,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date
        )

    create_chart_with_time_selector_fragment(
        st_obj=st_obj,
        chart_id="enterprise_chart1",
        state_namespace="monitoring.industrial.enterprise",
        chart_title=None,
        chart_creator_func=create_chart1,
        chart_data=df_profit,
        chart_variables=available_vars,
        get_state_func=IndustrialStateManager.get,
        set_state_func=IndustrialStateManager.set
    )

    # 添加数据下载功能
    if not df_profit.empty:
        create_excel_download_button(
            st_obj=st_obj,
            data=df_profit,
            file_name="企业经营指标_全部数据.xlsx",
            sheet_name='企业经营指标',
            button_key="industrial_enterprise_operations_download_data_button",
            column_ratio=(1, 3)
        )

    # 企业经营指标图表
    st_obj.markdown("#### 企业经营指标")

    from dashboard.analysis.industrial.utils import load_enterprise_operations_data, convert_cumulative_to_current

    df_operations = load_enterprise_operations_data(uploaded_file)

    if df_operations is not None and not df_operations.empty:
        # 定义需要的列名
        profit_cumulative_col = '中国:利润总额:规模以上工业企业:累计值'
        revenue_cumulative_col = '中国:营业收入:规模以上工业企业:累计值'
        assets_col = '中国:资产合计:规模以上工业企业'
        equity_col = '中国:所有者权益合计:规模以上工业企业'

        required_cols = [profit_cumulative_col, revenue_cumulative_col, assets_col, equity_col]
        missing_cols = [col for col in required_cols if col not in df_operations.columns]

        if missing_cols:
            logger.warning(f"缺少必需列: {missing_cols}")
            st_obj.warning(f"数据中缺少部分企业经营指标列，无法生成完整图表")
        else:
            # 转换累计值为当期值
            df_operations['利润总额当期值'] = convert_cumulative_to_current(df_operations[profit_cumulative_col])
            df_operations['营业收入当期值'] = convert_cumulative_to_current(df_operations[revenue_cumulative_col])

            # 过滤掉1月和2月的数据
            jan_feb_mask = df_operations.index.month.isin([1, 2])
            df_operations_filtered = df_operations[~jan_feb_mask].copy()

            # 计算4个指标
            df_operations_filtered['ROE'] = (df_operations_filtered['利润总额当期值'] / df_operations_filtered[equity_col]) * 100
            df_operations_filtered['利润率'] = (df_operations_filtered['利润总额当期值'] / df_operations_filtered['营业收入当期值']) * 100
            df_operations_filtered['总资产周转率'] = df_operations_filtered['营业收入当期值'] / df_operations_filtered[assets_col]
            df_operations_filtered['权益乘数'] = df_operations_filtered[assets_col] / df_operations_filtered[equity_col]

            df_operations = df_operations_filtered

            all_indicators = ['ROE', '利润率', '总资产周转率', '权益乘数']
            default_indicators = ['ROE', '利润率', '总资产周转率']

            selected_indicators = st_obj.multiselect(
                "选择要显示的企业经营指标",
                options=all_indicators,
                default=default_indicators,
                key="enterprise_operations_indicator_selector"
            )

            if not selected_indicators:
                st_obj.warning("请至少选择一个指标")
                return

            def create_operations_chart(df, variables, time_range, custom_start_date, custom_end_date):
                return create_enterprise_operations_indicators_chart(
                    df_operations=df,
                    time_range=time_range,
                    custom_start_date=custom_start_date,
                    custom_end_date=custom_end_date
                )

            create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="enterprise_operations_indicators",
                state_namespace="monitoring.industrial.enterprise",
                chart_title=None,
                chart_creator_func=create_operations_chart,
                chart_data=df_operations,
                chart_variables=selected_indicators,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set
            )

            # 添加数据下载功能
            if not df_operations.empty:
                download_df = df_operations[all_indicators].copy()
                download_df = download_df.sort_index(ascending=False)
                download_df = download_df.reset_index()
                first_col = download_df.columns[0]
                download_df.rename(columns={first_col: '时间'}, inplace=True)
                download_df['时间'] = download_df['时间'].dt.strftime('%Y-%m')
                download_columns = ['时间'] + all_indicators
                download_df = download_df[download_columns]

                create_excel_download_button(
                    st_obj=st_obj,
                    data=download_df,
                    file_name="企业经营指标.xlsx",
                    sheet_name='企业经营指标',
                    button_key="enterprise_operations_indicators_download_button",
                    column_ratio=(1, 3)
                )
    else:
        logger.warning("未能加载企业经营数据")
        st_obj.info("提示：数据模板中未找到'工业企业经营'sheet，跳过企业经营指标图表")

    # 分割线
    st_obj.markdown("---")

    # 加载分行业利润数据
    from dashboard.analysis.industrial.utils import load_industry_profit_data
    from dashboard.analysis.industrial.utils.contribution_calculator import calculate_profit_contributions

    df_industry_profit = load_industry_profit_data(uploaded_file)

    if df_industry_profit is None:
        logger.error("无法加载分行业利润数据")
        st_obj.error("错误：无法加载分行业利润数据")
        return

    if df_weights is None:
        st_obj.error("错误：缺少权重数据，无法进行利润拆解分析")
        return

    # 计算利润拉动率
    try:
        profit_contribution_result = calculate_profit_contributions(
            df_industry_profit=df_industry_profit,
            df_weights=df_weights
        )

        stream_contribution_df = profit_contribution_result['stream_groups']
        total_growth_series = profit_contribution_result['total_growth']

        def create_chart2(df, variables, time_range, custom_start_date, custom_end_date):
            return create_profit_contribution_chart(
                df_contribution=df,
                total_growth=total_growth_series,
                time_range=time_range,
                custom_start_date=custom_start_date,
                custom_end_date=custom_end_date
            )

        available_vars_chart2 = list(stream_contribution_df.columns)

        if available_vars_chart2:
            create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="enterprise_chart2",
                state_namespace="monitoring.industrial.enterprise",
                chart_title=None,
                chart_creator_func=create_chart2,
                chart_data=stream_contribution_df,
                chart_variables=available_vars_chart2,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set
            )
        else:
            st_obj.warning("未找到上中下游拉动率数据")

        # 添加拉动率数据下载功能
        if not stream_contribution_df.empty:
            download_df = stream_contribution_df.copy()
            download_df.columns = [col.replace('上中下游_', '') for col in download_df.columns]
            download_df.insert(0, '利润总额累计同比', total_growth_series)
            download_df = download_df.sort_index(ascending=False)
            download_df = download_df.reset_index()
            first_col = download_df.columns[0]
            download_df.rename(columns={first_col: '时间'}, inplace=True)
            download_df['时间'] = download_df['时间'].dt.strftime('%Y-%m')

            create_excel_download_button(
                st_obj=st_obj,
                data=download_df,
                file_name="分行业利润拆解_拉动率数据.xlsx",
                sheet_name='拉动率',
                button_key="industrial_profit_contribution_download_button",
                column_ratio=(1, 3)
            )

    except Exception as e:
        logger.error(f"计算利润拉动率时发生错误: {e}", exc_info=True)
        st_obj.error(f"计算利润拉动率失败：{str(e)}")
        return


def render_enterprise_profit_analysis_with_data(
    st_obj,
    df_macro: Optional[pd.DataFrame],
    df_weights: Optional[pd.DataFrame],
    uploaded_file=None
):
    """
    渲染工业企业利润分析（包含利润拆解和分行业拆解）

    Args:
        st_obj: Streamlit对象
        df_macro: 宏观运行数据
        df_weights: 权重数据
        uploaded_file: 上传的Excel文件对象
    """
    if uploaded_file is None:
        uploaded_file = st.session_state.get("analysis.industrial.unified_file_uploader")

    if uploaded_file is None:
        st_obj.info("请先上传Excel数据文件以开始工业企业利润分析")
        return

    # 读取企业利润拆解数据
    df_profit = load_enterprise_profit_data(uploaded_file)

    if df_profit is None:
        logger.error("无法加载企业利润数据")
        st_obj.error("错误：无法加载企业利润数据")
        return

    # 处理营业收入利润率：累计值转换为年同比
    profit_margin_col = None
    for col in df_profit.columns:
        if '营业收入利润率' in str(col) and '累计值' in str(col):
            profit_margin_col = col
            break

    if profit_margin_col:
        yoy_data = convert_cumulative_to_yoy(df_profit[profit_margin_col])
        yoy_col_name = profit_margin_col.replace('累计值', '累计同比')
        df_profit[yoy_col_name] = yoy_data

    # 过滤掉所有1月和2月的数据
    jan_feb_mask = df_profit.index.month.isin([1, 2])
    df_profit = df_profit[~jan_feb_mask]

    if len(df_profit) == 0:
        logger.error("过滤1月2月后数据为空")
        st_obj.error("错误：过滤1月2月后，数据为空！")
        return

    # 图表1：工业企业利润拆解
    from dashboard.analysis.industrial.utils import (
        create_chart_with_time_selector_fragment,
        IndustrialStateManager
    )
    from dashboard.analysis.industrial.constants import (
        PROFIT_TOTAL_COLUMN,
        CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
        PPI_COLUMN,
        PROFIT_MARGIN_COLUMN_YOY
    )

    chart1_variables = [
        PROFIT_TOTAL_COLUMN,
        CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
        PPI_COLUMN,
        PROFIT_MARGIN_COLUMN_YOY
    ]

    available_vars = [var for var in chart1_variables if var in df_profit.columns]

    if not available_vars:
        st_obj.error(f"错误：未找到任何必需的指标列！")
        return

    def create_chart1(df, variables, time_range, custom_start_date, custom_end_date):
        return create_enterprise_indicators_chart(
            df_data=df,
            time_range=time_range,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date
        )

    create_chart_with_time_selector_fragment(
        st_obj=st_obj,
        chart_id="enterprise_profit_chart1",
        state_namespace="monitoring.industrial.enterprise.profit",
        chart_title=None,
        chart_creator_func=create_chart1,
        chart_data=df_profit,
        chart_variables=available_vars,
        get_state_func=IndustrialStateManager.get,
        set_state_func=IndustrialStateManager.set
    )

    if not df_profit.empty:
        create_excel_download_button(
            st_obj=st_obj,
            data=df_profit,
            file_name="企业利润指标_全部数据.xlsx",
            sheet_name='企业利润指标',
            button_key="enterprise_profit_download_button",
            column_ratio=(1, 3)
        )

    # 分割线
    st_obj.markdown("---")

    # 图表2：分行业利润拆解
    from dashboard.analysis.industrial.utils import load_industry_profit_data
    from dashboard.analysis.industrial.utils.contribution_calculator import calculate_profit_contributions

    df_industry_profit = load_industry_profit_data(uploaded_file)

    if df_industry_profit is None:
        logger.error("无法加载分行业利润数据")
        st_obj.error("错误：无法加载分行业利润数据")
        return

    if df_weights is None:
        st_obj.error("错误：缺少权重数据，无法进行利润拆解分析")
        return

    try:
        profit_contribution_result = calculate_profit_contributions(
            df_industry_profit=df_industry_profit,
            df_weights=df_weights
        )

        stream_contribution_df = profit_contribution_result['stream_groups']
        total_growth_series = profit_contribution_result['total_growth']

        def create_chart2(df, variables, time_range, custom_start_date, custom_end_date):
            return create_profit_contribution_chart(
                df_contribution=df,
                total_growth=total_growth_series,
                time_range=time_range,
                custom_start_date=custom_start_date,
                custom_end_date=custom_end_date
            )

        available_vars_chart2 = list(stream_contribution_df.columns)

        if available_vars_chart2:
            create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="enterprise_profit_chart2",
                state_namespace="monitoring.industrial.enterprise.profit",
                chart_title=None,
                chart_creator_func=create_chart2,
                chart_data=stream_contribution_df,
                chart_variables=available_vars_chart2,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set
            )
        else:
            st_obj.warning("未找到上中下游拉动率数据")

        if not stream_contribution_df.empty:
            download_df = stream_contribution_df.copy()
            download_df.columns = [col.replace('上中下游_', '') for col in download_df.columns]
            download_df.insert(0, '利润总额累计同比', total_growth_series)
            download_df = download_df.sort_index(ascending=False)
            download_df = download_df.reset_index()
            first_col = download_df.columns[0]
            download_df.rename(columns={first_col: '时间'}, inplace=True)
            download_df['时间'] = download_df['时间'].dt.strftime('%Y-%m')

            create_excel_download_button(
                st_obj=st_obj,
                data=download_df,
                file_name="分行业利润拆解_拉动率数据.xlsx",
                sheet_name='拉动率',
                button_key="profit_contribution_download_button",
                column_ratio=(1, 3)
            )

    except Exception as e:
        logger.error(f"计算利润拉动率时发生错误: {e}", exc_info=True)
        st_obj.error(f"计算利润拉动率失败：{str(e)}")
        return


def render_enterprise_efficiency_analysis_with_data(
    st_obj,
    df_macro: Optional[pd.DataFrame],
    df_weights: Optional[pd.DataFrame],
    uploaded_file=None
):
    """
    渲染工业企业经营效率分析（包含净资产收益率分析）

    Args:
        st_obj: Streamlit对象
        df_macro: 宏观运行数据
        df_weights: 权重数据
        uploaded_file: 上传的Excel文件对象
    """
    if uploaded_file is None:
        uploaded_file = st.session_state.get("analysis.industrial.unified_file_uploader")

    if uploaded_file is None:
        st_obj.info("请先上传Excel数据文件以开始工业企业经营效率分析")
        return

    # 加载企业经营数据
    from dashboard.analysis.industrial.utils import load_enterprise_operations_data, convert_cumulative_to_current

    df_operations = load_enterprise_operations_data(uploaded_file)

    if df_operations is None or df_operations.empty:
        logger.warning("未能加载企业经营数据")
        st_obj.info("提示：数据模板中未找到'工业企业经营'sheet，无法生成经营效率分析")
        return

    # 定义需要的列名
    profit_cumulative_col = '中国:利润总额:规模以上工业企业:累计值'
    revenue_cumulative_col = '中国:营业收入:规模以上工业企业:累计值'
    assets_col = '中国:资产合计:规模以上工业企业'
    equity_col = '中国:所有者权益合计:规模以上工业企业'

    required_cols = [profit_cumulative_col, revenue_cumulative_col, assets_col, equity_col]
    missing_cols = [col for col in required_cols if col not in df_operations.columns]

    if missing_cols:
        logger.warning(f"缺少必需列: {missing_cols}")
        st_obj.warning(f"数据中缺少部分企业经营指标列，无法生成完整图表")
        return

    # 转换累计值为当期值
    df_operations['利润总额当期值'] = convert_cumulative_to_current(df_operations[profit_cumulative_col])
    df_operations['营业收入当期值'] = convert_cumulative_to_current(df_operations[revenue_cumulative_col])

    # 过滤掉1月和2月的数据
    jan_feb_mask = df_operations.index.month.isin([1, 2])
    df_operations_filtered = df_operations[~jan_feb_mask].copy()

    # 计算4个指标
    df_operations_filtered['ROE'] = (df_operations_filtered['利润总额当期值'] / df_operations_filtered[equity_col]) * 100
    df_operations_filtered['利润率'] = (df_operations_filtered['利润总额当期值'] / df_operations_filtered['营业收入当期值']) * 100
    df_operations_filtered['总资产周转率'] = df_operations_filtered['营业收入当期值'] / df_operations_filtered[assets_col]
    df_operations_filtered['权益乘数'] = df_operations_filtered[assets_col] / df_operations_filtered[equity_col]

    df_operations = df_operations_filtered

    all_indicators = ['ROE', '利润率', '总资产周转率', '权益乘数']

    def create_operations_chart(df, variables, time_range, custom_start_date, custom_end_date):
        return create_enterprise_operations_indicators_chart(
            df_operations=df,
            time_range=time_range,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date
        )

    from dashboard.analysis.industrial.utils import (
        create_chart_with_time_selector_fragment,
        IndustrialStateManager
    )

    create_chart_with_time_selector_fragment(
        st_obj=st_obj,
        chart_id="enterprise_efficiency_indicators",
        state_namespace="monitoring.industrial.enterprise.efficiency",
        chart_title=None,
        chart_creator_func=create_operations_chart,
        chart_data=df_operations,
        chart_variables=all_indicators,
        get_state_func=IndustrialStateManager.get,
        set_state_func=IndustrialStateManager.set
    )

    # 添加数据下载功能
    if not df_operations.empty:
        download_df = df_operations[all_indicators].copy()
        download_df = download_df.sort_index(ascending=False)
        download_df = download_df.reset_index()
        first_col = download_df.columns[0]
        download_df.rename(columns={first_col: '时间'}, inplace=True)
        download_df['时间'] = download_df['时间'].dt.strftime('%Y-%m')
        download_columns = ['时间'] + all_indicators
        download_df = download_df[download_columns]

        create_excel_download_button(
            st_obj=st_obj,
            data=download_df,
            file_name="企业经营效率指标.xlsx",
            sheet_name='企业经营效率指标',
            button_key="efficiency_indicators_download_button",
            column_ratio=(1, 3)
        )

    # 分割线
    st_obj.markdown("---")

    # 企业经营效率指标分析（每百元成本/费用/资产/人均收入）
    cost_per_hundred_cumulative_col = '中国:每百元营业收入中的成本:规模以上工业企业:累计值'
    expense_per_hundred_cumulative_col = '中国:每百元营业收入中的费用:规模以上工业企业:累计值'
    asset_revenue_per_hundred_cumulative_col = '中国:每百元资产实现的营业收入:规模以上工业企业:累计值'
    revenue_per_capita_cumulative_col = '中国:人均营业收入:规模以上工业企业:累计值'
    turnover_days_cumulative_col = '中国:产成品周转天数:规模以上工业企业:累计值'
    receivable_period_cumulative_col = '中国:应收账款平均回收期:规模以上工业企业:累计值'

    required_efficiency_cols = [
        cost_per_hundred_cumulative_col,
        expense_per_hundred_cumulative_col,
        asset_revenue_per_hundred_cumulative_col,
        revenue_per_capita_cumulative_col,
        turnover_days_cumulative_col,
        receivable_period_cumulative_col
    ]

    df_efficiency_metrics = load_enterprise_operations_data(uploaded_file)

    if df_efficiency_metrics is None or df_efficiency_metrics.empty:
        logger.warning("未能加载企业经营效率指标数据")
        st_obj.info("提示：数据模板中未找到'工业企业经营'sheet，无法生成企业经营效率指标分析")
    else:
        missing_efficiency_cols = [col for col in required_efficiency_cols if col not in df_efficiency_metrics.columns]

        if missing_efficiency_cols:
            logger.warning(f"企业经营效率指标分析缺少必需列: {missing_efficiency_cols}")
            st_obj.warning(f"数据中缺少部分企业经营效率指标列，无法生成完整图表")
        else:
            # 转换累计值为累计同比
            df_efficiency_metrics['每百元营业收入中的成本'] = convert_cumulative_to_yoy(df_efficiency_metrics[cost_per_hundred_cumulative_col])
            df_efficiency_metrics['每百元营业收入中的费用'] = convert_cumulative_to_yoy(df_efficiency_metrics[expense_per_hundred_cumulative_col])
            df_efficiency_metrics['每百元资产实现的营业收入'] = convert_cumulative_to_yoy(df_efficiency_metrics[asset_revenue_per_hundred_cumulative_col])
            df_efficiency_metrics['人均营业收入'] = convert_cumulative_to_yoy(df_efficiency_metrics[revenue_per_capita_cumulative_col])
            df_efficiency_metrics['产成品周转天数'] = convert_cumulative_to_yoy(df_efficiency_metrics[turnover_days_cumulative_col])
            df_efficiency_metrics['应收账款平均回收期'] = convert_cumulative_to_yoy(df_efficiency_metrics[receivable_period_cumulative_col])

            # 过滤掉1月和2月的数据
            jan_feb_mask = df_efficiency_metrics.index.month.isin([1, 2])
            df_efficiency_metrics = df_efficiency_metrics[~jan_feb_mask].copy()

            efficiency_indicators = [
                '每百元营业收入中的成本',
                '每百元营业收入中的费用',
                '每百元资产实现的营业收入',
                '人均营业收入',
                '产成品周转天数',
                '应收账款平均回收期'
            ]

            def create_efficiency_metrics_chart(df, variables, time_range, custom_start_date, custom_end_date):
                return create_enterprise_efficiency_metrics_chart(
                    df_efficiency=df,
                    time_range=time_range,
                    custom_start_date=custom_start_date,
                    custom_end_date=custom_end_date
                )

            create_chart_with_time_selector_fragment(
                st_obj=st_obj,
                chart_id="enterprise_efficiency_metrics",
                state_namespace="monitoring.industrial.enterprise.efficiency_metrics",
                chart_title=None,
                chart_creator_func=create_efficiency_metrics_chart,
                chart_data=df_efficiency_metrics,
                chart_variables=efficiency_indicators,
                get_state_func=IndustrialStateManager.get,
                set_state_func=IndustrialStateManager.set
            )

            # 添加数据下载功能
            if not df_efficiency_metrics.empty:
                download_df = df_efficiency_metrics[efficiency_indicators].copy()
                download_df = download_df.sort_index(ascending=False)
                download_df = download_df.reset_index()
                first_col = download_df.columns[0]
                download_df.rename(columns={first_col: '时间'}, inplace=True)
                download_df['时间'] = download_df['时间'].dt.strftime('%Y-%m')
                download_columns = ['时间'] + efficiency_indicators
                download_df = download_df[download_columns]

                create_excel_download_button(
                    st_obj=st_obj,
                    data=download_df,
                    file_name="企业经营效率指标.xlsx",
                    sheet_name='企业经营效率指标',
                    button_key="efficiency_metrics_download_button",
                    column_ratio=(1, 3)
                )
