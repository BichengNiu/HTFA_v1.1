# -*- coding: utf-8 -*-
"""
资源加载器 - 简化版
提供模块懒加载功能
"""

import streamlit as st
import time
import importlib
import sys
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResourceLoader:
    """资源加载器 - 简化版"""

    def __init__(self):
        self.loaded_resources: Dict[str, Any] = {}
        self.load_times: Dict[str, float] = {}
        self._setup_config()
        self._setup_component_registry()

    def _setup_config(self):
        """从配置系统加载配置"""
        from dashboard.core.backend.config import get_core_config
        self.config = get_core_config()

    def _setup_component_registry(self):
        """设置组件注册表"""
        from dashboard.core.ui.components.registry import get_component_registry
        self.component_registry = get_component_registry()

    def load_resource(self, resource_name: str,
                     is_component: bool = False,
                     force_reload: bool = False) -> Optional[Any]:
        """
        加载资源（模块或组件）

        Args:
            resource_name: 资源名称
            is_component: 是否为组件（默认False，即模块）
            force_reload: 是否强制重新加载

        Returns:
            加载的资源，失败返回None
        """
        # 快速路径：已加载
        if not force_reload and resource_name in self.loaded_resources:
            return self.loaded_resources[resource_name]

        start_time = time.time()

        try:
            # 获取模块路径
            module_path = self._get_resource_path(resource_name, is_component)

            if not module_path:
                logger.warning(f"未知的资源: {resource_name}")
                return None

            # 动态导入
            if force_reload and module_path in sys.modules:
                del sys.modules[module_path]

            module = importlib.import_module(module_path)

            # 缓存结果
            self.loaded_resources[resource_name] = module
            self.load_times[resource_name] = (time.time() - start_time) * 1000

            logger.info(f"资源加载成功: {resource_name} ({self.load_times[resource_name]:.2f}ms)")
            return module

        except Exception as e:
            logger.error(f"加载资源 {resource_name} 失败: {e}")
            return None

    def _get_resource_path(self, resource_name: str,
                          is_component: bool) -> Optional[str]:
        """获取资源路径"""
        if is_component and self.component_registry:
            return self.component_registry.get_component_path(resource_name)
        return self.config.get_module_path(resource_name)

    def preload_critical_resources(self):
        """预加载关键资源"""
        critical_resources = ['data_loader', 'preview_main']

        logger.info("开始预加载关键资源")
        for resource in critical_resources:
            try:
                self.load_resource(resource)
            except Exception as e:
                logger.warning(f"预加载资源 {resource} 失败: {e}")

    def get_loading_stats(self) -> Dict[str, Any]:
        """获取加载统计信息"""
        return {
            'loaded_count': len(self.loaded_resources),
            'total_configured': len(self.config.get_module_paths()),
            'load_times': self.load_times.copy(),
            'average_load_time': (
                sum(self.load_times.values()) / len(self.load_times)
                if self.load_times else 0
            )
        }

    def is_loaded(self, resource_name: str) -> bool:
        """检查资源是否已加载"""
        return resource_name in self.loaded_resources

    def get_resource(self, resource_name: str) -> Optional[Any]:
        """获取已加载的资源（不触发加载）"""
        return self.loaded_resources.get(resource_name)

    def clear_cache(self):
        """清理资源缓存"""
        self.loaded_resources.clear()
        self.load_times.clear()
        logger.info("资源缓存已清理")


# 全局资源加载器实例
@st.cache_resource
def get_resource_loader() -> ResourceLoader:
    """获取全局资源加载器实例"""
    return ResourceLoader()
