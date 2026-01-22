# -*- coding: utf-8 -*-
"""
DFM数据准备页面

重构版本：UI层仅负责渲染和状态管理，业务逻辑调用后端API
"""

import streamlit as st
import pandas as pd
import io
import time
from datetime import date
from typing import Optional, Tuple, List, Dict
import logging

from dashboard.models.DFM.prep.ui.state import PrepStateKeys, prep_state
from dashboard.models.DFM.prep.utils.html_helpers import render_tag_group

logger = logging.getLogger(__name__)


# ============================================================================
# 状态管理辅助函数（委托给PrepStateManager）
# ============================================================================

def _get_state(key: str, default=None):
    """获取状态值（委托给prep_state）"""
    return prep_state.get(key, default)


def _set_state(key: str, value):
    """设置状态值（委托给prep_state）"""
    prep_state.set(key, value)


# ============================================================================
# 核心功能函数（调用后端API）
# ============================================================================

def _detect_data_date_range(uploaded_file) -> Tuple[Optional[date], Optional[date], int, dict]:
    """
    从上传的文件中检测日期范围和变量数（调用后端API）
    """
    if uploaded_file is None or not hasattr(uploaded_file, 'getvalue'):
        return None, None, 0, {}

    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        return None, None, 0, {}

    from dashboard.models.DFM.prep.services.stats_service import StatsService
    return StatsService.detect_date_range(file_bytes)


def _compute_raw_variable_stats(uploaded_file) -> pd.DataFrame:
    """
    从原始Excel文件计算变量统计信息（调用后端API）
    """
    if uploaded_file is None:
        return pd.DataFrame()

    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        return pd.DataFrame()

    from dashboard.models.DFM.prep.services.stats_service import StatsService
    return StatsService.compute_raw_stats(file_bytes)


def _render_raw_variable_stats_table(st_obj, uploaded_file):
    """
    渲染变量状态表（文件上传后立即显示）

    Args:
        st_obj: Streamlit对象
        uploaded_file: 上传的文件对象
    """
    if uploaded_file is None:
        return

    # 使用缓存
    try:
        file_bytes = uploaded_file.getvalue()
        cache_key = f"var_stats_{uploaded_file.name}_{len(file_bytes)}"
    except:
        cache_key = "var_stats_none"

    cached_stats = _get_state(cache_key)
    if cached_stats is not None:
        stats_df = cached_stats
    else:
        with st_obj.spinner("正在分析变量状态..."):
            stats_df = _compute_raw_variable_stats(uploaded_file)
        _set_state(cache_key, stats_df)

    if stats_df.empty:
        return

    st_obj.dataframe(
        stats_df,
        column_config={
            '变量名': st.column_config.TextColumn('变量名', width='large'),
            '频率': st.column_config.TextColumn('频率', width='small'),
            '缺失值占比': st.column_config.TextColumn('缺失值占比', width='small'),
            '开始日期': st.column_config.TextColumn('开始日期', width='medium'),
            '结束日期': st.column_config.TextColumn('结束日期', width='medium')
        },
        hide_index=True,
        width='stretch'
    )


# ============================================================================
# UI渲染函数
# ============================================================================

def _render_file_upload_section(st_obj):
    """渲染文件上传区域"""

    st_obj.markdown("#### 数据上传")

    # 检查已有文件
    existing_file = _get_state(PrepStateKeys.TRAINING_DATA_FILE)
    existing_file_path = _get_state(PrepStateKeys.UPLOADED_FILE_PATH)

    # 文件上传组件
    uploaded_file_new = st_obj.file_uploader(
        "选择Excel数据文件",
        type=['xlsx', 'xls'],
        key="dfm_data_prep_file_uploader",
        help="请上传包含时间序列数据的Excel文件（支持.xlsx, .xls格式）"
    )

    # 处理新上传的文件
    uploaded_file = None
    if uploaded_file_new is not None:
        # 检查文件是否真的变更
        file_bytes = uploaded_file_new.getvalue()

        new_file_id = f"{uploaded_file_new.name}_{len(file_bytes)}"
        existing_file_id = f"{existing_file_path}_{len(_get_state(PrepStateKeys.FILE_BYTES, b''))}"

        # 只有文件真正变更时才更新状态
        if new_file_id != existing_file_id:
            _set_state(PrepStateKeys.TRAINING_DATA_FILE, uploaded_file_new)
            prep_state.on_file_change(uploaded_file_new.name, file_bytes)
            logger.info("新文件上传: %s，字节大小: %d，已重置参数", uploaded_file_new.name, len(file_bytes))

        uploaded_file = uploaded_file_new
    elif existing_file:
        uploaded_file = existing_file

    return uploaded_file


