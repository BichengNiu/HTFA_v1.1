# -*- coding: utf-8 -*-
"""
DFM数据准备页面状态管理

集中管理所有状态键和状态操作，避免状态键分散在代码各处
"""

from dataclasses import dataclass
from typing import Any, Optional, List
import streamlit as st


@dataclass(frozen=True)
class PrepStateKeys:
    """
    数据准备页面状态键常量

    使用frozen=True确保键值不可变
    所有键都以'data_prep.'命名空间前缀
    """

    # ============================================================================
    # 文件相关
    # ============================================================================
    TRAINING_DATA_FILE = "training_data_file"
    UPLOADED_FILE_PATH = "uploaded_file_path"
    FILE_BYTES = "file_bytes"
    FILE_PROCESSED = "file_processed"

    # ============================================================================
    # 日期检测相关
    # ============================================================================
    DATE_DETECTION_NEEDED = "date_detection_needed"
    DETECTED_START_DATE = "detected_start_date"
    DETECTED_END_DATE = "detected_end_date"
    DETECTED_VARIABLE_COUNT = "detected_variable_count"
    DETECTED_FREQ_COUNTS = "detected_freq_counts"

    # ============================================================================
    # 参数配置
    # ============================================================================
    PARAM_TARGET_FREQ = "param_target_freq"
    PARAM_REMOVE_CONSECUTIVE_NANS = "param_remove_consecutive_nans"
    PARAM_CONSECUTIVE_NAN_THRESHOLD = "param_consecutive_nan_threshold"
    PARAM_TYPE_MAPPING_SHEET = "param_type_mapping_sheet"
    PARAM_DATA_START_DATE = "param_data_start_date"
    PARAM_DATA_END_DATE = "param_data_end_date"
    PARAM_ENABLE_FREQ_ALIGNMENT = "param_enable_freq_alignment"
    PARAM_ENABLE_BORROWING = "param_enable_borrowing"
    PARAM_ZERO_HANDLING = "param_zero_handling"
    PARAM_NEGATIVE_HANDLING = "param_negative_handling"
    PARAM_PUBLICATION_DATE_CALIBRATION = "param_publication_date_calibration"

    # ============================================================================
    # 处理结果
    # ============================================================================
    PREPARED_DATA_DF = "prepared_data_df"
    BASE_PREPARED_DATA_DF = "base_prepared_data_df"
    TRANSFORM_LOG_OBJ = "transform_log_obj"
    INDUSTRY_MAP_OBJ = "industry_map_obj"
    REMOVED_VARS_LOG_OBJ = "removed_vars_log_obj"
    PROCESSED_OUTPUTS = "processed_outputs"
    MAPPING_VALIDATION_RESULT = "mapping_validation_result"
    VALUE_REPLACEMENT_HISTORY = "value_replacement_history"  # 值替换历史
    STATIONARITY_CHECK_RESULTS = "stationarity_check_results"  # API层平稳性检验结果

    # ============================================================================
    # 变量转换配置
    # ============================================================================
    TRANSFORM_CONFIG_DF = "transform_config_df"
    VARIABLE_TRANSFORM_DETAILS = "variable_transform_details"
    VAR_NATURE_MAP_OBJ = "var_nature_map_obj"
    VAR_FREQUENCY_MAP_OBJ = "var_frequency_map_obj"

    # ============================================================================
    # 导出相关
    # ============================================================================
    EXPORT_BASE_NAME = "export_base_name"


