# -*- coding: utf-8 -*-
"""
DFM模型操作模块

合并训练和评估功能，提供统一的模型操作接口
支持经典DFM（EM算法）和深度学习DFM（DDFM自编码器）
"""

import pandas as pd
import numpy as np
from typing import Optional, Callable, Tuple, List, Dict
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics
from dashboard.models.DFM.train.core.factor_model import DFMModel
from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_single_variable_rmse
)

logger = get_logger(__name__)


# ==================== 训练功能 ====================

def train_dfm_model(
    observation_data: pd.DataFrame,
    k_factors: int,
    training_start: str,
    train_end: str,
    max_iter: int = 30,
    max_lags: int = 1,
    tolerance: float = 1e-6,
    progress_callback: Optional[Callable[[str], None]] = None
) -> DFMModelResult:
    """
    训练经典DFM模型

    完成以下流程：
    1. 创建并配置DFM模型
    2. 在训练集上拟合模型 (EM算法)
    3. 返回因子、载荷矩阵等模型参数

    Args:
        observation_data: 观测变量数据 (DataFrame, columns=变量名, index=日期)
        k_factors: 因子个数
        training_start: 训练期开始日期
        train_end: 训练期结束日期
        max_iter: EM算法最大迭代次数
        max_lags: 因子自回归最大滞后阶数
        tolerance: EM算法收敛容差
        progress_callback: 进度回调函数

    Returns:
        DFMModelResult: 包含模型参数、因子的完整结果

    Raises:
        ValueError: 如果数据格式不正确或参数无效
        RuntimeError: 如果模型训练失败
    """
    # 参数验证
    if k_factors <= 0:
        raise ValueError(f"k_factors必须为正数，当前值: {k_factors}")
    if max_iter <= 0:
        raise ValueError(f"max_iter必须为正数，当前值: {max_iter}")
    if max_lags < 1:
        raise ValueError(f"max_lags必须>=1，当前值: {max_lags}")

    # 1. 创建并配置DFM模型
    dfm = DFMModel(
        n_factors=k_factors,
        max_lags=max_lags,
        max_iter=max_iter,
        tolerance=tolerance
    )

    # 2. 训练模型
    try:
        model_result = dfm.fit(
            data=observation_data,
            training_start=training_start,
            train_end=train_end,
            progress_callback=progress_callback
        )

    except Exception as e:
        logger.error(f"[ModelOps] 模型训练失败: {e}")
        raise RuntimeError(f"DFM模型训练失败: {e}") from e

    return model_result