def _render_date_detection(st_obj, uploaded_file):
    """
    渲染日期检测逻辑

    Returns:
        (detected_start, detected_end, min_date, max_date) 元组
    """

    if uploaded_file is None:
        return None, None, date(1900, 1, 1), date(2050, 12, 31)

    # 使用文件名和大小作为缓存键
    try:
        file_bytes = uploaded_file.getvalue()
        cache_key = f"date_range_{uploaded_file.name}_{len(file_bytes)}"
    except:
        cache_key = "date_range_none"

    # 检查缓存是否有效
    cached_result = _get_state(cache_key)
    cache_valid = cached_result is not None and not _get_state(PrepStateKeys.DATE_DETECTION_NEEDED)

    if not cache_valid:
        # 需要重新检测
        logger.debug("执行日期检测: %s", uploaded_file.name)
        with st_obj.spinner("正在检测数据日期范围..."):
            detected_start, detected_end, variable_count, freq_counts = _detect_data_date_range(uploaded_file)

        # 缓存结果
        _set_state(cache_key, (detected_start, detected_end, variable_count, freq_counts))
        _set_state(PrepStateKeys.DETECTED_START_DATE, detected_start)
        _set_state(PrepStateKeys.DETECTED_END_DATE, detected_end)
        _set_state(PrepStateKeys.DETECTED_VARIABLE_COUNT, variable_count)
        _set_state(PrepStateKeys.DETECTED_FREQ_COUNTS, freq_counts)
        _set_state(PrepStateKeys.DATE_DETECTION_NEEDED, False)

        # 清理旧缓存
        try:
            all_keys = [k for k in st.session_state.keys() if k.startswith("data_prep.date_range_")]
            old_keys = [k for k in all_keys if k != f"data_prep.{cache_key}"]
            for old_key in old_keys:
                del st.session_state[old_key]
        except Exception as e:
            logger.warning("清理旧缓存时出错: %s", e)
    else:
        # 使用缓存的结果
        if cached_result and len(cached_result) == 4:
            detected_start, detected_end, variable_count, freq_counts = cached_result
        elif cached_result and len(cached_result) == 3:
            detected_start, detected_end, variable_count = cached_result
            freq_counts = {}
        elif cached_result:
            detected_start, detected_end = cached_result[:2]
            variable_count = 0
            freq_counts = {}
        else:
            detected_start, detected_end, variable_count, freq_counts = None, None, 0, {}
        _set_state(PrepStateKeys.DETECTED_START_DATE, detected_start)
        _set_state(PrepStateKeys.DETECTED_END_DATE, detected_end)
        _set_state(PrepStateKeys.DETECTED_VARIABLE_COUNT, variable_count)
        _set_state(PrepStateKeys.DETECTED_FREQ_COUNTS, freq_counts)
        logger.debug("使用缓存的日期范围: %s 到 %s", detected_start, detected_end)

    # 显示检测结果
    if detected_start and detected_end:
        variable_count = _get_state(PrepStateKeys.DETECTED_VARIABLE_COUNT, 0)
        freq_counts = _get_state(PrepStateKeys.DETECTED_FREQ_COUNTS, {})

        # 构建频率统计字符串
        freq_parts = []
        for freq_name in ['日度', '周度', '旬度', '月度', '季度', '年度', '其他']:
            if freq_name in freq_counts and freq_counts[freq_name] > 0:
                freq_parts.append(f"{freq_name}({freq_counts[freq_name]}个)")
        freq_str = "，".join(freq_parts) if freq_parts else ""

        # 构建显示信息
        if freq_str:
            display_msg = f"已检测数据文件的真实日期范围: {detected_start} 到 {detected_end}，共 {variable_count} 个变量：{freq_str}"
        else:
            display_msg = f"已检测数据文件的真实日期范围: {detected_start} 到 {detected_end}，共 {variable_count} 个变量"

        st_obj.success(display_msg)
        # 设置日期选择器范围（宽松一年）
        min_date = detected_start - pd.Timedelta(days=365)
        max_date = detected_end + pd.Timedelta(days=365)
    else:
        st_obj.warning("无法自动检测文件日期范围，使用默认值。请手动调整日期设置。")
        min_date = date(1990, 1, 1)
        max_date = date(2050, 12, 31)

    return detected_start, detected_end, min_date, max_date


