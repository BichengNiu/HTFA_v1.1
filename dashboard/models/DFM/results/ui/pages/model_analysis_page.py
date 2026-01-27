# -*- coding: utf-8 -*-
"""
DFM模型分析页面组件

经典DFM模型：所有变量平等参与因子提取，无目标变量概念
展示因子时间序列、载荷矩阵等模型参数
"""

import streamlit as st
import pandas as pd
import logging
import plotly.graph_objects as go
import numpy as np
import joblib
import pickle
import io
from datetime import datetime
from typing import Optional, Dict, Any
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows


def is_valid_file_object(file_obj) -> bool:
    """
    检查是否为有效的文件对象

    Args:
        file_obj: 待检查的文件对象

    Returns:
        bool: 是否为有效文件对象
    """
    if file_obj is None:
        return False
    return (hasattr(file_obj, 'seek') and
            hasattr(file_obj, 'read') and
            hasattr(file_obj, 'name') and
            getattr(file_obj, 'name', '未知文件') != '未知文件')


def get_dfm_state(key, default=None):
    """获取DFM状态值（完全解耦，仅从model_analysis命名空间读取）"""
    full_key = f'model_analysis.{key}'
    return st.session_state.get(full_key, default)


def set_dfm_state(key, value):
    """设置DFM状态值"""
    full_key = f'model_analysis.{key}'
    st.session_state[full_key] = value

# Import backend functions
from dashboard.models.DFM.results.dfm_backend import (
    load_dfm_results_from_uploads,
    perform_loadings_clustering
)

# Import new components
from dashboard.models.DFM.results.ui.pages.domain import DFMMetadataAccessor
from dashboard.models.DFM.results.ui.pages.components import MetricsPanel

logger = logging.getLogger(__name__)


def load_dfm_data() -> tuple[Optional[Any], Optional[Dict]]:
    """从 session_state 加载模型结果和元数据。"""
    model_file = get_dfm_state('dfm_model_file_indep', None)
    metadata_file = get_dfm_state('dfm_metadata_file_indep', None)

    model_results = None
    metadata = None

    if is_valid_file_object(model_file):
        try:
            model_file.seek(0)
            model_results = joblib.load(model_file)
            logger.info("Model loaded successfully from session state.")
        except (pickle.UnpicklingError, EOFError, ValueError, TypeError, ModuleNotFoundError) as e:
            file_name = getattr(model_file, 'name', '未知文件')
            st.error(f"加载模型文件 ('{file_name}') 时出错: {e}")
            logger.error(f"Model file loading failed: {type(e).__name__}: {e}")
    elif model_file is not None:
        logger.warning(f"检测到无效的模型文件对象类型: {type(model_file)}")

    if is_valid_file_object(metadata_file):
        try:
            metadata_file.seek(0)
            metadata = pickle.load(metadata_file)
            logger.info("Metadata loaded successfully from session state.")
        except (pickle.UnpicklingError, EOFError, ValueError, TypeError, ModuleNotFoundError) as e:
            file_name = getattr(metadata_file, 'name', '未知文件')
            st.error(f"加载元数据文件 ('{file_name}') 时出错: {e}")
            logger.error(f"Metadata file loading failed: {type(e).__name__}: {e}")
    elif metadata_file is not None:
        logger.warning(f"检测到无效的元数据文件对象类型: {type(metadata_file)}")

    return model_results, metadata


def _cleanup_invalid_file_states():
    """清理可能存在的无效文件状态"""
    model_file = get_dfm_state('dfm_model_file_indep', None)
    metadata_file = get_dfm_state('dfm_metadata_file_indep', None)

    if not is_valid_file_object(model_file):
        set_dfm_state('dfm_model_file_indep', None)
    if not is_valid_file_object(metadata_file):
        set_dfm_state('dfm_metadata_file_indep', None)


