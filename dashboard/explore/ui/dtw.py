# -*- coding: utf-8 -*-
"""
DTW分析组件
迁移自 dashboard/explore/dtw_frontend.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import logging
import io
from typing import List, Dict, Any, Optional, Tuple

from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore import perform_batch_dtw_calculation

logger = logging.getLogger(__name__)


class DTWAnalysisComponent(TimeSeriesAnalysisComponent):
    """DTW分析组件"""
    
    def __init__(self):
        super().__init__("dtw", "DTW分析")

    def clear_analysis_state(self):
        """
        清除所有DTW分析相关状态

        用于：
        - 参数变化时清除旧结果
        - 数据变化时清除缓存
        - 确保状态一致性
        """
        state_keys = [
            'auto_results',
            'target_series',
            'comparison_series',
            'dtw_params',
            'dtw_analysis_data',
            'dtw_paths_dict',
            'dtw_data_version'
        ]
        for key in state_keys:
            self.set_state(key, None)
        logger.info("[DTW] 已清除所有分析状态")

    @staticmethod
    def _parse_alignment_mode(alignment_mode_choice: str) -> Tuple[bool, bool]:
        """
        解析对齐模式选择（DRY helper）

        Args:
            alignment_mode_choice: 对齐模式选择 ('freq_align_strict', 'freq_align_loose', 'no_align')

        Returns:
            Tuple[enable_alignment, strict_alignment]
        """
        if alignment_mode_choice == "freq_align_strict":
            return True, True
        elif alignment_mode_choice == "freq_align_loose":
            return True, False
        else:  # no_align
            return False, False

    def smart_window_selection(self, target_length: int, comparison_length: int, series_length: int) -> Tuple[str, int]:
        """
        智能选择窗口类型和大小

        Args:
            target_length: 目标序列长度
            comparison_length: 比较序列长度
            series_length: 数据总长度

        Returns:
            Tuple[str, int]: (窗口类型, 窗口大小)
        """
        length_diff_ratio = abs(target_length - comparison_length) / max(target_length, comparison_length)

        # 根据长度差异选择窗口类型
        if length_diff_ratio > 0.3:  # 长度差异超过30%
            window_type = "Itakura"
        elif series_length >= 100:  # 长序列使用约束窗口
            window_type = "Sakoe-Chiba"
        else:  # 短序列可以使用无约束
            window_type = "无约束"

        # 根据序列长度选择窗口大小
        if window_type == "无约束":
            window_size = 0
        else:
            # 使用10%的序列长度作为窗口大小，最小5，最大50
            window_size = max(5, min(50, series_length // 10))

        return window_type, window_size


    def render_analysis_parameters(self, st_obj, data: pd.DataFrame, data_name: str):
        """
        渲染分析参数设置界面

        Args:
            st_obj: Streamlit对象
            data: 分析数据
            data_name: 数据名称

        Returns:
            分析参数字典
        """
        numeric_cols = [col for col in data.columns if pd.api.types.is_numeric_dtype(data[col])]

        if len(numeric_cols) < 2:
            st_obj.warning("DTW分析需要至少两个数值列")
            return None

        # 直接调用自动模式参数渲染（现在包含所有参数）
        params = self.render_auto_mode_parameters(st_obj, data, data_name, numeric_cols)

        return params

    def collect_analysis_parameters(self, st_obj, data: pd.DataFrame, data_name: str) -> Optional[dict]:
        """
        收集当前界面上的所有分析参数

        Args:
            st_obj: Streamlit对象
            data: 输入数据
            data_name: 数据名称

        Returns:
            dict: 当前界面参数字典，如果参数收集失败或验证失败则返回None
        """
        try:
            # 获取数值列
            numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()

            # 直接从st.session_state读取UI控件的值（而不是从统一状态管理器）
            # 因为Streamlit控件使用key参数时，值会自动保存到st.session_state
            target_series = st.session_state.get(f"dtw_{data_name}_auto_target_series")
            # 清理target_series的首尾空格
            if target_series and isinstance(target_series, str):
                target_series = target_series.strip()

            # 验证必需参数：目标序列
            if not target_series:
                logger.warning(f"[DTW参数收集] 目标序列未设置或为空")
                return None

            # 获取窗口约束参数（从下拉菜单读取）
            window_constraint_choice = st.session_state.get(f"dtw_{data_name}_window_constraint_choice", "是")
            enable_window_constraint = (window_constraint_choice == "是")
            # 只有当窗口约束启用时才获取radius，否则设为None
            # 这与render_auto_mode_parameters的行为保持一致，避免参数变化误判
            if enable_window_constraint:
                radius = st.session_state.get(f"dtw_{data_name}_radius", 10)
            else:
                radius = None

            # 获取对齐模式选择
            alignment_mode_choice = st.session_state.get(f"dtw_{data_name}_alignment_mode_choice", 'freq_align_strict')

            # 解析对齐模式
            if alignment_mode_choice == "freq_align_strict":
                enable_alignment = True
                strict_alignment = True
            elif alignment_mode_choice == "freq_align_loose":
                enable_alignment = True
                strict_alignment = False
            else:  # no_align
                enable_alignment = False
                strict_alignment = False

            alignment_mode = 'stat_align'  # 固定为统计对齐
            agg_method = st.session_state.get(f"dtw_{data_name}_freq_agg_method", 'mean')

            # 获取标准化参数
            standardization_method = st.session_state.get(f"dtw_{data_name}_standardization_method", 'zscore')
            enable_standardization = (standardization_method != 'none')

            # 距离度量在后端固定为euclidean，界面上无需设置
            # dist_metric_key = f"dtw_{data_name}_distance_metric"
            # distance_metric = st.session_state.get(dist_metric_key, 'euclidean')

            # 获取比较序列（所有除目标序列外的数值列）
            # 清理列名首尾空格，防止空格导致的匹配失败
            # 注意：必须先strip再比较，因为target_series已经被strip过了
            comparison_series = []
            if target_series:
                for col in numeric_cols:
                    col_cleaned = col.strip() if isinstance(col, str) else col
                    if col_cleaned != target_series:
                        comparison_series.append(col_cleaned)

            # 验证必需参数：比较序列不能为空
            if not comparison_series:
                logger.warning(f"[DTW参数收集] 比较序列为空（可能所有数值列都被选为目标序列）")
                return None

            return {
                'target_series': target_series,
                'comparison_series': comparison_series,
                'enable_window_constraint': enable_window_constraint,
                'radius': radius,
                'enable_alignment': enable_alignment,
                'alignment_mode': alignment_mode,
                'agg_method': agg_method,
                'strict_alignment': strict_alignment,
                'enable_standardization': enable_standardization,
                'standardization_method': standardization_method
                # 'distance_metric': distance_metric  # 移除：界面上不存在此参数
            }

        except Exception as e:
            # 如果获取参数失败，返回None（而不是空字典）
            logger.error(f"[DTW参数收集] 参数收集失败: {e}", exc_info=True)
            return None
    
    def render_auto_mode_parameters(self, st_obj, data: pd.DataFrame, data_name: str, numeric_cols: list):
        """渲染自动模式参数（新3列布局）"""

        # ========== 第一排：3列布局 ==========
        row1_col1, row1_col2, row1_col3 = st_obj.columns(3)

        # 第一排第一列：目标序列选择
        with row1_col1:
            target_series = st_obj.selectbox(
                "选择目标序列:",
                options=numeric_cols,
                key=f"dtw_{data_name}_auto_target_series"
            )

        # 第一排第二列：对齐模式
        with row1_col2:
            alignment_mode_choice = st_obj.selectbox(
                "对齐模式:",
                options=["freq_align_strict", "freq_align_loose", "no_align"],
                format_func=lambda x: {
                    "freq_align_strict": "频率对齐 + 时点对齐",
                    "freq_align_loose": "仅频率对齐",
                    "no_align": "不对齐"
                }[x],
                index=0,
                key=f"dtw_{data_name}_alignment_mode_choice",
                help="选择序列对齐方式"
            )

        # 第一排第三列：启用窗口约束
        with row1_col3:
            window_constraint_choice = st_obj.selectbox(
                "启用窗口约束:",
                options=["是", "否"],
                index=0,
                key=f"dtw_{data_name}_window_constraint_choice",
                help="限制DTW对齐路径在对角线附近，提高计算效率"
            )

        # ========== 第二排：3列布局 ==========
        row2_col1, row2_col2, row2_col3 = st_obj.columns(3)

        # 第二排第一列：聚合方法（条件显示）
        with row2_col1:
            if alignment_mode_choice in ["freq_align_strict", "freq_align_loose"]:
                agg_method = st_obj.selectbox(
                    "聚合方法:",
                    options=["mean", "last", "first", "sum", "median"],
                    format_func=lambda x: {
                        "mean": "平均值",
                        "last": "最后值",
                        "first": "首个值",
                        "sum": "求和",
                        "median": "中位数"
                    }[x],
                    key=f"dtw_{data_name}_freq_agg_method",
                    help="将高频数据聚合到低频时使用的方法"
                )
            else:
                agg_method = "mean"  # 不对齐时使用默认值

        # 第二排第二列：标准化方法
        with row2_col2:
            standardization_method = st_obj.selectbox(
                "标准化方法:",
                options=["zscore", "minmax", "none"],
                format_func=lambda x: {
                    "zscore": "Z-Score标准化 (推荐)",
                    "minmax": "Min-Max归一化",
                    "none": "不标准化"
                }[x],
                index=0,
                key=f"dtw_{data_name}_standardization_method",
                help="选择数据标准化方法"
            )

        # 第二排第三列：Radius设置（条件显示）
        enable_window_constraint = (window_constraint_choice == "是")

        with row2_col3:
            if enable_window_constraint:
                radius = st_obj.number_input(
                    "Radius (窗口大小):",
                    min_value=1,
                    max_value=min(50, len(data) // 2),
                    value=max(5, len(data) // 10),
                    key=f"dtw_{data_name}_radius",
                    help="限制对齐路径在主对角线上下各radius个单位内"
                )
            else:
                radius = None

        # 解析对齐模式（使用DRY helper）
        enable_alignment, strict_alignment = self._parse_alignment_mode(alignment_mode_choice)

        # 计算比较序列
        comparison_series = [col for col in numeric_cols if col != target_series]

        # 计算是否启用标准化
        enable_standardization = (standardization_method != 'none')

        return {
            'mode': 'auto',
            'target_series': target_series,
            'comparison_series': comparison_series,
            'enable_window_constraint': enable_window_constraint,
            'radius': radius,
            'enable_alignment': enable_alignment,
            'alignment_mode': 'stat_align',
            'agg_method': agg_method,
            'strict_alignment': strict_alignment,
            'enable_standardization': enable_standardization,
            'standardization_method': standardization_method
        }


    def perform_auto_dtw_analysis(self, st_obj, data: pd.DataFrame, target_series: str, comparison_series: list, enable_window_constraint: bool, radius: int = None, freq_options: dict = None, std_options: dict = None):
        """执行自动DTW分析，包含频率处理"""
        results = []

        # 设置默认频率选项
        if freq_options is None:
            freq_options = {'enable_alignment': True, 'alignment_mode': 'stat_align', 'agg_method': 'mean', 'strict_alignment': True}

        # 设置默认标准化选项
        if std_options is None:
            std_options = {'enable_standardization': True, 'standardization_method': 'zscore'}

        # 准备目标序列数据
        target_data = data[target_series].dropna()
        target_length = len(target_data)

        # 设置窗口约束参数
        if enable_window_constraint and radius is not None:
            window_type_param = "固定大小窗口 (Radius约束)"
            window_size_param = radius
        else:
            window_type_param = "无限制"
            window_size_param = None

        # 执行DTW计算（现在包含频率处理和标准化）
        dtw_results, paths_dict, errors, warnings = perform_batch_dtw_calculation(
            df_input=data,
            target_series_name=target_series,
            comparison_series_names=comparison_series,
            window_type_param=window_type_param,
            window_size_param=window_size_param,
            dist_metric_name_param="euclidean",
            dist_metric_display_param="欧氏距离",
            enable_freq_alignment=freq_options.get('enable_alignment', True),
            freq_alignment_mode=freq_options.get('alignment_mode', 'stat_align'),
            freq_agg_method=freq_options.get('agg_method', 'mean'),
            strict_alignment=freq_options.get('strict_alignment', True),
            standardization_method=std_options.get('standardization_method', 'zscore')
        )

        # 转换结果格式
        for result in dtw_results:
            comp_var = result.get('对比变量', 'Unknown')
            dtw_distance = result.get('DTW距离', 'Error')

            if isinstance(dtw_distance, (int, float)) and not np.isnan(dtw_distance) and np.isfinite(dtw_distance):
                # 获取路径长度
                path_length = 'N/A'
                if comp_var in paths_dict:
                    path_data = paths_dict[comp_var]
                    if 'path' in path_data and path_data['path']:
                        path_length = len(path_data['path'])

                # 计算标准化DTW距离（使用路径长度）
                if isinstance(path_length, int) and path_length > 0:
                    normalized_dtw = round(dtw_distance / path_length, 4)
                else:
                    normalized_dtw = 'Error'

                results.append({
                    '变量名': comp_var,
                    '窗口约束': '启用' if enable_window_constraint else '禁用',
                    'Radius': radius if enable_window_constraint else 'N/A',
                    'DTW距离': round(dtw_distance, 4),
                    '对齐路径长度': path_length,
                    '标准化DTW距离': normalized_dtw,
                    '分析状态': '计算成功'
                })
            else:
                results.append({
                    '变量名': comp_var,
                    '窗口约束': '启用' if enable_window_constraint else '禁用',
                    'Radius': radius if enable_window_constraint else 'N/A',
                    'DTW距离': 'Error',
                    '对齐路径长度': 'Error',
                    '标准化DTW距离': 'Error',
                    '分析状态': '计算失败'
                })

        # 仅显示重要的错误信息
        if errors:
            for error in errors:
                st_obj.error(error)

        # 缓存分析时使用的数据和路径字典，避免第二次重复计算
        # 添加数据版本号，用于检测数据是否变化
        data_version = hash(tuple(data.columns.tolist() + [len(data)]))
        self.set_state('dtw_analysis_data', data.copy())
        self.set_state('dtw_paths_dict', paths_dict)
        self.set_state('dtw_data_version', data_version)
        logger.info(f"[DTW] 已缓存分析数据（列数: {len(data.columns)}, 版本: {data_version}）和路径字典（{len(paths_dict)}个变量）")

        return results

    def render_download_button(self, st_obj, results, params, data_name):
        """渲染下载按钮"""
        try:
            # 自动模式：下载批量结果
            if isinstance(results, list) and results:
                # 转换为DataFrame
                df = pd.DataFrame(results)

                # 生成CSV数据 - 使用UTF-8 BOM编码确保Excel正确显示中文
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8')
                csv_data = '\ufeff' + csv_buffer.getvalue()  # 添加BOM

                # 生成文件名
                target_name = params.get('target_series', 'unknown') if params else 'unknown'
                filename = f"DTW批量分析结果_{target_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"

                st_obj.download_button(
                    label="下载结果",
                    data=csv_data.encode('utf-8-sig'),
                    file_name=filename,
                    mime="text/csv",
                    type="primary",  # 与开始分析按钮颜色样式相同
                    key=f"dtw_download_auto_{data_name}_{len(results)}",  # 添加结果长度确保唯一性
                    help="下载DTW批量分析结果为CSV文件"
                )
            else:
                # 没有结果时显示禁用的按钮
                st_obj.download_button(
                    label="下载结果",
                    data="",
                    file_name="no_results.csv",
                    mime="text/csv",
                    type="primary",  # 与开始分析按钮颜色样式相同
                    key=f"dtw_download_auto_disabled_{data_name}",
                    help="暂无分析结果可下载",
                    disabled=True
                )

        except Exception as e:
            logger.error(f"生成下载按钮失败: {e}")
            st_obj.error(f"下载功能暂时不可用: {str(e)}")

    def render_auto_results(self, st_obj, results: list, target_series: str, params: dict = None, data_name: str = None):
        """渲染自动模式结果"""
        if not results:
            st_obj.warning("没有分析结果")
            return

        # 转换为DataFrame并排序
        results_df = pd.DataFrame(results)

        # 过滤掉错误的结果进行排序
        valid_results = results_df[results_df['标准化DTW距离'] != 'Error'].copy()
        error_results = results_df[results_df['标准化DTW距离'] == 'Error'].copy()

        if not valid_results.empty:
            # 按标准化DTW距离排序（从小到大，越小越相似）
            valid_results = valid_results.sort_values('标准化DTW距离')

            # 合并结果
            final_results = pd.concat([valid_results, error_results], ignore_index=True)
        else:
            final_results = results_df

        # 显示统计信息在表格上方
        if not valid_results.empty:
            col1, col2, col3, col4, col5 = st_obj.columns(5)
            with col1:
                st_obj.metric("成功分析", len(valid_results))
            with col2:
                st_obj.metric("最小标准化DTW距离", f"{valid_results['标准化DTW距离'].min():.4f}")
            with col3:
                st_obj.metric("最大标准化DTW距离", f"{valid_results['标准化DTW距离'].max():.4f}")
            with col4:
                # 显示实际使用的窗口设置
                window_constraint = valid_results['窗口约束'].iloc[0] if '窗口约束' in valid_results.columns else '未知'
                st_obj.metric("窗口约束", f"{window_constraint}")
            with col5:
                radius = valid_results['Radius'].iloc[0] if 'Radius' in valid_results.columns else '未知'
                st_obj.metric("Radius", f"{radius}")

        # 显示结果表格
        # 转换混合类型列为字符串以避免Arrow序列化错误
        display_results = final_results.copy()
        for col in ['DTW距离', '对齐路径长度', '标准化DTW距离']:
            if col in display_results.columns:
                display_results[col] = display_results[col].astype(str)

        st_obj.dataframe(
            display_results,
            width='stretch',
            hide_index=True
        )

        # 在表格下方添加下载按钮（与开始分析按钮颜色样式相同）
        if params and data_name:
            self.render_download_button(st_obj, results, params, data_name)

    def render_comparison_selection_and_plot(self, st_obj, data: pd.DataFrame, results: list, target_series: str, comparison_series: list, data_name: str):
        """
        渲染比较序列选择和DTW对比图

        Args:
            st_obj: Streamlit对象
            data: 原始数据
            results: DTW分析结果列表
            target_series: 目标序列名称
            comparison_series: 比较序列列表
            data_name: 数据名称（用于读取当前界面参数）
        """
        if not results or not comparison_series:
            return

        st_obj.markdown("---")
        st_obj.markdown("#### DTW对比图")
        
        # 创建比较序列选择下拉菜单
        col1, col2 = st_obj.columns([1, 2])
        
        with col1:
            # 获取所有有效的比较序列（去除错误的结果）
            valid_comparison_series = []
            for result in results:
                var_name = result.get('变量名')
                dtw_distance = result.get('DTW距离')
                if var_name and dtw_distance != 'Error' and isinstance(dtw_distance, (int, float)):
                    # 去除变量名首尾的空格（修复空格导致的匹配失败问题）
                    var_name = var_name.strip() if isinstance(var_name, str) else var_name
                    valid_comparison_series.append(var_name)

            if valid_comparison_series:
                selected_comparison = st_obj.selectbox(
                    "选择比较序列:",
                    options=valid_comparison_series,
                    key=f"dtw_{data_name}_comparison_selection",
                    help="选择一个序列查看DTW对比图"
                )
            else:
                st_obj.warning("没有有效的比较结果可供显示")
                return
        
        with col2:
            # 显示选中比较序列的DTW信息
            selected_result = None
            for result in results:
                # 防御性strip，避免旧缓存结果的变量名未被清理
                result_var_name = result.get('变量名')
                if isinstance(result_var_name, str):
                    result_var_name = result_var_name.strip()
                if result_var_name == selected_comparison:
                    selected_result = result
                    break
            
            if selected_result:
                dtw_distance = selected_result.get('DTW距离')
                normalized_distance = selected_result.get('标准化DTW距离')

                info_col1, info_col2 = st_obj.columns(2)
                with info_col1:
                    st_obj.metric("DTW距离", f"{dtw_distance:.4f}" if isinstance(dtw_distance, (int, float)) else str(dtw_distance))
                with info_col2:
                    st_obj.metric("标准化DTW距离", f"{normalized_distance:.4f}" if isinstance(normalized_distance, (int, float)) else str(normalized_distance))
        
        # 绘制DTW对比图
        # 重新读取当前界面参数（使用实时参数而不是保存的旧参数）
        # 直接从st.session_state读取当前界面的窗口约束设置
        window_constraint_choice = st.session_state.get(f"dtw_{data_name}_window_constraint_choice", "是")
        enable_constraint = (window_constraint_choice == "是")
        radius = st.session_state.get(f"dtw_{data_name}_radius", 10)

        # 直接从st.session_state读取频率和标准化参数
        alignment_mode_choice = st.session_state.get(f"dtw_{data_name}_alignment_mode_choice", 'freq_align_strict')

        # 解析对齐模式（使用DRY helper）
        enable_alignment, strict_alignment = self._parse_alignment_mode(alignment_mode_choice)

        freq_options = {
            'enable_alignment': enable_alignment,
            'alignment_mode': 'stat_align',
            'agg_method': st.session_state.get(f"dtw_{data_name}_freq_agg_method", 'mean'),
            'strict_alignment': strict_alignment
        }

        standardization_method = st.session_state.get(f"dtw_{data_name}_standardization_method", 'zscore')
        std_options = {
            'enable_standardization': (standardization_method != 'none'),
            'standardization_method': standardization_method
        }

        # 设置窗口约束参数
        if enable_constraint and radius is not None:
            window_type_param = "固定大小窗口 (Radius约束)"
            window_size_param = radius
        else:
            window_type_param = "无限制"
            window_size_param = None

        # 诊断日志：检查selected_comparison是否在data中
        logger.info(f"[DTW诊断] 用户选择: {selected_comparison}")
        logger.info(f"[DTW诊断] 数据集列数: {len(data.columns)}")
        logger.info(f"[DTW诊断] 是否存在于数据集: {selected_comparison in data.columns}")

        # 如果不存在，记录最相似的列名并使用缓存数据
        if selected_comparison not in data.columns:
            numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
            from difflib import SequenceMatcher
            similarities = [(col, SequenceMatcher(None, selected_comparison, col).ratio())
                            for col in numeric_cols]
            top3 = sorted(similarities, key=lambda x: x[1], reverse=True)[:3]
            logger.warning(f"[DTW诊断] 变量不存在！最相似的3个列名: {top3}")

        # 优先使用缓存的路径字典，避免重复计算
        # 但是需要先检查数据版本是否匹配，避免使用旧数据的路径
        cached_paths_dict = self.get_state('dtw_paths_dict')
        cached_version = self.get_state('dtw_data_version')
        current_version = hash(tuple(data.columns.tolist() + [len(data)]))

        if cached_paths_dict and selected_comparison in cached_paths_dict and cached_version == current_version:
            logger.info(f"[DTW] 使用缓存的路径数据（版本匹配: {current_version}，无需重新计算）: {selected_comparison}")
            paths_dict = cached_paths_dict
            errors = []
            warnings = []
        else:
            # 缓存中没有或版本不匹配，需要重新计算
            if cached_version != current_version:
                logger.info(f"[DTW] 缓存版本不匹配（缓存: {cached_version}, 当前: {current_version}），重新计算: {selected_comparison}")
            else:
                logger.info(f"[DTW] 缓存中没有路径数据，重新计算: {selected_comparison}")

            # 使用缓存的分析数据（如果存在且版本匹配）
            cached_data = self.get_state('dtw_analysis_data')

            if cached_data is not None and cached_version == current_version:
                logger.info(f"[DTW] 使用缓存的分析数据（版本匹配: {current_version}）")
                data_for_calc = cached_data
                # 确保缓存数据的列名也被清理（防止旧缓存列名带空格）
                data_for_calc.columns = data_for_calc.columns.str.strip() if hasattr(data_for_calc.columns, 'str') else data_for_calc.columns
                logger.info(f"[DTW] 已清理缓存数据列名，列数: {len(data_for_calc.columns)}")
            elif cached_data is not None and cached_version != current_version:
                logger.warning(f"[DTW] 缓存数据版本不匹配（缓存: {cached_version}, 当前: {current_version}），使用当前data")
                data_for_calc = data
                # 确保当前data的列名也被清理
                data_for_calc.columns = data_for_calc.columns.str.strip() if hasattr(data_for_calc.columns, 'str') else data_for_calc.columns
                logger.info(f"[DTW] 已清理当前数据列名，列数: {len(data_for_calc.columns)}")
            else:
                logger.warning("[DTW] 未找到缓存数据，使用当前data")
                data_for_calc = data
                # 确保当前data的列名也被清理
                data_for_calc.columns = data_for_calc.columns.str.strip() if hasattr(data_for_calc.columns, 'str') else data_for_calc.columns
                logger.info(f"[DTW] 已清理当前数据列名，列数: {len(data_for_calc.columns)}")

            # 为单个比较序列重新计算DTW以获取路径信息
            dtw_results, paths_dict, errors, warnings = perform_batch_dtw_calculation(
            df_input=data_for_calc,
            target_series_name=target_series,
            comparison_series_names=[selected_comparison],
            window_type_param=window_type_param,
            window_size_param=window_size_param,
            dist_metric_name_param="euclidean",
            dist_metric_display_param="欧氏距离",
            enable_freq_alignment=freq_options.get('enable_alignment', True),
            freq_alignment_mode=freq_options.get('alignment_mode', 'stat_align'),
            freq_agg_method=freq_options.get('agg_method', 'mean'),
            strict_alignment=freq_options.get('strict_alignment', True),
            standardization_method=std_options.get('standardization_method', 'zscore')
        )

        # 获取路径数据
        if selected_comparison in paths_dict:
            path_data = paths_dict[selected_comparison]
            s1_data = path_data.get('target_np')
            s2_data = path_data.get('compare_np')
            path = path_data.get('path', [])
            target_time_index = path_data.get('target_index')
            compare_time_index = path_data.get('compare_index')

            if s1_data is not None and s2_data is not None and path:
                # 使用DTW计算时实际使用的时间索引
                self.plot_dtw_path(st_obj, s1_data, s2_data, path, target_series, selected_comparison,
                                 target_time_index, compare_time_index)
            else:
                warning_msg = f"路径数据不完整 - s1_data存在: {s1_data is not None}, s2_data存在: {s2_data is not None}, path长度: {len(path) if path else 0}"
                logger.warning(f"[DTW图表] {warning_msg}")
                st_obj.warning(f"无法获取 {selected_comparison} 的DTW路径数据")
        else:
            logger.warning(f"[DTW图表] 在paths_dict中未找到 {selected_comparison}")

            # 提供更友好的错误提示和建议
            if errors:
                st_obj.error(f"DTW计算失败：{errors[0]}")
            else:
                st_obj.error(f"无法找到 '{selected_comparison}' 的DTW计算结果")

            # 如果变量不在数据集中，显示最相似的变量作为建议
            if selected_comparison not in data_for_calc.columns:
                numeric_cols = data_for_calc.select_dtypes(include=[np.number]).columns.tolist()
                from difflib import SequenceMatcher
                suggestions = sorted(
                    [(col, SequenceMatcher(None, selected_comparison, col).ratio())
                     for col in numeric_cols],
                    key=lambda x: x[1],
                    reverse=True
                )[:3]

                if suggestions and suggestions[0][1] > 0.7:
                    st_obj.info("数据集中不存在该变量，您是否想选择以下相似变量？")
                    for col, ratio in suggestions:
                        st_obj.write(f"- {col} (相似度: {ratio:.1%})")

            # 显示调试信息（仅在有警告时）
            if warnings:
                with st_obj.expander("查看详细警告信息"):
                    for warning in warnings:
                        st_obj.text(warning)

    def plot_dtw_path(self, st_obj, s1_np, s2_np, path, s1_name, s2_name, s1_time_index=None, s2_time_index=None):
        """绘制DTW路径图（使用Plotly）

        Args:
            st_obj: Streamlit对象
            s1_np: 目标序列数据
            s2_np: 比较序列数据
            path: DTW对齐路径
            s1_name: 目标序列名称
            s2_name: 比较序列名称
            s1_time_index: 目标序列的时间索引（pd.Index或None）
            s2_time_index: 比较序列的时间索引（pd.Index或None）
        """
        try:
            # 创建Plotly图表
            fig = go.Figure()

            # 创建X轴索引（必须使用DatetimeIndex）
            if not isinstance(s1_time_index, pd.DatetimeIndex):
                raise ValueError(f"目标序列时间索引类型错误: {type(s1_time_index).__name__}，必须为DatetimeIndex")
            if not isinstance(s2_time_index, pd.DatetimeIndex):
                raise ValueError(f"比较序列时间索引类型错误: {type(s2_time_index).__name__}，必须为DatetimeIndex")

            # pandas DatetimeIndex: 转换为月初
            s1_x = s1_time_index.to_period('M').to_timestamp()
            s2_x = s2_time_index.to_period('M').to_timestamp()

            # 格式化时间用于hover显示
            s1_hover_times = [t.strftime('%Y-%m') for t in s1_x]
            s2_hover_times = [t.strftime('%Y-%m') for t in s2_x]

            # 添加目标序列（序列1）- 实线
            fig.add_trace(go.Scatter(
                x=s1_x,
                y=s1_np,
                mode='lines+markers',
                name=s1_name,
                line=dict(color='#1f77b4', width=3, dash='solid'),  # 实线
                marker=dict(size=8, symbol='circle'),  # 从6加大到8
                customdata=s1_hover_times,
                hovertemplate='<b>%{fullData.name}</b><br>时间: %{customdata}<br>数值: %{y:.4f}<extra></extra>'
            ))

            # 添加比较序列（序列2）- 虚线
            fig.add_trace(go.Scatter(
                x=s2_x,
                y=s2_np,
                mode='lines+markers',
                name=s2_name,
                line=dict(color='#ff7f0e', width=3, dash='dash'),  # 虚线
                marker=dict(size=8, symbol='square'),  # 从6加大到8
                customdata=s2_hover_times,
                hovertemplate='<b>%{fullData.name}</b><br>时间: %{customdata}<br>数值: %{y:.4f}<extra></extra>'
            ))

            # 添加DTW对齐路径（灰色虚线）
            for idx1, idx2 in path:
                if idx1 < len(s1_np) and idx2 < len(s2_np):
                    fig.add_trace(go.Scatter(
                        x=[s1_x[idx1], s2_x[idx2]],
                        y=[s1_np[idx1], s2_np[idx2]],
                        mode='lines',
                        line=dict(color='grey', width=1, dash='dash'),
                        opacity=0.3,
                        showlegend=False,
                        hoverinfo='skip'
                    ))

            # 更新布局
            fig.update_layout(
                title=dict(
                    text=f"DTW对齐路径: {s1_name} vs {s2_name}",
                    font=dict(size=16, family='Microsoft YaHei, SimHei, sans-serif'),
                    x=0.5,  # 标题居中
                    xanchor='center'
                ),
                xaxis=dict(
                    title=None,  # 取消X轴标题
                    gridcolor='rgba(128, 128, 128, 0.2)',
                    showgrid=True,
                    tickfont=dict(size=13, family='Microsoft YaHei, SimHei, sans-serif'),  # X轴刻度字体加大
                    tickformat='%Y-%m'  # 时间格式：年-月
                ),
                yaxis=dict(
                    title=dict(
                        text='Z值',
                        font=dict(size=12, family='Microsoft YaHei, SimHei, sans-serif')
                    ),
                    gridcolor='rgba(128, 128, 128, 0.2)',
                    showgrid=True
                ),
                hovermode='closest',
                plot_bgcolor='white',
                height=500,
                margin=dict(l=60, r=40, t=80, b=100),  # 增加底部边距以容纳图例
                legend=dict(
                    orientation='h',
                    yanchor='top',
                    y=-0.15,  # 放在图表下方
                    xanchor='center',
                    x=0.5,
                    font=dict(size=12, family='Microsoft YaHei, SimHei, sans-serif'),  # 字体从11号加大到12号
                    itemwidth=50  # 增加图例项宽度，使色块和文字更大
                )
            )

            # 显示图表
            st_obj.plotly_chart(fig, width='stretch')

        except ValueError as ve:
            # 用户友好的错误提示（不显示技术堆栈）
            error_msg = f"绘制DTW路径图失败: {str(ve)}"
            logger.warning(f"[DTW绘图] {error_msg}")
            st_obj.error(error_msg)
        except Exception as e:
            error_msg = f"绘制DTW路径图失败: {str(e)}"
            logger.error(f"[DTW绘图] {error_msg}", exc_info=True)
            st_obj.error(error_msg)
    
    
    def render_analysis_interface(self, st_obj, data: pd.DataFrame, data_name: str) -> Any:
        """渲染DTW分析界面"""

        try:
            # 防御性检查：确保列名已清理（上游bivariate_page.py应该已处理）
            data = data.copy()
            if hasattr(data.columns, 'str'):
                # 检查是否需要清理（先保存原始列名，再比较）
                original_columns = data.columns.tolist()
                cleaned_columns = data.columns.str.strip().tolist()
                if original_columns != cleaned_columns:
                    logger.warning(f"[DTW界面] 检测到列名包含空格，已清理。建议检查上游数据处理流程。")
                    data.columns = cleaned_columns
            logger.debug(f"[DTW界面] 数据准备完成，列数: {len(data.columns)}")

            # 渲染参数设置
            params = self.render_analysis_parameters(st_obj, data, data_name)

            if params is None:
                return None

            # 分析按钮
            analysis_key = f"dtw_analyze_btn_{data_name}"
            analyze_clicked = st_obj.button("开始分析", key=analysis_key, type="primary")

            # 初始化分析结果变量
            current_results = None

            if analyze_clicked:
                # 提取频率选项
                freq_options = {
                    'enable_alignment': params.get('enable_alignment', True),
                    'alignment_mode': params.get('alignment_mode', 'stat_align'),
                    'agg_method': params.get('agg_method', 'mean'),
                    'strict_alignment': params.get('strict_alignment', True)
                }

                # 提取标准化选项
                std_options = {
                    'enable_standardization': params.get('enable_standardization', True),
                    'standardization_method': params.get('standardization_method', 'zscore')
                }
                
                with st_obj.spinner("正在进行批量DTW分析..."):
                    try:
                        results = self.perform_auto_dtw_analysis(
                            st_obj, data, params['target_series'], params['comparison_series'], 
                            params['enable_window_constraint'], params['radius'], freq_options, std_options
                        )

                        # 保存结果到状态
                        self.set_state('auto_results', results)
                        self.set_state('target_series', params['target_series'])
                        self.set_state('comparison_series', params['comparison_series'])
                        self.set_state('dtw_params', params)
                        
                        # 设置当前结果
                        current_results = results

                        # 显示结果
                        self.render_auto_results(st_obj, results, params['target_series'], params, data_name)

                        # 添加比较序列选择和DTW图显示
                        self.render_comparison_selection_and_plot(st_obj, data, results, params['target_series'], params['comparison_series'], data_name)

                        return results

                    except Exception as e:
                        error_msg = f"批量DTW分析失败: {str(e)}"
                        st_obj.error(error_msg)
                        logger.error(error_msg)
                        return None
            
            # 检查是否有之前的分析结果，并验证参数是否发生变化
            previous_auto_results = self.get_state('auto_results')
            previous_target = self.get_state('target_series')
            previous_comparison_series = self.get_state('comparison_series')
            previous_params = self.get_state('dtw_params')

            logger.info(f"DTW状态检查 - 是否有之前的结果: {previous_auto_results is not None}")

            if previous_auto_results and previous_target:
                # 获取当前界面参数
                current_params = self.collect_analysis_parameters(st_obj, data, data_name)

                # 验证参数收集是否成功
                if current_params is None:
                    logger.warning("[DTW] 无法收集当前参数（UI控件可能未初始化），清除之前的结果")
                    self.clear_analysis_state()
                    return None

                logger.info(f"DTW参数收集 - 当前参数: {list(current_params.keys())}")

                # 检查关键参数是否发生变化
                params_changed = False
                if previous_params is None:
                    params_changed = True
                    logger.info("DTW参数检查 - 之前无参数记录，判定为参数已变化")
                else:
                    # 检查影响DTW计算的关键参数
                    # alignment_mode_choice已经包含了enable_alignment和strict_alignment的信息
                    # enable_standardization是从standardization_method派生的，只需检查standardization_method
                    key_params = ['target_series', 'enable_window_constraint', 'radius',
                                'standardization_method',
                                'enable_alignment', 'strict_alignment', 'agg_method']

                    # 检查关键参数是否变化（带类型标准化）
                    for param in key_params:
                        current_val = current_params.get(param)
                        previous_val = previous_params.get(param)

                        # 对数字类型进行标准化比较（避免int/float误判）
                        if isinstance(current_val, (int, float)) and isinstance(previous_val, (int, float)):
                            if abs(current_val - previous_val) > 1e-9:
                                logger.info(f"DTW参数变化检测 - {param}: {previous_val} → {current_val} (数字类型)")
                                params_changed = True
                                break
                        elif current_val != previous_val:
                            logger.info(f"DTW参数变化检测 - {param}: {previous_val} ({type(previous_val).__name__}) → {current_val} ({type(current_val).__name__})")
                            params_changed = True
                            break

                    # 添加调试信息
                    if not params_changed:
                        logger.info("DTW参数检查 - 无变化，保持现有结果")

                    # 检查比较序列是否变化（注意：需要对列名进行空格清理以匹配保存时的处理）
                    # 必须先strip再比较，因为target_series已经被strip过了
                    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
                    current_comparison = []
                    target_series_value = current_params.get('target_series')
                    for col in numeric_cols:
                        col_cleaned = col.strip() if isinstance(col, str) else col
                        if col_cleaned != target_series_value:
                            current_comparison.append(col_cleaned)
                    previous_comparison_set = set(previous_comparison_series or [])
                    current_comparison_set = set(current_comparison)
                    if current_comparison_set != previous_comparison_set:
                        logger.info(f"DTW参数变化检测 - 比较序列发生变化: 当前{len(current_comparison_set)}个 vs 之前{len(previous_comparison_set)}个")
                        params_changed = True

                if params_changed:
                    # 参数已变化，使用统一的状态清理方法
                    logger.info("DTW参数已变化 - 清除之前的分析结果")
                    self.clear_analysis_state()
                else:
                    # 参数未变化，显示之前的结果
                    logger.info("DTW参数未变化 - 显示之前的分析结果")
                    st_obj.markdown("---")
                    st_obj.markdown("#### 分析结果")
                    self.render_auto_results(st_obj, previous_auto_results, previous_target, previous_params, data_name)

                    # 添加比较序列选择和DTW图显示（使用当前界面参数）
                    self.render_comparison_selection_and_plot(st_obj, data, previous_auto_results, previous_target, previous_comparison_series, data_name)

                    return previous_auto_results

            return None
            
        except Exception as e:
            self.handle_error(st_obj, e, "渲染DTW分析界面")
            return None


__all__ = ['DTWAnalysisComponent']