def _render_parameter_config(st_obj, detected_start, detected_end, min_date, max_date):
    """
    渲染参数配置区域（9个参数，5行2列布局）

    Returns:
        bool - 参数是否有效
    """

    # 设置默认值（使用检测到的真实日期范围）
    default_start_date = detected_start if detected_start else date(2020, 1, 1)
    default_end_date = detected_end if detected_end else date(2025, 4, 30)

    param_defaults = {
        PrepStateKeys.PARAM_TARGET_FREQ: 'W-FRI',
        PrepStateKeys.PARAM_REMOVE_CONSECUTIVE_NANS: "是",
        PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD: 10,
        PrepStateKeys.PARAM_TYPE_MAPPING_SHEET: '指标字典',
        PrepStateKeys.PARAM_DATA_START_DATE: default_start_date,
        PrepStateKeys.PARAM_DATA_END_DATE: default_end_date,
        PrepStateKeys.PARAM_ENABLE_FREQ_ALIGNMENT: '否',
        PrepStateKeys.PARAM_ENABLE_BORROWING: '否',
        PrepStateKeys.PARAM_ZERO_HANDLING: 'missing',
        PrepStateKeys.PARAM_NEGATIVE_HANDLING: 'none',
        PrepStateKeys.PARAM_PUBLICATION_DATE_CALIBRATION: '否'
    }

    # 初始化默认值（仅当值为None时设置，保留用户手动修改的值）
    for key, default_value in param_defaults.items():
        if _get_state(key) is None:
            _set_state(key, default_value)

    # 第1行：日期范围
    row1_col1, row1_col2 = st_obj.columns(2)
    with row1_col1:
        start_date_value = st_obj.date_input(
            "数据开始日期",
            value=_get_state(PrepStateKeys.PARAM_DATA_START_DATE),
            min_value=min_date,
            max_value=max_date,
            key="ss_dfm_data_start",
            help=f"设置系统处理数据的最早日期边界。数据实际范围：{detected_start} 到 {detected_end}" if detected_start else "设置系统处理数据的最早日期边界。"
        )
        _set_state(PrepStateKeys.PARAM_DATA_START_DATE, start_date_value)

    with row1_col2:
        end_date_value = st_obj.date_input(
            "数据结束日期",
            value=_get_state(PrepStateKeys.PARAM_DATA_END_DATE),
            min_value=min_date,
            max_value=max_date,
            key="ss_dfm_data_end",
            help=f"设置系统处理数据的最晚日期边界。数据实际范围：{detected_start} 到 {detected_end}" if detected_end else "设置系统处理数据的最晚日期边界。"
        )
        _set_state(PrepStateKeys.PARAM_DATA_END_DATE, end_date_value)

    # 第2行：发布日期校准和频率对齐
    row2_col1, row2_col2 = st_obj.columns(2)
    with row2_col1:
        publication_options = ["否", "是"]
        current_publication = _get_state(PrepStateKeys.PARAM_PUBLICATION_DATE_CALIBRATION, '否')
        publication_index = 1 if current_publication == "是" else 0
        publication_calibration = st_obj.selectbox(
            "发布日期校准",
            options=publication_options,
            index=publication_index,
            key="ss_dfm_publication_calibration",
            help="选择'是'将按指标实际发布日期对齐数据（基于指标字典中的'发布日期'列）"
        )
        _set_state(PrepStateKeys.PARAM_PUBLICATION_DATE_CALIBRATION, publication_calibration)

    with row2_col2:
        freq_alignment_options = ["是", "否"]
        current_freq_alignment = _get_state(PrepStateKeys.PARAM_ENABLE_FREQ_ALIGNMENT, '否')
        freq_alignment_index = 0 if current_freq_alignment == "是" else 1
        enable_freq_alignment = st_obj.selectbox(
            "频率对齐",
            options=freq_alignment_options,
            index=freq_alignment_index,
            key="ss_dfm_enable_freq_alignment",
            help="选择'是'将所有数据对齐到目标频率；选择'否'则保留原始发布日期，按发布日合并"
        )
        _set_state(PrepStateKeys.PARAM_ENABLE_FREQ_ALIGNMENT, enable_freq_alignment)

    # 第3行：目标频率和启用数据借调
    row3_col1, row3_col2 = st_obj.columns(2)
    with row3_col1:
        # 目标频率选择（仅在频率对齐=是时启用）
        freq_disabled = (enable_freq_alignment == "否")
        freq_options = {
            'D': '日度 (Daily)',
            'W-FRI': '周度-周五 (Weekly-Friday)',
            'MS': '月度-周五 (Monthly-Friday)',
            'QS': '季度-周五 (Quarterly-Friday)',
            'AS': '年度-周五 (Annual-Friday)'
        }
        current_freq = _get_state(PrepStateKeys.PARAM_TARGET_FREQ, 'W-FRI')
        target_freq = st_obj.selectbox(
            "目标频率",
            options=list(freq_options.keys()),
            format_func=lambda x: freq_options[x],
            index=list(freq_options.keys()).index(current_freq) if current_freq in freq_options else 0,
            key="ss_dfm_target_freq",
            disabled=freq_disabled,
            help="选择模型的目标频率（仅在频率对齐=是时有效）。日度数据转换为周度时默认取均值聚合，其他频率转换时取最后值。"
        )
        _set_state(PrepStateKeys.PARAM_TARGET_FREQ, target_freq)

    with row3_col2:
        # 启用数据借调（改为selectbox，仅在频率对齐=是时启用）
        borrowing_disabled = (enable_freq_alignment == "否")
        borrowing_options = ["是", "否"]
        current_borrowing = _get_state(PrepStateKeys.PARAM_ENABLE_BORROWING, '否')
        borrowing_index = 0 if current_borrowing == "是" else 1
        enable_borrowing = st_obj.selectbox(
            "启用数据借调",
            options=borrowing_options,
            index=borrowing_index,
            key="ss_dfm_enable_borrowing",
            disabled=borrowing_disabled,
            help="开启时，当某个时间窗口无数据但下个窗口有多个数据时，会将数据借调到前一个窗口（仅在频率对齐=是时有效）"
        )
        _set_state(PrepStateKeys.PARAM_ENABLE_BORROWING, enable_borrowing)

    # 第4行：移除选项和缺失值阈值（第三执行：步骤5）
    row4_col1, row4_col2 = st_obj.columns(2)
    with row4_col1:
        remove_nans = st_obj.selectbox(
            "移除存在过多连续缺失值的变量",
            options=["是", "否"],
            index=0 if _get_state(PrepStateKeys.PARAM_REMOVE_CONSECUTIVE_NANS) == "是" else 1,
            key="ss_dfm_remove_nans",
            help="移除列中连续缺失值数量超过阈值的变量"
        )
        _set_state(PrepStateKeys.PARAM_REMOVE_CONSECUTIVE_NANS, remove_nans)

    with row4_col2:
        # 连续缺失值阈值（仅在移除=是时启用）
        threshold_disabled = (remove_nans == "否")
        nan_threshold = st_obj.number_input(
            "连续缺失值阈值",
            min_value=0,
            value=_get_state(PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD) or 10,
            step=1,
            key="ss_dfm_nan_thresh",
            disabled=threshold_disabled
        )
        if remove_nans == "是":
            _set_state(PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD, nan_threshold)
        else:
            _set_state(PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD, None)

    # 第5行：零值处理和负值处理
    row5_col1, row5_col2 = st_obj.columns(2)
    with row5_col1:
        zero_options = {
            'none': '不处理',
            'missing': '缺失值',
            'adjust': '调正（+1）'
        }
        current_zero = _get_state(PrepStateKeys.PARAM_ZERO_HANDLING, 'missing')
        zero_keys = list(zero_options.keys())
        zero_index = zero_keys.index(current_zero) if current_zero in zero_keys else 1
        zero_handling = st_obj.selectbox(
            "零值处理",
            options=zero_keys,
            format_func=lambda x: zero_options[x],
            index=zero_index,
            key="ss_dfm_zero_handling",
            help="设置全局零值处理方式，对所有变量生效"
        )
        _set_state(PrepStateKeys.PARAM_ZERO_HANDLING, zero_handling)

    with row5_col2:
        negative_options = {
            'none': '不处理',
            'missing': '缺失值',
            'adjust': '调正（+1）'
        }
        current_negative = _get_state(PrepStateKeys.PARAM_NEGATIVE_HANDLING, 'none')
        negative_keys = list(negative_options.keys())
        negative_index = negative_keys.index(current_negative) if current_negative in negative_keys else 0
        negative_handling = st_obj.selectbox(
            "负值处理",
            options=negative_keys,
            format_func=lambda x: negative_options[x],
            index=negative_index,
            key="ss_dfm_negative_handling",
            help="设置全局负值处理方式，对所有变量生效"
        )
        _set_state(PrepStateKeys.PARAM_NEGATIVE_HANDLING, negative_handling)

    return True


def _render_processing_section(st_obj, uploaded_file):
    """
    渲染数据处理按钮区域

    Returns:
        bool - 是否点击了处理按钮
    """

    # 开始预处理按钮
    run_button_clicked = st_obj.button(
        "开始处理",
        key="ss_dfm_run_preprocessing",
        type="primary"
    )

    return run_button_clicked


def _clear_previous_results():
    """清空旧结果状态"""
    prep_state.clear_results()


