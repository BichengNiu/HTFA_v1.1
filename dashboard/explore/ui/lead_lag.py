# -*- coding: utf-8 -*-
"""
领先滞后分析组件
提供多变量领先滞后筛选分析功能，基于KL散度评估
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.dates as mdates
import logging
from typing import List, Dict, Any

# 配置matplotlib中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore import perform_combined_lead_lag_analysis, get_detailed_lag_data_for_candidate
from dashboard.explore.preprocessing.frequency_alignment import align_series_for_analysis
from dashboard.explore.preprocessing.standardization import standardize_series

logger = logging.getLogger(__name__)


class LeadLagAnalysisComponent(TimeSeriesAnalysisComponent):
    """领先滞后分析组件"""
    
    def __init__(self):
        super().__init__("lead_lag", "领先滞后分析")

    def render(self, st_obj, **kwargs) -> Any:
        """
        重写渲染方法，跳过数据状态显示

        Args:
            st_obj: Streamlit对象
            **kwargs: 其他参数

        Returns:
            Any: 分析结果
        """
        try:
            # 检测标签页激活状态
            tab_index = kwargs.get('tab_index', 0)
            self.detect_tab_activation(st_obj, tab_index)

            # 直接获取数据，不显示数据状态信息
            data, data_source, data_name = self.get_module_data()

            if data is None:
                st_obj.info("请上传数据文件以进行分析")
                st_obj.divider()
                st_obj.markdown(f"""
                **使用说明：**
                1. **数据格式**：第一列为时间戳，其余列为变量数据
                2. **支持格式**：CSV、Excel (.xlsx, .xls)
                3. **编码支持**：UTF-8、GBK、GB2312等
                """)
                return None

            # 渲染分析界面
            return self.render_analysis_interface(st_obj, data, data_name)

        except Exception as e:
            self.handle_error(st_obj, e, f"渲染{self.title}组件")
            return None
    
    def render_analysis_interface(self, st_obj, data: pd.DataFrame, data_name: str) -> Any:
        """
        渲染领先滞后分析界面

        Args:
            st_obj: Streamlit对象
            data: 分析数据
            data_name: 数据名称

        Returns:
            Any: 分析结果
        """
        try:
                       
            # 渲染领先滞后分析
            result = self.render_multivariate_screening(st_obj, data, data_name)
            return result

        except Exception as e:
            logger.error(f"渲染领先滞后分析界面时出错: {e}")
            st_obj.error(f"渲染分析界面时出错: {e}")
            return None
    
    def render_multivariate_screening(self, st_obj, data: pd.DataFrame, data_name: str) -> Any:
        """渲染多变量领先滞后筛选界面"""
        try:

            # 参数设置区域
            # ========== 第一排：目标变量（全宽）==========
            numeric_columns = data.select_dtypes(include=[np.number]).columns.tolist()
            if len(numeric_columns) < 2:
                st_obj.warning("数据中的数值型变量少于2个，无法进行分析")
                return None

            target_var = st_obj.selectbox(
                "目标变量",
                numeric_columns,
                key="lead_lag_target_var",
                help="选择要预测的目标变量"
            )

            # ========== 第二排：3列布局 ==========
            row2_col1, row2_col2, row2_col3 = st_obj.columns(3)

            with row2_col1:
                alignment_mode = st_obj.selectbox(
                    "对齐模式",
                    options=['strict_align', 'no_align'],
                    format_func=lambda x: {
                        'strict_align': '严格对齐',
                        'no_align': '不对齐'
                    }[x],
                    index=0,
                    key="lead_lag_alignment_mode",
                    help="严格对齐：频率对齐+成对删除NA；不对齐：原始数据+成对删除NA"
                )

            with row2_col2:
                # 聚合方法：只在严格对齐时显示
                if alignment_mode == 'strict_align':
                    freq_agg_method = st_obj.selectbox(
                        "聚合方法",
                        options=['mean', 'last', 'first', 'sum', 'median'],
                        format_func=lambda x: {
                            'mean': '平均值',
                            'last': '最后值',
                            'first': '首个值',
                            'sum': '求和',
                            'median': '中位数'
                        }[x],
                        index=0,
                        key="lead_lag_freq_agg_method",
                        help="频率对齐时的数据聚合方法"
                    )
                else:
                    freq_agg_method = 'mean'  # 默认值

            with row2_col3:
                max_lags_val = st_obj.number_input(
                    "领先滞后期数",
                    min_value=1,
                    max_value=5,
                    value=5,
                    key="lead_lag_max_lags",
                    help="设置领先滞后期数范围（如设为5，则分析-5到+5共11个期数，正值表示候选变量领先，负值表示滞后）"
                )

            # ========== 第四排：分析按钮 ==========
            if st_obj.button(
                "开始分析",
                key="lead_lag_analyze_button",
                use_container_width=False,
                type = "primary"
            ):
                analyze_button = True
            else:
                analyze_button = False

            # 解析参数
            enable_frequency_alignment = (alignment_mode == 'strict_align')
            standardize_for_kl = True  # 固定为True
            standardization_method = 'zscore'  # 固定为zscore

            # 自动获取所有候选变量（除目标变量外的所有数值型变量）
            candidate_vars = [col for col in numeric_columns if col != target_var]

            if analyze_button and target_var:
                return self.perform_multivariate_screening(st_obj, data, target_var, candidate_vars, max_lags_val, standardize_for_kl, standardization_method, enable_frequency_alignment, None, freq_agg_method)
            
            # 显示之前的结果（如果有）
            results = self.get_state('multivariate_results')
            if results:
                self.render_multivariate_results(st_obj, results)
                
            return results
            
        except Exception as e:
            logger.error(f"渲染多变量领先滞后筛选界面时出错: {e}")
            st_obj.error(f"渲染多变量领先滞后筛选界面时出错: {e}")
            return None
    
    def perform_multivariate_screening(self, st_obj, data: pd.DataFrame, target_var: str, candidate_vars: List[str], max_lags: int, standardize_for_kl: bool = True, standardization_method: str = 'zscore', enable_frequency_alignment: bool = True, target_frequency: str = None, freq_agg_method: str = 'mean'):
        """执行多变量领先滞后筛选分析"""
        with st_obj.spinner("正在进行多变量领先滞后筛选分析..."):
            # 构建配置字典
            config = {
                'max_lags': max_lags,
                'standardize_for_kl': standardize_for_kl,
                'standardization_method': standardization_method,
                'enable_frequency_alignment': enable_frequency_alignment,
                'target_frequency': target_frequency,
                'freq_agg_method': freq_agg_method
            }

            # 调用后端函数
            results_list, errors, warnings = perform_combined_lead_lag_analysis(
                data, target_var, candidate_vars, config
            )

            # 转换结果为DataFrame
            if results_list:
                results_df = pd.DataFrame(results_list)
            else:
                results_df = pd.DataFrame()

            results = {
                'target_var': target_var,
                'candidate_vars': candidate_vars,
                'max_lags': max_lags,
                'standardize_for_kl': standardize_for_kl,
                'standardization_method': standardization_method,
                'enable_frequency_alignment': enable_frequency_alignment,
                'target_frequency': target_frequency,
                'freq_agg_method': freq_agg_method,
                'results_df': results_df,
                'errors': errors,
                'warnings': warnings
            }

            # 保存结果
            self.set_state('multivariate_results', results)

            # 渲染结果
            self.render_multivariate_results(st_obj, results)

            return results

    def render_multivariate_results(self, st_obj, results: Dict[str, Any]):
        """渲染多变量领先滞后筛选结果"""
        try:
            results_df = results['results_df']
            errors = results['errors']
            warnings = results['warnings']

            # 显示错误（不显示警告信息）
            if errors:
                for error in errors:
                    st_obj.error(f"{error}")

            if results_df is None or results_df.empty:
                st_obj.warning("没有分析结果可显示")
                return

            st_obj.markdown("##### 分析结果")

            # 格式化结果表格
            display_results = results_df.copy()

            # 移除不能序列化的列
            columns_to_remove = ['full_kl_divergence_df']
            for col in columns_to_remove:
                if col in display_results.columns:
                    display_results = display_results.drop(columns=[col])

            # 列名映射
            column_mapping = {
                'target_variable': '目标变量',
                'candidate_variable': '候选变量',
                'k_kl': '最优滞后(KL)',
                'kl_at_k_kl': '最小KL散度',
                'notes': '备注'
            }

            display_results = display_results.rename(columns=column_mapping)

            # 数值格式化
            if '最小KL散度' in display_results.columns:
                display_results['最小KL散度'] = display_results['最小KL散度'].round(4)

            # 结果排序：按KL散度升序排列
            if not display_results.empty and '最小KL散度' in display_results.columns:
                display_results = display_results.sort_values(
                    by='最小KL散度',
                    ascending=True,
                    na_position='last'
                )
                display_results = display_results.reset_index(drop=True)

            st_obj.dataframe(display_results, hide_index=True, width='stretch')

            # 提供下载功能
            csv_string = display_results.to_csv(index=False, encoding='utf-8-sig')
            csv_data = csv_string.encode('utf-8-sig')
            st_obj.download_button(
                label="下载结果",
                data=csv_data,
                file_name=f"lead_lag_analysis_{results['target_var']}.csv",
                mime="text/csv",
                key="download_lead_lag_data",
                use_container_width=False,
                type = "primary"
            )

            st_obj.divider()

            # 详细图表展示标题
            st_obj.markdown("##### 领先滞后分析图")

            # 变量选择器和指标显示（列布局）
            select_col, metric_col = st_obj.columns([3, 1])

            with select_col:
                candidate_var_for_plot = st_obj.selectbox(
                    "选择变量查看详细图表",
                    results['candidate_vars'],
                    key="lead_lag_plot_var",
                    help="选择一个候选变量查看其详细的KL散度图表"
                )

            # 根据选中的变量显示指标
            if candidate_var_for_plot and not display_results.empty:
                selected_row = display_results[display_results['候选变量'] == candidate_var_for_plot]
                if not selected_row.empty:
                    k_kl_val = selected_row['最优滞后(KL)'].values[0]

                    with metric_col:
                        st_obj.metric("最优滞后(KL)", f"{k_kl_val:.0f}" if pd.notna(k_kl_val) else "N/A")

            if candidate_var_for_plot:
                self.render_detailed_multivariate_charts(st_obj, results, candidate_var_for_plot)

        except Exception as e:
            logger.error(f"渲染多变量结果时出错: {e}")
            st_obj.error(f"显示结果时出错: {e}")

    def render_detailed_multivariate_charts(self, st_obj, results: Dict[str, Any], candidate_var: str):
        """渲染多变量分析的详细图表"""
        # 获取原始数据
        data, _, _ = self.get_module_data()
        if data is None:
            st_obj.warning("无法获取原始数据")
            return

        # 构建配置字典
        config = {
            'max_lags': results['max_lags'],
            'standardize_for_kl': results['standardize_for_kl'],
            'standardization_method': results['standardization_method'],
            'enable_frequency_alignment': results['enable_frequency_alignment'],
            'target_frequency': results['target_frequency'],
            'freq_agg_method': results['freq_agg_method']
        }

        detailed_kl_df = get_detailed_lag_data_for_candidate(
            data, results['target_var'], candidate_var, config
        )

        if detailed_kl_df is not None:
            # 限制图表数据只显示±5期
            kl_df_filtered = detailed_kl_df[
                (detailed_kl_df['Lag'] >= -5) &
                (detailed_kl_df['Lag'] <= 5)
            ].copy()

            # 单列全宽布局
            st_obj.markdown(f"**{candidate_var} KL散度分析**")
            if not kl_df_filtered.empty:
                # 配置matplotlib以禁用工具栏
                plt.rcParams['toolbar'] = 'None'
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(kl_df_filtered['Lag'], kl_df_filtered['KL_Divergence'],
                       marker='s', linewidth=2, markersize=4, color='orange')
                ax.set_xlabel('滞后期')
                ax.set_ylabel('KL散度')
                ax.set_title(f'{results["target_var"]} vs {candidate_var} KL散度')
                ax.grid(True, alpha=0.3)
                plt.tight_layout()
                st_obj.pyplot(fig, use_container_width=True)
                plt.close()

        # 添加时间序列对比图
        st_obj.markdown(f"**{results['target_var']} vs {candidate_var} 时间序列对比**")
        self.render_time_series_comparison(st_obj, data, results, candidate_var)

    def render_time_series_comparison(self, st_obj, data: pd.DataFrame, results: Dict[str, Any], candidate_var: str):
        """渲染目标变量与候选变量的时间序列对比图"""
        target_var = results['target_var']

        # 执行频率对齐
        df_aligned = data
        if results['enable_frequency_alignment']:
            df_aligned, alignment_report = align_series_for_analysis(
                data,
                target_var,
                [candidate_var],
                enable_frequency_alignment=True,
                target_frequency=results['target_frequency'],
                agg_method=results['freq_agg_method']
            )

            if alignment_report['status'] == 'error':
                raise ValueError(f"频率对齐失败: {alignment_report['error']}")

        # 获取对齐后的序列
        target_series = df_aligned[target_var].copy()
        candidate_series = df_aligned[candidate_var].copy()

        # 删除任一序列中的NaN值（保持索引对齐）
        valid_idx = target_series.notna() & candidate_series.notna()
        target_series_clean = target_series[valid_idx]
        candidate_series_clean = candidate_series[valid_idx]

        if len(target_series_clean) < 2:
            st_obj.warning("有效数据点太少，无法绘制时间序列图")
            return

        # 应用标准化处理（如果启用KL散度标准化）
        if results['standardize_for_kl']:
            standardization_method = results['standardization_method']
            if standardization_method != 'none':
                target_series_plot = standardize_series(target_series_clean, standardization_method)
                candidate_series_plot = standardize_series(candidate_series_clean, standardization_method)
                y_label = f"标准化值 ({standardization_method})"
                title_suffix = f" (已标准化 - {standardization_method})"
            else:
                target_series_plot = target_series_clean
                candidate_series_plot = candidate_series_clean
                y_label = "原始值"
                title_suffix = " (原始值)"
        else:
            target_series_plot = target_series_clean
            candidate_series_plot = candidate_series_clean
            y_label = "原始值"
            title_suffix = " (原始值)"

        # 配置matplotlib以禁用工具栏
        plt.rcParams['toolbar'] = 'None'

        # 创建时间序列对比图
        fig, ax = plt.subplots(figsize=(12, 6))

        # 绘制时间序列
        ax.plot(target_series_plot.index, target_series_plot.values,
               label=target_var, linewidth=2, alpha=0.8)
        ax.plot(candidate_series_plot.index, candidate_series_plot.values,
               label=candidate_var, linewidth=2, alpha=0.8)

        # 设置图表样式
        ax.set_xlabel('时间')
        ax.set_ylabel(y_label)
        ax.set_title(f'{target_var} vs {candidate_var} 时间序列对比{title_suffix}')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 优化x轴标签显示
        if hasattr(target_series_plot.index, 'to_pydatetime'):
            # 如果是日期时间索引，优化显示
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(target_series_plot) // 10)))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        plt.tight_layout()
        st_obj.pyplot(fig, width='stretch')
        plt.close()