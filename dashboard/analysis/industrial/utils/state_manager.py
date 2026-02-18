"""
统一状态管理模块
Unified State Management Module

提供工业分析模块的集中状态管理，消除重复的状态封装函数
"""

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager


# 模块级单例
_instance = NamespacedStateManager("industrial.analysis")


class IndustrialStateManager:
    """
    工业分析模块统一状态管理器

    使用点分命名空间管理状态，避免键冲突
    命名空间: industrial.analysis

    所有方法为 classmethod，委托给 NamespacedStateManager 单例
    """

    @classmethod
    def get(cls, key, default=None):
        return _instance.get(key, default)

    @classmethod
    def set(cls, key, value):
        _instance.set(key, value)

    @classmethod
    def delete(cls, key):
        _instance.delete(key)

    @classmethod
    def has(cls, key):
        return _instance.has(key)