def render_file_upload_section(st_instance):
    """
    渲染文件上传区域
    """
    # 执行状态清理
    _cleanup_invalid_file_states()

    st_instance.markdown("### 模型文件上传")
    st_instance.caption("注意: 请仅上传来自可信来源的模型文件。模型文件包含序列化的Python对象。")

    # 创建两列布局
    col_model, col_metadata = st_instance.columns(2)

    with col_model:
        st_instance.markdown("**DFM 模型文件 (.joblib)**")
        uploaded_model_file = st_instance.file_uploader(
            "选择模型文件",
            type=['joblib'],
            key="dfm_model_upload_independent",
            help="上传训练好的DFM模型文件(.joblib格式)。请确保文件来自本系统训练模块或其他可信来源。"
        )

        if uploaded_model_file:
            set_dfm_state("dfm_model_file_indep", uploaded_model_file)
        else:
            existing_model_file = get_dfm_state('dfm_model_file_indep', None)
            if is_valid_file_object(existing_model_file):
                st_instance.info(f"当前文件: {existing_model_file.name}")

    with col_metadata:
        st_instance.markdown("**元数据文件 (.pkl)**")
        uploaded_metadata_file = st_instance.file_uploader(
            "选择元数据文件",
            type=['pkl'],
            key="dfm_metadata_upload_independent",
            help="上传包含训练元数据的.pkl文件。请确保文件来自本系统训练模块或其他可信来源。"
        )

        if uploaded_metadata_file:
            set_dfm_state("dfm_metadata_file_indep", uploaded_metadata_file)
        else:
            existing_metadata_file = get_dfm_state('dfm_metadata_file_indep', None)
            if is_valid_file_object(existing_metadata_file):
                st_instance.info(f"当前文件: {existing_metadata_file.name}")

    # 文件状态总结
    model_file = get_dfm_state('dfm_model_file_indep', None)
    metadata_file = get_dfm_state('dfm_metadata_file_indep', None)

    model_file_exists = is_valid_file_object(model_file)
    metadata_file_exists = is_valid_file_object(metadata_file)

    if model_file_exists and metadata_file_exists:
        return True
    else:
        missing_files = []
        if not model_file_exists:
            missing_files.append("模型文件")
        if not metadata_file_exists:
            missing_files.append("元数据文件")

        st_instance.warning(f"[WARNING] 缺少文件: {', '.join(missing_files)}。请上传所有文件后再进行分析。")
        return False

def _load_and_validate_data(st) -> tuple:
    """
    加载并验证模型和元数据

    Args:
        st: Streamlit模块

    Returns:
        tuple: (model, metadata, accessor) 或在错误时返回 (None, None, None)
    """
    model_results, metadata = load_dfm_data()

    if model_results is None or metadata is None:
        st.error("[ERROR] 无法加载模型数据，请检查文件格式和内容。")
        return None, None, None

    # 调用后端处理函数
    model, metadata, load_errors = load_dfm_results_from_uploads(model_results, metadata)

    if load_errors:
        st.error("加载 DFM 相关文件时遇到错误:")
        for error in load_errors:
            st.error(f"- {error}")
        return None, None, None

    # 创建元数据访问器
    accessor = DFMMetadataAccessor(metadata)

    return model, metadata, accessor


def _add_period_annotation(fig, start_str: str, end_str: str, label: str,
                           add_background: bool = False, bg_color: str = "yellow",
                           bg_opacity: float = 0.2) -> bool:
    """
    添加时间段标注（文字标签和可选背景色）

    Args:
        fig: Plotly图表对象
        start_str: 开始日期字符串
        end_str: 结束日期字符串
        label: 时期标签（如"训练期"、"验证期"）
        add_background: 是否添加背景矩形
        bg_color: 背景颜色
        bg_opacity: 背景透明度

    Returns:
        bool: 是否成功添加标注
    """
    if not start_str or not end_str or start_str == 'N/A' or end_str == 'N/A':
        return False

    try:
        start_dt = pd.to_datetime(start_str)
        end_dt = pd.to_datetime(end_str)
    except (pd.errors.ParserError, ValueError) as e:
        logger.warning(f"Invalid date format for {label}: start='{start_str}', end='{end_str}': {e}")
        return False

    if start_dt > end_dt:
        logger.warning(f"Start date ({start_str}) is after end date ({end_str}) for {label}")
        return False

    mid_dt = start_dt + (end_dt - start_dt) / 2

    if add_background:
        fig.add_vrect(
            x0=start_dt,
            x1=end_dt,
            fillcolor=bg_color,
            opacity=bg_opacity,
            layer="below",
            line_width=0
        )

    fig.add_annotation(
        x=mid_dt,
        y=1.05,
        yref="paper",
        text=f"<b>{label}</b>",
        showarrow=False,
        font=dict(size=12, color="red"),
        xanchor="center"
    )
    logger.info(f"已添加{label}标注: {start_dt} 到 {end_dt}")
    return True


