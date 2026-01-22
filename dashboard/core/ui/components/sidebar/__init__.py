# -*- coding: utf-8 -*-
"""
侧边栏组件模块
拆分后的统一导出接口
"""

from dashboard.core.ui.components.sidebar.base import SidebarComponent
from dashboard.core.ui.components.sidebar.dfm import DFMDataUploadSidebar
from dashboard.core.ui.components.sidebar.renderer import (
    render_complete_sidebar,
    render_data_upload_section,
    create_sidebar_container,
    get_upload_section_config,
    filter_modules_by_permission
)

__all__ = [
    'SidebarComponent',
    'DFMDataUploadSidebar',
    'render_complete_sidebar',
    'render_data_upload_section',
    'create_sidebar_container',
    'get_upload_section_config',
    'filter_modules_by_permission'
]
