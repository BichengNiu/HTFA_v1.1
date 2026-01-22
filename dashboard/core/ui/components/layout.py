# -*- coding: utf-8 -*-
"""
布局组件
提供标准化的页面布局组件
"""

import streamlit as st
from typing import List, Dict, Any, Optional
from dashboard.core.ui.components.base import UIComponent

class LayoutComponent(UIComponent):
    """布局组件基类"""
    
    def __init__(self):
        pass
    
    def render(self, st_obj, **kwargs) -> None:
        """渲染布局组件"""
        pass
    
    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        return []

class PageContainer(LayoutComponent):
    """页面容器组件"""
    
    def __init__(self, title: str, subtitle: Optional[str] = None):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
    
    def render(self, st_obj, **kwargs) -> None:
        """渲染页面容器"""
        # 页面标题
        st_obj.markdown(f"# {self.title}")
        
        if self.subtitle:
            st_obj.markdown(f"*{self.subtitle}*")
        
        # 分隔线
        st_obj.markdown("---")

class GridLayout(LayoutComponent):
    """网格布局组件"""
    
    def __init__(self, columns: int = 2, gap: str = "medium"):
        super().__init__()
        self.columns = columns
        self.gap = gap
    
    def render(self, st_obj, **kwargs) -> None:
        """渲染网格布局"""
        items = kwargs.get('items', [])
        
        if not items:
            return
        
        # 创建列
        cols = st_obj.columns(self.columns)
        
        # 分配项目到列
        for i, item in enumerate(items):
            col_index = i % self.columns
            with cols[col_index]:
                if hasattr(item, 'render'):
                    item.render(st_obj)
                else:
                    st_obj.write(item)

class TabbedLayout(LayoutComponent):
    """标签页布局组件"""
    
    def __init__(self, tabs: List[Dict[str, Any]]):
        super().__init__()
        self.tabs = tabs
    
    def render(self, st_obj, **kwargs) -> None:
        """渲染标签页布局"""
        if not self.tabs:
            return
        
        # 创建标签页
        tab_names = [tab['name'] for tab in self.tabs]
        tab_objects = st_obj.tabs(tab_names)
        
        # 渲染每个标签页的内容
        for i, (tab_obj, tab_config) in enumerate(zip(tab_objects, self.tabs)):
            with tab_obj:
                content = tab_config.get('content')
                if content:
                    if hasattr(content, 'render'):
                        content.render(st_obj)
                    elif callable(content):
                        content(st_obj)
                    else:
                        st_obj.write(content)