def _prepare_processing_params(uploaded_file, st_obj) -> Optional[dict]:
    """
    准备数据处理参数

    Args:
        uploaded_file: 上传的文件对象
        st_obj: Streamlit对象（用于显示警告）

    Returns:
        dict: 处理参数字典，包含所有API调用需要的参数
    """
    uploaded_file_bytes = uploaded_file.getvalue()
    excel_file_like_object = io.BytesIO(uploaded_file_bytes)

    # 日期参数
    start_date = _get_state(PrepStateKeys.PARAM_DATA_START_DATE)
    end_date = _get_state(PrepStateKeys.PARAM_DATA_END_DATE)
    start_date_str = start_date.strftime('%Y-%m-%d') if start_date else None
    end_date_str = end_date.strftime('%Y-%m-%d') if end_date else None

    # NaN阈值参数
    nan_threshold_int = None
    if _get_state(PrepStateKeys.PARAM_REMOVE_CONSECUTIVE_NANS) == "是":
        nan_threshold = _get_state(PrepStateKeys.PARAM_CONSECUTIVE_NAN_THRESHOLD)
        if not pd.isna(nan_threshold):
            try:
                nan_threshold_int = int(nan_threshold)
            except ValueError:
                st_obj.warning(f"连续缺失值阈值 '{nan_threshold}' 不是有效整数，将忽略此阈值")

    # 频率对齐和数据借调参数
    enable_freq_alignment = _get_state(PrepStateKeys.PARAM_ENABLE_FREQ_ALIGNMENT, '否') == '是'
    enable_borrowing = _get_state(PrepStateKeys.PARAM_ENABLE_BORROWING, '否') == '是'
    if not enable_freq_alignment:
        enable_borrowing = False

    # 其他参数
    zero_handling = _get_state(PrepStateKeys.PARAM_ZERO_HANDLING, 'missing')
    negative_handling = _get_state(PrepStateKeys.PARAM_NEGATIVE_HANDLING, 'none')
    enable_publication_calibration = _get_state(PrepStateKeys.PARAM_PUBLICATION_DATE_CALIBRATION, '否') == '是'

    return {
        'excel_file': excel_file_like_object,
        'target_freq': _get_state(PrepStateKeys.PARAM_TARGET_FREQ),
        'consecutive_nan_threshold': nan_threshold_int,
        'data_start_date': start_date_str,
        'data_end_date': end_date_str,
        'reference_sheet_name': _get_state(PrepStateKeys.PARAM_TYPE_MAPPING_SHEET),
        'enable_freq_alignment': enable_freq_alignment,
        'enable_borrowing': enable_borrowing,
        'zero_handling': zero_handling,
        'negative_handling': negative_handling,
        'enable_publication_calibration': enable_publication_calibration,
    }


def _call_prepare_api(params: dict) -> dict:
    """
    调用数据准备API

    Args:
        params: 处理参数字典

    Returns:
        dict: API返回结果
    """
    from dashboard.models.DFM.prep.api import prepare_dfm_data_simple

    logger.info("调用prepare_dfm_data_simple参数:")
    logger.info("  - target_freq: %s", params['target_freq'])
    logger.info("  - consecutive_nan_threshold: %s", params['consecutive_nan_threshold'])
    logger.info("  - data_start_date: %s", params['data_start_date'])
    logger.info("  - data_end_date: %s", params['data_end_date'])
    logger.info("  - enable_freq_alignment: %s", params['enable_freq_alignment'])
    logger.info("  - enable_borrowing: %s", params['enable_borrowing'])
    logger.info("  - zero_handling: %s", params['zero_handling'])
    logger.info("  - negative_handling: %s", params['negative_handling'])
    logger.info("  - enable_publication_calibration: %s", params['enable_publication_calibration'])

    return prepare_dfm_data_simple(
        uploaded_file=params['excel_file'],
        target_variable_name=None,
        target_freq=params['target_freq'],
        consecutive_nan_threshold=params['consecutive_nan_threshold'],
        data_start_date=params['data_start_date'],
        data_end_date=params['data_end_date'],
        reference_sheet_name=params['reference_sheet_name'],
        enable_borrowing=params['enable_borrowing'],
        enable_freq_alignment=params['enable_freq_alignment'],
        zero_handling=params['zero_handling'],
        negative_handling=params['negative_handling'],
        enable_publication_calibration=params['enable_publication_calibration']
    )


def _process_success_result(st_obj, result: dict, excel_file_like_object) -> bool:
    """
    处理成功的API返回结果

    Args:
        st_obj: Streamlit对象
        result: API返回结果
        excel_file_like_object: Excel文件对象（用于重新加载映射）

    Returns:
        bool: 处理是否成功
    """
    prepared_data = result['data']
    industry_map = result['metadata']['variable_mapping']
    transform_log = result['metadata']['transform_log']
    removed_variables_log = result['metadata']['removal_log']
    mapping_validation = result['metadata'].get('mapping_validation', {})
    stationarity_check_results = result['metadata'].get('stationarity_check_results', {})

    logger.info("准备数据形状: %s", prepared_data.shape if prepared_data is not None else 'None')
    logger.info("移除日志长度: %d", len(removed_variables_log) if removed_variables_log else 0)

    if prepared_data is None:
        return False

    # 保存数据对象到状态管理
    _set_state(PrepStateKeys.PREPARED_DATA_DF, prepared_data)
    _set_state(PrepStateKeys.BASE_PREPARED_DATA_DF, prepared_data.copy())
    _set_state(PrepStateKeys.TRANSFORM_LOG_OBJ, transform_log)
    _set_state(PrepStateKeys.INDUSTRY_MAP_OBJ, industry_map)
    _set_state(PrepStateKeys.REMOVED_VARS_LOG_OBJ, removed_variables_log)
    _set_state(PrepStateKeys.MAPPING_VALIDATION_RESULT, mapping_validation)
    _set_state(PrepStateKeys.STATIONARITY_CHECK_RESULTS, stationarity_check_results)

    # 生成导出文件
    processed_outputs = {'excel_file': None}

    if industry_map:
        try:
            from dashboard.models.DFM.prep.api import load_mappings_once
            from dashboard.models.DFM.prep.services.export_service import ExportService

            excel_file_like_object.seek(0)
            mapping_result = load_mappings_once(
                excel_path=excel_file_like_object,
                reference_sheet_name=_get_state(PrepStateKeys.PARAM_TYPE_MAPPING_SHEET),
                reference_column_name='指标名称'
            )

            if mapping_result['status'] != 'success':
                raise ValueError(mapping_result['message'])

            mappings = mapping_result['mappings']

            # 保存性质映射和频率映射到状态
            _set_state(PrepStateKeys.VAR_NATURE_MAP_OBJ, mappings.get('var_nature_map', {}))
            _set_state(PrepStateKeys.VAR_FREQUENCY_MAP_OBJ, mappings.get('var_frequency_map', {}))

            # 平稳性过滤：清除不平稳变量的"一次估计"和"一阶段预测"标记
            updated_mappings = ExportService.clear_non_stationary_markers(
                mappings=mappings,
                stationarity_check_results=stationarity_check_results
            )

            # 生成Excel文件
            processed_outputs['excel_file'] = ExportService.generate_excel(
                prepared_data=prepared_data,
                industry_map=industry_map,
                mappings=updated_mappings,
                removed_vars_log=removed_variables_log,
                transform_details=_get_state(PrepStateKeys.VARIABLE_TRANSFORM_DETAILS),
                replacement_history=_get_state(PrepStateKeys.VALUE_REPLACEMENT_HISTORY),
                stationarity_check_results=stationarity_check_results
            )

            logger.info("导出Excel文件: 数据形状 %s, 映射 %d 条记录",
                       prepared_data.shape, len(industry_map))

        except Exception as e:
            st_obj.warning(f"生成Excel文件时出错: {e}")
            processed_outputs['excel_file'] = None

    _set_state(PrepStateKeys.PROCESSED_OUTPUTS, processed_outputs)
    return True


