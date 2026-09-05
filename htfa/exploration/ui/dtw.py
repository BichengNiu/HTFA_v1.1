"""
DTW分析组件
迁移自 htfa/exploration/dtw_frontend.py
"""

import logging
from difflib import SequenceMatcher
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom
from htfa.exploration.analysis.dtw_batch import perform_batch_dtw_calculation
from htfa.exploration.core.series_utils import fingerprint_dataframe
from htfa.exploration.ui.base import TimeSeriesAnalysisComponent
from htfa.exploration.ui.multivariate_state import (
    build_dtw_backend_options,
    build_dtw_result_signature,
    parse_dtw_alignment_mode,
)
from htfa.exploration.ui.result_presenters import (
    encode_csv_with_bom,
    format_dtw_results,
    prepare_dtw_display,
)

logger = logging.getLogger(__name__)


def _valid_comparison_names(results: list[dict[str, Any]]) -> list[str]:
    names = []
    for result in results:
        name = result.get("变量名")
        distance = result.get("DTW距离")
        if (
            name
            and distance != "Error"
            and isinstance(distance, (int, float))
        ):
            names.append(name.strip() if isinstance(name, str) else name)
    return names


def _find_comparison_result(
    results: list[dict[str, Any]],
    comparison_name: str,
) -> dict[str, Any] | None:
    for result in results:
        result_name = result.get("变量名")
        if isinstance(result_name, str):
            result_name = result_name.strip()
        if result_name == comparison_name:
            return result
    return None


