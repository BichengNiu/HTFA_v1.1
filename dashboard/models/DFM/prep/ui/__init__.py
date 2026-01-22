# -*- coding: utf-8 -*-
"""
DFM数据准备UI模块
提供数据准备相关的页面和组件
"""

# 状态键定义（无依赖，可安全导入）
from dashboard.models.DFM.prep.ui.state_keys import DataPrepStateKeys

# 延迟导入页面和组件，避免循环导入
def get_render_function():
    from dashboard.models.DFM.prep.ui.pages.data_prep_page import render_dfm_data_prep_page
    return render_dfm_data_prep_page

def get_components():
    from dashboard.models.DFM.prep.ui.components import (
        DataPreviewComponent,
        ProcessingStatusComponent
    )
    return DataPreviewComponent, ProcessingStatusComponent

__all__ = [
    'DataPrepStateKeys',
    'get_render_function',
    'get_components'
]
