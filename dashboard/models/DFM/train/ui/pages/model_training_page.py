# -*- coding: utf-8 -*-
"""
DFM模型训练页面组件

提供DFM模型训练的完整UI界面，包括数据上传、参数配置、变量选择和训练执行
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import re
from datetime import datetime, timedelta, date
from collections import defaultdict
import traceback
from typing import Dict, List, Optional, Union, Any

# 添加路径以导入状态管理辅助函数
current_dir = os.path.dirname(os.path.abspath(__file__))
dashboard_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if dashboard_root not in sys.path:
    sys.path.insert(0, dashboard_root)

import logging

# 导入文本标准化工具（从共享工具库）
from dashboard.models.DFM.utils.text_utils import normalize_text

# 导入组件化训练状态管理
from dashboard.models.DFM.train.ui.components.training_status import TrainingStatusComponent

# 导入新增工具和组件
from dashboard.models.DFM.train.utils import StateManager, filter_industries_by_target, get_non_target_indicators
from dashboard.models.DFM.train.ui.components.file_uploader_component import FileUploaderComponent
from dashboard.models.DFM.train.config import UIConfig
from dashboard.models.DFM.train.ui.utils.config_builder import TrainingConfigBuilder
from dashboard.models.DFM.train.ui.utils.date_helpers import (
    get_target_frequency,
    get_previous_period_date,
    get_frequency_label,
    validate_date_ranges,
)
from dashboard.models.DFM.train.ui.utils.text_helpers import (
    normalize_variable_name,
    normalize_variable_name_no_space,
    build_normalized_mapping,
    filter_exclude_targets,
    get_valid_indicators_for_industry,
    build_exclude_targets_list
)

# 配置日志记录器
logger = logging.getLogger(__name__)

# 创建全局状态管理器实例
_state = StateManager('train_model')


# 配置已移除，使用硬编码默认值
class TrainModelConfig:
    # 基于项目结构的路径设置
    PROJECT_ROOT = os.path.abspath(os.path.join(current_dir, '..', '..', '..', '..'))

    # UI默认配置值
    TYPE_MAPPING_SHEET = '指标字典'
    TARGET_VARIABLE = '规模以上工业增加值:当月同比'
    INDICATOR_COLUMN_NAME_IN_EXCEL = '指标名称'
    INDUSTRY_COLUMN_NAME_IN_EXCEL = '行业'
    TYPE_COLUMN_NAME_IN_EXCEL = '类型'
    EXCLUDE_COLS_FROM_TARGET = []  # 排除的目标变量列名列表

config = TrainModelConfig()

# 导入DFM训练脚本
_TRAIN_UI_IMPORT_ERROR_MESSAGE = None
try:
    from dashboard.models.DFM.train import DFMTrainer, TrainingConfig, TrainingResult
except ImportError as e:
    _TRAIN_UI_IMPORT_ERROR_MESSAGE = f"train模块导入失败: {e}"
    raise ImportError(f"导入train模块失败: {e}") from e


def _reset_training_state():
    """重置所有训练相关状态"""
    from dashboard.core.ui.utils.debug_helpers import debug_log

    training_keys = [
        'dfm_training_status',
        'dfm_training_log',
        'dfm_training_progress',
        'dfm_model_results_paths',
        'dfm_model_results',
        'dfm_training_error',
        'dfm_training_start_time',
        'dfm_training_end_time',
        'dfm_force_reset_training_state',
        'dfm_page_initialized',
        'dfm_training_completed_timestamp'
    ]

    for key in training_keys:
        _state.set(key, None)
        debug_log(f"状态重置 - 已清理状态键: {key}", "DEBUG")

    # 重置为初始状态
    _state.set('dfm_training_status', '等待开始')
    _state.set('dfm_training_log', [])
    _state.set('dfm_training_progress', 0)
    _state.set('dfm_model_results_paths', None)
    _state.set('dfm_model_results', None)

    debug_log("状态重置 - 已重置所有训练状态到初始值", "DEBUG")


def _get_default_target_variable() -> str:
    """获取默认目标变量名称"""
    return config.TARGET_VARIABLE


def render_dfm_model_training_page(st_instance):

    # 确保datetime在函数开头就可用
    from datetime import datetime
    import time

    if _TRAIN_UI_IMPORT_ERROR_MESSAGE:
        if "train" in _TRAIN_UI_IMPORT_ERROR_MESSAGE:
            st_instance.error(f"关键模块导入错误，模型训练功能不可用:\n{_TRAIN_UI_IMPORT_ERROR_MESSAGE}")
            return  # 如果训练模块不可用，直接返回
        else:
            # 如果只是数据准备模块的导入问题，显示警告但继续
            st_instance.warning("[WARNING] 数据准备模块导入警告，但映射数据传递已修复，功能应该正常")

    current_training_status = _state.get('dfm_training_status')
    current_model_results = _state.get('dfm_model_results_paths')

    # 如果页面刚加载且存在之前的训练完成状态，询问用户是否要重置
    page_just_loaded = _state.get('dfm_page_initialized') is None

    if page_just_loaded:
        _state.set('dfm_page_initialized', True)

        # 如果存在之前的训练结果，显示提示并自动重置（避免混淆）
        if current_training_status == '训练完成' and current_model_results:
            st_instance.info("[LOADING] 检测到之前的训练结果，已自动重置训练状态以开始新的训练")
            _reset_training_state()
            current_training_status = '等待开始'

    # 使用状态管理器初始化DFM状态
    if current_training_status is None:
        _state.set('dfm_training_status', "等待开始")
    if _state.get('dfm_model_results') is None:
        _state.set('dfm_model_results', None)
    if _state.get('dfm_training_log') is None:
        _state.set('dfm_training_log', [])
    if _state.get('dfm_model_results_paths') is None:
        _state.set('dfm_model_results_paths', None)



    training_status = _state.get('dfm_training_status', '等待开始')

    training_results = _state.get('dfm_model_results_paths')
    if training_results and training_status != '训练完成':
        logger.info(f"状态修复: 检测到训练结果存在但状态未更新: {training_status} -> 训练完成")
        _state.set('dfm_training_status', '训练完成')
        training_status = '训练完成'

    from dashboard.core.ui.utils.debug_helpers import debug_log
    debug_log(f"UI状态检查 - 当前训练状态: {training_status}", "DEBUG")

    # 使用组件化的文件上传器
    state_manager = StateManager('train_model')
    file_uploader = FileUploaderComponent(state_manager)
    input_df, var_industry_map, dfm_default_map, var_frequency_map, var_unit_map = file_uploader.render(st_instance)

    # 如果文件验证失败，提前返回
    if input_df is None or not var_industry_map:
        return

    available_target_vars = []
    if input_df is not None:
        # 从已加载数据中获取可选的目标变量
        available_target_vars = [col for col in input_df.columns if 'date' not in col.lower() and 'time' not in col.lower() and col not in config.EXCLUDE_COLS_FROM_TARGET]

        default_target = _get_default_target_variable()

        # 如果默认目标变量在数据中存在但不在过滤列表中，则添加它
        if default_target and default_target in input_df.columns and default_target not in available_target_vars:
            available_target_vars.insert(0, default_target)  # 插入到开头作为首选


        # 如果过滤后的列表为空，但默认目标变量存在，则使用它
        if not available_target_vars and default_target and default_target in input_df.columns:
            available_target_vars = [default_target]


        if not available_target_vars:
            st_instance.warning("预处理数据中未找到合适的目标变量候选。")
            # 即使没找到，也提供一个默认选项避免selectbox为空
            if default_target:
                available_target_vars = [default_target]
                st_instance.info(f"使用默认目标变量: {default_target}")


    else:

        st_instance.warning("数据尚未准备，请先在\"数据准备\"选项卡中处理数据。变量选择功能将受限。")

        default_target = _get_default_target_variable()

        if default_target:
            available_target_vars = [default_target]
            st_instance.info(f"使用默认目标变量: {default_target}")


    # 直接使用文件上传器加载的映射数据（已由FileUploaderComponent处理）
    # 完全解耦，不从其他模块的session_state读取数据

    # 构建行业到指标的映射
    industry_to_indicators_temp = defaultdict(list)
    if var_industry_map:
        for indicator, industry in var_industry_map.items():
            if indicator and industry:
                industry_to_indicators_temp[str(industry).strip()].append(str(indicator).strip())

    unique_industries = sorted(list(industry_to_indicators_temp.keys()))
    var_to_indicators_map_by_industry = {k: sorted(v) for k, v in industry_to_indicators_temp.items()}

    # ===== 计算日期默认值的辅助函数 =====
    def get_data_based_date_defaults():
        """基于实际数据计算日期默认值，优先使用数据准备页面设置的日期边界"""
        from datetime import datetime
        today = datetime.now().date()

        # 使用统一配置类
        static_defaults = UIConfig.get_date_defaults()

        try:
            # 仅从train_model模块获取数据（完全解耦）
            data_df = _state.get('dfm_prepared_data_df')

            if data_df is not None and isinstance(data_df.index, pd.DatetimeIndex) and len(data_df.index) > 0:
                # 从数据获取第一期
                data_first_date = data_df.index.min().date()

                # 训练开始日期默认为数据的第一期
                training_start_date = data_first_date
                validation_start_date = UIConfig.DEFAULT_VALIDATION_START
                observation_start_date = UIConfig.DEFAULT_OBSERVATION_START

                # 计算验证期结束日期 = 观察期开始日期 - 1周
                validation_end_timestamp = pd.Timestamp(observation_start_date) - pd.Timedelta(weeks=1)

                return {
                    'training_start': training_start_date,
                    'validation_start': validation_start_date,
                    'validation_end': validation_end_timestamp.date()
                }
            else:
                return static_defaults
        except Exception as e:
            logger.warning(f"计算数据默认日期失败: {e}，使用静态默认值")
            return static_defaults

    # 获取智能默认值
    date_defaults = get_data_based_date_defaults()

    # 初始化数据相关状态
    has_data = False
    data_df = _state.get('dfm_prepared_data_df')
    if data_df is not None:
        has_data = True

    if has_data:
        if isinstance(data_df.index, pd.DatetimeIndex) and len(data_df.index) > 0:
            # 初始化默认日期（只在状态为空时设置）
            if _state.get('dfm_training_start_date') is None:
                _state.set('dfm_training_start_date', date_defaults['training_start'])
            if _state.get('dfm_validation_start_date') is None:
                _state.set('dfm_validation_start_date', date_defaults['validation_start'])
            if _state.get('dfm_observation_start_date') is None:
                _state.set('dfm_observation_start_date', UIConfig.DEFAULT_OBSERVATION_START)

    # ===== 训练设置 =====
    st_instance.subheader("训练设置")

    # 获取当前算法值（用于判断是否显示变量筛选和因子选择）
    current_algorithm = _state.get('dfm_algorithm', UIConfig.DEFAULT_ALGORITHM)
    if current_algorithm not in UIConfig.ALGORITHM_OPTIONS:
        raise ValueError(f"无效的算法类型: {current_algorithm}，有效值: {list(UIConfig.ALGORITHM_OPTIONS.keys())}")

    # 初始化前一次算法值（用于检测变化）
    if _state.get('_prev_dfm_algorithm') is None:
        _state.set('_prev_dfm_algorithm', current_algorithm)

    # 深度学习模式标志
    is_deep_learning_mode = (current_algorithm == 'deep_learning')

    # 第一行：选择算法 + 目标值 + 变量筛选方法 + 因子选择策略（后两者仅经典算法显示）
    if is_deep_learning_mode:
        col_algo, col_align = st_instance.columns(2)
    else:
        col_algo, col_align, col_var_method, col_factor_strategy = st_instance.columns(4)

    with col_algo:
        algorithm_value = st_instance.selectbox(
            "选择算法",
            options=list(UIConfig.ALGORITHM_OPTIONS.keys()),
            format_func=lambda x: UIConfig.ALGORITHM_OPTIONS[x],
            index=UIConfig.get_safe_option_index(
                UIConfig.ALGORITHM_OPTIONS, current_algorithm, UIConfig.DEFAULT_ALGORITHM
            ),
            key='dfm_algorithm_selector',
            help="经典DFM使用EM算法，深度学习DFM使用神经网络自编码器"
        )
        _state.set('dfm_algorithm', algorithm_value)
        current_algorithm = algorithm_value

        # 检测算法变化，触发rerun以更新UI布局
        if algorithm_value != _state.get('_prev_dfm_algorithm'):
            _state.set('_prev_dfm_algorithm', algorithm_value)
            st_instance.rerun()

    with col_align:
        current_alignment = _state.get('dfm_target_alignment_mode', UIConfig.DEFAULT_TARGET_ALIGNMENT)
        if current_alignment not in UIConfig.TARGET_ALIGNMENT_OPTIONS:
            raise ValueError(f"无效的目标对齐方式: {current_alignment}，有效值: {list(UIConfig.TARGET_ALIGNMENT_OPTIONS.keys())}")

        alignment_value = st_instance.selectbox(
            "目标值",
            options=list(UIConfig.TARGET_ALIGNMENT_OPTIONS.keys()),
            format_func=lambda x: UIConfig.TARGET_ALIGNMENT_OPTIONS[x],
            index=UIConfig.get_safe_option_index(
                UIConfig.TARGET_ALIGNMENT_OPTIONS, current_alignment, UIConfig.DEFAULT_TARGET_ALIGNMENT
            ),
            key='dfm_target_alignment_mode_input',
            help="nowcast预测值与目标变量实际值的配对方式"
        )
        _state.set('dfm_target_alignment_mode', alignment_value)

    if not is_deep_learning_mode:
        with col_var_method:
            current_var_method = _state.get('dfm_variable_selection_method', UIConfig.DEFAULT_VAR_SELECTION)
            if current_var_method not in UIConfig.VARIABLE_SELECTION_METHODS:
                raise ValueError(f"无效的变量筛选方法: {current_var_method}，有效值: {list(UIConfig.VARIABLE_SELECTION_METHODS.keys())}")

            var_method_value = st_instance.selectbox(
                "变量筛选方法",
                options=list(UIConfig.VARIABLE_SELECTION_METHODS.keys()),
                format_func=lambda x: UIConfig.VARIABLE_SELECTION_METHODS[x],
                index=UIConfig.get_safe_option_index(
                    UIConfig.VARIABLE_SELECTION_METHODS, current_var_method, UIConfig.DEFAULT_VAR_SELECTION
                ),
                key='dfm_variable_selection_method_input',
                help="选择在已选变量基础上的筛选方法"
            )
            _state.set('dfm_variable_selection_method', var_method_value)

            enable_var_selection = (var_method_value != 'none')
            _state.set('dfm_enable_variable_selection', enable_var_selection)

        with col_factor_strategy:
            current_strategy = _state.get('dfm_factor_selection_strategy', UIConfig.DEFAULT_FACTOR_STRATEGY)
            if current_strategy not in UIConfig.FACTOR_STRATEGIES:
                raise ValueError(f"无效的因子选择策略: {current_strategy}，有效值: {list(UIConfig.FACTOR_STRATEGIES.keys())}")

            strategy_value = st_instance.selectbox(
                "因子选择策略",
                options=list(UIConfig.FACTOR_STRATEGIES.keys()),
                format_func=lambda x: UIConfig.FACTOR_STRATEGIES[x],
                index=UIConfig.get_safe_option_index(
                    UIConfig.FACTOR_STRATEGIES, current_strategy, UIConfig.DEFAULT_FACTOR_STRATEGY
                ),
                key='dfm_factor_selection_strategy',
                help="选择确定因子数量的方法"
            )
            _state.set('dfm_factor_selection_strategy', strategy_value)
    else:
        # 深度学习模式：禁用变量选择
        _state.set('dfm_variable_selection_method', 'none')
        _state.set('dfm_enable_variable_selection', False)
        enable_var_selection = False
        strategy_value = 'fixed_number'

    # ===== 训练周期设置 =====

    # 获取目标变量的频率标签（用于动态文案）
    target_variable = _state.get('dfm_target_variable', '')
    var_frequency_map = _state.get('dfm_frequency_map_obj', {})
    target_freq_code = get_target_frequency(target_variable, var_frequency_map, default_freq='W')
    freq_label = get_frequency_label(target_freq_code)

    col_time1, col_time2, col_time3 = st_instance.columns(3)

    with col_time1:
        training_start_value = st_instance.date_input(
            "训练期开始",
            value=_state.get('dfm_training_start_date', date_defaults['training_start']),
            key='dfm_training_start_date_input',
            help="模型训练数据的起始日期，默认为数据开始日期"
        )
        _state.set('dfm_training_start_date', training_start_value)

    # 判断是否为DDFM模式
    is_ddfm_mode = (current_algorithm == 'deep_learning')

    with col_time2:
        if is_ddfm_mode:
            # DDFM模式：没有验证期，显示观察期开始
            observation_start_value = st_instance.date_input(
                "观察期开始",
                value=_state.get('dfm_observation_start_date', UIConfig.DEFAULT_OBSERVATION_START),
                key='dfm_observation_start_date_input',
                help="观察期开始日期，训练期将延伸到该日期的前一期"
            )
            _state.set('dfm_observation_start_date', observation_start_value)
            # DDFM内部用validation_start/end存储观察期范围
            _state.set('dfm_validation_start_date', observation_start_value)
        else:
            # 经典DFM模式：显示验证期开始
            validation_start_value = st_instance.date_input(
                "验证期开始",
                value=_state.get('dfm_validation_start_date', date_defaults['validation_start']),
                key='dfm_validation_start_date_input',
                help="验证期开始日期，训练期将在此日期前一天结束"
            )
            _state.set('dfm_validation_start_date', validation_start_value)

    with col_time3:
        if is_ddfm_mode:
            # DDFM模式：显示观察期结束（数据最后日期，只读）
            if not has_data or not isinstance(data_df.index, pd.DatetimeIndex):
                raise ValueError("DDFM模式需要有效的数据，请先上传预处理后的数据文件")
            observation_end_value = data_df.index.max().date()
            st_instance.date_input(
                "观察期结束",
                value=observation_end_value,
                key='dfm_observation_end_date_display',
                disabled=True,
                help="观察期结束日期（数据最后日期）"
            )
            _state.set('dfm_validation_end_date', observation_end_value)
        else:
            # 经典DFM模式：显示观察期开始
            observation_start_value = st_instance.date_input(
                "观察期开始",
                value=_state.get('dfm_observation_start_date', UIConfig.DEFAULT_OBSERVATION_START),
                key='dfm_observation_start_date_input',
                help=f"观察期开始日期，验证期结束日期自动设置为该日期的上一{freq_label}"
            )
            _state.set('dfm_observation_start_date', observation_start_value)
            # 经典DFM：validation_end = observation_start的前一期
            validation_end_value = get_previous_period_date(observation_start_value, target_freq_code, periods=1)
            _state.set('dfm_validation_end_date', validation_end_value)

    # 显示算法模式说明（占据整行）
    if current_algorithm == 'deep_learning':
        st_instance.caption(
            f"DDFM模式: 使用从训练期开始到观察期上一{freq_label}的全部数据进行训练"
        )
    else:
        st_instance.caption(
            "经典DFM模式: 模型在训练期数据上拟合参数，在验证期数据上评估性能"
        )

    # ===== 高级选项 (折叠) =====
    is_deep_learning = (algorithm_value == 'deep_learning')
    with st_instance.expander("高级选项", expanded=False):

        # ===== DDFM专用参数（仅深度学习算法显示）=====
        if is_deep_learning:
            st_instance.markdown("**深度学习参数**")

            # 第一行：编码器结构 + 因子AR阶数
            ddfm_col1, ddfm_col2 = st_instance.columns(2)

            with ddfm_col1:
                # 解析因子数用于显示
                encoder_structure_str = _state.get('dfm_encoder_structure', UIConfig.ENCODER_STRUCTURE_DEFAULT)
                try:
                    parts = [int(x.strip()) for x in encoder_structure_str.split(',')]
                    factor_label = f"编码器结构（因子数: {parts[-1]}）" if parts else "编码器结构"
                except ValueError:
                    factor_label = "编码器结构"

                encoder_structure_value = st_instance.text_input(
                    factor_label,
                    value=encoder_structure_str,
                    key='dfm_encoder_structure_input',
                    help=UIConfig.ENCODER_STRUCTURE_HELP
                )
                _state.set('dfm_encoder_structure', encoder_structure_value)

            with ddfm_col2:
                ddfm_factor_order = st_instance.selectbox(
                    "因子AR阶数",
                    options=list(UIConfig.DDFM_FACTOR_ORDER_OPTIONS.keys()),
                    format_func=lambda x: UIConfig.DDFM_FACTOR_ORDER_OPTIONS[x],
                    index=0 if _state.get('dfm_ddfm_factor_order', UIConfig.DDFM_FACTOR_ORDER_DEFAULT) == 1 else 1,
                    key='dfm_ddfm_factor_order_input',
                    help="因子的自回归阶数"
                )
                _state.set('dfm_ddfm_factor_order', ddfm_factor_order)

            # 第二行：学习率 + 优化器
            ddfm_col3, ddfm_col4 = st_instance.columns(2)

            with ddfm_col3:
                learning_rate_value = st_instance.number_input(
                    "学习率",
                    min_value=UIConfig.LEARNING_RATE_MIN,
                    max_value=UIConfig.LEARNING_RATE_MAX,
                    value=_state.get('dfm_ddfm_learning_rate', UIConfig.LEARNING_RATE_DEFAULT),
                    step=UIConfig.LEARNING_RATE_STEP,
                    format="%.4f",
                    key='dfm_ddfm_learning_rate_input',
                    help="神经网络学习率"
                )
                _state.set('dfm_ddfm_learning_rate', learning_rate_value)

            with ddfm_col4:
                current_optimizer = _state.get('dfm_ddfm_optimizer', UIConfig.DDFM_OPTIMIZER_DEFAULT)
                optimizer_value = st_instance.selectbox(
                    "优化器",
                    options=list(UIConfig.DDFM_OPTIMIZER_OPTIONS.keys()),
                    format_func=lambda x: UIConfig.DDFM_OPTIMIZER_OPTIONS[x],
                    index=0 if current_optimizer == 'Adam' else 1,
                    key='dfm_ddfm_optimizer_input',
                    help="神经网络优化器"
                )
                _state.set('dfm_ddfm_optimizer', optimizer_value)

            # 第三行：MCMC迭代次数 + 批量大小
            ddfm_col5, ddfm_col6 = st_instance.columns(2)

            with ddfm_col5:
                mcmc_max_iter_value = st_instance.number_input(
                    "MCMC最大迭代",
                    min_value=UIConfig.MCMC_MAX_ITER_MIN,
                    max_value=UIConfig.MCMC_MAX_ITER_MAX,
                    value=_state.get('dfm_ddfm_max_iter', UIConfig.MCMC_MAX_ITER_DEFAULT),
                    step=UIConfig.MCMC_MAX_ITER_STEP,
                    key='dfm_ddfm_max_iter_input',
                    help="MCMC算法最大迭代次数"
                )
                _state.set('dfm_ddfm_max_iter', mcmc_max_iter_value)

            with ddfm_col6:
                batch_size_value = st_instance.number_input(
                    "批量大小",
                    min_value=UIConfig.BATCH_SIZE_MIN,
                    max_value=UIConfig.BATCH_SIZE_MAX,
                    value=_state.get('dfm_ddfm_batch_size', UIConfig.BATCH_SIZE_DEFAULT),
                    step=UIConfig.BATCH_SIZE_STEP,
                    key='dfm_ddfm_batch_size_input',
                    help="神经网络训练批量大小"
                )
                _state.set('dfm_ddfm_batch_size', batch_size_value)

            # 第四行：激活函数 + 输入滞后期数
            ddfm_col7, ddfm_col8 = st_instance.columns(2)

            with ddfm_col7:
                current_activation = _state.get('dfm_ddfm_activation', UIConfig.DDFM_ACTIVATION_DEFAULT)
                activation_value = st_instance.selectbox(
                    "激活函数",
                    options=list(UIConfig.DDFM_ACTIVATION_OPTIONS.keys()),
                    format_func=lambda x: UIConfig.DDFM_ACTIVATION_OPTIONS[x],
                    index=UIConfig.get_safe_option_index(
                        UIConfig.DDFM_ACTIVATION_OPTIONS,
                        current_activation,
                        UIConfig.DDFM_ACTIVATION_DEFAULT
                    ),
                    key='dfm_ddfm_activation_input',
                    help="神经网络激活函数"
                )
                _state.set('dfm_ddfm_activation', activation_value)

            with ddfm_col8:
                lags_input_value = st_instance.number_input(
                    "输入滞后期数",
                    min_value=UIConfig.LAGS_INPUT_MIN,
                    max_value=UIConfig.LAGS_INPUT_MAX,
                    value=_state.get('dfm_ddfm_lags_input', UIConfig.LAGS_INPUT_DEFAULT),
                    step=1,
                    key='dfm_ddfm_lags_input_input',
                    help=UIConfig.LAGS_INPUT_HELP
                )
                _state.set('dfm_ddfm_lags_input', lags_input_value)

            # 第五行：每次MCMC的epoch数 + MCMC收敛阈值
            ddfm_col9, ddfm_col10 = st_instance.columns(2)

            with ddfm_col9:
                epochs_per_mcmc_value = st_instance.number_input(
                    "每次MCMC训练轮数",
                    min_value=UIConfig.EPOCHS_PER_MCMC_MIN,
                    max_value=UIConfig.EPOCHS_PER_MCMC_MAX,
                    value=_state.get('dfm_ddfm_epochs', UIConfig.EPOCHS_PER_MCMC_DEFAULT),
                    step=UIConfig.EPOCHS_PER_MCMC_STEP,
                    key='dfm_ddfm_epochs_input',
                    help="每次MCMC迭代中神经网络训练的epoch数"
                )
                _state.set('dfm_ddfm_epochs', epochs_per_mcmc_value)

            with ddfm_col10:
                mcmc_tolerance_value = st_instance.number_input(
                    "MCMC收敛阈值",
                    min_value=UIConfig.MCMC_TOLERANCE_MIN,
                    max_value=UIConfig.MCMC_TOLERANCE_MAX,
                    value=_state.get('dfm_ddfm_tolerance', UIConfig.MCMC_TOLERANCE_DEFAULT),
                    step=0.0001,
                    format="%.5f",
                    key='dfm_ddfm_tolerance_input',
                    help="MCMC算法收敛判定阈值"
                )
                _state.set('dfm_ddfm_tolerance', mcmc_tolerance_value)

            st_instance.divider()

        # ===== 经典DFM因子参数（仅经典算法显示）=====
        if not is_deep_learning:
            # 因子参数（根据策略条件显示）- 两列布局
            # 两列布局：左列策略参数，右列因子自回归阶数
            factor_col1, factor_col2 = st_instance.columns(2)

            # 左列：根据策略条件显示参数
            with factor_col1:
                if strategy_value == 'fixed_number':
                    fixed_factors_value = st_instance.number_input(
                        "因子数",
                        min_value=UIConfig.K_FACTORS_MIN,
                        max_value=UIConfig.K_FACTORS_MAX,
                        value=_state.get('dfm_fixed_number_of_factors', UIConfig.DEFAULT_K_FACTORS),
                        step=1,
                        key='dfm_fixed_number_of_factors',
                        help="指定使用的因子数量"
                    )
                    _state.set('dfm_fixed_number_of_factors', fixed_factors_value)
                elif strategy_value == 'cumulative_variance':
                    cum_var_value = st_instance.number_input(
                        "累积方差阈值",
                        min_value=UIConfig.CUM_VARIANCE_MIN,
                        max_value=UIConfig.CUM_VARIANCE_MAX,
                        value=_state.get('dfm_cumulative_variance_threshold', UIConfig.DEFAULT_CUM_VARIANCE),
                        step=UIConfig.CUM_VARIANCE_STEP,
                        format="%.2f",
                        key='dfm_cumulative_variance_threshold_input',
                        help="因子累积解释方差的阈值"
                    )
                    _state.set('dfm_cumulative_variance_threshold', cum_var_value)
                elif strategy_value == 'kaiser':
                    kaiser_threshold_value = st_instance.number_input(
                        "特征值阈值",
                        min_value=UIConfig.KAISER_THRESHOLD_MIN,
                        max_value=UIConfig.KAISER_THRESHOLD_MAX,
                        value=_state.get('dfm_kaiser_threshold', UIConfig.DEFAULT_KAISER_THRESHOLD),
                        step=UIConfig.KAISER_THRESHOLD_STEP,
                        format="%.1f",
                        key='dfm_kaiser_threshold_input',
                        help="选择特征值大于此阈值的因子"
                    )
                    _state.set('dfm_kaiser_threshold', kaiser_threshold_value)

            # 右列：因子自回归阶数
            with factor_col2:
                ar_order_value = st_instance.number_input(
                    "因子自回归阶数",
                    min_value=UIConfig.FACTOR_AR_ORDER_MIN,
                    max_value=UIConfig.FACTOR_AR_ORDER_MAX,
                    value=_state.get('dfm_factor_ar_order', UIConfig.DEFAULT_FACTOR_AR_ORDER),
                    step=1,
                    key='dfm_factor_ar_order_input',
                    help="因子的自回归阶数，通常设为1"
                )
                _state.set('dfm_factor_ar_order', ar_order_value)

            # EM算法最大迭代次数（始终显示）+ 最少保留变量数（仅启用筛选时显示）
            if enable_var_selection:
                em_var_col1, em_var_col2 = st_instance.columns(2)
            else:
                em_var_col1 = st_instance.container()

            with em_var_col1:
                max_iterations_value = st_instance.number_input(
                    "EM算法最大迭代次数",
                    min_value=UIConfig.EM_MAX_ITERATIONS_MIN,
                    max_value=UIConfig.EM_MAX_ITERATIONS_MAX,
                    value=_state.get('dfm_max_iterations', UIConfig.EM_MAX_ITERATIONS_DEFAULT),
                    step=UIConfig.EM_MAX_ITERATIONS_STEP,
                    key='dfm_max_iterations_input',
                    help="EM算法的最大迭代次数，影响训练时间和收敛质量"
                )
                _state.set('dfm_max_iterations', max_iterations_value)

            if enable_var_selection:
                with em_var_col2:
                    min_vars_value = st_instance.number_input(
                        "最少保留变量数",
                        min_value=UIConfig.MIN_VARIABLES_AFTER_SELECTION_MIN,
                        max_value=UIConfig.MIN_VARIABLES_AFTER_SELECTION_MAX,
                        value=_state.get('dfm_min_variables_after_selection', UIConfig.MIN_VARIABLES_AFTER_SELECTION_DEFAULT),
                        step=1,
                        key='dfm_min_variables_after_selection_input',
                        help="变量筛选后至少保留的变量数，防止过度删减"
                    )
                    _state.set('dfm_min_variables_after_selection', min_vars_value)

        # 筛选策略和混合优先级（筛选启用时显示）- 两列布局
        if enable_var_selection:
            st_instance.divider()

            current_criterion = _state.get('dfm_selection_criterion', UIConfig.DEFAULT_SELECTION_CRITERION)
            # 验证策略有效性
            if current_criterion not in UIConfig.SELECTION_CRITERIA:
                raise ValueError(f"无效的筛选策略: {current_criterion}，有效值: {list(UIConfig.SELECTION_CRITERIA.keys())}")

            # 两列布局：左列筛选策略，右列混合优先级
            selection_col1, selection_col2 = st_instance.columns(2)

            with selection_col1:
                criterion_value = st_instance.selectbox(
                    "筛选策略",
                    options=list(UIConfig.SELECTION_CRITERIA.keys()),
                    format_func=lambda x: UIConfig.SELECTION_CRITERIA[x],
                    index=UIConfig.get_safe_option_index(
                        UIConfig.SELECTION_CRITERIA, current_criterion, UIConfig.DEFAULT_SELECTION_CRITERION
                    ),
                    key='dfm_selection_criterion_input',
                    help="RMSE/胜率/混合"
                )
                _state.set('dfm_selection_criterion', criterion_value)

            # 右列：混合优先级（仅在混合策略时显示）
            with selection_col2:
                if criterion_value == 'hybrid':
                    current_priority = _state.get('dfm_hybrid_priority', UIConfig.DEFAULT_HYBRID_PRIORITY)
                    # 验证优先级有效性
                    if current_priority not in UIConfig.HYBRID_PRIORITIES:
                        raise ValueError(f"无效的混合优先级: {current_priority}，有效值: {list(UIConfig.HYBRID_PRIORITIES.keys())}")

                    priority_value = st_instance.selectbox(
                        "混合优先级",
                        options=list(UIConfig.HYBRID_PRIORITIES.keys()),
                        format_func=lambda x: UIConfig.HYBRID_PRIORITIES[x],
                        index=UIConfig.get_safe_option_index(
                            UIConfig.HYBRID_PRIORITIES, current_priority, UIConfig.DEFAULT_HYBRID_PRIORITY
                        ),
                        key='dfm_hybrid_priority_input',
                        help="胜率优先或RMSE优先"
                    )
                    _state.set('dfm_hybrid_priority', priority_value)

            # 训练期权重（始终显示）+ 阈值（仅混合策略显示）
            st_instance.divider()

            if criterion_value == 'hybrid':
                # 混合策略：三列布局
                weight_col1, weight_col2, weight_col3 = st_instance.columns(3)
            else:
                # 非混合策略：单列显示训练期权重
                weight_col1 = st_instance.container()

            with weight_col1:
                current_weight = _state.get('dfm_training_weight', UIConfig.DEFAULT_TRAINING_WEIGHT)
                training_weight_value = st_instance.slider(
                    "训练期权重 (%)",
                    min_value=UIConfig.TRAINING_WEIGHT_MIN,
                    max_value=UIConfig.TRAINING_WEIGHT_MAX,
                    value=current_weight,
                    step=UIConfig.TRAINING_WEIGHT_STEP,
                    key='dfm_training_weight_input',
                    help="0%=仅验证期, 100%=仅训练期"
                )
                _state.set('dfm_training_weight', training_weight_value)

            if criterion_value == 'hybrid':
                with weight_col2:
                    current_rmse_tolerance = _state.get('dfm_rmse_tolerance', UIConfig.DEFAULT_RMSE_TOLERANCE)
                    rmse_tolerance_value = st_instance.slider(
                        "RMSE相近阈值 (%)",
                        min_value=UIConfig.RMSE_TOLERANCE_MIN,
                        max_value=UIConfig.RMSE_TOLERANCE_MAX,
                        value=float(current_rmse_tolerance),
                        step=UIConfig.RMSE_TOLERANCE_STEP,
                        key='dfm_rmse_tolerance_input',
                        help="当两个模型RMSE差异小于此百分比时视为相近"
                    )
                    _state.set('dfm_rmse_tolerance', rmse_tolerance_value)

                with weight_col3:
                    current_win_rate_tolerance = _state.get('dfm_win_rate_tolerance', UIConfig.DEFAULT_WIN_RATE_TOLERANCE)
                    win_rate_tolerance_value = st_instance.slider(
                        "胜率相近阈值 (%)",
                        min_value=UIConfig.WIN_RATE_TOLERANCE_MIN,
                        max_value=UIConfig.WIN_RATE_TOLERANCE_MAX,
                        value=float(current_win_rate_tolerance),
                        step=UIConfig.WIN_RATE_TOLERANCE_STEP,
                        key='dfm_win_rate_tolerance_input',
                        help="当两个模型胜率差异小于此百分点时视为相近"
                    )
                    _state.set('dfm_win_rate_tolerance', win_rate_tolerance_value)

    # ===== 变量选择 =====
    st_instance.markdown("--- ")

    # 添加变量选择大标题
    st_instance.subheader("变量选择")

    # 1. 目标变量选择/识别
    # 从映射文件自动识别目标变量
    target_map = _state.get('dfm_target_map', {})

    # 将标准化的键转换回原始列名
    target_candidates = []

    if input_df is not None:
        for col in input_df.columns:
            col_norm = normalize_text(col)
            if col_norm in target_map:
                target_candidates.append(col)

    # 验证唯一性
    if len(target_candidates) == 0:
        st_instance.error("[ERROR] 映射文件'目标变量'列中未标记任何目标变量")
        st_instance.info("提示：目标变量通过映射文件'目标变量'列标记")
        _state.set('dfm_target_variable', None)
    elif len(target_candidates) > 1:
        st_instance.error(f"[ERROR] 映射文件'目标变量'列中标记了多个目标变量，请确保只有一个目标变量标记为'是'")
        st_instance.warning(f"当前识别到的目标变量：{', '.join(target_candidates)}")
        _state.set('dfm_target_variable', None)
    else:
        # 唯一目标变量
        target_var = target_candidates[0]
        _state.set('dfm_target_variable', target_var)

    # 根据映射文件选择预测变量默认配置
    # dfm_default_map 已从 file_uploader.render() 加载（line 176）

    # 2. 过滤行业：移除仅包含目标变量的行业（使用工具函数）
    current_target_var = _state.get('dfm_target_variable', None)
    filtered_industries = filter_industries_by_target(
        unique_industries,
        var_to_indicators_map_by_industry,
        current_target_var
    )

    # 预计算各行业有效指标（DRY：只计算一次，后续复用）
    exclude_targets = build_exclude_targets_list(current_target_var, first_stage_targets=None)

    var_industry_map = _state.get('dfm_industry_map_obj')
    if not var_industry_map:
        raise ValueError("行业映射数据未加载，请先上传并加载指标字典文件")

    # 构建行业→有效指标映射缓存
    industry_available_indicators = {}
    for industry in filtered_industries:
        all_indicators = var_to_indicators_map_by_industry.get(industry, [])
        valid_indicators = get_valid_indicators_for_industry(
            all_indicators,
            exclude_targets,
            var_industry_map,
        )
        if valid_indicators:
            industry_available_indicators[industry] = valid_indicators

    # 暂时存储过滤后的行业，以供后续步骤3中使用
    if not filtered_industries:
        st_instance.info("没有可用的行业数据。")
        _state.set('dfm_selected_industries', [])
    else:
        pass  # 继续进行到步骤3，用户将直接选择指标

    # 3. 根据选定行业选择预测指标 (每个行业一个多选下拉菜单，默认全选)
    with st_instance.expander("选择预测指标", expanded=False):
        indicators_state_key = 'dfm_selected_indicators_per_industry'

        # 初始化指标选择状态
        if _state.get(indicators_state_key, None) is None:
            _state.set(indicators_state_key, {})

        final_selected_indicators_flat = []
        current_selected_industries = filtered_industries  # 直接使用过滤后的所有行业

        # 注意：industry_available_indicators 已在上方预计算，直接复用

        # 添加全局控制按钮
        if current_selected_industries and industry_available_indicators:
            st_instance.markdown("**全局控制**")
            global_control_col1, global_control_col2 = st_instance.columns(2)

            with global_control_col1:
                global_select_all = st_instance.button(
                    "全选所有指标",
                    key="dfm_global_select_all",
                    width='stretch'
                )

            with global_control_col2:
                global_deselect_all = st_instance.button(
                    "取消全选所有指标",
                    key="dfm_global_deselect_all",
                    width='stretch'
                )

            # 处理全局全选
            if global_select_all:
                for industry_name, available_indicators in industry_available_indicators.items():
                    multiselect_key = f"dfm_indicators_multiselect_{industry_name}"
                    select_all_key = f"dfm_select_all_{industry_name}"

                    # 更新multiselect状态
                    st.session_state[multiselect_key] = available_indicators
                    # 删除checkbox状态，让它在下次渲染时重新初始化
                    if select_all_key in st.session_state:
                        del st.session_state[select_all_key]

                # 刷新页面
                st_instance.rerun()

            # 处理全局取消全选
            if global_deselect_all:
                for industry_name in industry_available_indicators.keys():
                    multiselect_key = f"dfm_indicators_multiselect_{industry_name}"
                    select_all_key = f"dfm_select_all_{industry_name}"

                    # 清空multiselect状态
                    st.session_state[multiselect_key] = []
                    # 删除checkbox状态，让它在下次渲染时重新初始化
                    if select_all_key in st.session_state:
                        del st.session_state[select_all_key]

                # 刷新页面
                st_instance.rerun()

            st_instance.markdown("---")

        if not current_selected_industries:
            st_instance.info("没有可用的行业数据。")
        else:
            current_selection = _state.get(indicators_state_key, {})

            num_cols = 3
            cols = st_instance.columns(num_cols)
            col_idx = 0

            # 从预计算缓存获取默认映射（使用 file_uploader 返回的值）
            # dfm_default_map 来自 line 176

            for industry_name in current_selected_industries:
                # 使用预计算的有效指标缓存（DRY：不重复计算）
                indicators_for_this_industry = industry_available_indicators.get(industry_name, [])

                # 完全跳过没有可用指标的行业
                if not indicators_for_this_industry:
                    current_selection[industry_name] = []
                    col_idx += 1
                    continue

                all_indicators_for_industry = var_to_indicators_map_by_industry.get(industry_name, [])

                with cols[col_idx % num_cols]:
                    # 只有在有指标被排除且仍有可用指标时才显示提示
                    excluded_count = len(all_indicators_for_industry) - len(indicators_for_this_industry)

                    # 从状态管理器读取已选指标，或使用DFM默认选择
                    default_selection_for_industry = current_selection.get(industry_name, None)

                    # 如果状态管理器中没有选择，使用DFM变量列配置
                    if default_selection_for_industry is None:
                        dfm_default_indicators = [
                            indicator for indicator in indicators_for_this_industry
                            if normalize_text(indicator) in dfm_default_map
                        ]
                        default_selection_for_industry = dfm_default_indicators

                    # 确保默认值是实际可选列表的子集
                    valid_default = [item for item in default_selection_for_industry if item in indicators_for_this_industry]

                    # 初始化multiselect
                    multiselect_key = f"dfm_indicators_multiselect_{industry_name}"
                    if multiselect_key not in st.session_state:
                        st.session_state[multiselect_key] = valid_default

                    # 判断是否应该勾选全选checkbox（根据当前multiselect的实际值判断）
                    current_multiselect_value = st.session_state.get(multiselect_key, [])
                    should_check_select_all = (
                        len(current_multiselect_value) > 0 and
                        set(current_multiselect_value) == set(indicators_for_this_industry)
                    )

                    # 行业名称与全选checkbox同行
                    header_col1, header_col2 = st_instance.columns([3, 1])
                    with header_col1:
                        st_instance.markdown(f"**{industry_name}**")
                    with header_col2:
                        # 创建checkbox（使用计算出的状态，不使用key避免状态冲突）
                        select_all_checked = st_instance.checkbox(
                            "全选",
                            value=should_check_select_all,
                            key=f"dfm_select_all_{industry_name}"
                        )

                    if excluded_count > 0:
                        st_instance.caption(f"排除目标变量: {excluded_count}个")

                    # 同步checkbox与multiselect: 仅在checkbox状态变化时更新
                    if select_all_checked and st.session_state[multiselect_key] != indicators_for_this_industry:
                        st.session_state[multiselect_key] = indicators_for_this_industry

                    selected_in_widget = st_instance.multiselect(
                        "选择指标",
                        options=indicators_for_this_industry,
                        key=multiselect_key,
                        label_visibility="collapsed"
                    )

                    current_selection[industry_name] = selected_in_widget
                    final_selected_indicators_flat.extend(selected_in_widget)

                col_idx += 1

            industries_to_remove_from_state = [
                ind for ind in current_selection
                if ind not in current_selected_industries
            ]
            for ind_to_remove in industries_to_remove_from_state:
                del current_selection[ind_to_remove]

            _state.set(indicators_state_key, current_selection)

        # 修复：如果循环没有执行（filtered_industries为空），但状态中有数据
        # 说明是旧数据，应该从状态重建指标列表
        if len(final_selected_indicators_flat) == 0 and len(current_selected_industries) == 0:
            saved_selection = _state.get(indicators_state_key, {})
            if saved_selection:
                for industry, indicators in saved_selection.items():
                    final_selected_indicators_flat.extend(indicators)

        # 更新最终的扁平化预测指标列表 (去重)
        final_indicators = sorted(list(set(final_selected_indicators_flat)))
        _state.set('dfm_selected_indicators', final_indicators)


        # 从选择的指标自动推断实际使用的行业（只有当该行业有指标被选中时）
        inferred_industries = []
        selected_indicators_per_industry = _state.get(indicators_state_key, {})
        for industry, indicators in selected_indicators_per_industry.items():
            if indicators and len(indicators) > 0:  # 如果该行业有选中的指标
                inferred_industries.append(industry)

        _state.set('dfm_selected_industries', inferred_industries)

    # 变量选择完成

    # 显示变量选择汇总信息
    current_target_var = _state.get('dfm_target_variable', None)
    current_selected_indicators = _state.get('dfm_selected_indicators', [])
    current_selected_industries_for_display = _state.get('dfm_selected_industries', [])

    # 计算总预测变量数
    total_predictor_count = len(current_selected_indicators)

    st_instance.text(f" - 目标变量: {current_target_var if current_target_var else '未选择'}")
    st_instance.text(f" - 选定行业数: {len(current_selected_industries_for_display)}")
    st_instance.text(f" - 选定预测指标总数: {total_predictor_count}")

    # 第四行：开始训练按钮（左对齐）
    # 重新获取变量选择状态（用于训练条件检查）
    current_target_var = _state.get('dfm_target_variable', None)
    current_selected_indicators = _state.get('dfm_selected_indicators', [])

    # 日期验证 - 使用算法感知的验证函数
    training_start_value = _state.get('dfm_training_start_date')
    validation_start_value = _state.get('dfm_validation_start_date')
    observation_start_value = _state.get('dfm_observation_start_date')
    current_algorithm = _state.get('dfm_algorithm', UIConfig.DEFAULT_ALGORITHM)

    date_validation_passed = True
    if training_start_value and observation_start_value:
        # 调用算法感知的验证函数
        validation_error = validate_date_ranges(
            algorithm=current_algorithm,
            training_start=training_start_value,
            validation_start=validation_start_value,
            observation_start=observation_start_value,
            target_freq=target_freq_code
        )
        if validation_error:
            st_instance.error(f"[ERROR] {validation_error}")
            date_validation_passed = False
    else:
        st_instance.warning("[WARNING] 请设置完整的日期范围")
        date_validation_passed = False

    # 检查训练准备状态
    training_ready = (
        current_target_var is not None and
        len(current_selected_indicators) > 0 and
        date_validation_passed and
        input_df is not None
    )

    if not training_ready:
        st_instance.warning("[WARNING] 训练条件未满足，请检查上述设置")

    # 开始训练按钮
    if training_ready:
        train_btn_clicked = st_instance.button("开始训练",
                            key="dfm_start_training",
                            help="开始DFM模型训练",
                            type="primary")
    else:
        train_btn_clicked = st_instance.button("开始训练",
                         disabled=True,
                         key="dfm_start_training_disabled",
                         help="请先满足所有训练条件",
                         type="primary")

    # 训练逻辑
    if training_ready and train_btn_clicked:
        current_status = _state.get('dfm_training_status', '等待开始')
        if current_status in ['正在训练...', '准备启动训练...']:
            st_instance.warning("[WARNING] 训练已在进行中，请勿重复启动")
        else:
            try:
                # 使用TrainingConfigBuilder构建配置
                state_manager = StateManager('train_model')
                config_builder = TrainingConfigBuilder(state_manager)

                training_config = config_builder.build(
                    input_df=input_df,
                    var_industry_map=_state.get('dfm_industry_map_obj', {}),
                    var_frequency_map=_state.get('dfm_frequency_map_obj', {})
                )

                logger.info(f"训练配置: 因子选择={training_config.factor_selection_method}, "
                           f"最大迭代={training_config.max_iterations}, AR阶数={training_config.max_lags}")

                # 创建进度条组件（所有模式都显示）
                progress_container = st_instance.container()
                with progress_container:
                    progress_bar = st_instance.progress(0, text="准备训练...")
                    progress_status = st_instance.empty()

                # 创建进度回调函数
                def progress_callback(message: str):
                    """进度回调函数 - 解析消息更新进度条"""
                    # 更新训练日志（创建新列表以触发Streamlit状态变更检测）
                    training_log = _state.get('dfm_training_log', [])
                    _state.set('dfm_training_log', training_log + [message])

                    # 解析进度信息并更新进度条（支持EM和DDFM格式）
                    if progress_bar is not None:
                        # 解析格式: [EM|progress%] 或 [DDFM|progress%]
                        progress_match = re.search(r'\[(EM|DDFM)\|(\d+)%\]', message)
                        if progress_match:
                            pct = int(progress_match.group(2))
                            # 提取实际消息内容（去除前缀）
                            display_msg = re.sub(r'\[(EM|DDFM)\|\d+%\]\s*', '', message)
                            progress_bar.progress(pct, text=display_msg)
                        elif progress_status is not None:
                            # 其他消息只更新状态文本
                            progress_status.text(message)

                # 设置训练状态
                _state.set('dfm_training_status', '正在训练...')
                _state.set('dfm_training_log', ['[TRAIN_REF] 开始训练...'])

                # 根据估计方法选择训练器并训练（同步执行）
                # 执行训练（单阶段）
                trainer = DFMTrainer(training_config)
                result = trainer.train(
                    progress_callback=progress_callback,
                    enable_export=True,
                    export_dir=None
                )

                # 处理训练结果并保存
                result_summary = {
                    'algorithm': algorithm_value,  # 保存算法类型
                    'selected_variables': result.selected_variables,
                    'k_factors': result.k_factors,
                    'metrics': {
                        'is_rmse': result.metrics.is_rmse if result.metrics else None,
                        'oos_rmse': result.metrics.oos_rmse if result.metrics else None,
                        'obs_rmse': result.metrics.obs_rmse if result.metrics else None,
                        'is_win_rate': result.metrics.is_win_rate if result.metrics else None,
                        'oos_win_rate': result.metrics.oos_win_rate if result.metrics else None,
                        'obs_win_rate': result.metrics.obs_win_rate if result.metrics else None
                    },
                    'training_time': result.training_time
                }

                training_time_display = result.training_time
                selected_variables = result.selected_variables
                k_factors_display = result.k_factors
                metrics_obj = result.metrics

                # 保存到状态管理器
                _state.set('dfm_training_result', result_summary)
                _state.set('dfm_model_results_paths', result.export_files)
                _state.set('dfm_training_status', '训练完成')
                _state.set('dfm_training_completed_timestamp', time.time())

                # 添加完成日志（创建新列表以触发Streamlit状态变更检测）
                new_log_entries = [
                    f"[SUCCESS] 训练完成！总耗时: {training_time_display:.2f}秒",
                    f"[RESULT] 选中变量数: {len(selected_variables)}",
                    f"[RESULT] 因子数: {k_factors_display}"
                ]

                if metrics_obj:
                    is_ddfm = (algorithm_value == 'deep_learning')

                    # 经典DFM：显示验证期指标（用于变量选择）
                    if not is_ddfm:
                        oos_rmse = metrics_obj.oos_rmse
                        oos_win_rate = metrics_obj.oos_win_rate
                        if oos_rmse is not None and not (np.isnan(oos_rmse) or np.isinf(oos_rmse)):
                            new_log_entries.append(f"[METRICS] 验证期RMSE: {oos_rmse:.4f}")
                        if oos_win_rate is not None and not (np.isnan(oos_win_rate) or np.isinf(oos_win_rate)):
                            new_log_entries.append(f"[METRICS] 验证期Win Rate: {oos_win_rate:.2f}%")

                    # 观察期指标（两种模型都显示）
                    obs_rmse = metrics_obj.obs_rmse
                    obs_win_rate = metrics_obj.obs_win_rate
                    if obs_rmse is not None and not (np.isnan(obs_rmse) or np.isinf(obs_rmse)):
                        new_log_entries.append(f"[METRICS] 观察期RMSE: {obs_rmse:.4f}")
                    else:
                        new_log_entries.append(f"[METRICS] 观察期RMSE: N/A")

                    if obs_win_rate is not None and not (np.isnan(obs_win_rate) or np.isinf(obs_win_rate)):
                        new_log_entries.append(f"[METRICS] 观察期Win Rate: {obs_win_rate:.2f}%")
                    else:
                        new_log_entries.append(f"[METRICS] 观察期Win Rate: N/A (数据不足)")

                training_log = _state.get('dfm_training_log', [])
                _state.set('dfm_training_log', training_log + new_log_entries)

                st_instance.success("[SUCCESS] 训练完成！")

            except Exception as e:
                import traceback
                error_msg = f"启动训练失败: {str(e)}\n{traceback.format_exc()}"
                logger.error(error_msg)
                _state.set('dfm_training_status', f'训练失败: {str(e)}')
                _state.set('dfm_training_error', error_msg)
                st_instance.error(f"[ERROR] {error_msg}")

    st_instance.markdown("---")

    # 训练日志
    st_instance.markdown("**训练日志**")

    training_log = _state.get('dfm_training_log', [])
    current_training_status = _state.get('dfm_training_status', '等待开始')

    if current_training_status == '正在训练...':
        if training_log:
            log_text = "\n".join(training_log[-20:])
            st_instance.text_area(
                "训练日志",
                value=log_text,
                height=300,
                key="dfm_training_log_display",
                help="显示最近20条训练日志",
                label_visibility="hidden"
            )
            st_instance.info("[LOADING] 训练正在进行中，日志实时更新...")
        else:
            st_instance.info("[LOADING] 训练正在启动，请稍候...")
    elif training_log:
        log_text = "\n".join(training_log[-20:])
        st_instance.text_area(
            "训练日志",
            value=log_text,
            height=300,
            key="dfm_training_log_display",
            help="显示最近20条训练日志",
            label_visibility="hidden"
        )
    else:
        st_instance.info("[NONE] 无日志")

    # 文件下载按钮
    training_status = _state.get('dfm_training_status') or '等待开始'
    training_results = _state.get('dfm_model_results_paths')

    from dashboard.core.ui.utils.debug_helpers import debug_log
    debug_log(f"UI状态检查 - 当前训练状态: {training_status}", "DEBUG")
    debug_log(f"UI状态检查 - 结果文件数量: {len(training_results) if training_results else 0}", "DEBUG")

    if training_status == '训练完成':
        if training_results:
            if isinstance(training_results, dict) and training_results:
                target_files = ['final_model_joblib', 'metadata', 'training_summary']
                available_files = []

                for file_key in target_files:
                    file_path = training_results.get(file_key)
                    if file_path and os.path.exists(file_path):
                        file_name = os.path.basename(file_path)
                        available_files.append((file_key, file_path, file_name))

                if available_files:
                    # 创建ZIP压缩包
                    import zipfile
                    import io
                    from datetime import datetime

                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file_key, file_path, file_name in available_files:
                            zip_file.write(file_path, file_name)

                    zip_buffer.seek(0)
                    zip_data = zip_buffer.getvalue()

                    # 生成压缩包文件名（包含时间戳）
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    zip_filename = f"dfm_model_{timestamp}.zip"

                    # 单一下载按钮
                    st_instance.download_button(
                        label="文件下载",
                        data=zip_data,
                        file_name=zip_filename,
                        mime="application/zip",
                        key="dfm_download_zip",
                        type="primary"
                    )
                else:
                    st_instance.warning("[WARNING] 未找到可用的结果文件")
            else:
                st_instance.warning("[WARNING] 训练完成但未找到结果文件")

    elif training_status.startswith('训练失败'):
        training_error = _state.get('dfm_training_error')
        st_instance.error(f"[ERROR] {training_status}")
        if training_error:
            st_instance.error(f"错误详情: {training_error}")


def _get_file_size(file_path: str) -> str:
    """获取文件大小的可读格式"""
    try:
        size_bytes = os.path.getsize(file_path)
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    except Exception as e:
        logger.warning(f"获取文件大小失败: {e}")
        return "未知大小"
