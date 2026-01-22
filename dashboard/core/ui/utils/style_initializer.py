# -*- coding: utf-8 -*-
"""
UI样式初始化器
负责UI模块的样式初始化和管理
从dashboard.core.app_initializer迁移而来
"""

import streamlit as st
import time
import logging
from typing import Dict, Any

from dashboard.core.ui.utils.style_loader import inject_cached_styles
from dashboard.core.ui.components.registry import get_component_registry

logger = logging.getLogger(__name__)

class UIInitializer:
    """UI初始化器"""
    
    def __init__(self):
        self.initialization_time = 0
        self.initialized_components = set()
    
    def load_styles(self):
        """加载应用样式"""
        start_time = time.time()

        try:
            inject_cached_styles()
            logger.info("UI样式加载成功")
        except Exception as e:
            logger.warning(f"样式加载失败: {e}, 应用将使用默认样式")

        setup_time = time.time() - start_time
        logger.debug(f"Styles loaded in {setup_time:.3f}s")
        self.initialized_components.add('styles')
    
    def initialize_ui_components(self):
        """初始化UI组件"""
        start_time = time.time()

        # 初始化组件注册表
        registry = get_component_registry()
        stats = registry.get_registry_stats()
        logger.info(f"UI组件注册表初始化完成，共注册 {stats['total_components']} 个组件")

        setup_time = time.time() - start_time
        logger.debug(f"UI components initialized in {setup_time:.3f}s")
        self.initialized_components.add('components')
    
    def full_initialize(self) -> Dict[str, Any]:
        """完整初始化UI模块"""
        total_start_time = time.time()

        # 按顺序执行UI初始化步骤
        initialization_steps = [
            ('styles', self.load_styles),
            ('components', self.initialize_ui_components)
        ]
        
        step_times = {}
        
        for step_name, step_func in initialization_steps:
            if step_name not in self.initialized_components:
                step_start = time.time()
                try:
                    step_func()
                    step_times[step_name] = time.time() - step_start
                except Exception as e:
                    logger.error(f"Failed to initialize UI {step_name}: {e}")
                    step_times[step_name] = -1
        
        self.initialization_time = time.time() - total_start_time
        
        return {
            'total_time': self.initialization_time,
            'step_times': step_times,
            'initialized_components': list(self.initialized_components)
        }
    
    def get_initialization_stats(self) -> Dict[str, Any]:
        """获取初始化统计信息"""
        return {
            'initialization_time': self.initialization_time,
            'initialized_components': list(self.initialized_components),
            'component_count': len(self.initialized_components)
        }
    
    def is_complete(self) -> bool:
        """检查UI初始化是否完成"""
        required_components = {'styles', 'components'}
        return required_components.issubset(self.initialized_components)

# 全局UI初始化器实例
import streamlit as st


@st.cache_resource
def get_ui_initializer() -> UIInitializer:
    """获取全局UI初始化器实例"""
    return UIInitializer()

def initialize_ui() -> Dict[str, Any]:
    """UI初始化函数"""
    initializer = get_ui_initializer()
    return initializer.full_initialize()

# 便捷函数
def load_ui_styles():
    """加载UI样式的便捷函数"""
    initializer = get_ui_initializer()
    initializer.load_styles()

def is_ui_initialized() -> bool:
    """检查UI是否已初始化"""
    initializer = get_ui_initializer()
    return initializer.is_complete()

logger.info("[UIInitializer] UI初始化器模块加载完成")