def _execute_data_preparation(st_obj, uploaded_file):
    """
    执行数据准备（协调入口）

    职责：协调清理、参数准备、API调用和结果处理的流程
    """
    _clear_previous_results()

    if uploaded_file is None:
        st_obj.error("错误：请先上传训练数据集")
        return

    progress_bar = st_obj.progress(0)
    status_text = st_obj.empty()

    try:
        # Step 1: 准备参数
        status_text.text("正在准备数据...")
        progress_bar.progress(10)
        params = _prepare_processing_params(uploaded_file, st_obj)

        # Step 2: 调用API
        status_text.text("正在执行数据预处理...")
        progress_bar.progress(30)
        result = _call_prepare_api(params)

        # Step 3: 处理结果
        status_text.text("数据预处理完成，正在生成结果...")
        progress_bar.progress(70)

        if result['status'] == 'success':
            status_text.text("正在处理结果数据...")
            progress_bar.progress(80)

            if _process_success_result(st_obj, result, params['excel_file']):
                progress_bar.progress(100)
                status_text.text("处理完成！")
            else:
                progress_bar.progress(100)
                status_text.text("处理失败")
                st_obj.error("数据预处理失败或未返回数据。请检查控制台日志获取更多信息。")
                _set_state(PrepStateKeys.PROCESSED_OUTPUTS, None)
        else:
            progress_bar.progress(100)
            status_text.text("处理失败")
            st_obj.error(f"数据预处理失败: {result['message']}")
            _set_state(PrepStateKeys.PROCESSED_OUTPUTS, None)

    except Exception as e:
        st_obj.error(f"运行数据预处理时发生错误: {e}")
        import traceback
        st_obj.text_area("详细错误信息:", traceback.format_exc(), height=200)
        _set_state(PrepStateKeys.PROCESSED_OUTPUTS, None)

    finally:
        time.sleep(0.5)
        progress_bar.empty()
        status_text.empty()


def _render_data_preview(st_obj):
    """渲染数据预览（显示最终处理后的数据）"""

    prepared_data = _get_state(PrepStateKeys.PREPARED_DATA_DF)
    if prepared_data is None:
        return

    # === 值替换功能 ===
    from dashboard.models.DFM.prep.ui.components.value_replacement import render_value_replacement_section
    updated_data = render_value_replacement_section(prepared_data)
    if updated_data is not None:
        _set_state(PrepStateKeys.PREPARED_DATA_DF, updated_data)
        # 重新生成导出文件以包含替换后的数据
        _regenerate_export_file(st_obj, updated_data)
        st.rerun()
    # 重新获取可能已更新的数据
    prepared_data = _get_state(PrepStateKeys.PREPARED_DATA_DF)
    # === 值替换功能结束 ===

    # 按时间由近及远排列（降序）
    display_data = prepared_data.copy()
    display_data = display_data.sort_index(ascending=False)

    # 格式化日期索引为 年-月-日 格式
    if isinstance(display_data.index, pd.DatetimeIndex):
        display_data.index = display_data.index.strftime('%Y-%m-%d')

    st_obj.dataframe(display_data, width='stretch')
    st_obj.caption(f"数据形状: {prepared_data.shape[0]} 行 x {prepared_data.shape[1]} 列")


def _render_mapping_warnings(st_obj):
    """渲染行业映射警告信息"""

    mapping_validation = _get_state(PrepStateKeys.MAPPING_VALIDATION_RESULT)

    if not mapping_validation:
        return

    # conflicts = mapping_validation.get('conflicts', [])  # 冲突检查已禁用
    undefined = mapping_validation.get('undefined_in_reference', [])

    # 只显示未定义变量的警告
    if not undefined:
        return

    # 显示警告信息
    with st_obj.expander("行业映射警告", expanded=True):
        if undefined:
            st_obj.warning(f"发现 {len(undefined)} 个变量在指标字典中未定义行业（已标记为Unknown）")
            st_obj.markdown("**建议**: 在Excel模板的\"指标字典\"sheet中为这些变量补充行业信息")

            # 最多显示20个
            undefined_to_show = undefined[:20]
            st_obj.write(undefined_to_show)

            if len(undefined) > 20:
                st_obj.caption(f"... 还有 {len(undefined) - 20} 个未定义变量")


def _render_details_row(st_obj):
    """
    渲染移除变量详情和数据借调详情（分两行显示，各占整行宽度）

    移除变量详情始终显示（即使0个）
    数据借调详情仅在启用借调且有借调发生时显示
    """
    # 检查是否已经处理过数据（有处理结果才显示）
    prepared_data = _get_state(PrepStateKeys.PREPARED_DATA_DF)
    if prepared_data is None:
        return

    # 第一行：移除变量详情（始终显示）
    _render_removed_variables_summary(st_obj)

    # 第二行：数据借调详情（有借调时显示）
    _render_borrowing_details_expander(st_obj)


def _render_removed_variables_summary(st_obj):
    """
    渲染移除变量摘要和详情

    格式：按原因分组，变量名横向流式排列
    始终显示，即使没有变量被移除
    """
    removed_vars_log = _get_state(PrepStateKeys.REMOVED_VARS_LOG_OBJ)
    removed_count = len(removed_vars_log) if removed_vars_log else 0

    with st_obj.expander(f"移除变量详情 ({removed_count}个)", expanded=False):
        if removed_count > 0:
            # 按原因分组显示详情
            reason_groups = {}
            for entry in removed_vars_log:
                reason = entry.get('Reason', '未知原因')
                if reason not in reason_groups:
                    reason_groups[reason] = []
                reason_groups[reason].append(entry.get('Variable', '未知变量'))

            # 每个原因分组，变量名横向流式排列
            for reason, var_names in reason_groups.items():
                st.markdown(f"**[{reason}]** ({len(var_names)}个变量)")
                st.markdown(render_tag_group(var_names), unsafe_allow_html=True)
        else:
            st.success("所有变量都通过了筛选，没有变量被移除")


