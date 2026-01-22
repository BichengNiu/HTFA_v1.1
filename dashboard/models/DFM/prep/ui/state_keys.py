"""
状态键定义模块

集中定义所有session_state键名，避免魔法字符串
"""


class DataPrepStateKeys:
    """数据准备模块状态键"""

    # 命名空间前缀
    PREFIX = 'data_prep'

    # 文件相关
    TRAINING_FILE = f'{PREFIX}.training_data_file'
    FILE_BYTES = f'{PREFIX}.file_bytes'
    UPLOADED_FILE_PATH = f'{PREFIX}.uploaded_file_path'
    FILE_PROCESSED = f'{PREFIX}.file_processed'
    DATE_DETECTION_NEEDED = f'{PREFIX}.date_detection_needed'

    # 检测结果
    DETECTED_START_DATE = f'{PREFIX}.detected_start_date'
    DETECTED_END_DATE = f'{PREFIX}.detected_end_date'
    DETECTED_VARIABLE_COUNT = f'{PREFIX}.detected_variable_count'
    DETECTED_FREQ_COUNTS = f'{PREFIX}.detected_freq_counts'

    # 参数配置
    PARAM_TARGET_FREQ = f'{PREFIX}.param_target_freq'
    PARAM_REMOVE_CONSECUTIVE_NANS = f'{PREFIX}.param_remove_consecutive_nans'
    PARAM_CONSECUTIVE_NAN_THRESHOLD = f'{PREFIX}.param_consecutive_nan_threshold'
    PARAM_TYPE_MAPPING_SHEET = f'{PREFIX}.param_type_mapping_sheet'
    PARAM_DATA_START_DATE = f'{PREFIX}.param_data_start_date'
    PARAM_DATA_END_DATE = f'{PREFIX}.param_data_end_date'
    PARAM_ENABLE_FREQ_ALIGNMENT = f'{PREFIX}.param_enable_freq_alignment'
    PARAM_ENABLE_BORROWING = f'{PREFIX}.param_enable_borrowing'
    PARAM_ZERO_HANDLING = f'{PREFIX}.param_zero_handling'
    PARAM_PUBLICATION_DATE_CALIBRATION = f'{PREFIX}.param_publication_date_calibration'

    # 处理结果
    PREPARED_DATA_DF = f'{PREFIX}.prepared_data_df'
    TRANSFORM_LOG_OBJ = f'{PREFIX}.transform_log_obj'
    INDUSTRY_MAP_OBJ = f'{PREFIX}.industry_map_obj'
    REMOVED_VARS_LOG_OBJ = f'{PREFIX}.removed_vars_log_obj'
    MAPPING_VALIDATION_RESULT = f'{PREFIX}.mapping_validation_result'
    PROCESSED_OUTPUTS = f'{PREFIX}.processed_outputs'

    # 映射数据
    VAR_TYPE_MAP_OBJ = f'{PREFIX}.var_type_map_obj'
    VAR_NATURE_MAP_OBJ = f'{PREFIX}.var_nature_map_obj'
    VAR_FREQUENCY_MAP_OBJ = f'{PREFIX}.var_frequency_map_obj'
    DFM_DEFAULT_SINGLE_STAGE_MAP = f'{PREFIX}.dfm_default_single_stage_map'
    DFM_FIRST_STAGE_PRED_MAP = f'{PREFIX}.dfm_first_stage_pred_map'
    DFM_FIRST_STAGE_TARGET_MAP = f'{PREFIX}.dfm_first_stage_target_map'
    DFM_SECOND_STAGE_TARGET_MAP = f'{PREFIX}.dfm_second_stage_target_map'
    VAR_PUBLICATION_LAG_MAP = f'{PREFIX}.var_publication_lag_map'

    # 变量转换
    TRANSFORM_CONFIG_DF = f'{PREFIX}.transform_config_df'
    VARIABLE_TRANSFORM_DETAILS = f'{PREFIX}.variable_transform_details'

    # 值替换
    VALUE_REPLACEMENT_HISTORY = f'{PREFIX}.value_replacement_history'  # List[Dict] 替换历史
    BASE_PREPARED_DATA_DF = f'{PREFIX}.base_prepared_data_df'  # 基准数据（用于撤销所有替换）

    # 导出
    EXPORT_BASE_NAME = f'{PREFIX}.export_base_name'

    @classmethod
    def cache_key(cls, prefix: str, file_name: str, file_size: int) -> str:
        """生成缓存键"""
        return f'{cls.PREFIX}.{prefix}_{file_name}_{file_size}'


def get_state(key: str, default=None):
    """获取状态值（使用完整键名）"""
    import streamlit as st
    return st.session_state.get(key, default)


def set_state(key: str, value):
    """设置状态值（使用完整键名）"""
    import streamlit as st
    st.session_state[key] = value


__all__ = ['DataPrepStateKeys', 'get_state', 'set_state']
