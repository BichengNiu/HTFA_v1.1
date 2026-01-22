# -*- coding: utf-8 -*-
"""
UI组件注册表
管理UI组件的映射关系和依赖关系
从dashboard.core.component_loader迁移而来
"""

from typing import Dict, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ComponentRegistry:
    """UI组件注册表"""
    
    def __init__(self):
        # 预定义组件映射
        self.component_map = {
            # 数据输入组件
            'shared_data_input': 'dashboard.core.ui.components.data_input.staging',

            # 时间序列分析组件（已迁移到explore/ui目录）
            'stationarity_analysis': 'dashboard.explore.ui.stationarity',
            'correlation_analysis': 'dashboard.explore.ui.correlation',
            'lead_lag_analysis': 'dashboard.explore.ui.lead_lag',
            'unified_correlation_analysis': 'dashboard.explore.ui.unified_correlation',
            'dtw_analysis': 'dashboard.explore.ui.dtw',
        }
        
        # 组件依赖关系
        self.component_dependencies = {
            'shared_data_input': set(),  # 独立组件
            'stationarity_analysis': set(),  # 独立分析组件
            'correlation_analysis': set(),  # 独立分析组件
            'lead_lag_analysis': set(),  # 独立分析组件
            'dtw_analysis': set(),  # 独立分析组件
            'unified_correlation_analysis': set(),  # 独立分析组件
        }
        
        logger.info("[ComponentRegistry] UI组件注册表初始化完成")
    
    def register_component(self, component_name: str, module_path: str, dependencies: Set[str] = None):
        """注册新组件"""
        self.component_map[component_name] = module_path
        if dependencies:
            self.component_dependencies[component_name] = dependencies
        else:
            self.component_dependencies[component_name] = set()
        
        logger.info(f"[ComponentRegistry] 注册组件: {component_name} -> {module_path}")
    
    def get_component_path(self, component_name: str) -> Optional[str]:
        """获取组件模块路径"""
        return self.component_map.get(component_name)
    
    def get_component_dependencies(self, component_name: str) -> Set[str]:
        """获取组件依赖关系"""
        return self.component_dependencies.get(component_name, set())
    
    def get_all_components(self) -> Dict[str, str]:
        """获取所有组件映射"""
        return self.component_map.copy()
    
    def get_critical_components(self) -> Set[str]:
        """获取关键组件列表"""
        return {
            'shared_data_input'
        }
    
# 全局组件注册表实例
import streamlit as st

@st.cache_resource
def get_component_registry() -> ComponentRegistry:
    """获取全局组件注册表实例"""
    return ComponentRegistry()

# 便捷函数
def register_ui_component(component_name: str, module_path: str, dependencies: Set[str] = None):
    """注册UI组件的便捷函数"""
    registry = get_component_registry()
    registry.register_component(component_name, module_path, dependencies)

def get_ui_component_path(component_name: str) -> Optional[str]:
    """获取UI组件路径的便捷函数"""
    registry = get_component_registry()
    return registry.get_component_path(component_name)

def get_ui_component_dependencies(component_name: str) -> Set[str]:
    """获取UI组件依赖的便捷函数"""
    registry = get_component_registry()
    return registry.get_component_dependencies(component_name)

logger.info("[ComponentRegistry] UI组件注册表模块初始化完成")