def _render_borrowing_details_expander(st_obj):
    """
    渲染数据借调详情expander

    格式：按变量分组，借调记录横向流式排列
    仅在启用借调且有借调发生时显示
    """
    enable_borrowing = _get_state(PrepStateKeys.PARAM_ENABLE_BORROWING, True)
    if not enable_borrowing:
        return

    transform_log = _get_state(PrepStateKeys.TRANSFORM_LOG_OBJ)
    if transform_log is None:
        return

    borrowing_log = transform_log.get('borrowing_log', {})
    if not borrowing_log:
        return

    total_vars = len(borrowing_log)
    total_count = sum(len(logs) for logs in borrowing_log.values())

    with st_obj.expander(f"数据借调详情 ({total_vars}个变量，{total_count}次借调)", expanded=False):
        for var_name, logs in borrowing_log.items():
            st.markdown(f"**[{var_name}]** ({len(logs)}次借调)")
            items = []
            for log in logs:
                borrowed_from = log.get('borrowed_from')
                borrowed_to = log.get('borrowed_to')
                from_str = borrowed_from.strftime('%Y-%m-%d') if hasattr(borrowed_from, 'strftime') else str(borrowed_from)
                to_str = borrowed_to.strftime('%Y-%m-%d') if hasattr(borrowed_to, 'strftime') else str(borrowed_to)
                items.append(f'{from_str} -> {to_str}')
            st.markdown(render_tag_group(items), unsafe_allow_html=True)


def _render_transform_details_expander(st_obj, transform_details: dict):
    """
    渲染变量转换详情expander（在应用转换按钮下方显示）

    格式与移除变量详情一致：按操作分组，变量名横向流式排列

    Args:
        st_obj: Streamlit对象
        transform_details: 转换详情字典
    """
    if not transform_details:
        return

    transform_count = len(transform_details)

    with st_obj.expander(f"变量转换详情 ({transform_count}个变量)", expanded=False):
        if transform_count > 0:
            # 按操作分组显示详情
            ops_groups = {}
            for var_name, details in transform_details.items():
                ops_str = ' -> '.join(details.get('operations', []))
                if not ops_str:
                    ops_str = '无操作'
                if ops_str not in ops_groups:
                    ops_groups[ops_str] = []
                ops_groups[ops_str].append(var_name)

            # 每个操作分组，变量名横向流式排列
            for ops_str, var_names in ops_groups.items():
                st.markdown(f"**[{ops_str}]** ({len(var_names)}个变量)")
                st.markdown(render_tag_group(var_names), unsafe_allow_html=True)
        else:
            st.info("没有变量被转换")


def _render_stationarity_test_expander(
    st_obj,
    all_variables_sorted: List[Dict],
    non_stationary_count: int
):
    """
    显示所有变量的平稳性检验结果（非平稳变量排在前面）

    Args:
        st_obj: Streamlit对象
        all_variables_sorted: 所有变量的检验结果（已排序），每项格式：
            {
                'variable': str,
                'frequency': str,
                'processing': str,
                'p_value': str,
                'stationarity': str
            }
        non_stationary_count: 非平稳变量数量
    """
    if not all_variables_sorted:
        return

    total_count = len(all_variables_sorted)
    stationary_count = total_count - non_stationary_count

    # 标题：显示统计信息
    title = f"平稳性检验结果 (共{total_count}个变量: {stationary_count}个平稳, {non_stationary_count}个非平稳/数据不足)"

    with st_obj.expander(title, expanded=False):
        if non_stationary_count == 0:
            st.success("所有变量均通过平稳性检验")

        # 构建DataFrame用于展示（显示所有变量）
        display_df = pd.DataFrame(all_variables_sorted)
        display_df = display_df.rename(columns={
            'variable': '变量名',
            'frequency': '频率',
            'processing': '处理',
            'p_value': 'P值',
            'stationarity': '平稳性'
        })

        # 使用st.dataframe显示表格
        st.dataframe(
            display_df,
            column_config={
                '变量名': st.column_config.TextColumn('变量名', width='large'),
                '频率': st.column_config.TextColumn('频率', width='small'),
                '处理': st.column_config.TextColumn('处理', width='medium'),
                'P值': st.column_config.TextColumn('P值', width='small'),
                '平稳性': st.column_config.TextColumn('平稳性', width='small')
            },
            hide_index=True,
            width='stretch'
        )

        # 添加说明信息
        if non_stationary_count > 0:
            st.caption(f"注：非平稳和数据不足的变量已排在前{non_stationary_count}行")


# ============================================================================
# 变量处理功能区
# ============================================================================

