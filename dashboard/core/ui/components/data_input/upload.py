# -*- coding: utf-8 -*-
"""
统一数据上传组件
整合原有的数据上传功能，提供统一的数据上传界面
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
from typing import List, Dict, Any, Optional, Tuple
import logging

from dashboard.core.ui.components.data_input.base import DataInputComponent
from dashboard.core.ui.components.sidebar import SidebarComponent

logger = logging.getLogger(__name__)


class UnifiedDataUploadComponent(DataInputComponent):
    """
    统一数据上传组件

    全局统一的数据上传组件，所有模块都使用此组件，统一默认样式。
    """

    def __init__(self,
                 accepted_types: List[str] = None,
                 max_file_size: int = 200,  # MB
                 help_text: str = None,
                 show_data_source_selector: bool = True,
                 show_staging_data_option: bool = True,
                 component_id: str = None,
                 return_file_object: bool = False,
                 quiet_mode: bool = False):
        """
        Args:
            accepted_types: 接受的文件类型列表
            max_file_size: 最大文件大小（MB）
            help_text: 帮助文本
            show_data_source_selector: 是否显示数据源选择器
            show_staging_data_option: 是否显示暂存区选项
            component_id: 组件ID
            return_file_object: 是否返回文件对象而不是DataFrame（某些模块需要）
            quiet_mode: 静默模式，不显示加载过程中的中间消息
        """
        component_name = component_id or f"upload_{id(self)}"
        super().__init__(component_name, "数据上传")
        self.accepted_types = accepted_types or ['xlsx', 'xls', 'csv']
        self.max_file_size = max_file_size
        self.help_text = help_text or "请上传Excel或CSV格式的数据文件"
        self.show_data_source_selector = show_data_source_selector
        self.show_staging_data_option = show_staging_data_option
        self.return_file_object = return_file_object
        self.quiet_mode = quiet_mode
    
    def load_and_preprocess_data(self, uploaded_file) -> Tuple[Optional[pd.DataFrame], str]:
        """
        加载和预处理上传的数据文件
        
        Args:
            uploaded_file: Streamlit上传的文件对象
            
        Returns:
            Tuple[Optional[pd.DataFrame], str]: (数据DataFrame, 状态消息)
        """
        try:
            file_name = uploaded_file.name
            file_extension = file_name.split('.')[-1].lower()
            
            # 读取文件内容
            file_content = uploaded_file.read()
            
            # 根据文件类型读取数据
            if file_extension == 'csv':
                # 尝试不同的编码
                for encoding in ['utf-8', 'gbk', 'gb2312']:
                    try:
                        # 第一列默认为时间列，直接解析为datetime
                        df = pd.read_csv(
                            io.StringIO(file_content.decode(encoding)),
                            parse_dates=[0]
                        )
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return None, f"无法解码CSV文件 '{file_name}'，请检查文件编码"

            elif file_extension in ['xlsx', 'xls']:
                # 第一列默认为时间列，直接解析为datetime
                df = pd.read_excel(io.BytesIO(file_content), parse_dates=[0])
            else:
                return None, f"不支持的文件格式: {file_extension}"
            
            # 基本数据清理
            if df.empty:
                return None, f"文件 '{file_name}' 为空"
            
            # 删除完全为空的行和列
            df = df.dropna(how='all').dropna(axis=1, how='all')
            
            if df.empty:
                return None, f"文件 '{file_name}' 在清理后为空"
            
            return df, f"成功加载文件 '{file_name}'"
            
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            return None, f"加载文件失败: {str(e)}"
    
    def render_data_source_selector(self, st_obj, **kwargs) -> str:
        """渲染数据源选择器"""
        if not self.show_data_source_selector:
            return "上传新文件"

        data_source_options = ["上传新文件"]
        if self.show_staging_data_option:
            data_source_options.append("从暂存区选择")

        def on_data_source_change():
            """数据源改变时的回调"""
            # 清理相关状态
            self.set_state('data', None)
            self.set_state('file_name', None)
            self.set_state('data_source', None)

        selected_source = st_obj.radio(
            "选择数据来源:",
            options=data_source_options,
            key=f"{self.component_name}_data_source_radio",
            horizontal=True,
            on_change=on_data_source_change
        )

        return selected_source

    def render_input_section(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染数据上传输入部分"""

        # 数据源选择
        selected_source = self.render_data_source_selector(st_obj, **kwargs)

        if selected_source == "上传新文件":
            return self.render_file_upload_section(st_obj, **kwargs)
        elif selected_source == "从暂存区选择":
            return self.render_staging_data_selection(st_obj, **kwargs)

        return None

    def render_file_upload_section(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染文件上传部分"""

        # 获取上传器重置键
        uploader_reset_key = self.get_state('uploader_reset_key', 0)

        # 文件上传器
        st_obj.markdown("##### 上传数据")
        upload_key = kwargs.get('upload_key', f'{self.component_name}_file_uploader_{uploader_reset_key}')
        uploaded_file = st_obj.file_uploader(
            "选择数据文件",
            type=self.accepted_types,
            help=self.help_text,
            key=upload_key
        )
        
        if uploaded_file is not None:
            # 检查是否是新上传的文件
            current_file_name = self.get_state('file_name')
            current_data = self.get_state('data')
            is_new_upload = (uploaded_file.name != current_file_name or current_data is None)

            if is_new_upload:
                # 检查文件大小
                file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
                if file_size_mb > self.max_file_size:
                    st_obj.error(f"文件大小 ({file_size_mb:.1f}MB) 超过限制 ({self.max_file_size}MB)")
                    return None

                # 如果需要返回文件对象，直接返回
                if self.return_file_object:
                    if not self.quiet_mode:
                        st_obj.success(f"已上传文件: {uploaded_file.name}")
                        st_obj.info(f"文件大小: {file_size_mb:.2f} MB")
                    return uploaded_file

                # 加载和预处理数据
                spinner_text = f"正在加载文件: {uploaded_file.name}..." if not self.quiet_mode else "正在加载..."
                with st_obj.spinner(spinner_text):
                    df, message = self.load_and_preprocess_data(uploaded_file)

                if df is not None and not df.empty:
                    # 保存到状态
                    self.set_state('data', df)
                    self.set_state('original_data', df.copy())
                    self.set_state('file_name', uploaded_file.name)
                    self.set_state('data_source', 'upload')

                    # 显示数据概览
                    if kwargs.get('show_overview', True):
                        self.render_data_overview(st_obj, df, uploaded_file.name)

                    # 显示数据预览
                    if kwargs.get('show_preview', True):
                        st_obj.markdown("**数据预览：**")
                        st_obj.dataframe(df.head(10), width='stretch')

                    return df
                elif df is not None and df.empty:
                    st_obj.error(f"文件 '{uploaded_file.name}' 加载后为空。请检查文件内容。")
                    # 清理状态
                    self.set_state('data', None)
                    self.set_state('original_data', None)
                    self.set_state('file_name', None)
                    return None
                else:
                    st_obj.error(f"无法加载文件 '{uploaded_file.name}'。{message}")
                    # 清理状态
                    self.set_state('data', None)
                    self.set_state('original_data', None)
                    self.set_state('file_name', None)
                    return None
            else:
                # 返回已加载的数据
                return current_data

        return None

    def render_data_overview(self, st_obj, df: pd.DataFrame, file_name: str):
        """渲染数据概览"""
        st_obj.markdown("**数据概览：**")

        col1, col2, col3, col4 = st_obj.columns(4)

        with col1:
            st_obj.metric("文件名", file_name)

        with col2:
            st_obj.metric("总行数", df.shape[0])

        with col3:
            st_obj.metric("总列数", df.shape[1])

        with col4:
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            st_obj.metric("数值列", len(numeric_cols))

    def render_staging_data_selection(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染暂存数据选择 - 使用统一命名约定"""
        import streamlit as st
                # 获取暂存数据 - 使用统一命名约定
        staged_data_dict = st.session_state.get('tools.data_input.staging.staged_data_dict', {})

        if not staged_data_dict:
            st_obj.info("暂存区中没有可用数据")
            return None

        # 数据选择器
        selected_name = st_obj.selectbox(
            "选择暂存数据:",
            options=list(staged_data_dict.keys()),
            key=f"{self.component_name}_staging_selector"
        )

        if selected_name:
            selected_data = staged_data_dict[selected_name]

            # 保存到状态
            self.set_state('data', selected_data)
            self.set_state('file_name', selected_name)
            self.set_state('data_source', 'staging')

            st_obj.success(f"已选择暂存数据: {selected_name}")

            # 显示数据概览
            if kwargs.get('show_overview', True):
                self.render_data_overview(st_obj, selected_data, selected_name)

            # 显示数据预览
            if kwargs.get('show_preview', True):
                st_obj.markdown("**数据预览：**")
                st_obj.dataframe(selected_data.head(10), width='stretch')

            return selected_data

        return None


class DataUploadSidebar(SidebarComponent):
    """
    数据上传侧边栏组件

    基于 UnifiedDataUploadComponent，提供sidebar版本的数据上传功能。
    所有模块统一使用默认样式。
    """

    def __init__(self,
                 title: str = "数据上传",
                 accepted_types: List[str] = None,
                 help_text: str = None,
                 show_staging_data: bool = True,
                 component_id: str = None):
        """
        Args:
            title: 侧边栏标题
            accepted_types: 接受的文件类型
            help_text: 帮助文本
            show_staging_data: 是否显示暂存数据选择
            component_id: 组件ID
        """
        super().__init__()
        self.title = title
        self.upload_component = UnifiedDataUploadComponent(
            accepted_types=accepted_types,
            help_text=help_text,
            component_id=component_id
        )
        self.show_staging_data = show_staging_data
    
    def render_staging_data_selection(self, st_obj) -> Optional[pd.DataFrame]:
        """渲染暂存数据选择"""
        if not self.show_staging_data:
            return None

        # 获取暂存数据 - 使用统一命名约定
        import streamlit as st
        if not tools_manager:
            return None

        # 获取所有暂存数据 - 使用统一命名约定
        staged_data_dict = st.session_state.get('tools.data_input.staging.staged_data_dict', {})

        if not staged_data_dict:
            st_obj.info("暂存区暂无数据")
            return None

        st_obj.markdown("**或从暂存区选择：**")

        # 创建选择选项
        staged_options = ["请选择..."] + list(staged_data_dict.keys())
        selected_staged = st_obj.selectbox(
            "选择暂存数据",
            options=staged_options,
            key="sidebar_staged_data_selector"
        )

        if selected_staged != "请选择...":
            staged_data = staged_data_dict[selected_staged]
            if isinstance(staged_data, pd.DataFrame):
                st_obj.success(f"已选择暂存数据: {selected_staged}")
                return staged_data
            else:
                st_obj.error(f"暂存数据 '{selected_staged}' 格式无效")

        return None
    
    def render(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染数据上传侧边栏"""
        with st_obj.sidebar:
            st_obj.markdown(f"### {self.title}")
            
            # 渲染上传组件
            uploaded_data = self.upload_component.render_input_section(
                st_obj, 
                show_preview=False,  # 侧边栏不显示预览
                **kwargs
            )
            
            if uploaded_data is not None:
                return uploaded_data
            
            # 渲染暂存数据选择
            staged_data = self.render_staging_data_selection(st_obj)
            if staged_data is not None:
                return staged_data
            
            return None
    
    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        return self.upload_component.get_state_keys() + [
            'sidebar_staged_data_selector'
        ]


__all__ = ['UnifiedDataUploadComponent', 'DataUploadSidebar']