class PrepStateManager:
    """
    数据准备状态管理器

    提供统一的状态读写接口，自动处理命名空间前缀
    """

    NAMESPACE = "data_prep"

    def __init__(self, namespace: Optional[str] = None):
        """
        初始化状态管理器

        Args:
            namespace: 命名空间，默认为'data_prep'
        """
        self._namespace = namespace or self.NAMESPACE

    def _full_key(self, key: str) -> str:
        """
        生成完整的状态键（带命名空间前缀）

        Args:
            key: 状态键（不含前缀）

        Returns:
            完整的状态键
        """
        if key.startswith(f"{self._namespace}."):
            return key
        return f"{self._namespace}.{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取状态值

        Args:
            key: 状态键（可以是PrepStateKeys常量或字符串）
            default: 默认值

        Returns:
            状态值或默认值
        """
        full_key = self._full_key(key)
        return st.session_state.get(full_key, default)

    def set(self, key: str, value: Any) -> None:
        """
        设置状态值

        Args:
            key: 状态键
            value: 状态值
        """
        full_key = self._full_key(key)
        st.session_state[full_key] = value

    def delete(self, key: str) -> bool:
        """
        删除状态键

        Args:
            key: 状态键

        Returns:
            是否成功删除
        """
        full_key = self._full_key(key)
        if full_key in st.session_state:
            del st.session_state[full_key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """
        检查状态键是否存在

        Args:
            key: 状态键

        Returns:
            是否存在
        """
        full_key = self._full_key(key)
        return full_key in st.session_state

    def clear_results(self) -> None:
        """清空所有处理结果状态"""
        result_keys = [
            PrepStateKeys.PROCESSED_OUTPUTS,
            PrepStateKeys.PREPARED_DATA_DF,
            PrepStateKeys.BASE_PREPARED_DATA_DF,
            PrepStateKeys.TRANSFORM_LOG_OBJ,
            PrepStateKeys.INDUSTRY_MAP_OBJ,
            PrepStateKeys.REMOVED_VARS_LOG_OBJ,
            PrepStateKeys.VARIABLE_TRANSFORM_DETAILS,
            PrepStateKeys.VALUE_REPLACEMENT_HISTORY,
        ]
        for key in result_keys:
            self.set(key, None)

    def clear_params(self) -> None:
        """清空所有参数配置状态（文件变更时调用）"""
        param_keys = [
            PrepStateKeys.PARAM_TARGET_FREQ,
            PrepStateKeys.PARAM_REMOVE_CONSECUTIVE_NANS,
            PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD,
            PrepStateKeys.PARAM_TYPE_MAPPING_SHEET,
            PrepStateKeys.PARAM_DATA_START_DATE,
            PrepStateKeys.PARAM_DATA_END_DATE,
            PrepStateKeys.PARAM_ENABLE_FREQ_ALIGNMENT,
            PrepStateKeys.PARAM_ENABLE_BORROWING,
            PrepStateKeys.PARAM_ZERO_HANDLING,
            PrepStateKeys.PARAM_PUBLICATION_DATE_CALIBRATION,
        ]
        for key in param_keys:
            self.set(key, None)

    def clear_transform_config(self) -> None:
        """清空变量转换配置"""
        transform_keys = [
            PrepStateKeys.TRANSFORM_CONFIG_DF,
            PrepStateKeys.VARIABLE_TRANSFORM_DETAILS,
            PrepStateKeys.VAR_NATURE_MAP_OBJ,
            PrepStateKeys.VAR_FREQUENCY_MAP_OBJ,
            PrepStateKeys.MAPPING_VALIDATION_RESULT,
        ]
        for key in transform_keys:
            self.set(key, None)

    def clear_all(self) -> None:
        """清空所有数据准备相关状态"""
        self.clear_results()
        self.clear_params()
        self.clear_transform_config()

        # 清空文件和检测相关
        file_keys = [
            PrepStateKeys.TRAINING_DATA_FILE,
            PrepStateKeys.UPLOADED_FILE_PATH,
            PrepStateKeys.FILE_BYTES,
            PrepStateKeys.FILE_PROCESSED,
            PrepStateKeys.DATE_DETECTION_NEEDED,
            PrepStateKeys.DETECTED_START_DATE,
            PrepStateKeys.DETECTED_END_DATE,
            PrepStateKeys.DETECTED_VARIABLE_COUNT,
            PrepStateKeys.DETECTED_FREQ_COUNTS,
        ]
        for key in file_keys:
            self.set(key, None)

    def get_cache_key(self, prefix: str, file_name: str, file_size: int) -> str:
        """
        生成缓存键

        Args:
            prefix: 缓存前缀（如'date_range', 'var_stats'）
            file_name: 文件名
            file_size: 文件大小

        Returns:
            缓存键字符串
        """
        return f"{prefix}_{file_name}_{file_size}"

    def clear_old_cache(self, prefix: str, current_cache_key: str) -> int:
        """
        清理旧缓存（保留当前缓存键）

        Args:
            prefix: 缓存前缀
            current_cache_key: 当前缓存键（不删除）

        Returns:
            删除的缓存数量
        """
        deleted_count = 0
        full_prefix = f"{self._namespace}.{prefix}_"
        full_current_key = self._full_key(current_cache_key)

        keys_to_delete = []
        for key in st.session_state.keys():
            if key.startswith(full_prefix) and key != full_current_key:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del st.session_state[key]
            deleted_count += 1

        return deleted_count

    def on_file_change(self, file_name: str, file_bytes: bytes) -> None:
        """
        处理文件变更事件

        清空旧参数和结果，重置检测状态

        Args:
            file_name: 新文件名
            file_bytes: 新文件字节内容
        """
        # 更新文件信息
        self.set(PrepStateKeys.UPLOADED_FILE_PATH, file_name)
        self.set(PrepStateKeys.FILE_BYTES, file_bytes)
        self.set(PrepStateKeys.FILE_PROCESSED, False)
        self.set(PrepStateKeys.DATE_DETECTION_NEEDED, True)

        # 清空参数和结果
        self.clear_params()
        self.clear_results()
        self.clear_transform_config()


# 全局实例（供模块内部使用）
prep_state = PrepStateManager()


__all__ = ['PrepStateKeys', 'PrepStateManager', 'prep_state']