def train_ddfm_model(
    observation_data: pd.DataFrame,
    encoder_structure: Tuple[int, ...],
    training_start: str,
    train_end: str,
    decoder_structure: Optional[Tuple[int, ...]] = None,
    use_bias: bool = True,
    factor_order: int = 2,
    lags_input: int = 0,
    batch_norm: bool = True,
    activation: str = 'relu',
    learning_rate: float = 0.005,
    optimizer: str = 'Adam',
    decay_learning_rate: bool = True,
    epochs: int = 100,
    batch_size: int = 100,
    max_iter: int = 200,
    tolerance: float = 0.0005,
    display_interval: int = 10,
    seed: int = 3,
    target_variable: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> DFMModelResult:
    """
    DDFM训练函数（深度学习算法）

    使用神经网络自编码器提取因子，通过MCMC迭代训练

    Args:
        observation_data: 观测变量数据 (DataFrame, columns=变量名, index=日期)
        encoder_structure: 编码器层结构，最后一个数为因子数
        training_start: 训练集开始日期
        train_end: 训练集结束日期
        decoder_structure: 解码器层结构(None=对称单层线性)
        use_bias: 解码器最后一层是否使用偏置
        factor_order: 因子AR阶数(1或2)
        lags_input: 输入滞后期数
        batch_norm: 是否使用批量归一化
        activation: 激活函数
        learning_rate: 学习率
        optimizer: 优化器
        decay_learning_rate: 是否使用学习率衰减
        epochs: 每次MCMC迭代的epoch数
        batch_size: 批量大小
        max_iter: MCMC最大迭代次数
        tolerance: MCMC收敛阈值
        display_interval: 显示间隔
        seed: 随机种子
        target_variable: 目标变量名（有监督模式），None表示无监督模式
        progress_callback: 进度回调函数

    Returns:
        DFMModelResult: 包含模型参数、因子的完整结果

    Raises:
        ImportError: 如果TensorFlow未安装
        ValueError: 如果数据格式不正确或参数无效
        RuntimeError: 如果模型训练失败
    """
    # 参数验证
    if not encoder_structure or len(encoder_structure) == 0:
        raise ValueError("encoder_structure不能为空")
    for i, neurons in enumerate(encoder_structure):
        if not isinstance(neurons, int) or neurons <= 0:
            raise ValueError(
                f"encoder_structure第{i+1}层必须为正整数，当前值: {neurons}"
            )
    if factor_order not in [1, 2]:
        raise ValueError(f"factor_order必须为1或2，当前值: {factor_order}")
    if batch_size <= 0:
        raise ValueError(f"batch_size必须>0，当前值: {batch_size}")
    if epochs <= 0:
        raise ValueError(f"epochs必须>0，当前值: {epochs}")
    if max_iter <= 0:
        raise ValueError(f"max_iter必须>0，当前值: {max_iter}")
    if learning_rate <= 0:
        raise ValueError(f"learning_rate必须>0，当前值: {learning_rate}")

    # 延迟导入DDFMModel（避免TensorFlow依赖问题）
    from dashboard.models.DFM.train.core.ddfm_model import DDFMModel

    # 因子数由编码器最后一层决定
    n_factors = encoder_structure[-1]

    if progress_callback:
        progress_callback(f"[DDFM] 初始化深度动态因子模型 (因子数={n_factors})")

    # 创建内部回调包装器，传递progress值到外部回调
    def ddfm_progress_callback(message: str, progress: float):
        if progress_callback:
            # 将progress值嵌入消息中，格式: [DDFM|progress%] message
            progress_pct = int(progress * 100)
            progress_callback(f"[DDFM|{progress_pct}%] {message}")

    # 1. 创建DDFM模型
    ddfm = DDFMModel(
        encoder_structure=encoder_structure,
        decoder_structure=decoder_structure,
        use_bias=use_bias,
        factor_order=factor_order,
        lags_input=lags_input,
        batch_norm=batch_norm,
        activation=activation,
        learning_rate=learning_rate,
        optimizer=optimizer,
        decay_learning_rate=decay_learning_rate,
        epochs=epochs,
        batch_size=batch_size,
        max_iter=max_iter,
        tolerance=tolerance,
        display_interval=display_interval,
        seed=seed,
        target_variable=target_variable,
        progress_callback=ddfm_progress_callback
    )

    # 2. 训练模型
    try:
        model_result = ddfm.fit(
            data=observation_data,
            training_start=training_start,
            train_end=train_end
        )

    except ImportError as e:
        logger.error(f"[DDFM] TensorFlow导入失败: {e}")
        raise ImportError(
            "DDFM需要TensorFlow。请安装: pip install tensorflow"
        ) from e
    except Exception as e:
        logger.error(f"[DDFM] 模型训练失败: {e}")
        raise RuntimeError(f"DDFM模型训练失败: {e}") from e

    return model_result


# ==================== 评估功能 ====================

def evaluate_model_fit(
    model_result: DFMModelResult,
    observation_data: pd.DataFrame,
    training_start: str,
    train_end: str,
    validation_start: Optional[str] = None,
    validation_end: Optional[str] = None,
    training_weight: float = 0.5,
    target_variable: Optional[str] = None,
    variable_names: Optional[List[str]] = None,
    rmse_alignment: str = 'current',
    var_frequency_map: Optional[Dict[str, str]] = None
) -> EvaluationMetrics:
    """
    评估DFM模型拟合质量

    计算目标变量RMSE用于模型评估。

    Args:
        model_result: DFM模型结果
        observation_data: 观测数据
        training_start: 训练期开始日期
        train_end: 训练期结束日期
        validation_start: 验证期开始日期（可选）
        validation_end: 验证期结束日期（可选）
        training_weight: 训练期权重 (0.0-1.0)
        target_variable: 目标变量名（用于计算目标变量RMSE）
        variable_names: 变量名列表（用于定位目标变量索引）
        rmse_alignment: RMSE计算对齐方式 ('current'=当月对齐, 'next'=下月对齐)

    Returns:
        EvaluationMetrics: 包含目标变量RMSE的评估指标对象
    """
    # 获取训练期数据
    train_start_dt = pd.to_datetime(training_start)
    train_end_dt = pd.to_datetime(train_end)
    train_data = observation_data[
        (observation_data.index >= train_start_dt) &
        (observation_data.index <= train_end_dt)
    ]

    n_time = len(train_data)

    # 初始化RMSE值
    target_rmse = np.inf

    # 确定目标变量索引
    target_var_index = None
    if target_variable:
        # 优先使用传入的variable_names，否则使用observation_data的列名
        var_names = variable_names if variable_names else list(observation_data.columns)
        if target_variable in var_names:
            target_var_index = var_names.index(target_variable)
        else:
            logger.warning(f"目标变量 '{target_variable}' 不在变量列表中，无法计算目标变量RMSE")

    if model_result.H is not None and model_result.factors_smooth is not None:
        try:
            n_factors = model_result.factors_smooth.shape[0]
            H = model_result.H[:, :n_factors]  # 只取前 n_factors 列（DDFM 的 H 包含特质项）
            factors = model_result.factors_smooth.T  # (n_time, n_factors)

            # 确保维度匹配
            if factors.shape[0] >= n_time:
                factors = factors[:n_time, :]

            reconstructed = factors @ H.T

            # 中心化观测数据
            obs_values = train_data.values
            obs_mean = np.nanmean(obs_values, axis=0)
            obs_centered = obs_values - obs_mean

            # 确保维度匹配
            min_time = min(obs_centered.shape[0], reconstructed.shape[0])
            obs_centered = obs_centered[:min_time, :]
            reconstructed = reconstructed[:min_time, :]

            # 根据对齐方式调整数据
            if var_frequency_map:
                # 混频数据：不预先偏移，由混频函数内部处理对齐
                obs_aligned = obs_centered
                recon_aligned = reconstructed
            elif rmse_alignment == 'next':
                # 下月对齐：预测值[t] vs 实际值[t+1]
                if min_time > 1:
                    obs_aligned = obs_centered[1:, :]
                    recon_aligned = reconstructed[:-1, :]
                else:
                    logger.warning("数据期数不足，无法进行下月对齐RMSE计算")
                    obs_aligned = obs_centered
                    recon_aligned = reconstructed
            else:
                # 当月对齐（默认）
                obs_aligned = obs_centered
                recon_aligned = reconstructed

            # 计算目标变量RMSE
            if target_var_index is not None:
                target_rmse = calculate_single_variable_rmse(
                    obs_aligned, recon_aligned, target_var_index
                )

            # 存储重构数据
            model_result.reconstructed_data = reconstructed

        except Exception as e:
            logger.warning(f"训练期RMSE计算失败: {e}")

    # 计算验证期RMSE
    target_rmse_validation = np.inf
    if validation_start and validation_end:
        try:
            val_start_dt = pd.to_datetime(validation_start)
            val_end_dt = pd.to_datetime(validation_end)
            val_data = observation_data[
                (observation_data.index >= val_start_dt) &
                (observation_data.index <= val_end_dt)
            ]

            if len(val_data) > 0 and model_result.H is not None and model_result.factors_smooth is not None:
                n_factors = model_result.factors_smooth.shape[0]
                H = model_result.H[:, :n_factors]  # 只取前 n_factors 列（DDFM 的 H 包含特质项）
                factors = model_result.factors_smooth.T  # (n_time, n_factors)

                # 计算验证期对应的因子索引范围
                full_data = observation_data[
                    (observation_data.index >= train_start_dt) &
                    (observation_data.index <= val_end_dt)
                ]
                val_start_idx = len(full_data) - len(val_data)
                val_end_idx = len(full_data)

                # 确保因子数据足够
                if factors.shape[0] >= val_end_idx:
                    val_factors = factors[val_start_idx:val_end_idx, :]
                    val_reconstructed = val_factors @ H.T

                    # 中心化验证期数据（使用训练期均值）
                    train_mean = np.nanmean(train_data.values, axis=0)
                    val_obs_centered = val_data.values - train_mean

                    # 确保维度匹配
                    min_val_time = min(val_obs_centered.shape[0], val_reconstructed.shape[0])
                    val_obs_centered = val_obs_centered[:min_val_time, :]
                    val_reconstructed = val_reconstructed[:min_val_time, :]

                    # 根据对齐方式调整数据
                    if var_frequency_map:
                        # 混频数据：不预先偏移，由混频函数内部处理对齐
                        val_obs_aligned = val_obs_centered
                        val_recon_aligned = val_reconstructed
                    elif rmse_alignment == 'next':
                        # 下月对齐：预测值[t] vs 实际值[t+1]
                        if min_val_time > 1:
                            val_obs_aligned = val_obs_centered[1:, :]
                            val_recon_aligned = val_reconstructed[:-1, :]
                        else:
                            logger.warning("验证期数据期数不足，无法进行下月对齐RMSE计算")
                            val_obs_aligned = val_obs_centered
                            val_recon_aligned = val_reconstructed
                    else:
                        # 当月对齐（默认）
                        val_obs_aligned = val_obs_centered
                        val_recon_aligned = val_reconstructed

                    # 计算验证期目标变量RMSE
                    if target_var_index is not None:
                        target_rmse_validation = calculate_single_variable_rmse(
                            val_obs_aligned, val_recon_aligned, target_var_index
                        )

        except Exception as e:
            logger.warning(f"验证期RMSE计算失败: {e}")

    # 计算目标变量加权RMSE
    weighted_target_rmse = _calculate_weighted_rmse(
        target_rmse, target_rmse_validation, training_weight
    )

    return EvaluationMetrics(
        target_rmse=target_rmse,
        target_rmse_validation=target_rmse_validation,
        weighted_target_rmse=weighted_target_rmse,
        converged=model_result.converged,
        iterations=model_result.iterations
    )


def _calculate_weighted_rmse(
    train_rmse: float,
    val_rmse: float,
    training_weight: float
) -> float:
    """
    计算加权RMSE

    Args:
        train_rmse: 训练期RMSE
        val_rmse: 验证期RMSE
        training_weight: 训练期权重 (0.0-1.0)

    Returns:
        float: 加权RMSE
    """
    # 处理无效值
    if not np.isfinite(train_rmse) and not np.isfinite(val_rmse):
        return np.inf
    if not np.isfinite(train_rmse):
        return val_rmse
    if not np.isfinite(val_rmse):
        return train_rmse

    return training_weight * train_rmse + (1.0 - training_weight) * val_rmse


__all__ = ['train_dfm_model', 'train_ddfm_model', 'evaluate_model_fit']