def _render_nowcast_chart(st, accessor: DFMMetadataAccessor, is_ddfm: bool) -> None:
    """
    渲染变量重构效果图（经典DFM无监督模型）

    Args:
        st: Streamlit模块
        accessor: 元数据访问器
        is_ddfm: 是否为DDFM模型
    """
    st.markdown("---")
    st.subheader("结果分析")
    _render_unsupervised_reconstruction_chart(st, accessor, is_ddfm)


def _render_unsupervised_reconstruction_chart(st, accessor: DFMMetadataAccessor, is_ddfm: bool) -> None:
    """
    渲染无监督模型的变量重构效果图

    Args:
        st: Streamlit模块
        accessor: 元数据访问器
        is_ddfm: 是否为DDFM模型
    """
    # 优先使用预计算的重构对比表
    reconstruction_comparison = accessor.get('reconstruction_comparison')

    if reconstruction_comparison is not None:
        # 使用预计算的重构对比表
        available_vars = reconstruction_comparison.columns.get_level_values(0).unique().tolist()

        if not available_vars:
            st.warning("重构对比表中没有可用变量")
            return

        # 用户选择变量
        selected_var = st.selectbox(
            "选择变量查看重构效果",
            options=available_vars,
            key="reconstruction_var_select"
        )

        # 直接从预计算表中获取数据
        original_values = reconstruction_comparison[(selected_var, '原始值')].values
        reconstructed_values = reconstruction_comparison[(selected_var, '重构值')].values
        time_index = reconstruction_comparison.index

        # 确保 time_index 是 DatetimeIndex
        if not isinstance(time_index, pd.DatetimeIndex):
            time_index = pd.to_datetime(time_index)

        # 构建对比数据
        comparison_df = pd.DataFrame({
            '原始值': original_values,
            '重构值': reconstructed_values
        }, index=time_index)

        logger.info(f"[重构图] 使用预计算重构对比表: 变量={selected_var}, 长度={len(comparison_df)}")
    else:
        # 回退到动态计算（兼容旧模型）
        logger.warning("[重构图] 未找到预计算重构对比表，使用动态计算")

        # 获取数据
        prepared_data = accessor.get('prepared_data')
        factor_loadings_df = accessor.factor_loadings_df
        factor_series = accessor.factor_series
        training_means = accessor.get('training_means')
        training_variable_names = accessor.get('training_variable_names')

        if prepared_data is None or factor_loadings_df is None or factor_series is None:
            st.warning("缺少重构所需数据（prepared_data/factor_loadings_df/factor_series）")
            return

        # 获取可选变量列表（与模型使用的变量一致）
        model_variables = factor_loadings_df.index.tolist()
        available_vars = [v for v in model_variables if v in prepared_data.columns]

        if not available_vars:
            st.warning("没有可用于重构对比的变量")
            return

        # 用户选择变量
        selected_var = st.selectbox(
            "选择变量查看重构效果",
            options=available_vars,
            key="reconstruction_var_select"
        )

        # 计算重构值（去均值尺度）
        H = factor_loadings_df.loc[available_vars].values  # (n_vars, k_factors)
        factors = factor_series.values  # (T, k_factors)
        reconstructed_all = factors @ H.T  # (T, n_vars)

        var_idx = available_vars.index(selected_var)
        reconstructed_centered = reconstructed_all[:, var_idx]

        # 获取 factor_series 的索引
        time_index = factor_series.index
        n_time = len(factor_series)

        # 检查 factor_series 是否有有效的日期索引
        has_valid_date_index = isinstance(time_index, pd.DatetimeIndex)

        # 如果不是 DatetimeIndex，检查是否是整数索引（RangeIndex 或 Int64Index）
        if not has_valid_date_index:
            if isinstance(time_index, pd.RangeIndex) or (hasattr(time_index, 'dtype') and np.issubdtype(time_index.dtype, np.integer)):
                # 整数索引，需要从 prepared_data 获取日期
                logger.warning("factor_series 是整数索引，从 prepared_data 获取日期索引")
                if len(prepared_data) >= n_time:
                    time_index = prepared_data.index[:n_time]
                    has_valid_date_index = True
                else:
                    st.error("因子序列缺少日期索引，无法绘制重构对比图")
                    return
            else:
                # 尝试转换为日期索引
                try:
                    time_index = pd.to_datetime(time_index)
                    has_valid_date_index = True
                except (ValueError, TypeError):
                    st.error("因子序列索引无法转换为日期，无法绘制重构对比图")
                    return

        # 确保 time_index 是 DatetimeIndex
        if not isinstance(time_index, pd.DatetimeIndex):
            time_index = pd.to_datetime(time_index)

        # 使用位置索引对齐原始数据（prepared_data 和 factor_series 长度相同且顺序一致）
        if selected_var in prepared_data.columns:
            if len(prepared_data) == n_time:
                # 长度相同，直接使用位置索引对齐
                original_values = prepared_data[selected_var].values
                logger.info(f"[重构图] 位置索引对齐成功: 长度={n_time}")
            else:
                # 长度不同（异常情况），记录警告并尝试日期对齐
                logger.warning(f"数据长度不匹配: prepared_data={len(prepared_data)}, factor_series={n_time}")
                if not isinstance(prepared_data.index, pd.DatetimeIndex):
                    prepared_data = prepared_data.copy()
                    prepared_data.index = pd.to_datetime(prepared_data.index)
                original_values = prepared_data[selected_var].reindex(time_index).values
        else:
            st.error(f"变量 {selected_var} 不在 prepared_data 中")
            return

        # 调试日志
        logger.info(f"[重构图] 变量: {selected_var}")
        logger.info(f"[重构图] time_index 类型: {type(time_index)}, 范围: {time_index.min()} ~ {time_index.max()}, 长度: {len(time_index)}")
        logger.info(f"[重构图] prepared_data 索引范围: {prepared_data.index.min()} ~ {prepared_data.index.max()}, 长度: {len(prepared_data)}")
        logger.info(f"[重构图] 对齐后原始值非空数量: {pd.notna(original_values).sum()} / {len(original_values)}")

        # 获取该变量的训练期均值
        if training_means is None or training_variable_names is None:
            st.error("元数据中缺少训练期均值（training_means），请使用最新版本重新训练模型")
            return

        try:
            mean_idx = list(training_variable_names).index(selected_var)
            var_mean = training_means[mean_idx]
        except (ValueError, IndexError):
            st.error(f"变量 {selected_var} 的训练期均值未找到，请重新训练模型")
            return

        # 还原到原始尺度
        reconstructed_original = reconstructed_centered + var_mean
        original_values_original_scale = original_values  # 已经是原始尺度，无需转换

        # 构建对比数据（原始尺度）
        comparison_df = pd.DataFrame({
            '原始值': original_values_original_scale,
            '重构值': reconstructed_original
        }, index=time_index)

    # 绘制图表（散点图）
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=comparison_df.index, y=comparison_df['原始值'],
        mode='markers', name='原始值', marker=dict(color='red', size=8)
    ))
    fig.add_trace(go.Scatter(
        x=comparison_df.index, y=comparison_df['重构值'],
        mode='markers', name='重构值', marker=dict(color='blue', size=8)
    ))

    # 获取训练信息并添加时期标注
    training_info = accessor.training_info

    # 添加训练期标注（白色背景，即不添加背景）
    _add_period_annotation(fig, training_info.training_start, training_info.training_end, "训练期")

    # 添加验证期标注（浅黄色背景）- DDFM模型跳过
    if not is_ddfm:
        _add_period_annotation(
            fig, training_info.validation_start, training_info.validation_end,
            "验证期", add_background=True, bg_color="yellow", bg_opacity=0.2
        )

    # 添加观察期标注（浅绿色背景）
    obs_start = accessor.observation_period_start
    obs_end = accessor.observation_period_end
    if obs_start and obs_start != 'N/A':
        obs_start_dt = pd.to_datetime(obs_start)
        if obs_end and obs_end != 'N/A':
            data_end_str = obs_end
        elif not comparison_df.empty and comparison_df.index.max() > obs_start_dt:
            data_end_str = str(comparison_df.index.max().date())
        else:
            data_end_str = None

        if data_end_str:
            _add_period_annotation(
                fig, obs_start, data_end_str, "观察期",
                add_background=True, bg_color="rgba(150, 230, 150, 0.4)", bg_opacity=0.4
            )

    fig.update_layout(
        title=dict(text=f'{selected_var} 重构效果对比', x=0.5),
        xaxis_title="", yaxis_title="值",
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
        height=500,
        margin=dict(t=100, b=100, l=50, r=50)
    )

    st.plotly_chart(fig, use_container_width=True)

    # 下载按钮
    csv_data = comparison_df.to_csv(index=True).encode('utf-8-sig')
    st.download_button(
        label="数据下载", data=csv_data,
        file_name=f"{selected_var}_重构对比.csv", mime="text/csv",
        key="download_reconstruction_comparison"
    )


