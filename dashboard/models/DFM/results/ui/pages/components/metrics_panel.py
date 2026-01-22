"""
Metrics Panel Components
指标面板组件
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Any, Optional, Callable
from dashboard.models.DFM.results.ui.pages.domain import DFMMetadataAccessor, ModelMetrics


class MetricsPanel:
    """
    指标面板组件

    统一管理和渲染模型评估指标
    """

    @staticmethod
    def render_basic_info(accessor: DFMMetadataAccessor) -> None:
        """
        渲染基本信息（行业数、变量数、因子数）

        Args:
            accessor: 元数据访问器
        """
        info = accessor.training_info

        col1, col2, col3 = st.columns(3)
        with col1:
            display_ind = int(info.n_industries) if isinstance(info.n_industries, (int, np.integer)) else 'N/A'
            st.metric("最终行业数", display_ind)
        with col2:
            display_n = int(info.n_variables) if isinstance(info.n_variables, (int, np.integer)) else 'N/A'
            st.metric("最终变量数", display_n)
        with col3:
            display_k = int(info.n_factors) if isinstance(info.n_factors, (int, np.integer)) else 'N/A'
            st.metric("最终因子数", display_k)

    @staticmethod
    def render_period_metrics(
        label: str,
        metrics: ModelMetrics,
        formatter: Optional[Callable] = None
    ) -> None:
        """
        渲染某个时期的三个指标（MAE、RMSE、胜率）

        Args:
            label: 时期标签（如"训练期"、"验证期"）
            metrics: 指标数据
            formatter: 可选的格式化函数
        """
        if formatter is None:
            formatter = DFMMetadataAccessor.format_metric

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(f"{label}MAE", formatter(metrics.mae))
        with col2:
            st.metric(f"{label}RMSE", formatter(metrics.rmse))
        with col3:
            st.metric(f"{label}胜率", formatter(metrics.hit_rate, is_percent=True))

    @staticmethod
    def render_all_metrics(accessor: DFMMetadataAccessor) -> None:
        """
        渲染所有指标（完整面板）

        Args:
            accessor: 元数据访问器
        """
        # 第1行：基本信息
        MetricsPanel.render_basic_info(accessor)

        # 第2行：训练期指标
        MetricsPanel.render_period_metrics("训练期", accessor.training_metrics)

        # 第3行：验证期指标（DDFM模型时隐藏，因为验证期指标为inf）
        if accessor.has_valid_validation_metrics:
            MetricsPanel.render_period_metrics("验证期", accessor.validation_metrics)

        # 第4行：观察期指标（条件显示）
        if accessor.has_observation_metrics:
            MetricsPanel.render_period_metrics("观察期", accessor.observation_metrics)


class TrainingInfoPanel:
    """
    训练信息面板组件
    """

    @staticmethod
    def render(accessor: DFMMetadataAccessor) -> None:
        """
        渲染训练信息

        Args:
            accessor: 元数据访问器
        """
        info = accessor.training_info

        st.markdown("#### 模型训练信息")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**训练时间范围**")
            st.text(f"开始: {info.training_start}")
            st.text(f"结束: {info.training_end}")

        with col2:
            st.markdown("**验证时间范围**")
            st.text(f"开始: {info.validation_start}")
            st.text(f"结束: {info.validation_end}")

        st.markdown(f"**目标变量**: {info.target_variable}")
        st.markdown(f"**估计方法**: {info.estimation_method}")

        st.markdown("---")