def _render_variable_transform_section(st_obj):
    """
    渲染变量处理功能区（表格式布局）

    使用 st.data_editor 显示可编辑的变量转换配置表格
    """
    from dashboard.models.DFM.prep.modules.variable_transformer import (
        get_default_transform_config,
        FREQUENCY_PERIOD_MAP
    )

    st_obj.markdown("---")
    st_obj.markdown("#### 变量处理")

    # 获取目标频率
    target_freq = _get_state(PrepStateKeys.PARAM_TARGET_FREQ, 'W-FRI')
    yoy_period = FREQUENCY_PERIOD_MAP.get(target_freq, 52)
    st_obj.caption(f"根据变量性质自动推荐转换操作。当前目标频率: {target_freq}，同比差分周期: {yoy_period}期")

    # 获取处理后数据
    prepared_data = _get_state(PrepStateKeys.PREPARED_DATA_DF)
    var_nature_map = _get_state(PrepStateKeys.VAR_NATURE_MAP_OBJ) or {}

    if prepared_data is None or prepared_data.empty:
        st_obj.info("请先完成数据处理")
        return

    # 操作选项列表
    OPERATIONS = ['不处理', '对数', '环比差分', '同比差分']
    # 注：零值处理已在基础设置中全局配置，变量处理区只配置转换操作

    # 获取或初始化配置DataFrame
    config_df = _get_state(PrepStateKeys.TRANSFORM_CONFIG_DF)

    if config_df is None:
        # 生成默认配置
        config_list = get_default_transform_config(
            list(prepared_data.columns),
            var_nature_map,
            freq=target_freq
        )
        config_df = pd.DataFrame(config_list)

    # 在传给 data_editor 之前应用联动逻辑
    # 规则1: 第一次处理选"不处理"时，第二次、第三次处理强制设为"不处理"
    # 规则2: 第二次处理选"不处理"时，第三次处理强制设为"不处理"
    mask_first = config_df['第一次处理'] == '不处理'
    mask_second = config_df['第二次处理'] == '不处理'
    if mask_first.any() or mask_second.any():
        config_df = config_df.copy()
        config_df.loc[mask_first, '第二次处理'] = '不处理'
        config_df.loc[mask_first, '第三次处理'] = '不处理'
        config_df.loc[mask_second, '第三次处理'] = '不处理'

    _set_state(PrepStateKeys.TRANSFORM_CONFIG_DF, config_df)

    # 使用 data_editor 显示可编辑表格
    edited_df = st_obj.data_editor(
        config_df,
        column_config={
            '变量名': st.column_config.TextColumn(
                '变量名',
                disabled=True,
                width='large'
            ),
            '性质': st.column_config.TextColumn(
                '性质',
                disabled=True,
                width='small'
            ),
            '第一次处理': st.column_config.SelectboxColumn(
                '第一次处理',
                options=OPERATIONS,
                width='medium',
                required=True
            ),
            '第二次处理': st.column_config.SelectboxColumn(
                '第二次处理',
                options=OPERATIONS,
                width='medium',
                required=True
            ),
            '第三次处理': st.column_config.SelectboxColumn(
                '第三次处理',
                options=OPERATIONS,
                width='medium',
                required=True
            )
        },
        hide_index=True,
        width='stretch',
        key="variable_transform_editor",
        num_rows="fixed"
    )

    # 联动逻辑：任何一次选"不处理"时，后续步骤自动改为"不处理"
    needs_sync = False
    mask_first = edited_df['第一次处理'] == '不处理'
    mask_second = edited_df['第二次处理'] == '不处理'

    # 检查第一次处理的不一致
    if mask_first.any():
        inconsistent_first = mask_first & (
            (edited_df['第二次处理'] != '不处理') |
            (edited_df['第三次处理'] != '不处理')
        )
        if inconsistent_first.any():
            edited_df = edited_df.copy()
            edited_df.loc[mask_first, '第二次处理'] = '不处理'
            edited_df.loc[mask_first, '第三次处理'] = '不处理'
            needs_sync = True

    # 检查第二次处理的不一致
    if mask_second.any():
        inconsistent_second = mask_second & (edited_df['第三次处理'] != '不处理')
        if inconsistent_second.any():
            if not needs_sync:
                edited_df = edited_df.copy()
            edited_df.loc[mask_second, '第三次处理'] = '不处理'
            needs_sync = True

    # 保存编辑后的配置
    _set_state(PrepStateKeys.TRANSFORM_CONFIG_DF, edited_df)

    # 如果有不一致需要同步，触发重新渲染
    if needs_sync:
        st.rerun()

    # 统计需要转换的变量数量
    vars_with_transform = len(edited_df[edited_df['第一次处理'] != '不处理'])

    if vars_with_transform > 0:
        st_obj.info(f"将对 {vars_with_transform} 个变量应用转换")
    else:
        st_obj.info("当前没有选择任何转换操作")

    # 应用按钮
    col1, col2 = st_obj.columns([1, 4])
    with col1:
        apply_clicked = st_obj.button(
            "应用转换",
            key="apply_variable_transform",
            type="primary",
            disabled=vars_with_transform == 0
        )

    if apply_clicked:
        _apply_variable_transforms(st_obj, edited_df)


def _apply_variable_transforms(st_obj, config_df):
    """
    应用变量转换和平稳性检验（调用后端服务，UI层只负责显示）

    Args:
        st_obj: Streamlit对象
        config_df: 配置DataFrame，包含 {变量名, 性质, 第一次处理, 第二次处理, 第三次处理}
    """
    from dashboard.models.DFM.prep.services.ui_backend_service import UIBackendService

    if config_df is None or config_df.empty:
        st_obj.warning("没有选择任何转换操作")
        return

    # 始终基于基准数据进行转换（避免累积叠加）
    base_data = _get_state(PrepStateKeys.BASE_PREPARED_DATA_DF)
    if base_data is None:
        st_obj.error("没有可处理的数据，请先点击\"开始处理\"")
        return

    # 获取目标频率和频率映射
    target_freq = _get_state(PrepStateKeys.PARAM_TARGET_FREQ, 'W-FRI')
    var_frequency_map = _get_state(PrepStateKeys.VAR_FREQUENCY_MAP_OBJ) or {}

    # 操作名称到代码的映射
    OP_NAME_TO_CODE = {
        '不处理': 'none',
        '对数': 'log',
        '环比差分': 'diff_1',
        '同比差分': 'diff_yoy'
    }

    # 构建转换配置列表（格式为后端服务期望的格式）
    transform_config = []
    for _, row in config_df.iterrows():
        var_name = row['变量名']
        first_op = OP_NAME_TO_CODE.get(row['第一次处理'], 'none')
        second_op = OP_NAME_TO_CODE.get(row['第二次处理'], 'none')
        third_op = OP_NAME_TO_CODE.get(row.get('第三次处理', '不处理'), 'none')

        # 构建操作序列
        ops = []
        if first_op != 'none':
            ops.append(first_op)
        if second_op != 'none':
            ops.append(second_op)
        if third_op != 'none':
            ops.append(third_op)

        # 如果有任何操作，添加到配置
        if ops:
            # 传递完整的操作序列
            transform_config.append({
                'variable': var_name,
                'operations': ops,  # 传递操作列表
                'zero_handling': 'none'
            })

    if not transform_config:
        st_obj.warning("没有选择任何转换操作")
        return

    try:
        with st_obj.spinner("正在应用转换和检验平稳性..."):
            # 调用后端服务（纯业务逻辑，UI层只负责调用和显示）
            result = UIBackendService.transform_and_check_stationarity(
                base_data.copy(),
                transform_config,
                target_freq=target_freq,
                var_frequency_map=var_frequency_map
            )

        if result['status'] != 'success':
            st_obj.error(f"后端处理失败: {result['message']}")
            if result['errors']:
                st_obj.error(f"详细错误: {result['errors']}")
            return

        # 获取后端返回的结果
        transformed_df = result['data']
        transform_details = result['transform_details']
        stationarity_results = result['stationarity_results']
        all_variables_sorted = result['all_variables_sorted']
        non_stationary_count = result['non_stationary_count']

        # 保存结果到状态
        _set_state(PrepStateKeys.PREPARED_DATA_DF, transformed_df)
        _set_state(PrepStateKeys.VARIABLE_TRANSFORM_DETAILS, transform_details)
        _set_state('data_prep.ui_stationarity_results', stationarity_results)

        # 显示转换详情
        _render_transform_details_expander(st_obj, transform_details)

        # 显示平稳性检验结果（所有变量，非平稳排在前面）
        _render_stationarity_test_expander(st_obj, all_variables_sorted, non_stationary_count)

        # 重新生成导出文件
        _regenerate_export_file(st_obj, transformed_df)

        # 根据是否有错误显示不同的结果提示
        if result.get('errors'):
            error_count = len(result['errors'])
            st_obj.warning(f"转换过程中有 {error_count} 个变量处理失败:")
            for err in result['errors'][:5]:
                st_obj.error(f"• {err}")
            if error_count > 5:
                st_obj.caption(f"... 还有 {error_count - 5} 个错误未显示")
            st_obj.info("其他变量已成功转换。请检查失败变量的数据或选择其他转换方式。")
        else:
            st_obj.success("转换和检验完成！")

    except Exception as e:
        st_obj.error(f"后端服务调用失败: {e}")
        import traceback
        st_obj.text_area("详细错误信息:", traceback.format_exc(), height=150)


