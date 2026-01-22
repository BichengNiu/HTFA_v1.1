# -*- coding: utf-8 -*-
"""
核心配置管理器
提供统一的配置访问接口，消除硬编码配置
"""

import os
from typing import Dict, List, Any
from dataclasses import dataclass, field


# ==================== 配置数据类 ====================

@dataclass
class EnvironmentConfig:
    """环境配置"""
    vars: Dict[str, str] = field(default_factory=lambda: {
        'STREAMLIT_LOGGER_LEVEL': 'CRITICAL',
        'STREAMLIT_CLIENT_TOOLBAR_MODE': 'minimal',
        'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false',
        'STREAMLIT_CLIENT_SHOW_ERROR_DETAILS': 'false',
        'PYTHONWARNINGS': 'ignore',
        'STREAMLIT_SILENT_IMPORTS': 'true',
        'STREAMLIT_SUPPRESS_WARNINGS': 'true'
    })


@dataclass
class ResourcePathsConfig:
    """资源路径配置"""
    module_paths: Dict[str, str] = field(default_factory=lambda: {
        # 预览模块
        'data_loader': 'dashboard.preview.modules.industrial.loader',
        'preview_main': 'dashboard.preview.main',

        # DFM模块
        'dfm_ui': 'dashboard.models.DFM.results.dfm_ui',
        'dfm_data_prep': 'dashboard.models.DFM.prep.data_prep_ui',
        'dfm_train_model': 'dashboard.DFM.train_model.train_model_ui',
        'news_analysis': 'dashboard.models.DFM.decomp.news_analysis_front_end',

        # 探索模块
        'stationarity_analysis': 'dashboard.explore.ui.stationarity',
        'dtw_analysis': 'dashboard.explore.ui.dtw',
        'correlation_analysis': 'dashboard.explore.ui.correlation',
        'lead_lag_analysis': 'dashboard.explore.ui.lead_lag',

        # UI组件
        'data_upload_sidebar': 'dashboard.core.ui.components.sidebar',
        'parameter_sidebar': 'dashboard.core.ui.components.sidebar'
    })


@dataclass
class NavigationConfig:
    """导航配置"""
    cache_keys: List[str] = field(default_factory=lambda: [
        'ui.button_state_cache',
        'ui.navigation_cache',
        'ui.module_selector_cache'
    ])


# ==================== 配置管理器 ====================

class CoreConfig:
    """
    核心配置管理器

    统一管理所有核心模块的配置，消除硬编码
    """

    def __init__(self):
        self.environment = EnvironmentConfig()
        self.resource_paths = ResourcePathsConfig()
        self.navigation = NavigationConfig()

    def get_env_vars(self) -> Dict[str, str]:
        """获取环境变量配置"""
        return self.environment.vars.copy()

    def get_module_paths(self) -> Dict[str, str]:
        """获取模块路径配置"""
        return self.resource_paths.module_paths.copy()

    def get_module_path(self, module_name: str) -> str:
        """
        获取指定模块的路径

        Args:
            module_name: 模块名称

        Returns:
            模块路径，如果不存在则返回None
        """
        return self.resource_paths.module_paths.get(module_name)

    def get_cache_keys(self) -> List[str]:
        """获取缓存键列表"""
        return self.navigation.cache_keys.copy()


# ==================== 全局配置实例 ====================

import streamlit as st


@st.cache_resource
def get_core_config() -> CoreConfig:
    """
    获取核心配置实例（单例模式）

    Returns:
        CoreConfig: 核心配置实例
    """
    return CoreConfig()