def _render_pca_section(st, accessor: DFMMetadataAccessor, is_ddfm: bool) -> None:
    """
    渲染PCA结果分析部分

    Args:
        st: Streamlit模块
        accessor: 元数据访问器
        is_ddfm: 是否为DDFM模型
    """
    if is_ddfm:
        return

    st.markdown("**PCA结果分析**")

    # 获取k_factors - 使用accessor的training_info，异常会向上传播
    training_info = accessor.training_info
    k_factors = training_info.n_factors

    if not isinstance(k_factors, (int, np.integer)) or k_factors <= 0:
        raise ValueError(f"k_factors值无效: {k_factors}，必须为正整数")

    pca_results = accessor.pca_results_df
    if pca_results is None:
        st.write("未找到 PCA 结果。")
        return

    pca_df_display = pca_results.head(k_factors).copy()
    if '主成分 (PC)' in pca_df_display.columns:
        pca_df_display = pca_df_display.drop(columns=['主成分 (PC)'])
    pca_df_display.insert(0, '主成分 (PC)', [f"PC{i+1}" for i in range(len(pca_df_display.index))])
    if not isinstance(pca_df_display.index, pd.RangeIndex):
        pca_df_display = pca_df_display.reset_index()
        if 'index' in pca_df_display.columns:
            pca_df_display = pca_df_display.rename(columns={'index': 'Original Index'})
    pca_df_display = pca_df_display.rename(columns={
        '解释方差 (%)': '解释方差(%)',
        '累计解释方差 (%)': '累计解释方差(%)',
        '特征值 (Eigenvalue)': '特征值(Eigenvalue)'
    })
    st.dataframe(pca_df_display, width='stretch')


