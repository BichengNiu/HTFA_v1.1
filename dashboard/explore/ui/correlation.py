# -*- coding: utf-8 -*-
"""
时间滞后相关性分析组件
迁移自 dashboard/explore/time_lag_corr_frontend.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import logging
from typing import List, Dict, Any, Optional, Tuple

# 配置matplotlib中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore import calculate_time_lagged_correlation

logger = logging.getLogger(__name__)


class CorrelationAnalysisComponent(TimeSeriesAnalysisComponent):
    """时间滞后相关性分析组件"""

    def __init__(self):
        super().__init__("time_lag_corr", "时间滞后相关性分析")

    def render_input_section(self, st_obj, data: pd.DataFrame, data_name: str = "数据") -> Dict[str, Any]:
        """渲染相关性分析输入界面"""
        st_obj.markdown("#### 时间滞后相关性分析配置")

        # 显示数据基本信息
        st_obj.info(f"正在分析数据: {data_name}，形状: {data.shape}")

        # 检查数值列
        numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) < 2:
            st_obj.error("数据中至少需要2个数值列才能进行相关性分析")
            return {'error': '数值列不足'}

        # 获取分析参数
        params = self.render_analysis_parameters(st_obj, data, data_name)
        if params[0] is None:  # 检查是否有错误
            return {'error': '参数设置失败'}

        lagged_var, leading_var, max_lag = params

        return {
            'data': data,
            'data_name': data_name,
            'lagged_var': lagged_var,
            'leading_var': leading_var,
            'max_lag': max_lag
        }

    def render_analysis_parameters(self, st_obj, data: pd.DataFrame, data_name: str) -> Tuple[str, str, int]:
        """
        渲染分析参数设置界面

        Args:
            st_obj: Streamlit对象
            data: 分析数据
            data_name: 数据名称

        Returns:
            Tuple[str, str, int]: (滞后变量, 领先变量, 最大滞后期数)
        """
        st_obj.markdown("### 参数输入")
        series_options_all = [col for col in data.columns if pd.api.types.is_numeric_dtype(data[col])]

        if not series_options_all:
            st_obj.warning("选定的数据集中没有可用的数值类型列。")
            return None, None, 0

        col1, col2 = st_obj.columns(2)

        with col1:

            # 1. 滞后变量
            lagged_var_key = f'{data_name}_lagged_variable'
            lagged_var_current_selection = self.get_state(lagged_var_key, series_options_all[0] if series_options_all else None)
            try:
                lagged_var_idx = series_options_all.index(lagged_var_current_selection) if lagged_var_current_selection in series_options_all else 0
            except ValueError:
                lagged_var_idx = 0

            selected_lagged_variable = st_obj.selectbox(
                "**选择滞后变量 (被预测的变量)**",
                options=series_options_all,
                key=f"tlc_{data_name}_lagged_variable_widget",
                index=lagged_var_idx
            )
            self.set_state(lagged_var_key, selected_lagged_variable)

            # 2. 领先变量
            leading_var_key = f'{data_name}_leading_variable'
            leading_var_current_selection = self.get_state(leading_var_key, series_options_all[1] if len(series_options_all) > 1 else series_options_all[0])
            try:
                leading_var_idx = series_options_all.index(leading_var_current_selection) if leading_var_current_selection in series_options_all else (1 if len(series_options_all) > 1 else 0)
            except ValueError:
                leading_var_idx = 1 if len(series_options_all) > 1 else 0

            selected_leading_variable = st_obj.selectbox(
                "**选择领先变量 (预测变量)**",
                options=series_options_all,
                key=f"tlc_{data_name}_leading_variable_widget",
                index=leading_var_idx
            )
            self.set_state(leading_var_key, selected_leading_variable)

        with col2:
            # 3. 最大滞后期数
            max_lags_key = f'{data_name}_max_lags'
            max_allowed = min(50, len(data) // 4)
            default_max_lags = min(12, max_allowed)  # 确保默认值不超过最大允许值
            max_lags_current = self.get_state(max_lags_key, default_max_lags)
            # 确保当前值不超过最大允许值
            max_lags_current = min(max_lags_current, max_allowed)

            max_lags = st_obj.number_input(
                "**最大滞后期数**",
                min_value=1,
                max_value=max_allowed,
                value=max_lags_current,
                step=1,
                key=f"tlc_{data_name}_max_lags_widget"
            )
            self.set_state(max_lags_key, max_lags)

            # 添加说明
            st_obj.info("[INFO] 最大滞后期数决定了分析的时间范围，建议设置为数据长度的1/4左右")

        return selected_lagged_variable, selected_leading_variable, max_lags

    def plot_correlation_chart(self, st_obj, correlations: List[float], lags: List[int],
                              lagged_var: str, leading_var: str):
        """
        绘制相关性图表

        Args:
            st_obj: Streamlit对象
            correlations: 相关系数列表
            lags: 滞后期列表
            lagged_var: 滞后变量名
            leading_var: 领先变量名
        """
        try:
            fig, ax = plt.subplots(figsize=(12, 6))

            # 绘制柱状图
            bars = ax.bar(lags, correlations, alpha=0.7, color='steelblue', edgecolor='black', linewidth=0.5)

            # 标记最大相关系数
            if correlations:
                max_corr_idx = np.argmax(np.abs(correlations))
                max_corr = correlations[max_corr_idx]
                max_lag = lags[max_corr_idx]

                bars[max_corr_idx].set_color('red')
                ax.annotate(f'最大相关性\n滞后期: {max_lag}\n相关系数: {max_corr:.3f}',
                           xy=(max_lag, max_corr),
                           xytext=(max_lag, max_corr + 0.1 * np.sign(max_corr)),
                           arrowprops=dict(arrowstyle='->', color='red'),
                           fontsize=10, ha='center')

            ax.axhline(0, color='black', linewidth=0.8, linestyle='--')
            ax.set_xlabel("滞后/超前阶数 (Lag)")
            ax.set_ylabel("皮尔逊相关系数")
            ax.set_title(f"时差相关性: {lagged_var} vs {leading_var}")
            ax.grid(True, linestyle=':', alpha=0.6)

            plt.tight_layout()
            st_obj.pyplot(fig)
            plt.close(fig)

        except Exception as e:
            logger.error(f"绘制相关性图表失败: {e}")
            st_obj.error(f"绘制图表失败: {str(e)}")

    def render_analysis_results(self, st_obj, results: Dict[str, Any]):
        """
        渲染分析结果

        Args:
            st_obj: Streamlit对象
            results: 分析结果
        """
        if not results:
            st_obj.warning("没有分析结果可显示")
            return

        col1, col2 = st_obj.columns(2)

        with col2:
            st_obj.markdown("### 分析结果")

            # 显示最优滞后期
            optimal_lag = results.get('optimal_lag', 'N/A')
            max_correlation = results.get('max_correlation', 'N/A')

            if optimal_lag != 'N/A' and max_correlation != 'N/A':
                st_obj.metric("最优滞后期", optimal_lag)
                st_obj.metric("最大相关系数", f"{max_correlation:.4f}")

                # 解释结果
                if optimal_lag > 0:
                    interpretation = f"领先变量领先滞后变量 {optimal_lag} 期"
                elif optimal_lag < 0:
                    interpretation = f"领先变量滞后于滞后变量 {abs(optimal_lag)} 期"
                else:
                    interpretation = "两变量同步变化"

                st_obj.info(f"**解释:** {interpretation}")

            # 显示相关性表格
            correlations = results.get('correlations', [])
            lags = results.get('lags', [])

            if correlations and lags:
                corr_df = pd.DataFrame({
                    '滞后期': lags,
                    '相关系数': correlations
                })
                corr_df['相关系数'] = corr_df['相关系数'].round(4)

                st_obj.markdown("**详细相关性数据:**")
                st_obj.dataframe(corr_df, width='stretch')

                # 提供下载功能，使用utf-8-sig编码避免中文乱码
                csv_string = corr_df.to_csv(index=False, encoding='utf-8-sig')
                csv_data = csv_string.encode('utf-8-sig')
                st_obj.download_button(
                    label="下载相关性数据",
                    data=csv_data,
                    file_name=f"correlation_analysis_{results.get('lagged_var', 'data')}.csv",
                    mime="text/csv",
                    key="download_correlation_data"
                )

        # 绘制图表
        correlations = results.get('correlations', [])
        lags = results.get('lags', [])
        lagged_var = results.get('lagged_var', 'Variable1')
        leading_var = results.get('leading_var', 'Variable2')

        if correlations and lags:
            st_obj.markdown("### 相关性图表")
            self.plot_correlation_chart(st_obj, correlations, lags, lagged_var, leading_var)

    def render_analysis_interface(self, st_obj, data: pd.DataFrame, data_name: str) -> Any:
        """
        渲染时间滞后相关性分析界面

        Args:
            st_obj: Streamlit对象
            data: 分析数据
            data_name: 数据名称

        Returns:
            Any: 分析结果
        """
        try:
            # 渲染参数设置
            lagged_var, leading_var, max_lags = self.render_analysis_parameters(st_obj, data, data_name)

            if lagged_var is None or leading_var is None:
                return None

            # 分析按钮
            analysis_key = f"correlation_analyze_btn_{data_name}"
            if st_obj.button("开始相关性分析", key=analysis_key, type="primary"):

                if lagged_var == leading_var:
                    st_obj.error("滞后变量和领先变量不能相同，请重新选择。")
                    return None

                with st_obj.spinner("正在进行时间滞后相关性分析..."):
                    # 调用后端函数
                    result_df = calculate_time_lagged_correlation(
                        data[lagged_var], data[leading_var], max_lags
                    )

                    # 提取结果
                    lags = result_df['Lag'].tolist()
                    correlations = result_df['Correlation'].tolist()

                    # 找到最大相关性和对应的滞后期
                    valid_correlations = result_df.dropna()
                    if not valid_correlations.empty:
                        max_corr_idx = valid_correlations['Correlation'].abs().idxmax()
                        optimal_lag = valid_correlations.loc[max_corr_idx, 'Lag']
                        max_correlation = valid_correlations.loc[max_corr_idx, 'Correlation']
                    else:
                        optimal_lag = 0
                        max_correlation = 0.0

                    # 构建结果
                    results = {
                        'correlations': correlations,
                        'lags': lags,
                        'optimal_lag': optimal_lag,
                        'max_correlation': max_correlation,
                        'lagged_var': lagged_var,
                        'leading_var': leading_var,
                        'max_lags': max_lags
                    }

                    # 保存结果到状态
                    self.set_state('results', results)
                    self.set_state('parameters', {
                        'lagged_var': lagged_var,
                        'leading_var': leading_var,
                        'max_lags': max_lags
                    })

                    st_obj.success("相关性分析完成！")

                    # 显示结果
                    self.render_analysis_results(st_obj, results)

                    return results

            # 显示之前的分析结果（如果有）
            previous_results = self.get_state('results')

            if previous_results:
                st_obj.markdown("---")
                st_obj.markdown("#### 上次分析结果")
                self.render_analysis_results(st_obj, previous_results)
                return previous_results

            return None

        except Exception as e:
            self.handle_error(st_obj, e, "渲染时间滞后相关性分析界面")
            return None


__all__ = ['CorrelationAnalysisComponent']