def _regenerate_export_file(st_obj, transformed_df):
    """
    重新生成导出文件（转换后）

    Args:
        st_obj: Streamlit对象
        transformed_df: 转换后的DataFrame
    """
    try:
        industry_map = _get_state(PrepStateKeys.INDUSTRY_MAP_OBJ) or {}

        if not industry_map:
            return

        # 重新加载映射以获取完整信息
        uploaded_file = _get_state(PrepStateKeys.TRAINING_DATA_FILE)
        if uploaded_file is None:
            return

        from dashboard.models.DFM.prep.api import load_mappings_once
        from dashboard.models.DFM.prep.services.export_service import ExportService

        file_bytes = uploaded_file.getvalue()
        excel_file = io.BytesIO(file_bytes)

        result = load_mappings_once(
            excel_path=excel_file,
            reference_sheet_name=_get_state(PrepStateKeys.PARAM_TYPE_MAPPING_SHEET),
            reference_column_name='指标名称'
        )

        if result['status'] != 'success':
            return

        mappings = result['mappings']

        # 获取检验结果（优先使用UI层的结果，否则使用API层的结果）
        ui_stationarity_results = _get_state('data_prep.ui_stationarity_results') or {}
        api_stationarity_results = _get_state(PrepStateKeys.STATIONARITY_CHECK_RESULTS) or {}

        # 优先使用UI层的检验结果（UI层在转换后立即检验），回退到API层的结果
        stationarity_check_results = ui_stationarity_results if ui_stationarity_results else api_stationarity_results

        logger.info(f"检验结果来源: {'UI层(转换后)' if ui_stationarity_results else 'API层(原始数据)'}, 共{len(stationarity_check_results)}个变量")

        # 平稳性过滤：清除不平稳变量的"一次估计"和"一阶段预测"标记
        updated_mappings = ExportService.clear_non_stationary_markers(
            mappings=mappings,
            stationarity_check_results=stationarity_check_results
        )

        # 调用 ExportService 生成 Excel 文件
        excel_bytes = ExportService.generate_excel(
            prepared_data=transformed_df,
            industry_map=industry_map,
            mappings=updated_mappings,
            removed_vars_log=_get_state(PrepStateKeys.REMOVED_VARS_LOG_OBJ),
            transform_details=_get_state(PrepStateKeys.VARIABLE_TRANSFORM_DETAILS),
            replacement_history=_get_state(PrepStateKeys.VALUE_REPLACEMENT_HISTORY),
            stationarity_check_results=stationarity_check_results
        )

        processed_outputs = _get_state(PrepStateKeys.PROCESSED_OUTPUTS) or {}
        processed_outputs['excel_file'] = excel_bytes
        _set_state(PrepStateKeys.PROCESSED_OUTPUTS, processed_outputs)

        logger.info(f"导出文件已重新生成: 数据形状 {transformed_df.shape}")

    except Exception as e:
        logger.warning(f"重新生成导出文件失败: {e}")


def _render_download_buttons(st_obj):
    """渲染下载按钮（在expander左下角）"""

    processed_outputs = _get_state(PrepStateKeys.PROCESSED_OUTPUTS)

    if processed_outputs:
        # 创建单列布局用于下载按钮（左对齐）
        btn_col1, btn_col2 = st_obj.columns([1, 9])

        with btn_col1:
            if processed_outputs.get('excel_file'):
                st_obj.download_button(
                    label="下载数据",
                    data=processed_outputs['excel_file'],
                    file_name="DFM预处理数据.xlsx",
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='download_processed_excel',
                    type="primary",
                    help="包含两个sheet: 数据和映射"
                )


# ============================================================================
# 主渲染函数
# ============================================================================

def render_dfm_data_prep_page(st_obj):
    """
    渲染DFM数据准备页面

    功能：
    1. 文件上传与变更检测
    2. 日期范围自动检测与缓存
    3. 参数配置（目标频率等）
    4. 数据预处理执行
    5. 变量转换配置（表格式布局）
    6. 处理结果展示
    7. 数据和映射文件导出
    """

    # 初始化有默认值的状态（其他状态在文件上传时按需初始化）
    if _get_state(PrepStateKeys.EXPORT_BASE_NAME) is None:
        _set_state(PrepStateKeys.EXPORT_BASE_NAME, "dfm_prepared_output")
    if _get_state(PrepStateKeys.VAR_NATURE_MAP_OBJ) is None:
        _set_state(PrepStateKeys.VAR_NATURE_MAP_OBJ, {})

    # 1. 文件上传区域
    uploaded_file = _render_file_upload_section(st_obj)

    if uploaded_file is None:
        st_obj.info("请上传训练数据集以开始数据准备。")
        return

    # 2. 日期检测
    detected_start, detected_end, min_date, max_date = _render_date_detection(st_obj, uploaded_file)

    # 3. 变量状态表（文件上传后立即显示）
    _render_raw_variable_stats_table(st_obj, uploaded_file)

    st_obj.markdown("---")
    st_obj.markdown("#### 基础设置")

    # 3. 参数配置区域
    _render_parameter_config(st_obj, detected_start, detected_end, min_date, max_date)

    # 4. 数据处理按钮
    run_button_clicked = _render_processing_section(st_obj, uploaded_file)

    # 5. 执行数据准备
    if run_button_clicked:
        # 清除旧的变量转换配置和详情
        _set_state(PrepStateKeys.TRANSFORM_CONFIG_DF, None)
        _set_state(PrepStateKeys.VARIABLE_TRANSFORM_DETAILS, None)
        _execute_data_preparation(st_obj, uploaded_file)

    # 6. 显示移除变量详情和数据借调详情（同一行布局）
    _render_details_row(st_obj)

    # 7. 变量处理功能区（在数据处理完成后显示）
    _render_variable_transform_section(st_obj)

    # 8. 处理结果区域
    st_obj.markdown("---")

    # 9. 数据预览（显示最终处理后的数据）
    _render_data_preview(st_obj)

    # 10. 显示警告信息
    _render_mapping_warnings(st_obj)

    # 11. 渲染下载按钮
    _render_download_buttons(st_obj)


__all__ = ['render_dfm_data_prep_page']