def _translate_factor_name(factor_name: str) -> str:
    """
    将英文因子名称转换为中文

    Args:
        factor_name: 原始因子名称(如'factor_1')

    Returns:
        str: 中文因子名称(如'因子1')
    """
    if isinstance(factor_name, str) and factor_name.lower().startswith('factor_'):
        try:
            num = factor_name.split('_')[1]
            return f"因子{num}"
        except (IndexError, ValueError):
            return factor_name
    return factor_name


def _render_factor_loadings(st, accessor: DFMMetadataAccessor) -> bool:
    """
    渲染因子载荷热力图

    Args:
        st: Streamlit模块
        accessor: 元数据访问器

    Returns:
        bool: 是否成功渲染（用于判断是否显示因子时间序列）
    """
    st.markdown("---")

    factor_loadings_df = accessor.factor_loadings_df

    if factor_loadings_df is None:
        st.write("未在元数据中找到因子载荷数据。")
        return False

    if not isinstance(factor_loadings_df, pd.DataFrame):
        raise TypeError("因子载荷数据不是有效的DataFrame格式")

    if factor_loadings_df.empty:
        st.write("因子载荷数据为空。")
        return False

    # 使用Backend的聚类函数
    data_for_clustering, y_labels_heatmap, clustering_performed_successfully = perform_loadings_clustering(
        factor_loadings_df,
        cluster_vars=True
    )

    if clustering_performed_successfully:
        logger.info("因子载荷热力图：变量聚类成功。")
    else:
        logger.info("因子载荷热力图：使用原始顺序。")

    factor_names_original = data_for_clustering.columns.tolist()
    z_values = data_for_clustering.values
    x_labels_heatmap = [_translate_factor_name(name) for name in factor_names_original]

    fig_heatmap = go.Figure(data=go.Heatmap(
        z=z_values,
        x=x_labels_heatmap,
        y=y_labels_heatmap,
        colorscale='RdBu_r',
        zmid=0,
        colorbar=dict(title='载荷值'),
        xgap=1,
        ygap=1,
        hovertemplate=(
            "变量 (Variable): %{y}<br>" +
            "因子 (Factor): %{x}<br>" +
            "载荷值 (Loading): %{z:.4f}<extra></extra>"
        )
    ))

    # Annotate heatmap cells
    annotations = []
    for i, var_name in enumerate(y_labels_heatmap):
        for j, factor_name in enumerate(x_labels_heatmap):
            val = z_values[i][j]
            annotations.append(
                go.layout.Annotation(
                    text=f"{val:.2f}",
                    x=factor_name,
                    y=var_name,
                    xref='x1',
                    yref='y1',
                    showarrow=False,
                    font=dict(color='white' if abs(val) > 0.5 else 'black')
                )
            )

    # Calculate label width once for reuse (empty list protection)
    max_label_width = max((len(name) for name in y_labels_heatmap), default=0) * 8
    left_margin = max(200, max_label_width)

    fig_heatmap.update_layout(
        title="因子载荷聚类热力图",
        xaxis_title="因子",
        yaxis=dict(
            type='category',
            categoryorder='array',
            categoryarray=y_labels_heatmap
        ),
        height=max(600, len(y_labels_heatmap) * 35 + 200),
        width=max(1000, len(x_labels_heatmap) * 100 + left_margin + 50),
        margin=dict(l=left_margin, r=50, t=100, b=200),
        annotations=annotations,
        xaxis=dict(side='top', tickangle=-45)
    )

    heatmap_col1, heatmap_col2, heatmap_col3 = st.columns([1, 8, 1])
    with heatmap_col2:
        st.plotly_chart(fig_heatmap, width='stretch')

    # Download button for factor loadings data
    factor_loadings_df_cn = factor_loadings_df.copy()
    factor_loadings_df_cn.columns = [_translate_factor_name(col) for col in factor_loadings_df_cn.columns]
    csv_loadings = factor_loadings_df_cn.to_csv(index=True).encode('utf-8-sig')
    st.download_button(
        label="数据下载",
        data=csv_loadings,
        file_name="因子载荷.csv",
        mime="text/csv",
        key="download_factor_loadings",
        type="primary"
    )

    return True


