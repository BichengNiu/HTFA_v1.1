# -*- coding: utf-8 -*-
"""
DFM训练器 - 简化版（真正的轻量级协调器）

仅负责协调训练流程，直接调用底层函数，避免不必要的包装
经典DFM：所有变量平等参与因子提取，无目标变量概念
"""

import time
import numpy as np
import pandas as pd
from typing import Optional, Callable
from dashboard.models.DFM.train.utils.logger import get_logger

# 导入数据模型
from dashboard.models.DFM.train.core.models import TrainingResult

# 导入统一训练和评估函数
from dashboard.models.DFM.train.training.model_ops import (
    train_dfm_model,
    train_ddfm_model,
    evaluate_model_fit
)

# 导入流程步骤
from dashboard.models.DFM.train.utils.data_utils import load_and_validate_data
from dashboard.models.DFM.train.training.evaluator_strategy import create_variable_selection_evaluator
from dashboard.models.DFM.train.export.exporter import TrainingResultExporter

# 导入核心功能
from dashboard.models.DFM.train.selection.backward_selector import BackwardSelector
from dashboard.models.DFM.train.core.pca_utils import select_num_factors

# 导入格式化工具
from dashboard.models.DFM.train.utils.formatting import print_training_summary, format_training_config

# 导入环境配置
from dashboard.models.DFM.train.utils.environment import setup_training_environment

logger = get_logger(__name__)