def _similar_numeric_columns(
    data: pd.DataFrame,
    requested_name: str,
) -> list[tuple[str, float]]:
    numeric_columns = data.select_dtypes(include=[np.number]).columns
    similarities = (
        (column, SequenceMatcher(None, requested_name, column).ratio())
        for column in numeric_columns
    )
    return sorted(similarities, key=lambda item: item[1], reverse=True)[:3]


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
            'dtw_signature',
            'dtw_analysis_data',
            'dtw_paths_dict',
            'dtw_data_version'
        ]
        for key in state_keys:
            self.set_state(key, None)
        logger.info("[DTW] 已清除所有分析状态")

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
        enable_alignment, strict_alignment = parse_dtw_alignment_mode(
            alignment_mode_choice
        )

        # 计算比较序列
        comparison_series = [col for col in numeric_cols if col != target_series]

        return {
            'mode': 'auto',
            'target_series': target_series,
            'comparison_series': comparison_series,
            'enable_window_constraint': enable_window_constraint,
            'radius': radius,
            'enable_alignment': enable_alignment,
            'agg_method': agg_method,
            'strict_alignment': strict_alignment,
            'standardization_method': standardization_method
        }


    def perform_auto_dtw_analysis(
        self,
        st_obj,
        data: pd.DataFrame,
        params: dict,
    ):
        """执行自动DTW分析，包含频率处理"""
        target_series = params["target_series"]
        comparison_series = params["comparison_series"]
        backend_options = build_dtw_backend_options(params)

        # 执行DTW计算（现在包含频率处理和标准化）
        dtw_results, paths_dict, errors, _warnings = perform_batch_dtw_calculation(
            df_input=data,
            target_series_name=target_series,
            comparison_series_names=comparison_series,
            **backend_options,
        )

        results = format_dtw_results(dtw_results, paths_dict, params)

        # 仅显示重要的错误信息
        if errors:
            for error in errors:
                st_obj.error(error)

        # 缓存分析时使用的数据和路径字典，避免第二次重复计算
        # 添加数据版本号，用于检测数据是否变化
        data_version = fingerprint_dataframe(data)
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
                df = pd.DataFrame(results)
                csv_data = encode_csv_with_bom(df)

                # 生成文件名
                target_name = params.get('target_series', 'unknown') if params else 'unknown'
                filename = f"DTW批量分析结果_{target_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"

                st_obj.download_button(
                    label="下载结果",
                    data=csv_data,
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

        except Exception as e:  # noqa: BLE001 - user-facing download boundary
            logger.error(f"生成下载按钮失败: {e}")
            st_obj.error(f"下载功能暂时不可用: {e!s}")

    def render_auto_results(
        self,
        st_obj,
        results: list,
        params: dict | None = None,
        data_name: str | None = None,
    ):
        """渲染自动模式结果"""
        if not results:
            st_obj.warning("没有分析结果")
            return

        display_results, valid_results = prepare_dtw_display(results)

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

        st_obj.dataframe(
            display_results,
            width='stretch',
            hide_index=True
        )

        # 在表格下方添加下载按钮（与开始分析按钮颜色样式相同）
        if params and data_name:
            self.render_download_button(st_obj, results, params, data_name)

    def _render_comparison_picker(
        self,
        st_obj,
        results: list[dict[str, Any]],
        data_name: str,
    ) -> str | None:
        selector_column, metric_column = st_obj.columns([1, 2])
        with selector_column:
            valid_names = _valid_comparison_names(results)
            if not valid_names:
                st_obj.warning("没有有效的比较结果可供显示")
                return None
            selected = st_obj.selectbox(
                "选择比较序列:",
                options=valid_names,
                key=f"dtw_{data_name}_comparison_selection",
                help="选择一个序列查看DTW对比图",
            )

        with metric_column:
            selected_result = _find_comparison_result(results, selected)
            if selected_result:
                distance = selected_result.get("DTW距离")
                normalized = selected_result.get("标准化DTW距离")
                distance_column, normalized_column = st_obj.columns(2)
                with distance_column:
                    st_obj.metric(
                        "DTW距离",
                        (
                            f"{distance:.4f}"
                            if isinstance(distance, (int, float))
                            else str(distance)
                        ),
                    )
                with normalized_column:
                    st_obj.metric(
                        "标准化DTW距离",
                        (
                            f"{normalized:.4f}"
                            if isinstance(normalized, (int, float))
                            else str(normalized)
                        ),
                    )
        return selected

    def _load_or_calculate_paths(
        self,
        data: pd.DataFrame,
        target_name: str,
        comparison_name: str,
        backend_options: dict[str, Any],
    ) -> tuple[
        dict[str, dict[str, Any]],
        list[str],
        list[str],
        pd.DataFrame,
    ]:
        cached_paths = self.get_state("dtw_paths_dict")
        cached_version = self.get_state("dtw_data_version")
        current_version = fingerprint_dataframe(data)
        cached_data = self.get_state("dtw_analysis_data")
        if cached_data is not None and cached_version == current_version:
            data_for_calculation = cached_data.copy()
        else:
            data_for_calculation = data.copy()
        if hasattr(data_for_calculation.columns, "str"):
            data_for_calculation.columns = data_for_calculation.columns.str.strip()

        if (
            cached_paths
            and comparison_name in cached_paths
            and cached_version == current_version
        ):
            logger.info(
                "[DTW] 使用版本匹配的缓存路径: %s",
                comparison_name,
            )
            return cached_paths, [], [], data_for_calculation

        logger.info("[DTW] 重新计算路径: %s", comparison_name)
        _, paths, errors, warnings = perform_batch_dtw_calculation(
            df_input=data_for_calculation,
            target_series_name=target_name,
            comparison_series_names=[comparison_name],
            **backend_options,
        )
        return paths, errors, warnings, data_for_calculation

    def _render_path_result(
        self,
        st_obj,
        paths: dict[str, dict[str, Any]],
        errors: list[str],
        warnings: list[str],
        data: pd.DataFrame,
        target_name: str,
        comparison_name: str,
    ) -> None:
        path_data = paths.get(comparison_name)
        if path_data is not None:
            target_values = path_data.get("target_np")
            comparison_values = path_data.get("compare_np")
            path = path_data.get("path", [])
            if (
                target_values is not None
                and comparison_values is not None
                and path
            ):
                self.plot_dtw_path(
                    st_obj,
                    target_values,
                    comparison_values,
                    path,
                    target_name,
                    comparison_name,
                    path_data.get("target_index"),
                    path_data.get("compare_index"),
                )
                return

            logger.warning("[DTW图表] %s 的路径数据不完整", comparison_name)
            st_obj.warning(f"无法获取 {comparison_name} 的DTW路径数据")
            return

        logger.warning("[DTW图表] 未找到 %s 的路径数据", comparison_name)
        if errors:
            st_obj.error(f"DTW计算失败：{errors[0]}")
        else:
            st_obj.error(f"无法找到 '{comparison_name}' 的DTW计算结果")

        if comparison_name not in data.columns:
            suggestions = _similar_numeric_columns(data, comparison_name)
            if suggestions and suggestions[0][1] > 0.7:
                st_obj.info("数据集中不存在该变量，您是否想选择以下相似变量？")
                for column, ratio in suggestions:
                    st_obj.write(f"- {column} (相似度: {ratio:.1%})")

        if warnings:
            with st_obj.expander("查看详细警告信息"):
                for warning in warnings:
                    st_obj.text(warning)

    def render_comparison_selection_and_plot(
        self,
        st_obj,
        data: pd.DataFrame,
        results: list[dict[str, Any]],
        params: dict[str, Any],
        data_name: str,
    ) -> None:
        """
        渲染比较序列选择和DTW对比图

        Args:
            st_obj: Streamlit对象
            data: 原始数据
            results: DTW分析结果列表
            params: 本次分析使用的唯一参数对象
            data_name: 数据名称
        """
        target_series = params["target_series"]
        if not results or not params["comparison_series"]:
            return

        st_obj.markdown("---")
        st_obj.markdown("#### DTW对比图")
        selected_comparison = self._render_comparison_picker(
            st_obj,
            results,
            data_name,
        )
        if selected_comparison is None:
            return

        logger.debug(
            "[DTW诊断] 选择=%s, 列数=%s, 存在=%s",
            selected_comparison,
            len(data.columns),
            selected_comparison in data.columns,
        )
        if selected_comparison not in data.columns:
            logger.warning(
                "[DTW诊断] 变量不存在，最相似列: %s",
                _similar_numeric_columns(data, selected_comparison),
            )

        paths, errors, warnings, calculation_data = (
            self._load_or_calculate_paths(
                data,
                target_series,
                selected_comparison,
                build_dtw_backend_options(params),
            )
        )
        self._render_path_result(
            st_obj,
            paths,
            errors,
            warnings,
            calculation_data,
            target_series,
            selected_comparison,
        )

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
                raise TypeError(f"目标序列时间索引类型错误: {type(s1_time_index).__name__}，必须为DatetimeIndex")
            if not isinstance(s2_time_index, pd.DatetimeIndex):
                raise TypeError(f"比较序列时间索引类型错误: {type(s2_time_index).__name__}，必须为DatetimeIndex")

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
                line={"color": '#1f77b4', "width": 3, "dash": 'solid'},  # 实线
                marker={"size": 8, "symbol": 'circle'},  # 从6加大到8
                customdata=s1_hover_times,
                hovertemplate='<b>%{fullData.name}</b><br>时间: %{customdata}<br>数值: %{y:.4f}<extra></extra>'
            ))

            # 添加比较序列（序列2）- 虚线
            fig.add_trace(go.Scatter(
                x=s2_x,
                y=s2_np,
                mode='lines+markers',
                name=s2_name,
                line={"color": '#ff7f0e', "width": 3, "dash": 'dash'},  # 虚线
                marker={"size": 8, "symbol": 'square'},  # 从6加大到8
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
                        line={"color": 'grey', "width": 1, "dash": 'dash'},
                        opacity=0.3,
                        showlegend=False,
                        hoverinfo='skip'
                    ))

            # 更新布局
            fig.update_layout(
                title={
                    "text": f"DTW对齐路径: {s1_name} vs {s2_name}",
                    "font": {"size": 16, "family": 'Microsoft YaHei, SimHei, sans-serif'},
                    "x": 0.5,  # 标题居中
                    "xanchor": 'center'
                },
                xaxis={
                    "title": None,  # 取消X轴标题
                    "gridcolor": 'rgba(128, 128, 128, 0.2)',
                    "showgrid": True,
                    "tickfont": {"size": 13, "family": 'Microsoft YaHei, SimHei, sans-serif'},  # X轴刻度字体加大
                    "tickformat": '%Y-%m'  # 时间格式：年-月
                },
                yaxis={
                    "title": {
                        "text": 'Z值',
                        "font": {"size": 12, "family": 'Microsoft YaHei, SimHei, sans-serif'}
                    },
                    "gridcolor": 'rgba(128, 128, 128, 0.2)',
                    "showgrid": True
                },
                hovermode='closest',
                plot_bgcolor='white',
                height=500,
                margin={"l": 60, "r": 40, "t": 80, "b": 100},  # 增加底部边距以容纳图例
                legend={
                    "orientation": 'h',
                    "yanchor": 'top',
                    "y": -0.15,  # 放在图表下方
                    "xanchor": 'center',
                    "x": 0.5,
                    "font": {"size": 12, "family": 'Microsoft YaHei, SimHei, sans-serif'},  # 字体从11号加大到12号
                    "itemwidth": 50  # 增加图例项宽度，使色块和文字更大
                }
            )

            # 显示图表
            st_obj.plotly_chart(
                place_chart_legend_at_bottom(fig),
                width='stretch',
            )

        except (TypeError, ValueError) as ve:
            # 用户友好的错误提示（不显示技术堆栈）
            error_msg = f"绘制DTW路径图失败: {ve!s}"
            logger.warning(f"[DTW绘图] {error_msg}")
            st_obj.error(error_msg)
        except Exception as e:
            error_msg = f"绘制DTW路径图失败: {e!s}"
            logger.exception(f"[DTW绘图] {error_msg}")
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
                    logger.warning(
                        "[DTW界面] 检测到列名包含空格，已清理。"
                        "建议检查上游数据处理流程。"
                    )
                    data.columns = cleaned_columns
            logger.debug(f"[DTW界面] 数据准备完成，列数: {len(data.columns)}")

            # 渲染参数设置
            params = self.render_analysis_parameters(st_obj, data, data_name)

            if params is None:
                return None

            current_signature = build_dtw_result_signature(data, params)

            # 分析按钮
            analysis_key = f"dtw_analyze_btn_{data_name}"
            analyze_clicked = st_obj.button("开始分析", key=analysis_key, type="primary")

            if analyze_clicked:
                with st_obj.spinner("正在进行批量DTW分析..."):
                    try:
                        results = self.perform_auto_dtw_analysis(
                            st_obj,
                            data,
                            params,
                        )

                        # 保存结果到状态
                        self.set_state('auto_results', results)
                        self.set_state('dtw_params', params)
                        self.set_state('dtw_signature', current_signature)
                        
                        # 显示结果
                        self.render_auto_results(
                            st_obj,
                            results,
                            params,
                            data_name,
                        )

                        # 添加比较序列选择和DTW图显示
                        self.render_comparison_selection_and_plot(
                            st_obj,
                            data,
                            results,
                            params,
                            data_name,
                        )

                        return results

                    except Exception as e:  # noqa: BLE001 - user-facing analysis boundary
                        error_msg = f"批量DTW分析失败: {e!s}"
                        st_obj.error(error_msg)
                        logger.error(error_msg)
                        return None
            
            previous_auto_results = self.get_state('auto_results')
            previous_params = self.get_state('dtw_params')
            previous_signature = self.get_state('dtw_signature')

            logger.info(f"DTW状态检查 - 是否有之前的结果: {previous_auto_results is not None}")

            if previous_auto_results:
                if (
                    previous_params is None
                    or previous_signature != current_signature
                ):
                    logger.info("DTW数据或参数已变化 - 清除之前的分析结果")
                    self.clear_analysis_state()
                else:
                    logger.info("DTW结果签名未变化 - 显示之前的分析结果")
                    st_obj.markdown("---")
                    st_obj.markdown("#### 分析结果")
                    self.render_auto_results(
                        st_obj,
                        previous_auto_results,
                        previous_params,
                        data_name,
                    )

                    self.render_comparison_selection_and_plot(
                        st_obj,
                        data,
                        previous_auto_results,
                        previous_params,
                        data_name,
                    )

                    return previous_auto_results

            return None
            
        except Exception as e:  # noqa: BLE001 - top-level component render boundary
            self.handle_error(st_obj, e, "渲染DTW分析界面")
            return None


__all__ = ['DTWAnalysisComponent']
