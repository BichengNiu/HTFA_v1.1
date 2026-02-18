# -*- coding: utf-8 -*-
"""
状态管理器包装类
为组件提供统一的状态访问接口
"""

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager


class StateManager(NamespacedStateManager):
    """状态管理器包装类，继承自通用 NamespacedStateManager"""

    def __init__(self, namespace: str = 'train_model'):
        super().__init__(namespace)
