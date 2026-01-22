# -*- coding: utf-8 -*-
"""
目标变量预测模块

通过因子回归生成目标变量的预测值
"""

import numpy as np
import pandas as pd
from typing import Optional
from dashboard.models.DFM.train.core.models import DFMModelResult
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.constants import ZERO_STD_REPLACEMENT

logger = get_logger(__name__)


def _filter_by_date_range(
    data: pd.Series,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp
) -> pd.Series:
    """按日期范围过滤数据（使用布尔索引，兼容升序和降序索引）"""
    return data[(data.index >= start_date) & (data.index <= end_date)]


def generate_target_forecast(
    model_result: DFMModelResult,
    target_data: pd.Series,
    training_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    observation_end: Optional[str] = None,
    is_ddfm: bool = False
) -> DFMModelResult:
    """
    生成目标变量的预测值

    术语说明：
    - 经典DFM: is=训练期, oos=验证期, obs=观察期
    - DDFM: is=训练期, obs=观察期（无验证期，validation参数映射到obs）

    Args:
        model_result: DFM模型结果
        target_data: 目标变量数据（原始尺度）
        training_start: 训练开始日期
        train_end: 训练结束日期
        validation_start: 经典DFM验证期开始 / DDFM观察期开始
        validation_end: 经典DFM验证期结束 / DDFM观察期结束
        observation_end: 经典DFM观察期结束（DDFM不使用）
        is_ddfm: 是否为DDFM模式
        progress_callback: 进度回调函数

    Returns:
        更新了预测字段的DFMModelResult
        - 经典DFM: forecast_is, forecast_oos, forecast_obs
        - DDFM: forecast_is, forecast_obs (forecast_oos=None)
    """
    try:
        # 提取因子（时间 x 因子数）- 因子是中心化的（mean≈0）
        factors = model_result.factors.T  # (n_time, n_factors)

        # 步骤1: 计算目标变量的训练期统计量（用于标准化和反标准化）
        training_start_date = pd.to_datetime(training_start)
        train_end_date = pd.to_datetime(train_end)
        target_train = _filter_by_date_range(target_data, training_start_date, train_end_date)

        target_mean = target_train.mean()
        target_std = target_train.std()

        # 验证标准差和均值
        if target_std == 0 or pd.isna(target_std):
            raise ValueError(
                f"目标变量训练期标准差为0或NaN，无法进行标准化。"
                f"请检查目标变量数据质量。"
            )
        if pd.isna(target_mean):
            raise ValueError(
                f"目标变量训练期均值为NaN，无法进行标准化。"
                f"请检查目标变量数据质量。"
            )

        logger.debug(f"目标变量标准化参数: mean={target_mean:.4f}, std={target_std:.4f}")

        # 步骤2: 标准化目标变量（匹配老代码逻辑）
        target_data_standardized = (target_data - target_mean) / target_std

        # 步骤3: 对齐目标变量和因子的时间索引（使用标准化后的目标）
        common_index = target_data_standardized.index[:factors.shape[0]]

        y_std = target_data_standardized.loc[common_index].values  # 标准化尺度
        X = factors[:len(common_index), :]

        # 步骤4: 严格限制在训练期（匹配老代码）
        train_mask = common_index <= train_end_date
        y_train_std = y_std[train_mask]  # 标准化尺度
        X_train = X[train_mask, :]

        # 移除NaN值（仅在训练集）
        y_isnan = np.isnan(y_train_std)
        X_has_nan = np.any(np.isnan(X_train), axis=1)
        valid_mask = ~(y_isnan | X_has_nan)

        if not valid_mask.any():
            logger.error("训练集没有找到有效的数据点用于回归")
            raise ValueError("训练集中目标变量和因子都没有有效的对齐数据点")

        y_clean = y_train_std[valid_mask]  # 标准化尺度
        X_clean = X_train[valid_mask, :]

        logger.debug(f"训练集有效数据点: {len(y_clean)}/{len(y_train_std)}")

        # 步骤5: 无截距回归（标准化数据）
        # y_std = factors_centered @ beta + epsilon
        from sklearn.linear_model import LinearRegression
        reg_model = LinearRegression(fit_intercept=False)  # 无截距
        reg_model.fit(X_clean, y_clean)

        beta = reg_model.coef_
        r2_score = reg_model.score(X_clean, y_clean)

        logger.debug(f"目标变量回归完成: beta shape={beta.shape}, R²={r2_score:.4f}")

        # 保存目标变量的因子载荷（用于新闻分解分析）
        model_result.target_factor_loading = beta.copy()

        # 步骤6: 生成预测（全样本，标准化尺度）
        forecast_standardized = X @ beta

        # 步骤7: 反标准化到原始尺度
        # 匹配老代码： nowcast_orig = nowcast_std * target_std + target_mean
        forecast_full = forecast_standardized * target_std + target_mean

        logger.debug("预测值已反标准化到原始尺度")

        # 步骤8: 分割训练期预测
        train_data_filtered = _filter_by_date_range(target_data, training_start_date, train_end_date)
        train_end_idx = len(train_data_filtered) - 1

        # 训练期预测
        forecast_is = forecast_full[:train_end_idx + 1]

        # 步骤9: 验证期/观察期预测（根据模型类型不同处理）
        val_start_date = pd.to_datetime(validation_start)
        val_end_date = pd.to_datetime(validation_end)

        val_data_filtered = _filter_by_date_range(target_data, val_start_date, val_end_date)
        if len(val_data_filtered) > 0:
            val_start_idx = target_data.index.get_loc(val_data_filtered.index[0])
            val_end_idx = target_data.index.get_loc(val_data_filtered.index[-1])

            if val_start_idx >= len(forecast_full) or val_end_idx >= len(forecast_full):
                raise ValueError(
                    f"验证期索引超出预测范围: val_start_idx={val_start_idx}, "
                    f"val_end_idx={val_end_idx}, forecast_len={len(forecast_full)}。"
                    f"请检查日期范围设置。"
                )
            val_forecast = forecast_full[val_start_idx:val_end_idx + 1]
        else:
            val_forecast = None

        if is_ddfm:
            # DDFM模式：validation参数实际是观察期，存储到forecast_obs
            model_result.forecast_oos = None  # DDFM没有验证期
            model_result.forecast_obs = val_forecast
            if val_forecast is not None:
                logger.debug(f"[DDFM] 观察期预测已生成: {len(val_forecast)} 个数据点")
        else:
            # 经典DFM模式：validation是验证期，存储到forecast_oos
            model_result.forecast_oos = val_forecast if val_forecast is not None and len(val_forecast) > 0 else None

            # 步骤10: 经典DFM的观察期预测（验证期之后）
            if observation_end is not None:
                obs_end_date = pd.to_datetime(observation_end)

                if obs_end_date > val_end_date:
                    obs_start_date = val_end_date + pd.DateOffset(weeks=1)
                    obs_data_filtered = _filter_by_date_range(target_data, obs_start_date, obs_end_date)

                    if len(obs_data_filtered) > 0:
                        obs_start_idx = target_data.index.get_loc(obs_data_filtered.index[0])
                        obs_end_idx = target_data.index.get_loc(obs_data_filtered.index[-1])

                        if obs_start_idx >= len(forecast_full) or obs_end_idx >= len(forecast_full):
                            raise ValueError(
                                f"观察期索引超出预测范围: obs_start_idx={obs_start_idx}, "
                                f"obs_end_idx={obs_end_idx}, forecast_len={len(forecast_full)}。"
                                f"请检查observation_end日期设置。"
                            )
                        forecast_obs = forecast_full[obs_start_idx:obs_end_idx + 1]
                        model_result.forecast_obs = forecast_obs
                        logger.debug(f"观察期预测已生成: {len(forecast_obs)} 个数据点")
                    else:
                        logger.warning("观察期没有有效数据点")
                        model_result.forecast_obs = None
                else:
                    logger.info("observation_end <= validation_end，跳过观察期")
                    model_result.forecast_obs = None
            else:
                logger.debug("未提供observation_end，跳过观察期预测")
                model_result.forecast_obs = None

        # 更新model_result（训练期预测在上面已处理，这里只更新is）
        model_result.forecast_is = forecast_is

    except Exception as e:
        logger.exception(f"生成目标变量预测时出错: {e}")
        raise

    return model_result


__all__ = ['generate_target_forecast']