def _render_factor_timeseries(st, accessor: DFMMetadataAccessor) -> None:
    """
    渲染因子时间序列图

    Args:
        st: Streamlit模块
        accessor: 元数据访问器
    """
    st.markdown("---")

    factor_series_data = accessor.factor_series

    if factor_series_data is None or not isinstance(factor_series_data, pd.DataFrame) or factor_series_data.empty:
        st.write("未在元数据中找到因子时间序列数据。")
        return

    factor_names = factor_series_data.columns.tolist()
    num_factors = len(factor_names)

    if num_factors == 0:
        st.write("未找到有效的因子数据。")
        return

    cols_per_row = 2 if num_factors % 2 == 0 else 3
    num_rows = (num_factors + cols_per_row - 1) // cols_per_row

    for row in range(num_rows):
        cols = st.columns(cols_per_row)

        for col_idx in range(cols_per_row):
            factor_idx = row * cols_per_row + col_idx

            if factor_idx < num_factors:
                factor_name = factor_names[factor_idx]
                factor_name_cn = _translate_factor_name(factor_name)

                with cols[col_idx]:
                    factor_data = factor_series_data[factor_name].dropna()

                    if not factor_data.empty:
                        fig_factor = go.Figure()

                        fig_factor.add_trace(go.Scatter(
                            x=factor_data.index,
                            y=factor_data.values,
                            mode='lines+markers',
                            name=factor_name_cn,
                            line=dict(width=2),
                            marker=dict(size=4),
                            hovertemplate=(
                                f"日期: %{{x|%Y/%m/%d}}<br>" +
                                f"{factor_name_cn}: %{{y:.4f}}<extra></extra>"
                            )
                        ))

                        fig_factor.update_layout(
                            title=f"{factor_name_cn}",
                            xaxis_title="",
                            yaxis_title="因子值",
                            height=400,
                            margin=dict(t=60, b=80, l=60, r=30),
                            showlegend=False,
                            hovermode='x unified'
                        )

                        fig_factor.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

                        st.plotly_chart(fig_factor, width='stretch')
                    else:
                        st.warning(f"{factor_name_cn}数据为空，无法绘制图表。")

    # 提供所有因子数据的统一下载
    factor_series_data_cn = factor_series_data.copy()
    factor_series_data_cn.columns = [_translate_factor_name(col) for col in factor_series_data_cn.columns]
    all_factors_csv = factor_series_data_cn.to_csv(index=True).encode('utf-8-sig')
    st.download_button(
        label="数据下载",
        data=all_factors_csv,
        file_name="因子时间序列.csv",
        mime="text/csv",
        key="download_all_factors_timeseries",
        type="primary"
    )