class DFMTrainer:
    """
    DFM主训练器（轻量级协调器）

    经典DFM：所有变量平等参与因子提取，无目标变量概念

    两阶段训练流程:
    1. 阶段1: 变量选择(可选)
    2. 阶段2: 因子数选择
    3. 最终训练: 使用选定变量和因子数训练模型
    """

    def __init__(self, config: 'TrainingConfig'):
        """
        初始化训练器

        Args:
            config: 训练配置对象(TrainingConfig)
        """
        self.config = config

        # 环境初始化
        setup_training_environment(
            seed=42,
            silent_mode=False,
            enable_debug_logging=True
        )

        # 训练统计
        self.total_evaluations = 0

    def train(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        enable_export: bool = True,
        export_dir: Optional[str] = None
    ) -> TrainingResult:
        """
        完整两阶段训练流程

        Args:
            progress_callback: 进度回调函数,签名为 (message: str) -> None
            enable_export: 是否导出结果文件(模型、元数据)
            export_dir: 导出目录(None=使用临时目录)

        Returns:
            TrainingResult对象
        """
        start_time = time.time()

        try:
            # 步骤1: 加载和验证数据（无目标变量）
            data, variable_names = load_and_validate_data(
                data_path=self.config.data_path,
                selected_indicators=self.config.selected_indicators,
                progress_callback=progress_callback
            )

            # 确保索引排序（pandas切片要求单调索引）
            if not data.index.is_monotonic_increasing:
                data = data.sort_index()

            # 输出训练配置摘要
            # 根据training_start切分训练数据
            train_data = data.loc[self.config.training_start:self.config.train_end]

            # DDFM模式没有验证期，显示观察期信息
            is_ddfm = (self.config.algorithm == 'deep_learning')
            if is_ddfm:
                # DDFM: validation_start/end 实际存储的是观察期日期
                obs_data = data.loc[self.config.validation_start:self.config.validation_end]
                config_summary = format_training_config(
                    train_start=self.config.training_start,
                    train_end=self.config.train_end,
                    validation_start=self.config.validation_start,  # 观察期开始
                    validation_end=self.config.validation_end,      # 观察期结束
                    train_samples=len(train_data),
                    validation_samples=len(obs_data),               # 观察期样本数
                    initial_vars=len(variable_names),
                    k_factors=self.config.k_factors,
                    is_ddfm=True
                )
            else:
                val_data = data.loc[self.config.validation_start:self.config.validation_end]
                config_summary = format_training_config(
                    train_start=self.config.training_start,
                    train_end=self.config.train_end,
                    validation_start=self.config.validation_start,
                    validation_end=self.config.validation_end,
                    train_samples=len(train_data),
                    validation_samples=len(val_data),
                    initial_vars=len(variable_names),
                    k_factors=self.config.k_factors,
                    is_ddfm=False
                )

            logger.info(config_summary)
            if progress_callback:
                progress_callback(config_summary.strip())

            # ========== 算法分支：深度学习 vs 经典 ==========
            if self.config.algorithm == 'deep_learning':
                # DDFM: 使用全部变量，不进行变量选择
                selected_vars = variable_names
                selection_history = []
                if not self.config.encoder_structure:
                    raise ValueError(
                        "encoder_structure不能为空，无法确定DDFM因子数。"
                        "请在配置中设置有效的encoder_structure，如(16, 4)。"
                    )
                k_factors = self.config.encoder_structure[-1]  # 因子数由编码器结构决定

                if progress_callback:
                    progress_callback(f"[DDFM] 使用深度学习算法，因子数={k_factors}")

                # DDFM训练（无目标变量预测）
                observation_data = data[selected_vars]

                model_result = train_ddfm_model(
                    observation_data=observation_data,
                    encoder_structure=self.config.encoder_structure,
                    training_start=self.config.training_start,
                    train_end=self.config.train_end,
                    decoder_structure=self.config.decoder_structure,
                    use_bias=self.config.use_bias,
                    factor_order=self.config.factor_order,
                    lags_input=self.config.lags_input,
                    batch_norm=self.config.batch_norm,
                    activation=self.config.activation,
                    learning_rate=self.config.learning_rate,
                    optimizer=self.config.ddfm_optimizer,
                    decay_learning_rate=self.config.decay_learning_rate,
                    epochs=self.config.epochs_per_mcmc,
                    batch_size=self.config.batch_size,
                    max_iter=self.config.mcmc_max_iter,
                    tolerance=self.config.mcmc_tolerance,
                    display_interval=self.config.display_interval,
                    seed=self.config.ddfm_seed,
                    target_variable=self.config.ddfm_target_variable,
                    progress_callback=progress_callback
                )

                # PCA分析不适用于DDFM
                pca_analysis = None

            else:
                # 经典DFM: EM算法

                # 步骤2: 阶段1变量选择
                if self.config.enable_variable_selection:
                    # 创建变量筛选专用评估器（使用对数似然）
                    evaluator = create_variable_selection_evaluator(self.config)

                    # 根据选择方法创建对应的选择器
                    if self.config.variable_selection_method == 'backward':
                        # 后向选择器
                        selector = BackwardSelector(
                            evaluator_func=evaluator,
                            min_variables=1,
                            parallel_config=self.config.get_parallel_config(),
                            target_variable=self.config.target_variable
                        )
                    else:
                        raise ValueError(
                            f"不支持的变量选择方法: '{self.config.variable_selection_method}'。"
                            f"支持的方法: 'backward'"
                        )

                    # 根据因子选择策略确定k_factors用于变量选择
                    if self.config.factor_selection_method == 'fixed':
                        # 如果使用固定因子数策略，直接使用用户设置的k_factors
                        k_for_selection = self.config.k_factors
                    else:  # cumulative, kaiser
                        # 如果使用累积方差贡献策略或Kaiser准则，计算合理的k_factors用于变量选择
                        # 最终的k_factors会在阶段2通过PCA确定
                        k_for_selection = max(2, min(len(variable_names) // 2, len(variable_names) - 2))

                    # 执行变量选择
                    selection_result = selector.select(
                        initial_variables=variable_names,
                        full_data=data,
                        params={
                            'k_factors': k_for_selection,
                            'factor_selection_method': self.config.factor_selection_method,
                            'pca_threshold': self.config.pca_threshold,
                            'kaiser_threshold': self.config.kaiser_threshold,
                            'tolerance': self.config.tolerance,
                            'validation_start': self.config.validation_start,
                            'validation_end': self.config.validation_end,
                            'target_variable': self.config.target_variable
                        },
                        training_start_date=self.config.training_start,
                        train_end_date=self.config.train_end,
                        max_iter=self.config.max_iterations,
                        progress_callback=progress_callback
                    )

                    # 提取选定的变量
                    selected_vars = selection_result.selected_variables
                    selection_history = selection_result.selection_history

                    # 更新统计
                    self.total_evaluations += selection_result.total_evaluations
                else:
                    selected_vars = variable_names
                    selection_history = []

                # 步骤3: 阶段2因子数选择
                k_factors, pca_analysis = select_num_factors(
                    data=data,
                    selected_vars=selected_vars,
                    method=self.config.factor_selection_method,
                    fixed_k=self.config.k_factors,
                    pca_threshold=self.config.pca_threshold,
                    kaiser_threshold=self.config.kaiser_threshold,
                    train_end=self.config.train_end
                )

                # 步骤4: 最终模型训练（无目标变量预测）
                observation_data = data[selected_vars]

                model_result = train_dfm_model(
                    observation_data=observation_data,
                    k_factors=k_factors,
                    training_start=self.config.training_start,
                    train_end=self.config.train_end,
                    max_iter=self.config.max_iterations,
                    max_lags=self.config.max_lags,
                    tolerance=self.config.tolerance,
                    progress_callback=progress_callback
                )

            # ========== 公共部分：评估和结果构建 ==========

            # 步骤5: 模型评估（有目标变量时基于目标变量RMSE，否则基于平均RMSE）
            observation_data = data[selected_vars]

            # DDFM模式不计算验证期RMSE（因为没有验证期）
            if self.config.algorithm == 'deep_learning':
                metrics = evaluate_model_fit(
                    model_result=model_result,
                    observation_data=observation_data,
                    training_start=self.config.training_start,
                    train_end=self.config.train_end,
                    validation_start=None,
                    validation_end=None,
                    target_variable=self.config.target_variable,
                    variable_names=selected_vars,
                    rmse_alignment=self.config.rmse_alignment,
                    var_frequency_map=self.config.var_frequency_map
                )
            else:
                metrics = evaluate_model_fit(
                    model_result=model_result,
                    observation_data=observation_data,
                    training_start=self.config.training_start,
                    train_end=self.config.train_end,
                    validation_start=self.config.validation_start,
                    validation_end=self.config.validation_end,
                    target_variable=self.config.target_variable,
                    variable_names=selected_vars,
                    rmse_alignment=self.config.rmse_alignment,
                    var_frequency_map=self.config.var_frequency_map
                )

            # 保存变量名到模型结果
            model_result.variable_names = selected_vars

            # 步骤6: 构建结果
            training_time = time.time() - start_time

            result = TrainingResult.build(
                selected_variables=selected_vars,
                selection_history=selection_history,
                k_factors=k_factors,
                factor_selection_method=self.config.factor_selection_method,
                pca_analysis=pca_analysis,
                model_result=model_result,
                metrics=metrics,
                total_evaluations=self.total_evaluations,
                training_time=training_time,
                output_dir=self.config.output_dir
            )

            # 步骤7: 打印摘要
            print_training_summary(result, progress_callback, logger)

            # 步骤8: 导出结果文件
            if enable_export:
                exporter = TrainingResultExporter()
                file_paths = exporter.export_all(
                    result,
                    self.config,
                    output_dir=export_dir,
                    prepared_data=data  # 传递完整观测数据
                )

                result.export_files = file_paths

                total_count = len(file_paths)
                success_count = len([p for p in file_paths.values() if p])

                if progress_callback:
                    progress_callback(f"结果文件导出完成 (成功 {success_count}/{total_count} 个)")

            return result

        except Exception as e:
            logger.exception(f"训练过程出错: {e}")

            if progress_callback:
                progress_callback(f"训练失败: {e}")

            raise


__all__ = [
    'DFMTrainer',
]
