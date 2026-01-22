# -*- coding: utf-8 -*-
"""
DFM数据上传侧边栏组件
"""

import streamlit as st
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dashboard.core.ui.components.sidebar.base import SidebarComponent

logger = logging.getLogger(__name__)


class DFMDataUploadSidebar(SidebarComponent):
    """
    DFM数据上传侧边栏组件

    完全基于UnifiedDataUploadComponent实现。
    """

    def __init__(self):
        super().__init__()
        self._supported_formats = ['xlsx', 'xls']
        self._max_file_size = 100  # MB

        # 使用UnifiedDataUploadComponent
        from dashboard.core.ui.components.data_input import UnifiedDataUploadComponent
        self.upload_component = UnifiedDataUploadComponent(
            accepted_types=self._supported_formats,
            max_file_size=self._max_file_size,
            help_text="请上传包含时间序列数据的Excel文件（支持.xlsx, .xls格式）",
            show_data_source_selector=False,
            show_staging_data_option=False,
            component_id="dfm_data_upload",
            return_file_object=True  # DFM需要文件对象
        )

    def render(self, st_obj, **kwargs) -> Dict[str, Any]:
        """渲染DFM数据上传侧边栏"""
        st_obj.subheader("DFM 数据上传")

        # 检查是否已有上传的文件
        existing_file = self._get_existing_file()

        if existing_file:
            # 显示已上传文件的信息
            st_obj.success(f"已上传文件: {existing_file['name']}")

            # 显示文件信息
            col1, col2 = st_obj.columns(2)
            with col1:
                st_obj.metric("文件大小", f"{existing_file.get('size', 0):.2f} MB")
            with col2:
                st_obj.metric("上传时间", existing_file.get('upload_time', '未知'))

            # 提供重新上传选项
            if st_obj.button("重新上传文件", key="dfm_reupload_btn"):
                self._clear_existing_file()
                st_obj.rerun()

            return {
                'has_file': True,
                'file_info': existing_file,
                'uploaded_file': None
            }

        # 使用UnifiedDataUploadComponent上传
        uploaded_file = self.upload_component.render_file_upload_section(
            st_obj,
            upload_key=kwargs.get('upload_key', 'dfm_data_upload_unified'),
            show_overview=False,
            show_preview=False
        )

        if uploaded_file is not None:
            file_name = self.upload_component.get_state('file_name')
            logger.debug(f"检测到文件上传，文件名: {file_name}")

            if file_name:
                self._save_to_dfm_state(uploaded_file, file_name)
            else:
                logger.warning("file_name为空，尝试使用uploaded_file.name")
                if hasattr(uploaded_file, 'name'):
                    file_name = uploaded_file.name
                    self._save_to_dfm_state(uploaded_file, file_name)
                else:
                    logger.error("无法获取文件名，跳过保存")

            st_obj.info("文件已加载，可用于DFM模型的各个功能模块。")
            file_size = len(uploaded_file.getvalue()) / 1024 / 1024

            return {
                'has_file': True,
                'uploaded_file': uploaded_file,
                'file_size': file_size,
                'save_result': {'success': True}
            }

        return {
            'has_file': False,
            'uploaded_file': None
        }

    def _get_existing_file(self) -> Optional[Dict[str, Any]]:
        """获取已存在的文件信息"""
        # 获取文件对象和路径
        file_obj = st.session_state.get('data_prep.dfm_training_data_file', None)
        file_path = st.session_state.get('data_prep.dfm_uploaded_excel_file_path', None)
        upload_time = st.session_state.get('data_prep.dfm_upload_time', None)

        if file_obj and file_path:
            # 计算文件大小
            file_size = len(file_obj.getvalue()) / 1024 / 1024 if hasattr(file_obj, 'getvalue') else 0

            return {
                'name': file_path,
                'size': file_size,
                'upload_time': upload_time or '未知',
                'file_obj': file_obj
            }
        return None

    def _clear_existing_file(self) -> None:
        """清除已存在的文件"""
        # 清除相关状态
        st.session_state['data_prep.dfm_training_data_file'] = None
        st.session_state['data_prep.dfm_uploaded_excel_file_path'] = None
        st.session_state['data_prep.dfm_file_processed'] = False
        st.session_state['data_prep.dfm_date_detection_needed'] = True

    def _save_to_dfm_state(self, data_or_file, filename: str) -> None:
        """保存文件到DFM状态管理（回调函数）"""
        uploaded_file = data_or_file

        logger.info(f"开始保存文件到DFM状态: {filename}")
        file_bytes = uploaded_file.getvalue()

        st.session_state['data_prep.dfm_training_data_bytes'] = file_bytes
        st.session_state['data_prep.dfm_training_data_file'] = uploaded_file
        st.session_state['data_prep.dfm_uploaded_excel_file_path'] = filename
        st.session_state['data_prep.dfm_upload_time'] = datetime.now().strftime('%H:%M:%S')
        st.session_state['data_prep.dfm_use_full_data_preparation'] = True
        st.session_state['data_prep.dfm_file_processed'] = False
        st.session_state['data_prep.dfm_date_detection_needed'] = True
        logger.info(f"文件保存成功: {filename}, 字节大小: {len(file_bytes)}")

        saved_bytes = st.session_state.get('data_prep.dfm_training_data_bytes', None)
        saved_path = st.session_state.get('data_prep.dfm_uploaded_excel_file_path', None)
        logger.debug(f"验证保存 - 字节内容: {saved_bytes is not None and len(saved_bytes) > 0}, 路径: {saved_path}")

    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        return [
            'dfm_training_data_file',
            'dfm_uploaded_excel_file_path',
            'dfm_use_full_data_preparation',
            'dfm_file_processed',
            'dfm_date_detection_needed'
        ]
