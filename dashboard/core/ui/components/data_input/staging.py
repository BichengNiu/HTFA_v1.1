# -*- coding: utf-8 -*-
"""
数据暂存组件
提供数据暂存、管理和选择功能
"""

import streamlit as st
import pandas as pd
import copy
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime

from dashboard.core.ui.components.data_input.base import DataInputComponent

logger = logging.getLogger(__name__)


class DataStagingComponent(DataInputComponent):
    """数据暂存组件"""
    
    def __init__(self):
        super().__init__("staging", "数据暂存")
    
    def get_staged_data_dict(self) -> Dict[str, pd.DataFrame]:
        """获取所有暂存数据 - 使用统一命名约定"""
        import streamlit as st
        # 使用统一的命名约定：data_input.staging.staged_data_dict
        return st.session_state.get('tools.data_input.staging.staged_data_dict', {})

    def set_staged_data_dict(self, staged_data_dict: Dict[str, pd.DataFrame]) -> bool:
        """设置暂存数据字典 - 使用统一命名约定"""
        import streamlit as st
        # 使用统一的命名约定：data_input.staging.staged_data_dict
        try:
            st.session_state['tools.data_input.staging.staged_data_dict'] = staged_data_dict
            logger.debug(f"设置暂存数据成功，共{len(staged_data_dict)}个数据集")
            return True
        except Exception as e:
            logger.warning(f"设置暂存数据失败: {e}")
            return False
    
    def add_to_staging(self, data: pd.DataFrame, name: str, overwrite: bool = False) -> Tuple[bool, str]:
        """
        添加数据到暂存区
        
        Args:
            data: 要暂存的数据
            name: 暂存名称
            overwrite: 是否覆盖已存在的数据
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            if data is None or data.empty:
                return False, "无法暂存空数据"
            
            staged_data_dict = self.get_staged_data_dict()
            
            # 检查名称冲突
            if name in staged_data_dict and not overwrite:
                return False, f"暂存名称 '{name}' 已存在，请选择其他名称或选择覆盖"
            
            # 深拷贝数据以避免引用问题
            staged_data_dict[name] = copy.deepcopy(data)
            
            # 保存到状态
            success = self.set_staged_data_dict(staged_data_dict)
            
            if success:
                action = "覆盖" if name in staged_data_dict else "添加"
                return True, f"成功{action}暂存数据 '{name}' ({data.shape[0]}行 × {data.shape[1]}列)"
            else:
                return False, "保存暂存数据失败"
                
        except Exception as e:
            logger.error(f"添加暂存数据失败: {e}")
            return False, f"添加暂存数据失败: {str(e)}"
    
    def remove_from_staging(self, name: str) -> Tuple[bool, str]:
        """
        从暂存区移除数据
        
        Args:
            name: 要移除的暂存名称
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            staged_data_dict = self.get_staged_data_dict()
            
            if name not in staged_data_dict:
                return False, f"暂存数据 '{name}' 不存在"
            
            del staged_data_dict[name]
            success = self.set_staged_data_dict(staged_data_dict)
            
            if success:
                return True, f"成功移除暂存数据 '{name}'"
            else:
                return False, "移除暂存数据失败"
                
        except Exception as e:
            logger.error(f"移除暂存数据失败: {e}")
            return False, f"移除暂存数据失败: {str(e)}"
    
    def clear_all_staging(self) -> Tuple[bool, str]:
        """清空所有暂存数据"""
        try:
            success = self.set_staged_data_dict({})
            if success:
                return True, "成功清空所有暂存数据"
            else:
                return False, "清空暂存数据失败"
        except Exception as e:
            logger.error(f"清空暂存数据失败: {e}")
            return False, f"清空暂存数据失败: {str(e)}"
    
    def render_staging_manager(self, st_obj):
        """渲染暂存数据管理界面"""
        
        staged_data_dict = self.get_staged_data_dict()
        
        if not staged_data_dict:
            st_obj.info("暂存区暂无数据")
            return
        
        st_obj.markdown(f"**暂存区数据 ({len(staged_data_dict)} 项)：**")
        
        # 创建数据表格显示
        staging_info = []
        for name, data in staged_data_dict.items():
            if isinstance(data, pd.DataFrame):
                staging_info.append({
                    '名称': name,
                    '行数': data.shape[0],
                    '列数': data.shape[1],
                    '大小(MB)': round(data.memory_usage(deep=True).sum() / 1024 / 1024, 2)
                })
        
        if staging_info:
            staging_df = pd.DataFrame(staging_info)
            st_obj.dataframe(staging_df, width='stretch')
            
            # 操作按钮
            col1, col2 = st_obj.columns(2)
            
            with col1:
                # 选择要移除的数据
                if len(staged_data_dict) > 0:
                    selected_to_remove = st_obj.selectbox(
                        "选择要移除的数据",
                        options=["请选择..."] + list(staged_data_dict.keys()),
                        key=f"{self.component_name}_remove_selector"
                    )
                    
                    if st_obj.button("移除选中数据", key=f"{self.component_name}_remove_btn"):
                        if selected_to_remove != "请选择...":
                            success, message = self.remove_from_staging(selected_to_remove)
                            if success:
                                st_obj.success(message)
                                st_obj.rerun()
                            else:
                                st_obj.error(message)
            
            with col2:
                # 清空所有数据
                if st_obj.button("清空所有暂存数据", 
                               key=f"{self.component_name}_clear_all_btn",
                               type="secondary"):
                    success, message = self.clear_all_staging()
                    if success:
                        st_obj.success(message)
                        st_obj.rerun()
                    else:
                        st_obj.error(message)
    
    def render_staging_selector(self, st_obj) -> Optional[pd.DataFrame]:
        """渲染暂存数据选择器"""
        
        staged_data_dict = self.get_staged_data_dict()
        
        if not staged_data_dict:
            return None
        
        # 选择暂存数据
        selected_name = st_obj.selectbox(
            "从暂存区选择数据",
            options=["请选择..."] + list(staged_data_dict.keys()),
            key=f"{self.component_name}_data_selector"
        )
        
        if selected_name != "请选择...":
            selected_data = staged_data_dict[selected_name]
            if isinstance(selected_data, pd.DataFrame):
                st_obj.success(f"已选择暂存数据: {selected_name}")
                
                # 显示数据预览
                with st_obj.expander("数据预览", expanded=False):
                    st_obj.dataframe(selected_data.head(10), width='stretch')
                
                return selected_data
            else:
                st_obj.error(f"暂存数据 '{selected_name}' 格式无效")
        
        return None
    
    def render_add_to_staging(self, st_obj, data: pd.DataFrame, default_name: str = None):
        """渲染添加到暂存区的界面"""
        
        if data is None or data.empty:
            st_obj.warning("没有可暂存的数据")
            return
        
        st_obj.markdown("**添加到暂存区：**")
        
        # 生成默认名称
        if default_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"data_{timestamp}"
        
        col1, col2 = st_obj.columns([3, 1])
        
        with col1:
            staging_name = st_obj.text_input(
                "暂存名称",
                value=default_name,
                key=f"{self.component_name}_name_input"
            )
        
        with col2:
            overwrite = st_obj.checkbox(
                "覆盖已存在",
                key=f"{self.component_name}_overwrite_checkbox"
            )
        
        if st_obj.button("添加到暂存区", key=f"{self.component_name}_add_btn"):
            if staging_name.strip():
                success, message = self.add_to_staging(data, staging_name.strip(), overwrite)
                if success:
                    st_obj.success(message)
                else:
                    st_obj.error(message)
            else:
                st_obj.error("请输入有效的暂存名称")
    
    def render_column_time_staging(self, st_obj, data: pd.DataFrame, **kwargs) -> Optional[pd.DataFrame]:
        """渲染列选择和时间筛选的暂存界面"""

        st_obj.markdown("#### 数据暂存控制")
        st_obj.caption("选择要暂存的列和时间范围，然后添加到暂存区")

        if data is None or data.empty:
            st_obj.info("没有可暂存的数据。请先处理数据。")
            return None

        # 列选择
        col1, col2 = st_obj.columns(2)

        with col1:
            st_obj.markdown("**选择要暂存的列：**")
            selected_columns = st_obj.multiselect(
                "选择列:",
                options=list(data.columns),
                default=list(data.columns)[:5] if len(data.columns) > 5 else list(data.columns),
                key=f"{self.component_name}_staging_columns"
            )

        with col2:
            st_obj.markdown("**时间范围筛选（可选）：**")

            # 尝试识别时间列
            time_column = None
            for col in data.columns:
                try:
                    pd.to_datetime(data[col], errors='raise')
                    time_column = col
                    break
                except:
                    continue

            if time_column:
                st_obj.success(f"识别到时间列: {time_column}")

                time_series = pd.to_datetime(data[time_column])
                min_date = time_series.min().date()
                max_date = time_series.max().date()

                enable_time_filter = st_obj.checkbox(
                    "启用时间筛选",
                    key=f"{self.component_name}_enable_time_filter"
                )

                if enable_time_filter:
                    date_range = st_obj.date_input(
                        "选择时间范围:",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key=f"{self.component_name}_staging_date_range"
                    )
                else:
                    date_range = None
            else:
                st_obj.info("未识别到时间列，跳过时间筛选")
                date_range = None

        # 暂存名称输入
        staging_name = st_obj.text_input(
            "暂存数据名称:",
            value=f"staged_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            key=f"{self.component_name}_staging_name"
        )

        # 暂存按钮
        col1, col2 = st_obj.columns(2)

        with col1:
            if st_obj.button("添加到暂存区", key=f"{self.component_name}_add_to_staging"):
                if not selected_columns:
                    st_obj.warning("请至少选择一列")
                    return None

                if not staging_name.strip():
                    st_obj.warning("请输入暂存数据名称")
                    return None

                # 处理数据
                staged_data = data[selected_columns].copy()

                # 应用时间筛选
                if time_column and date_range and len(date_range) == 2:
                    start_date, end_date = date_range
                    time_mask = (pd.to_datetime(staged_data[time_column]).dt.date >= start_date) & \
                               (pd.to_datetime(staged_data[time_column]).dt.date <= end_date)
                    staged_data = staged_data[time_mask]

                # 添加到暂存区
                success, message = self.add_to_staging(staged_data, staging_name.strip())

                if success:
                    st_obj.success(message)
                    st_obj.info(f"暂存数据形状: {staged_data.shape}")

                    # 显示暂存数据预览
                    with st_obj.expander("查看暂存数据预览"):
                        st_obj.dataframe(staged_data.head(10), width='stretch')

                    return staged_data
                else:
                    st_obj.error(message)
                    return None

        with col2:
            if st_obj.button("预览处理后数据", key=f"{self.component_name}_preview_processed"):
                if not selected_columns:
                    st_obj.warning("请至少选择一列")
                    return None

                # 处理数据预览
                preview_data = data[selected_columns].copy()

                # 应用时间筛选
                if time_column and date_range and len(date_range) == 2:
                    start_date, end_date = date_range
                    time_mask = (pd.to_datetime(preview_data[time_column]).dt.date >= start_date) & \
                               (pd.to_datetime(preview_data[time_column]).dt.date <= end_date)
                    preview_data = preview_data[time_mask]

                st_obj.markdown("**处理后数据预览：**")
                st_obj.dataframe(preview_data.head(10), width='stretch')
                st_obj.info(f"预览数据形状: {preview_data.shape}")

                return preview_data

        return None

    def render_input_section(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染暂存组件输入部分"""

        mode = kwargs.get('mode', 'select')  # 'select', 'manage', 'add', 'column_time'

        if mode == 'select':
            return self.render_staging_selector(st_obj)
        elif mode == 'manage':
            self.render_staging_manager(st_obj)
            return None
        elif mode == 'add':
            data = kwargs.get('data')
            default_name = kwargs.get('default_name')
            self.render_add_to_staging(st_obj, data, default_name)
            return data
        elif mode == 'column_time':
            data = kwargs.get('data')
            return self.render_column_time_staging(st_obj, data, **kwargs)
        else:
            st_obj.error(f"未知的暂存模式: {mode}")
            return None


__all__ = ['DataStagingComponent']
