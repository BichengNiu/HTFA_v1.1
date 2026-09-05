# -*- coding: utf-8 -*-
"""
DFM模型训练页面组件

提供DFM模型训练的完整UI界面，包括数据上传、参数配置、变量选择和训练执行
经典DFM模型：所有变量平等参与因子提取，无目标变量概念
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import re
import time
from collections import defaultdict

import logging

# 导入文本标准化工具（从共享工具库）
from dashboard.models.DFM.utils.text_utils import normalize_text

# 导入新增工具和组件
from htfa.app.state.session_state import NamespacedStateManager
from htfa.workspace import SessionWorkspace
from dashboard.models.DFM.train.ui.components.file_uploader_component import FileUploaderComponent
from dashboard.models.DFM.train.config.ui_config import UIConfig
from dashboard.models.DFM.train.ui.utils.config_builder import TrainingConfigBuilder
from dashboard.models.DFM.train.ui.utils.date_helpers import (
    get_previous_period_date,
    get_frequency_label,
    validate_date_ranges,
)
# 配置日志记录器
logger = logging.getLogger(__name__)

# 导入调试日志工具
from htfa.ui_shared.debug_helpers import debug_log

# 创建全局状态管理器实例
_state = NamespacedStateManager('train_model')

# 导入DFM训练脚本
from dashboard.models.DFM.train.training.trainer import DFMTrainer


def _reset_training_state():
    """重置所有训练相关状态"""

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


def _initialize_training_state(st_instance):

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

    debug_log(f"UI状态检查 - 当前训练状态: {training_status}", "DEBUG")


def _load_training_inputs(st_instance):
    # 使用组件化的文件上传器
    state_manager = NamespacedStateManager('train_model')
    file_uploader = FileUploaderComponent(state_manager)
    input_df, var_industry_map, dfm_default_map, _, _ = file_uploader.render(st_instance)

    # 如果文件验证失败，提前返回
    if input_df is None or not var_industry_map:
        return None

    # 直接使用文件上传器加载的映射数据（已由FileUploaderComponent处理）
    # 完全解耦，不从其他模块的session_state读取数据
    # 经典DFM：所有变量平等参与因子提取，无目标变量概念

    # 构建行业到指标的映射
    industry_to_indicators_temp = defaultdict(list)
    if var_industry_map:
        for indicator, industry in var_industry_map.items():
            if indicator and industry:
                industry_to_indicators_temp[str(industry).strip()].append(str(indicator).strip())

    unique_industries = sorted(industry_to_indicators_temp.keys())
    var_to_indicators_map_by_industry = {k: sorted(v) for k, v in industry_to_indicators_temp.items()}

    # ===== 计算日期默认值的辅助函数 =====
    def get_data_based_date_defaults():
        """基于实际数据计算日期默认值，优先使用数据准备页面设置的日期边界"""
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

    return (
        input_df,
        dfm_default_map,
        unique_industries,
        var_to_indicators_map_by_industry,
        data_df,
        date_defaults,
    )


def _render_algorithm_settings(st_instance, data_df):
    # ===== 训练设置 =====
    st_instance.subheader("训练设置")

    # 获取当前算法值（用于判断是否显示变量筛选和因子选择）
    current_algorithm = _state.get('dfm_algorithm', UIConfig.DEFAULT_ALGORITHM)
    if current_algorithm not in UIConfig.ALGORITHM_OPTIONS:
        raise ValueError(f"无效的算法类型: {current_algorithm}，有效值: {list(UIConfig.ALGORITHM_OPTIONS.keys())}")

    # 初始化前一次算法值（用于检测变化）
    if _state.get('_prev_dfm_algorithm') is None:
        _state.set('_prev_dfm_algorithm', current_algorithm)

    # 根据算法类型动态调整布局
    # 统一使用3列布局：选择算法 | 目标变量 | RMSE计算方式
    algo_col1, algo_col2, algo_col3 = st_instance.columns(3)

    with algo_col1:
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

    # 变量筛选方法：固定使用后向选择法（不显示UI）
    _state.set('dfm_variable_selection_method', 'backward')
    _state.set('dfm_enable_variable_selection', True)

    # 目标变量（经典DFM和DDFM都显示）
    with algo_col2:
        selected_indicators = _state.get('dfm_selected_indicators', [])
        # 修复：首次进入页面时，从已准备的数据中初始化指标列表
        if not selected_indicators and data_df is not None and len(data_df.columns) > 0:
            selected_indicators = list(data_df.columns)
            _state.set('dfm_selected_indicators', selected_indicators)

        # 目标变量配置（用于后向剔除保护和RMSE计算）
        state_key_target = 'dfm_target_variable'
        help_text = UIConfig.TARGET_VARIABLE_HELP

        if selected_indicators:
            target_var_options = list(selected_indicators)
            current_target = _state.get(state_key_target)
            if current_target and current_target in selected_indicators:
                default_index = target_var_options.index(current_target)
            else:
                default_index = 0

            target_var_value = st_instance.selectbox(
                "目标变量",
                options=target_var_options,
                index=default_index,
                key='dfm_target_variable_input',
                help=help_text
            )
            _state.set(state_key_target, target_var_value)
        else:
            st_instance.selectbox(
                "目标变量",
                options=['请先选择指标'],
                key='dfm_target_variable_input',
                disabled=True,
                help=help_text
            )
            _state.set(state_key_target, None)

    # 检测算法变化，触发rerun以更新UI布局
    if algorithm_value != _state.get('_prev_dfm_algorithm'):
        _state.set('_prev_dfm_algorithm', algorithm_value)
        st_instance.rerun()

    # 误差计算方式（第一排第三列）
    with algo_col3:
        current_rmse_alignment = _state.get('dfm_rmse_alignment', UIConfig.DEFAULT_RMSE_ALIGNMENT)
        if current_rmse_alignment not in UIConfig.RMSE_ALIGNMENT_OPTIONS:
            current_rmse_alignment = UIConfig.DEFAULT_RMSE_ALIGNMENT

        rmse_alignment_value = st_instance.selectbox(
            "误差计算方式",
            options=list(UIConfig.RMSE_ALIGNMENT_OPTIONS.keys()),
            format_func=lambda x: UIConfig.RMSE_ALIGNMENT_OPTIONS[x],
            index=UIConfig.get_safe_option_index(
                UIConfig.RMSE_ALIGNMENT_OPTIONS, current_rmse_alignment, UIConfig.DEFAULT_RMSE_ALIGNMENT
            ),
            key='dfm_rmse_alignment_input',
            help=UIConfig.RMSE_ALIGNMENT_HELP
        )
        _state.set('dfm_rmse_alignment', rmse_alignment_value)

    return algorithm_value


def _render_period_settings(
    st_instance, data_df, date_defaults, algorithm_value
):
    # ===== 训练周期设置 =====

    # 经典DFM：使用默认周频率
    target_freq_code = 'W'
    freq_label = get_frequency_label(target_freq_code)

    # 判断是否为DDFM模式
    is_ddfm_mode = (algorithm_value == 'deep_learning')

    # 根据算法类型动态调整布局
    # DDFM：2列（训练期开始、观察期开始）
    # 经典DFM：3列（训练期开始、验证期开始、观察期开始）
    if is_ddfm_mode:
        col_time1, col_time2 = st_instance.columns(2)
    else:
        col_time1, col_time2, col_time3 = st_instance.columns(3)

    with col_time1:
        training_start_value = st_instance.date_input(
            "训练期开始",
            value=_state.get('dfm_training_start_date', date_defaults['training_start']),
            key='dfm_training_start_date_input',
            help="模型训练数据的起始日期，默认为数据开始日期"
        )
        _state.set('dfm_training_start_date', training_start_value)

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
            # DDFM：观察期结束为数据最后日期（不显示UI）
            if data_df is not None and isinstance(data_df.index, pd.DatetimeIndex):
                observation_end_value = data_df.index.max().date()
                _state.set('dfm_validation_end_date', observation_end_value)
        else:
            # 经典DFM模式：显示验证期开始
            validation_start_value = st_instance.date_input(
                "验证期开始",
                value=_state.get('dfm_validation_start_date', date_defaults['validation_start']),
                key='dfm_validation_start_date_input',
                help="验证期开始日期，训练期将在此日期前一天结束"
            )
            _state.set('dfm_validation_start_date', validation_start_value)

    if not is_ddfm_mode:
        with col_time3:
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

    return target_freq_code


def _render_advanced_options(st_instance, algorithm_value):
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

            # 第四行：激活函数
            ddfm_col7, _ = st_instance.columns(2)

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
            st_instance.markdown("**因子策略**")

            # 三列布局：因子选择策略 | 策略参数 | 因子自回归阶数
            factor_col1, factor_col2, factor_col3 = st_instance.columns(3)

            # 第一列：因子选择策略
            with factor_col1:
                current_strategy = _state.get('dfm_factor_selection_strategy', UIConfig.DEFAULT_FACTOR_STRATEGY)
                if current_strategy not in UIConfig.FACTOR_STRATEGIES:
                    current_strategy = UIConfig.DEFAULT_FACTOR_STRATEGY

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

            # 第二列：根据策略条件显示参数
            with factor_col2:
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

            # 第三列：因子自回归阶数
            with factor_col3:
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


def _render_variable_selection(
    st_instance,
    unique_industries,
    var_to_indicators_map_by_industry,
    dfm_default_map,
):
    # ===== 变量选择 =====
    st_instance.markdown("--- ")

    # 添加变量选择大标题
    st_instance.subheader("变量选择")

    # 经典DFM：所有变量平等参与因子提取，无目标变量概念
    # 直接进入预测变量选择

    # 根据映射文件选择预测变量默认配置
    # dfm_default_map 已从 file_uploader.render() 加载。

    # 过滤行业（不再需要排除目标变量）
    filtered_industries = unique_industries

    # 预计算各行业有效指标
    var_industry_map = _state.get('dfm_industry_map_obj')
    if not var_industry_map:
        raise ValueError("行业映射数据未加载，请先上传并加载指标字典文件")

    # 构建行业→有效指标映射缓存
    industry_available_indicators = {}
    for industry in filtered_industries:
        all_indicators = var_to_indicators_map_by_industry.get(industry, [])
        if all_indicators:
            industry_available_indicators[industry] = all_indicators

    # 暂时存储过滤后的行业，以供后续步骤中使用
    if not filtered_industries:
        st_instance.info("没有可用的行业数据。")
        _state.set('dfm_selected_industries', [])

    # 根据选定行业选择预测指标 (每个行业一个多选下拉菜单，默认全选)
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
            for industry_name in current_selected_industries:
                # 使用预计算的有效指标缓存（DRY：不重复计算）
                indicators_for_this_industry = industry_available_indicators.get(industry_name, [])

                # 完全跳过没有可用指标的行业
                if not indicators_for_this_industry:
                    current_selection[industry_name] = []
                    col_idx += 1
                    continue

                with cols[col_idx % num_cols]:
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
        final_indicators = sorted(set(final_selected_indicators_flat))
        _state.set('dfm_selected_indicators', final_indicators)


        # 从选择的指标自动推断实际使用的行业（只有当该行业有指标被选中时）
        inferred_industries = []
        selected_indicators_per_industry = _state.get(indicators_state_key, {})
        for industry, indicators in selected_indicators_per_industry.items():
            if indicators and len(indicators) > 0:  # 如果该行业有选中的指标
                inferred_industries.append(industry)

        _state.set('dfm_selected_industries', inferred_industries)


def _render_training_controls(
    st_instance, input_df, target_freq_code, algorithm_value
):

    # 显示变量选择汇总信息
    current_selected_indicators = _state.get('dfm_selected_indicators', [])
    current_selected_industries_for_display = _state.get('dfm_selected_industries', [])

    # 计算总变量数
    total_variable_count = len(current_selected_indicators)

    st_instance.text(f" - 选定行业数: {len(current_selected_industries_for_display)}")
    st_instance.text(f" - 选定变量总数: {total_variable_count}")

    # 第四行：开始训练按钮（左对齐）
    # 重新获取变量选择状态（用于训练条件检查）
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

    # 检查训练准备状态（必须选择目标变量）
    target_var = _state.get('dfm_target_variable')

    training_ready = (
        len(current_selected_indicators) > 0 and
        date_validation_passed and
        input_df is not None and
        target_var is not None  # 必须选择目标变量
    )

    if not training_ready:
        st_instance.warning("[WARNING] 训练条件未满足，请检查上述设置")

    # 开始训练按钮和下载按钮（并排，CSS强制紧凑布局）
    st_instance.markdown("""
    <style>
    .stMainBlockContainer [data-testid="stHorizontalBlock"]:has([data-testid="stBaseButton-primary"]) {
        gap: 1rem !important;
        flex-wrap: nowrap !important;
    }
    .stMainBlockContainer [data-testid="stHorizontalBlock"]:has([data-testid="stBaseButton-primary"]) > [data-testid="stColumn"] {
        width: fit-content !important;
        flex: 0 0 auto !important;
        min-width: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    btn_col1, btn_col2 = st_instance.columns(2)

    with btn_col1:
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

    with btn_col2:
        # 文件下载按钮（仅训练完成后显示）
        training_status_for_download = _state.get('dfm_training_status') or '等待开始'
        training_results_for_download = _state.get('dfm_model_results_paths')

        if training_status_for_download == '训练完成' and training_results_for_download:
            if isinstance(training_results_for_download, dict) and training_results_for_download:
                target_files = ['final_model_joblib', 'metadata', 'training_summary']
                available_files = []

                for file_key in target_files:
                    file_path = training_results_for_download.get(file_key)
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

                    st_instance.download_button(
                        label="文件下载",
                        data=zip_data,
                        file_name=zip_filename,
                        mime="application/zip",
                        key="dfm_download_zip",
                        type="primary"
                    )

    # 训练逻辑
    if training_ready and train_btn_clicked:
        current_status = _state.get('dfm_training_status', '等待开始')
        if current_status in ['正在训练...', '准备启动训练...']:
            st_instance.warning("[WARNING] 训练已在进行中，请勿重复启动")
        else:
            try:
                # 使用TrainingConfigBuilder构建配置
                state_manager = NamespacedStateManager('train_model')
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

                # 清除 text_area 的缓存，确保新日志能正确显示
                if 'dfm_training_log_display' in st.session_state:
                    del st.session_state['dfm_training_log_display']

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
                        'target_rmse': result.metrics.target_rmse if result.metrics else None,
                        'target_rmse_validation': result.metrics.target_rmse_validation if result.metrics else None,
                        'weighted_target_rmse': result.metrics.weighted_target_rmse if result.metrics else None,
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
                    # 显示目标变量RMSE（监督学习模式）
                    target_rmse = metrics_obj.target_rmse
                    if target_rmse is not None and not (np.isnan(target_rmse) or np.isinf(target_rmse)):
                        new_log_entries.append(f"[METRICS] 训练期目标变量RMSE: {target_rmse:.4f}")
                    # 仅经典DFM显示验证期RMSE（DDFM没有验证期）
                    if algorithm_value != 'deep_learning':
                        target_rmse_val = metrics_obj.target_rmse_validation
                        if target_rmse_val is not None and not (np.isnan(target_rmse_val) or np.isinf(target_rmse_val)):
                            new_log_entries.append(f"[METRICS] 验证期目标变量RMSE: {target_rmse_val:.4f}")
                    weighted_target_rmse = metrics_obj.weighted_target_rmse
                    if weighted_target_rmse is not None and not (np.isnan(weighted_target_rmse) or np.isinf(weighted_target_rmse)):
                        new_log_entries.append(f"[METRICS] 加权目标变量RMSE: {weighted_target_rmse:.4f}")

                training_log = _state.get('dfm_training_log', [])
                _state.set('dfm_training_log', training_log + new_log_entries)

                st_instance.success("[SUCCESS] 训练完成！")
                st.rerun()  # 强制重新渲染页面，使下载按钮立即显示

            except Exception as e:
                import traceback
                error_msg = f"启动训练失败: {str(e)}\n{traceback.format_exc()}"
                logger.error(error_msg)
                _state.set('dfm_training_status', f'训练失败: {str(e)}')
                _state.set('dfm_training_error', error_msg)
                st_instance.error(f"[ERROR] {error_msg}")


def _render_dfm_model_training_page_content(st_instance):
    _initialize_training_state(st_instance)
    training_inputs = _load_training_inputs(st_instance)
    if training_inputs is None:
        return

    (
        input_df,
        dfm_default_map,
        unique_industries,
        var_to_indicators_map_by_industry,
        data_df,
        date_defaults,
    ) = training_inputs

    algorithm_value = _render_algorithm_settings(st_instance, data_df)
    target_freq_code = _render_period_settings(
        st_instance, data_df, date_defaults, algorithm_value
    )
    _render_advanced_options(st_instance, algorithm_value)
    _render_variable_selection(
        st_instance,
        unique_industries,
        var_to_indicators_map_by_industry,
        dfm_default_map,
    )
    _render_training_controls(
        st_instance, input_df, target_freq_code, algorithm_value
    )


def render_dfm_model_training_page(st_instance):
    """渲染 DFM 训练页，并在切换模块前保存训练配置。"""
    workspace = SessionWorkspace(st_instance.session_state)
    workspace.begin_page(
        "model_analysis.dfm.train",
        keys=(
            "dfm_training_start_date_input",
            "dfm_validation_start_date_input",
            "dfm_validation_end_date_input",
            "dfm_observation_start_date_input",
            "dfm_variable_selection_method_input",
            "dfm_target_alignment_mode_input",
            "dfm_factor_selection_strategy",
            "dfm_fixed_number_of_factors",
            "dfm_cumulative_variance_threshold_input",
            "dfm_kaiser_threshold_input",
            "dfm_factor_ar_order_input",
        ),
        prefixes=("dfm_indicators_multiselect_", "dfm_select_all_"),
    )
    try:
        return _render_dfm_model_training_page_content(st_instance)
    finally:
        workspace.end_page("model_analysis.dfm.train")
