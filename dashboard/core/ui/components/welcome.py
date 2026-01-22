# -*- coding: utf-8 -*-
"""
欢迎页面组件
提供标准化的欢迎页面和介绍界面
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from dashboard.core.ui.components.base import UIComponent
from dashboard.core.ui.constants import UIConstants

class WelcomeComponent(UIComponent):
    """欢迎页面组件"""
    
    def __init__(self):
        self.constants = UIConstants
    
    def render(self, st_obj, **kwargs) -> None:
        """渲染欢迎页面"""
        welcome_type = kwargs.get('type', 'main_module')
        
        if welcome_type == 'main_module':
            self._render_main_module_welcome(st_obj, **kwargs)
        elif welcome_type == 'sub_module':
            self._render_sub_module_welcome(st_obj, **kwargs)
        else:
            st_obj.error(f"未知的欢迎页面类型: {welcome_type}")
    
    def _render_main_module_welcome(self, st_obj, **kwargs):
        """渲染主模块欢迎页面"""
        module_name = kwargs.get('module_name')
        if not module_name or module_name not in self.constants.MAIN_MODULES:
            st_obj.error("无效的主模块名称")
            return
        
        module_config = self.constants.MAIN_MODULES[module_name]
        
        # 页面标题
        st_obj.markdown(f"""
        <div style="text-align: center; padding: 2rem 0;">
            <h1>{module_config['icon']} {module_name}</h1>
            <p style="font-size: 1.2em; color: #666; margin: 1rem 0;">
                {module_config['description']}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 子模块介绍
        if module_config['sub_modules']:
            st_obj.markdown("### [INFO] 子模块")
            
            # 使用列布局展示子模块
            cols = st_obj.columns(len(module_config['sub_modules']))
            
            for i, sub_module in enumerate(module_config['sub_modules']):
                with cols[i]:
                    self._render_sub_module_card(st_obj, module_name, sub_module)
        
        # 使用说明
        self._render_usage_guide(st_obj, module_name)
    
    def _render_sub_module_welcome(self, st_obj, **kwargs):
        """渲染子模块欢迎页面"""
        sub_module_name = kwargs.get('sub_module_name')
        if not sub_module_name or sub_module_name not in self.constants.SUB_MODULES:
            st_obj.error("无效的子模块名称")
            return
        
        sub_module_config = self.constants.SUB_MODULES[sub_module_name]
        
        # 页面标题
        st_obj.markdown(f"""
        <div style="text-align: center; padding: 2rem 0;">
            <h1>{sub_module_config['icon']} {sub_module_name}</h1>
            <p style="font-size: 1.2em; color: #666; margin: 1rem 0;">
                {sub_module_config['description']}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 子模块介绍
        if 'functions' in sub_module_config:
            st_obj.markdown("### [CONFIG] 分析工具")
            
            # 使用网格布局展示功能
            functions = sub_module_config['functions']
            cols_per_row = 2
            
            for i in range(0, len(functions), cols_per_row):
                cols = st_obj.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(functions):
                        with cols[j]:
                            self._render_function_card(st_obj, functions[i + j])
        
        # 使用流程
        self._render_workflow_guide(st_obj, sub_module_name)
    
    def _render_sub_module_card(self, st_obj, main_module: str, sub_module: str):
        """渲染子模块卡片"""
        # 获取子模块配置
        sub_config = self.constants.SUB_MODULES.get(sub_module, {})
        icon = sub_config.get('icon', '[DATA]')
        description = sub_config.get('description', '暂无描述')
        
        # 使用模板函数渲染子模块卡片
        from dashboard.core.ui.constants import render_template
        card_html = render_template(
            'sub_module_card',
            icon=icon,
            title=sub_module,
            description=description
        )
        st_obj.markdown(card_html, unsafe_allow_html=True)
        
        # 添加选择按钮
        if st_obj.button(f"进入{sub_module}", key=f"enter_{sub_module}", width='stretch'):
            st.session_state["navigation.navigate_to_sub_module"] = sub_module
            st_obj.rerun()
    
    def _render_function_card(self, st_obj, function_config: Dict[str, str]):
        """渲染功能卡片"""
        name = function_config['name']
        icon = function_config['icon']
        description = function_config['description']
        
        # 使用模板函数渲染功能卡片
        from dashboard.core.ui.constants import render_template
        card_html = render_template(
            'function_card',
            icon=icon,
            title=name,
            description=description
        )
        st_obj.markdown(card_html, unsafe_allow_html=True)
    
    def _render_usage_guide(self, st_obj, module_name: str):
        """渲染使用指南"""
        st_obj.markdown("### [GUIDE] 使用指南")
        
        if module_name == "数据探索":
            st_obj.markdown("""
            **使用步骤：**
            1. 选择数据探索子模块
            2. 在子模块页面了解具体的分析工具
            3. 点击相应的分析工具标签页开始使用
            4. 在侧边栏上传数据文件并配置参数
            5. 查看分析结果和可视化图表

            **支持的数据格式：**
            - Excel文件 (.xlsx, .xls)
            - CSV文件 (.csv)
            - 时间序列数据（第一列为时间戳）
            """)
        else:
            st_obj.markdown("""
            **使用步骤：**
            1. 选择相应的子模块
            2. 按照页面指引进行操作
            3. 查看分析结果
            """)
    
    def _render_workflow_guide(self, st_obj, sub_module_name: str):
        """渲染工作流程指南"""
        st_obj.markdown("### [INFO] 工作流程")
        
        if sub_module_name == "数据探索":
            st_obj.markdown("""
            **推荐分析流程：**
            1. **平稳性分析** - 首先检验数据的平稳性特征
            2. **相关性分析** - 探索变量间的时间滞后相关性
            3. **领先滞后分析** - 识别变量间的因果关系和预测能力

            **数据要求：**
            - 时间序列数据，第一列为时间戳
            - 支持多个变量的同时分析
            - 建议数据长度不少于30个观测值
            """)
    
    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        return ['navigate_to_sub_module']
