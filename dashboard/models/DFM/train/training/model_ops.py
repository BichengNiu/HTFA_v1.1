# -*- coding: utf-8 -*-
"""
DFM模型操作模块

合并训练和评估功能，提供统一的模型操作接口
支持经典DFM（EM算法）和深度学习DFM（DDFM自编码器）
"""

import pandas as pd
import numpy as np
from typing import Optional, Callable, Tuple
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics
from dashboard.models.DFM.train.core.factor_model import DFMModel
from dashboard.models.DFM.train.core.prediction import generate_target_forecast
from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_aligned_rmse,
    calculate_aligned_mae,
    calculate_aligned_win_rate
)

logger = get_logger(__name__)


# ==================== 训练功能 ====================

def train_dfm_with_forecast(
    predictor_data: pd.DataFrame,
    target_data: pd.Series,
    k_factors: int,
    training_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    observation_end: Optional[str] = None,
    max_iter: int = 30,
    max_lags: int = 1,
    tolerance: float = 1e-6,
    progress_callback: Optional[Callable[[str], None]] = None
) -> DFMModelResult:
    """
    统一的DFM训练和预测函数

    完成以下流程：
    1. 创建并配置DFM模型
    2. 在训练集上拟合模型 (EM算法)
    3. 生成目标变量的训练期和观察期预测

    Args:
        predictor_data: 预测变量数据 (DataFrame, columns=变量名, index=日期)
        target_data: 目标变量数据 (Series, index=日期)
        k_factors: 因子个数
        training_start: 训练期开始日期（必填）
        train_end: 训练期结束日期（必填）
        validation_start: 观察期开始日期（必填）
        validation_end: 观察期结束日期（必填）
        max_iter: EM算法最大迭代次数
        max_lags: 因子自回归最大滞后阶数
        tolerance: EM算法收敛容差
        progress_callback: 进度回调函数

    Returns:
        DFMModelResult: 包含模型参数、因子、预测值的完整结果

    Raises:
        ValueError: 如果数据格式不正确或参数无效
        RuntimeError: 如果模型训练失败

    Examples:
        >>> result = train_dfm_with_forecast(
        ...     predictor_data=df[indicator_cols],
        ...     target_data=df['target'],
        ...     k_factors=3,
        ...     train_end='2023-12-31',
        ...     validation_start='2024-01-01',
        ...     validation_end='2024-06-30',
        ...     max_iter=50
        ... )
        >>> print(f"收敛: {result.converged}, 迭代: {result.iterations}次")
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
            data=predictor_data,
            training_start=training_start,
            train_end=train_end,
            progress_callback=progress_callback
        )

    except Exception as e:
        logger.error(f"[ModelOps] 模型训练失败: {e}")
        raise RuntimeError(f"DFM模型训练失败: {e}") from e

    # 3. 生成目标变量预测
    try:
        model_result = generate_target_forecast(
            model_result=model_result,
            target_data=target_data,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            observation_end=observation_end
        )

    except Exception as e:
        logger.error(f"[ModelOps] 预测生成失败: {e}")
        raise RuntimeError(f"目标预测生成失败: {e}") from e

    return model_result


def train_ddfm_with_forecast(
    predictor_data: pd.DataFrame,
    target_data: pd.Series,
    encoder_structure: Tuple[int, ...],
    training_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
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
    DDFM训练和预测函数（深度学习算法）

    使用神经网络自编码器提取因子，通过MCMC迭代训练

    DDFM只有训练期和观察期两个阶段，无验证期。
    validation_start/validation_end参数实际对应DDFM的观察期。

    Args:
        predictor_data: 预测变量数据 (DataFrame, columns=变量名, index=日期)
        target_data: 目标变量数据 (Series, index=日期)
        encoder_structure: 编码器层结构，最后一个数为因子数
        training_start: 训练集开始日期
        train_end: 训练集结束日期
        validation_start: 观察期开始日期
        validation_end: 观察期结束日期
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
        DFMModelResult: 包含模型参数、因子、预测值的完整结果

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
            data=predictor_data,
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

    # 3. 生成目标变量预测
    try:
        if progress_callback:
            progress_callback("[DDFM] 生成目标变量预测...")

        model_result = generate_target_forecast(
            model_result=model_result,
            target_data=target_data,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            observation_end=None,  # DDFM不使用观察期后的扩展数据
            is_ddfm=True  # DDFM模式：validation映射到obs
        )

    except Exception as e:
        logger.error(f"[DDFM] 预测生成失败: {e}")
        raise RuntimeError(f"目标预测生成失败: {e}") from e

    return model_result


# ==================== 评估功能 ====================

def evaluate_model_performance(
    model_result: DFMModelResult,
    target_data: pd.Series,
    train_end: str,
    validation_start: str,
    validation_end: str,
    observation_end: Optional[str] = None,
    alignment_mode: str = 'next_month',
    is_ddfm: bool = False
) -> EvaluationMetrics:
    """
    统一的模型性能评估函数

    术语说明：
    - 经典DFM: is=训练期, oos=验证期, obs=观察期
    - DDFM: is=训练期, obs=观察期（无验证期）

    计算评估指标：
    - RMSE (均方根误差)
    - MAE (平均绝对误差)
    - Win Rate (方向命中率)

    Args:
        model_result: DFM模型结果，包含预测值
        target_data: 目标变量的真实值 (Series with DatetimeIndex)
        train_end: 训练期结束日期
        validation_start: 经典DFM验证期开始 / DDFM观察期开始
        validation_end: 经典DFM验证期结束 / DDFM观察期结束
        observation_end: 经典DFM观察期结束（DDFM不使用）
        alignment_mode: 目标配对模式 ('current_month' 或 'next_month')
        is_ddfm: 是否为DDFM模式

    Returns:
        EvaluationMetrics: 包含所有评估指标的对象
    """
    metrics = EvaluationMetrics()

    try:
        # 1. 分割训练期数据（使用布尔索引，兼容升序和降序索引）
        train_end_dt = pd.to_datetime(train_end)
        val_start_dt = pd.to_datetime(validation_start)
        val_end_dt = pd.to_datetime(validation_end)

        train_data = target_data[target_data.index <= train_end_dt]
        val_data = target_data[
            (target_data.index >= val_start_dt) &
            (target_data.index <= val_end_dt)
        ]

        # 2. 训练期评估（两种模型相同）
        if model_result.forecast_is is not None and len(train_data) > 0:
            _evaluate_performance(
                metrics=metrics,
                forecast=model_result.forecast_is,
                actual=train_data,
                period_type="is",
                alignment_mode=alignment_mode
            )

        if is_ddfm:
            # DDFM模式：validation参数是观察期，使用forecast_obs
            if model_result.forecast_obs is not None and len(val_data) > 0:
                _evaluate_performance(
                    metrics=metrics,
                    forecast=model_result.forecast_obs,
                    actual=val_data,
                    period_type="obs",
                    alignment_mode=alignment_mode
                )
                logger.info(f"[DDFM] 观察期评估完成: {len(val_data)} 个数据点")
            # DDFM没有验证期，oos指标保持默认值（inf/nan）
        else:
            # 经典DFM模式：validation是验证期
            # 3. 验证期评估
            if model_result.forecast_oos is not None and len(val_data) > 0:
                _evaluate_performance(
                    metrics=metrics,
                    forecast=model_result.forecast_oos,
                    actual=val_data,
                    period_type="oos",
                    alignment_mode=alignment_mode,
                    full_target_data=target_data  # 传递完整target用于下月配对
                )

            # 4. 观察期评估（验证期之后）
            if observation_end is not None and model_result.forecast_obs is not None:
                obs_end_date = pd.to_datetime(observation_end)

                if obs_end_date > val_end_dt:
                    obs_start_date = val_end_dt + pd.DateOffset(weeks=1)
                    obs_data = target_data[
                        (target_data.index >= obs_start_date) &
                        (target_data.index <= obs_end_date)
                    ]

                    if len(obs_data) > 0:
                        _evaluate_performance(
                            metrics=metrics,
                            forecast=model_result.forecast_obs,
                            actual=obs_data,
                            period_type="obs",
                            alignment_mode=alignment_mode
                        )
                        logger.info(f"观察期评估完成: {len(obs_data)} 个数据点")

    except Exception as e:
        logger.exception(f"[ModelOps] 评估过程出错: {e}")

    return metrics


def _evaluate_performance(
    metrics: EvaluationMetrics,
    forecast: np.ndarray,
    actual: pd.Series,
    period_type: str,
    alignment_mode: str = 'next_month',
    full_target_data: Optional[pd.Series] = None
) -> None:
    """
    计算评估指标（统一的训练期/验证期/观察期评估逻辑）

    根据alignment_mode选择配对评估方式：
    - next_month: m月nowcast与m+1月target配对（默认）
    - current_month: m月nowcast与m月target配对

    Args:
        metrics: 要更新的EvaluationMetrics对象
        forecast: 预测值数组
        actual: 真实值Series
        period_type: 时间段类型，'is'表示训练期，'oos'表示验证期，'obs'表示观察期
        alignment_mode: 配对模式 ('current_month' 或 'next_month')
        full_target_data: 完整的target数据（用于下月配对时获取下月target）
    """
    min_len = min(len(forecast), len(actual))
    forecast_aligned = forecast[:min_len]

    actual_index = pd.to_datetime(actual.index[:min_len])
    pred_series = pd.Series(forecast_aligned, index=actual_index)
    # 对于下月配对模式，使用完整target数据；否则使用切分后的数据
    actual_series = full_target_data if full_target_data is not None else actual

    # 日志前缀映射：训练期/验证期/观察期
    log_prefix_map = {
        "is": "TRAIN",   # 训练期
        "oos": "VALID",  # 验证期
        "obs": "OBS"     # 观察期
    }
    log_prefix = log_prefix_map.get(period_type, period_type.upper())

    # 使用统一调度函数根据配对模式计算指标
    try:
        rmse = calculate_aligned_rmse(pred_series, actual_series, alignment_mode)
        logger.debug(f"[{log_prefix}] RMSE计算成功: {rmse:.4f}")
    except Exception as e:
        logger.error(f"[{log_prefix}] RMSE计算失败: {e}")
        rmse = np.inf

    try:
        mae = calculate_aligned_mae(pred_series, actual_series, alignment_mode)
        logger.debug(f"[{log_prefix}] MAE计算成功: {mae:.4f}")
    except Exception as e:
        logger.error(f"[{log_prefix}] MAE计算失败: {e}")
        mae = np.inf

    try:
        win_rate = calculate_aligned_win_rate(pred_series, actual_series, alignment_mode)
        logger.debug(f"[{log_prefix}] Win Rate计算成功: {win_rate:.2f}%")
    except Exception as e:
        logger.error(f"[{log_prefix}] Win Rate计算失败: {e}")
        win_rate = np.nan

    if period_type == "is":
        metrics.is_rmse = rmse
        metrics.is_mae = mae
        metrics.is_win_rate = win_rate
    elif period_type == "oos":
        metrics.oos_rmse = rmse
        metrics.oos_mae = mae
        metrics.oos_win_rate = win_rate
    elif period_type == "obs":
        metrics.obs_rmse = rmse
        metrics.obs_mae = mae
        metrics.obs_win_rate = win_rate

    logger.debug(
        f"[{log_prefix}] RMSE={rmse:.4f}, "
        f"MAE={mae:.4f}, "
        f"WinRate={win_rate:.2f}%"
    )


__all__ = ['train_dfm_with_forecast', 'train_ddfm_with_forecast', 'evaluate_model_performance']