def render_dfm_tab(st):
    """
    渲染DFM模型分析标签页

    主编排函数，协调各子组件的渲染
    """
    # 文件上传区域
    files_ready = render_file_upload_section(st)

    if not files_ready:
        return

    # 加载并验证数据
    model, metadata, accessor = _load_and_validate_data(st)
    if model is None or metadata is None or accessor is None:
        return

    # 使用MetricsPanel显示所有指标
    MetricsPanel.render_all_metrics(accessor)

    # 判断是否为DDFM模型
    is_ddfm = accessor.is_ddfm

    # 渲染Nowcast图表
    _render_nowcast_chart(st, accessor, is_ddfm)

    # 渲染PCA结果
    _render_pca_section(st, accessor, is_ddfm)

    # 渲染因子载荷
    has_loadings = _render_factor_loadings(st, accessor)

    # 渲染因子时间序列（仅当有因子载荷数据时）
    if has_loadings:
        _render_factor_timeseries(st, accessor)


def render_dfm_model_analysis_page(st_module: Any) -> Dict[str, Any]:
    """
    渲染DFM模型分析页面

    Args:
        st_module: Streamlit模块

    Returns:
        Dict[str, Any]: 渲染结果
    """
    try:
        # 调用主要的UI渲染函数
        render_dfm_tab(st_module)

        return {
            'status': 'success',
            'page': 'model_analysis',
            'components': ['file_upload', 'model_info', 'nowcasting', 'factor_analysis']
        }

    except (KeyError, TypeError, ValueError) as e:
        # 数据验证错误 - 显示具体错误信息
        logger.error(f"Data validation error in model analysis: {type(e).__name__}: {e}")
        st_module.error(f"数据验证错误: {str(e)}")
        return {
            'status': 'error',
            'page': 'model_analysis',
            'error': str(e),
            'error_type': type(e).__name__
        }
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        # 数据解析错误
        logger.error(f"Data parsing error: {type(e).__name__}: {e}")
        st_module.error(f"数据解析错误: {str(e)}")
        return {
            'status': 'error',
            'page': 'model_analysis',
            'error': str(e),
            'error_type': 'DataParsingError'
        }
