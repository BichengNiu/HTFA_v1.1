# -*- coding: utf-8 -*-
"""
训练配置构建器 - 从UI层分离业务逻辑

将TrainingConfig构建逻辑从UI代码中提取，实现：
1. 职责分离：UI负责展示，Builder负责配置构建
2. 可测试性：业务逻辑可独立单元测试
3. 可复用性：配置构建逻辑可在其他地方复用
"""

import pandas as pd
import unicodedata
import tempfile
from datetime import timedelta
from typing import Dict, List, Optional, Any

from dashboard.models.DFM.train import TrainingConfig
from dashboard.models.DFM.train.ui.utils.date_helpers import (
    get_target_frequency,
    get_previous_period_date,
    freq_code_to_pandas_freq,
    validate_date_ranges,
)


class TrainingConfigBuilder:
    """训练配置构建器"""

    def __init__(self, state_manager):
        """
        初始化配置构建器

        Args:
            state_manager: 状态管理器实例
        """
        self.state = state_manager

    def _get_required(self, key: str) -> Any:
        """
        获取必需的状态值，如果不存在则抛出错误

        Args:
            key: 状态键名

        Returns:
            状态值

        Raises:
            ValueError: 如果键不存在
        """
        value = self.state.get(key)
        if value is None:
            raise ValueError(
                f"必需的UI参数 '{key}' 未设置。"
                f"这表明UI控件未正常初始化，请检查model_training_page.py中的控件定义。"
            )
        return value

    def build(
        self,
        input_df: pd.DataFrame,
        var_industry_map: Dict[str, str],
        var_frequency_map: Optional[Dict[str, str]] = None
    ) -> TrainingConfig:
        """
        构建TrainingConfig对象

        Args:
            input_df: 输入数据DataFrame
            var_industry_map: 变量到行业的映射
            var_frequency_map: 变量到频率的映射（可选）

        Returns:
            TrainingConfig对象

        Raises:
            ValueError: 配置验证失败
        """
        # 1. 获取核心配置
        target_variable = self._get_required('dfm_target_variable')
        current_selected_indicators = self._get_required('dfm_selected_indicators')

        # 验证非空
        if not current_selected_indicators:
            raise ValueError("预测指标列表不能为空")

        # 2. 获取日期配置
        training_start_value = self.state.get('dfm_training_start_date')
        validation_start_value = self.state.get('dfm_validation_start_date')
        validation_end_value = self.state.get('dfm_validation_end_date')
        observation_start_value = self.state.get('dfm_observation_start_date')

        if not all([training_start_value, validation_start_value, validation_end_value, observation_start_value]):
            raise ValueError("日期配置不完整")

        # 获取算法类型（需要提前获取以计算train_end_date）
        algorithm = self._get_required('dfm_algorithm')

        # 获取目标变量的频率
        target_freq_code = get_target_frequency(
            target_variable,
            var_frequency_map or {},
            default_freq='W'
        )

        # 根据算法类型和数据频率计算train_end_date
        if algorithm == 'deep_learning':
            # DDFM模式：训练期延伸到观察期开始前一期
            prev_period = get_previous_period_date(observation_start_value, target_freq_code, periods=1)
            train_end_date = prev_period - timedelta(days=1)
        else:
            # 经典DFM模式：训练期结束于验证期开始前一天
            train_end_date = validation_start_value - timedelta(days=1)

        # 日期范围验证（使用date_helpers中的统一验证函数）
        validation_error = validate_date_ranges(
            algorithm=algorithm,
            training_start=training_start_value,
            validation_start=validation_start_value,
            observation_start=observation_start_value,
            target_freq=target_freq_code
        )
        if validation_error:
            raise ValueError(validation_error)

        # 3. 修正变量名（大小写匹配）
        corrected_indicators = self._correct_variable_names(input_df, current_selected_indicators)

        # 4. 获取变量选择配置
        var_selection_method = self._get_required('dfm_variable_selection_method')
        enable_var_selection = (var_selection_method != 'none')
        mapped_var_selection_method = self._map_variable_selection_method(var_selection_method)

        # 5. 获取因子选择配置
        factor_selection_method, factor_params = self._get_factor_selection_params()

        # 6. 获取目标变量配对模式（2025-12新增）
        target_alignment_mode = self._get_required('dfm_target_alignment_mode')

        # 7. 获取筛选策略配置（2025-12-20新增）
        selection_criterion = 'hybrid'
        prioritize_win_rate = True
        training_weight = 0.5

        if enable_var_selection:
            selection_criterion = self._get_required('dfm_selection_criterion')
            training_weight_pct = self._get_required('dfm_training_weight')
            training_weight = training_weight_pct / 100.0  # 转换为0-1范围

            # 转换为后端参数
            if selection_criterion == 'hybrid':
                hybrid_priority = self._get_required('dfm_hybrid_priority')
                prioritize_win_rate = (hybrid_priority == 'win_rate_first')
            else:
                prioritize_win_rate = None  # 纯策略不需要此参数

        # 7.8 algorithm已在步骤2中获取（用于计算train_end_date）

        # 7.9 获取DDFM专用参数（仅当algorithm='deep_learning'时）
        ddfm_params = {}
        if algorithm == 'deep_learning':
            ddfm_params = self._get_ddfm_params()

        # 8. 保存DataFrame到临时文件
        temp_data_path = self._save_dataframe_to_temp(input_df)

        # 9. 构建TrainingConfig（基础配置）
        config_kwargs = {
            # 核心配置
            'data_path': temp_data_path,
            'target_variable': target_variable,
            'selected_indicators': corrected_indicators,

            # 训练/验证期配置
            'training_start': training_start_value.strftime('%Y-%m-%d'),
            'train_end': train_end_date.strftime('%Y-%m-%d'),
            'validation_start': validation_start_value.strftime('%Y-%m-%d'),
            'validation_end': validation_end_value.strftime('%Y-%m-%d'),
            'target_freq': freq_code_to_pandas_freq(target_freq_code),

            # 模型参数
            'k_factors': factor_params.get('k_factors', 4),
            'max_lags': self._get_required('dfm_factor_ar_order') if algorithm != 'deep_learning' else self.state.get('dfm_ddfm_factor_order', 1),
            'max_iterations': self.state.get('dfm_max_iterations', 30) if algorithm != 'deep_learning' else 30,
            'tolerance': 1e-6,

            # 变量选择配置
            'enable_variable_selection': enable_var_selection,
            'variable_selection_method': mapped_var_selection_method,
            'min_variables_after_selection': self._get_required('dfm_min_variables_after_selection') if enable_var_selection else None,

            # 因子数选择配置
            'factor_selection_method': factor_selection_method,
            'pca_threshold': factor_params.get('pca_threshold'),
            'kaiser_threshold': factor_params.get('kaiser_threshold'),

            # 并行计算配置
            'enable_parallel': True,
            'n_jobs': -1,
            'parallel_backend': 'loky',
            'min_variables_for_parallel': 5,

            # 目标变量配对模式（2025-12新增）
            'target_alignment_mode': target_alignment_mode,

            # 筛选策略配置（2025-12-20新增）
            'selection_criterion': selection_criterion,
            'prioritize_win_rate': prioritize_win_rate,

            # 训练期权重配置（2025-12-20新增）
            'training_weight': training_weight,

            # 容忍度配置（2026-01新增）
            'rmse_tolerance_percent': self._get_required('dfm_rmse_tolerance') if enable_var_selection else 1.0,
            'win_rate_tolerance_percent': self._get_required('dfm_win_rate_tolerance') if enable_var_selection else 5.0,

            # 算法选择（2025-12-21新增）
            'algorithm': algorithm,

            # 行业映射（用于R²分析）
            'industry_map': var_industry_map,
        }

        # 添加DDFM专用参数
        if algorithm == 'deep_learning':
            config_kwargs.update(ddfm_params)
            # DDFM不支持变量选择
            config_kwargs['enable_variable_selection'] = False
            config_kwargs['variable_selection_method'] = 'none'
            # DDFM观察期配置
            config_kwargs['observation_start'] = observation_start_value.strftime('%Y-%m-%d')
            config_kwargs['observation_end'] = validation_end_value.strftime('%Y-%m-%d')

        training_config = TrainingConfig(**config_kwargs)

        return training_config

    def _correct_variable_names(
        self,
        input_df: pd.DataFrame,
        selected_indicators: List[str]
    ) -> List[str]:
        """
        修正变量名（支持大小写不敏感匹配）

        Args:
            input_df: 输入DataFrame
            selected_indicators: 选择的指标列表

        Returns:
            修正后的指标列表
        """
        csv_columns = set(input_df.columns)

        # 构建不区分大小写的列名映射
        column_mapping = {}
        for col in csv_columns:
            normalized_col = unicodedata.normalize('NFKC', str(col)).strip().lower()
            column_mapping[normalized_col] = col

        # 检查并修正变量名
        corrected_indicators = []
        case_mismatches = []

        for var in selected_indicators:
            if var in csv_columns:
                corrected_indicators.append(var)
            else:
                # 尝试不区分大小写匹配
                normalized_var = unicodedata.normalize('NFKC', str(var)).strip().lower()
                if normalized_var in column_mapping:
                    actual_col = column_mapping[normalized_var]
                    corrected_indicators.append(actual_col)
                    case_mismatches.append((var, actual_col))

        if case_mismatches:
            print(f"[INFO] 检测到{len(case_mismatches)}个变量名大小写不匹配，已自动修正:")
            for original, corrected in case_mismatches:
                print(f"  '{original}' -> '{corrected}'")

        if len(corrected_indicators) < len(selected_indicators):
            missing_count = len(selected_indicators) - len(corrected_indicators)
            print(f"[WARNING] {missing_count}个变量在DataFrame中找不到")
        else:
            print(f"[INFO] 所有选择的变量({len(selected_indicators)}个)都已找到")

        return corrected_indicators

    def _map_variable_selection_method(self, var_selection_method: str) -> str:
        """
        映射UI的变量选择方法到train模块的方法名

        Args:
            var_selection_method: UI方法名

        Returns:
            train模块方法名

        Raises:
            ValueError: 无效的变量选择方法
        """
        var_selection_method_map = {
            'none': 'none',
            'backward': 'backward',
            'forward': 'forward',
            'stepwise': 'stepwise'
        }
        if var_selection_method not in var_selection_method_map:
            raise ValueError(f"无效的变量选择方法: {var_selection_method}，有效值: {list(var_selection_method_map.keys())}")
        return var_selection_method_map[var_selection_method]

    def _get_factor_selection_params(self):
        """
        获取因子选择参数（扁平化）

        Returns:
            (factor_selection_method, factor_params): 方法名和参数字典

        Raises:
            ValueError: 配置参数缺失
        """
        factor_strategy = self.state.get('dfm_factor_selection_strategy')

        if factor_strategy is None:
            raise ValueError("因子选择策略未设置")

        if factor_strategy == 'fixed_number':
            k_factors = self.state.get('dfm_fixed_number_of_factors')
            if k_factors is None:
                raise ValueError("固定因子数未设置")
            print(f"[INFO] 使用固定因子数策略: k={k_factors}")
            return 'fixed', {'k_factors': k_factors}

        elif factor_strategy == 'cumulative_variance':
            pca_threshold = self.state.get('dfm_cumulative_variance_threshold')
            if pca_threshold is None:
                raise ValueError("累积方差阈值未设置")
            print(f"[INFO] 使用累积方差策略: 阈值={pca_threshold}")
            return 'cumulative', {'pca_threshold': pca_threshold}

        elif factor_strategy == 'kaiser':
            kaiser_threshold = self.state.get('dfm_kaiser_threshold')
            if kaiser_threshold is None:
                raise ValueError("Kaiser阈值未设置")
            print(f"[INFO] 使用Kaiser准则: 阈值={kaiser_threshold}")
            return 'kaiser', {'kaiser_threshold': kaiser_threshold}

        else:
            raise ValueError(f"未知的因子选择策略: {factor_strategy}")

    def _save_dataframe_to_temp(self, input_df: pd.DataFrame) -> str:
        """
        保存DataFrame到临时文件

        Args:
            input_df: 输入DataFrame

        Returns:
            临时文件路径
        """
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.csv',
            delete=False,
            encoding='utf-8'
        )
        temp_data_path = temp_file.name
        temp_file.close()
        input_df.to_csv(temp_data_path)
        print(f"[INFO] 临时数据文件: {temp_data_path}")
        return temp_data_path

    def _get_ddfm_params(self) -> Dict[str, Any]:
        """
        获取DDFM专用参数

        Returns:
            DDFM参数字典
        """
        # 解析编码器结构字符串
        encoder_structure_str = self._get_required('dfm_encoder_structure')
        encoder_structure = self._parse_encoder_structure(encoder_structure_str)

        return {
            # 自编码器结构
            'encoder_structure': encoder_structure,
            'decoder_structure': None,  # 使用默认对称结构
            'use_bias': True,
            'batch_norm': True,  # 默认使用批量归一化
            'activation': self._get_required('dfm_ddfm_activation'),

            # 因子动态
            'factor_order': self._get_required('dfm_ddfm_factor_order'),
            'lags_input': self._get_required('dfm_ddfm_lags_input'),

            # 训练参数
            'learning_rate': self._get_required('dfm_ddfm_learning_rate'),
            'ddfm_optimizer': self._get_required('dfm_ddfm_optimizer'),
            'decay_learning_rate': True,
            'epochs_per_mcmc': self._get_required('dfm_ddfm_epochs'),
            'batch_size': self._get_required('dfm_ddfm_batch_size'),
            'mcmc_max_iter': self._get_required('dfm_ddfm_max_iter'),
            'mcmc_tolerance': self._get_required('dfm_ddfm_tolerance'),
            'display_interval': 10,
            'ddfm_seed': 3,
        }

    def _parse_encoder_structure(self, structure_str: str) -> tuple:
        """
        解析编码器结构字符串

        Args:
            structure_str: 如 "16, 4" 或 "32, 16, 8"

        Returns:
            整数元组，如 (16, 4)
        """
        try:
            parts = [int(x.strip()) for x in structure_str.split(',')]
            if not parts:
                raise ValueError("编码器结构不能为空")
            if any(p <= 0 for p in parts):
                raise ValueError("编码器结构中所有值必须为正整数")
            return tuple(parts)
        except ValueError as e:
            raise ValueError(f"无效的编码器结构 '{structure_str}': {e}")
