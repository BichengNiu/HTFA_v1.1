# -*- coding: utf-8 -*-
"""
标签页状态检测工具
简化版本：使用静态方法，直接操作st.session_state
"""

import streamlit as st
from typing import Optional
from dashboard.core.ui.constants import NavigationLevel
from dashboard.explore.core.constants import STATE_KEYS


class TabStateDetector:
    """标签页状态检测器 - 静态方法版本"""

    @staticmethod
    def detect_active_tab(sub_module: str) -> Optional[str]:
        """
        检测当前激活的标签页

        Args:
            sub_module: 子模块名称(如"数据探索")

        Returns:
            激活的标签页名称,如果没有激活的标签页则返回None
        """
        # 检查活跃标签页
        active_tab = st.session_state.get(STATE_KEYS["active_tab"], None)
        if active_tab:
            return active_tab

        # 备用方法: 通过标志和时间戳检测
        return TabStateDetector._detect_by_flags_and_timestamps(sub_module)

    @staticmethod
    def _detect_by_flags_and_timestamps(sub_module: str = None) -> Optional[str]:
        """通过标志和时间戳检测活跃标签页"""
        flags = STATE_KEYS["tab_flags"]
        timestamps = STATE_KEYS["timestamps"]

        # 检查哪个标签页的标志为True
        active_tabs = []
        for tab_name, flag_key in flags.items():
            if st.session_state.get(flag_key, False):
                timestamp = st.session_state.get(timestamps[tab_name], 0)
                active_tabs.append((tab_name, timestamp))

        if active_tabs:
            # 返回时间戳最新的标签页
            active_tabs.sort(key=lambda x: x[1], reverse=True)
            return active_tabs[0][0]

        return None

    @staticmethod
    def has_active_tab(sub_module: str) -> bool:
        """
        检查是否有激活的标签页

        Args:
            sub_module: 子模块名称

        Returns:
            是否有激活的标签页
        """
        return TabStateDetector.detect_active_tab(sub_module) is not None

    @staticmethod
    def get_navigation_level(main_module: str, sub_module: Optional[str]) -> NavigationLevel:
        """
        获取当前导航层级

        Args:
            main_module: 主模块名称
            sub_module: 子模块名称

        Returns:
            当前导航层级
        """
        if not sub_module:
            # 如果没有选择子模块，清除所有标签页状态
            TabStateDetector.clear_all_tab_states()
            return NavigationLevel.MAIN_MODULE

        if sub_module and not TabStateDetector.has_active_tab(sub_module):
            return NavigationLevel.SUB_MODULE

        return NavigationLevel.FUNCTION

    @staticmethod
    def clear_all_tab_states():
        """清除所有标签页状态"""
        tab_key = STATE_KEYS["active_tab"]
        if tab_key in st.session_state:
            del st.session_state[tab_key]

    @staticmethod
    def should_show_sidebar(main_module: str, sub_module: Optional[str]) -> bool:
        """
        判断是否应该显示侧边栏

        Args:
            main_module: 主模块名称
            sub_module: 子模块名称

        Returns:
            是否应该显示侧边栏
        """
        # 只有在第三层(具体功能层)才显示侧边栏
        if main_module == "数据探索":
            return True

        return False


