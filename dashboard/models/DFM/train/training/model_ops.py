# -*- coding: utf-8 -*-
"""
DFM模型操作模块

合并训练和评估功能，提供统一的模型操作接口
支持经典DFM（EM算法）和深度学习DFM（DDFM自编码器）

经典DFM模型：所有变量平等参与因子提取，无目标变量概念
"""

import pandas as pd
import numpy as np
from typing import Optional, Callable, Tuple, List
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics
from dashboard.models.DFM.train.core.factor_model import DFMModel

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
    训练经典DFM模型（无目标变量预测）

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
    progress_callback: Optional[Callable[[str], None]] = None
) -> DFMModelResult:
    """
    DDFM训练函数（深度学习算法，无目标变量预测）

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
    train_end: str
) -> EvaluationMetrics:
    """
    评估DFM模型拟合质量

    基于模型拟合质量的评估，只计算重构RMSE。

    Args:
        model_result: DFM模型结果
        observation_data: 观测数据
        training_start: 训练期开始日期
        train_end: 训练期结束日期

    Returns:
        EvaluationMetrics: 包含重构RMSE的评估指标对象
    """
    # 获取训练期数据
    train_start_dt = pd.to_datetime(training_start)
    train_end_dt = pd.to_datetime(train_end)
    train_data = observation_data[
        (observation_data.index >= train_start_dt) &
        (observation_data.index <= train_end_dt)
    ]

    n_time = len(train_data)

    # 计算重构RMSE
    reconstruction_rmse = np.inf

    if model_result.H is not None and model_result.factors_smooth is not None:
        try:
            H = model_result.H
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

            # 计算重构RMSE
            reconstruction_rmse = np.sqrt(np.nanmean((obs_centered - reconstructed) ** 2))

            # 存储重构数据
            model_result.reconstructed_data = reconstructed

        except Exception as e:
            logger.warning(f"重构误差计算失败: {e}")

    return EvaluationMetrics(
        reconstruction_rmse=reconstruction_rmse,
        converged=model_result.converged,
        iterations=model_result.iterations
    )


__all__ = ['train_dfm_model', 'train_ddfm_model', 'evaluate_model_fit']
