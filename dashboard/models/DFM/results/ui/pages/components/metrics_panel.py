"""
Metrics Panel Components
指标面板组件
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Any, Optional
from dashboard.models.DFM.results.ui.pages.domain import DFMMetadataAccessor


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
    def render_period_dates(accessor: DFMMetadataAccessor) -> None:
        """渲染三个时期的开始日期"""
        info = accessor.training_info
        obs_start = accessor.observation_period_start

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("训练期", info.training_start)
        with col2:
            st.metric("验证期", info.validation_start)
        with col3:
            st.metric("观察期", obs_start if obs_start != 'N/A' else 'N/A')

    @staticmethod
    def render_mae_row(accessor: DFMMetadataAccessor) -> None:
        """渲染MAE指标行"""
        formatter = DFMMetadataAccessor.format_metric
        training = accessor.training_metrics
        validation = accessor.validation_metrics
        observation = accessor.observation_metrics

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("训练期MAE", formatter(training.mae))
        with col2:
            val = formatter(validation.mae) if accessor.has_valid_validation_metrics else 'N/A'
            st.metric("验证期MAE", val)
        with col3:
            val = formatter(observation.mae) if accessor.has_observation_metrics else 'N/A'
            st.metric("观察期MAE", val)

    @staticmethod
    def render_rmse_row(accessor: DFMMetadataAccessor) -> None:
        """渲染RMSE指标行"""
        formatter = DFMMetadataAccessor.format_metric
        training = accessor.training_metrics
        validation = accessor.validation_metrics
        observation = accessor.observation_metrics

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("训练期RMSE", formatter(training.rmse))
        with col2:
            val = formatter(validation.rmse) if accessor.has_valid_validation_metrics else 'N/A'
            st.metric("验证期RMSE", val)
        with col3:
            val = formatter(observation.rmse) if accessor.has_observation_metrics else 'N/A'
            st.metric("观察期RMSE", val)

    @staticmethod
    def render_all_metrics(accessor: DFMMetadataAccessor) -> None:
        """
        渲染所有指标（完整面板）

        Args:
            accessor: 元数据访问器
        """
        # 分割线和标题
        st.markdown("---")
        st.markdown("#### 结果摘要")

        # 第1行：三个期的开始日期
        MetricsPanel.render_period_dates(accessor)

        # 第2行：基本信息
        MetricsPanel.render_basic_info(accessor)

        # 第3行：MAE指标
        MetricsPanel.render_mae_row(accessor)

        # 第4行：RMSE指标
        MetricsPanel.render_rmse_row(accessor)


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

        st.markdown(f"**估计方法**: {info.estimation_method}")

        st.markdown("---")
