"""
时间序列分析组件共享状态与错误处理。
"""

import logging
import pandas as pd
import streamlit as st

from dashboard.core.ui.utils.error_handler import handle_ui_error

logger = logging.getLogger(__name__)


class TimeSeriesAnalysisComponent:
    """为探索组件提供命名空间状态、数据访问和统一错误展示。"""

    def __init__(self, analysis_type: str, title: str | None = None):
        self.analysis_type = analysis_type
        self.title = title or analysis_type
        self.logger = logging.getLogger(f"{__name__}.{analysis_type}")
        self.component_id = f"timeseries_{analysis_type}"

    def get_state(self, key: str, default=None):
        """获取分析状态"""
        state_key = f'tools.analysis.{self.analysis_type}.{key}'
        return st.session_state.get(state_key, default)

    def set_state(self, key: str, value):
        """设置分析状态"""
        state_key = f'tools.analysis.{self.analysis_type}.{key}'
        try:
            st.session_state[state_key] = value
            return True
        except Exception:  # noqa: BLE001 - Streamlit state adapter boundary
            return False

    def handle_error(self, st_obj, error: Exception, context: str = "") -> dict:
        """展示组件异常并记录最近一次错误。"""

        result = handle_ui_error(
            error,
            st_obj,
            component_id=self.component_id,
            context=context,
        )
        self.set_state("last_error", result["error_info"])
        self.set_state("error_count", self.get_state("error_count", 0) + 1)
        return result

    def get_module_data(self) -> tuple[pd.DataFrame | None, str, str]:
        """
        获取当前模块的数据

        Returns:
            Tuple[Optional[pd.DataFrame], str, str]: (数据, 数据源描述, 数据名称)
        """
        self.logger.debug(f"Getting module data for analysis type: {self.analysis_type}")

        # 从tab内上传的独立数据读取
        data_key = f"exploration.{self.analysis_type}.upload_data"
        file_name_key = f"exploration.{self.analysis_type}.file_name"

        selected_data = st.session_state.get(data_key)

        if selected_data is not None:
            file_name = st.session_state.get(file_name_key, '')

            self.logger.debug(f"Found data with shape: {selected_data.shape}, file: {file_name}")

            data_source = f"上传文件: {file_name}" if file_name else "上传文件"
            selected_df_name = file_name or "data"
            return selected_data, data_source, selected_df_name
        else:
            self.logger.debug(f"No data found for module: {self.analysis_type}")
            return None, "未选择数据", ""

__all__ = ['TimeSeriesAnalysisComponent']
