# -*- coding: utf-8 -*-
"""
DDFM工具函数模块

整合深度动态因子模型所需的工具函数
"""

from typing import Tuple
import numpy as np
from dashboard.models.DFM.train.utils.logger import get_logger

# 常量定义
_FACTOR_ORDER_ERROR = "仅支持AR(1)或AR(2)因子动态"
logger = get_logger(__name__)


def mse_missing(y_actual, y_predicted):
    """
    处理缺失数据的MSE损失函数（TensorFlow版本）

    Args:
        y_actual: 实际值张量
        y_predicted: 预测值张量

    Returns:
        MSE损失值
    """
    import tensorflow as tf

    mask = tf.where(tf.math.is_nan(y_actual), tf.zeros_like(y_actual), tf.ones_like(y_actual))
    y_actual_ = tf.where(tf.math.is_nan(y_actual), tf.zeros_like(y_actual), y_actual)
    y_predicted_ = tf.multiply(y_predicted, mask)
    return tf.reduce_mean(tf.square(y_actual_ - y_predicted_))


def convergence_checker(y_prev: np.ndarray, y_now: np.ndarray, y_actual: np.ndarray) -> Tuple[float, float]:
    """
    检查收敛性

    Args:
        y_prev: 上一次迭代的预测值
        y_now: 当前迭代的预测值
        y_actual: 实际值

    Returns:
        (相对变化量, 当前损失)

    Raises:
        ValueError: 当y_actual全是NaN时
    """
    from sklearn.metrics import mean_squared_error as mse

    # 获取非NaN掩码（同时检查y_actual和预测值）
    valid_mask = ~np.isnan(y_actual) & ~np.isnan(y_prev) & ~np.isnan(y_now)
    if not np.any(valid_mask):
        raise ValueError("没有有效数据点可用于计算收敛性（所有值都是NaN）")

    loss_minus = mse(y_prev[valid_mask], y_actual[valid_mask])
    loss = mse(y_now[valid_mask], y_actual[valid_mask])

    # 双重判断：相对阈值 + 绝对阈值（修复：防止delta爆炸）
    if loss_minus < 1e-8:
        # 损失极小时，使用绝对变化量
        delta = np.abs(loss - loss_minus)
    else:
        # 正常情况，使用相对变化量
        delta = np.abs(loss - loss_minus) / loss_minus

    # 防止delta爆炸（loss_minus很小时）
    delta = np.minimum(delta, 1000.0)  # 裁剪到合理范围

    return delta, loss


def convert_decoder_to_numpy(decoder, has_bias: bool, factor_order: int,
                             structure_decoder: tuple = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    将Keras解码器转换为numpy矩阵

    Args:
        decoder: Keras解码器模型
        has_bias: 是否有偏置项
        factor_order: 因子自回归阶数
        structure_decoder: 解码器结构，None表示单层

    Returns:
        (偏置, 观测矩阵H)
    """
    if structure_decoder is None:
        if has_bias:
            ws, bs = decoder.get_layer(index=-1).get_weights()
        else:
            ws = decoder.get_layer(index=-1).get_weights()[0]
            bs = np.zeros(ws.shape[1])

        # 构建观测方程矩阵
        if factor_order == 2:
            emission = np.hstack((
                ws.T,  # 权重项
                np.zeros((ws.shape[1], ws.shape[0])),  # 滞后因子的零矩阵
                np.identity(ws.shape[1])  # 特质项
            ))
        elif factor_order == 1:
            emission = np.hstack((
                ws.T,  # 权重项
                np.identity(ws.shape[1])  # 特质项
            ))
        else:
            raise NotImplementedError(_FACTOR_ORDER_ERROR)
    else:
        raise NotImplementedError("非线性解码器尚未实现")

    return bs, emission


def get_transition_params(f_t: np.ndarray, eps_t: np.ndarray, factor_order: int,
                          bool_no_miss: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    计算状态转移方程参数

    Args:
        f_t: 公共因子
        eps_t: 特质项
        factor_order: 因子自回归阶数
        bool_no_miss: 非缺失值标记数组

    Returns:
        (转移矩阵A, 噪声协方差Q, 初始均值mu_0, 初始协方差Sigma_0, 状态序列x_t)
    """
    if factor_order == 2:
        f_past = np.hstack((f_t[1:-1, :], f_t[:-2, :]))
        A_f = (np.linalg.pinv(f_past.T @ f_past) @ f_past.T @ f_t[2:, :]).T
    elif factor_order == 1:
        f_past = f_t[:-1, :]
        A_f = (np.linalg.pinv(f_past.T @ f_past) @ f_past.T @ f_t[1:, :]).T
    else:
        raise NotImplementedError(_FACTOR_ORDER_ERROR)

    # 获取特质项的AR系数
    A_eps, _, _ = get_idio(eps_t, bool_no_miss)

    # 构建伴随形式状态 x_t = [f_t, f_{t-1}, eps_t]
    if factor_order == 2:
        x_t = np.vstack((f_t[1:, :].T, f_t[:-1, :].T, eps_t[1:, :].T))
        A = np.vstack((
            np.hstack((A_f, np.zeros((A_f.shape[0], eps_t.shape[1])))),  # VAR因子
            np.hstack((np.identity(A_f.shape[0]), np.zeros((A_f.shape[0], A_f.shape[0] + eps_t.shape[1])))),
            np.hstack((np.zeros((eps_t.shape[1], A_f.shape[1])), A_eps))  # AR(1)特质项
        ))
    elif factor_order == 1:
        x_t = np.vstack((f_t.T, eps_t.T))
        A = np.vstack((
            np.hstack((A_f, np.zeros((A_f.shape[0], eps_t.shape[1])))),  # VAR因子
            np.hstack((np.zeros((eps_t.shape[1], A_f.shape[1])), A_eps))  # AR(1)特质项
        ))
    else:
        raise NotImplementedError(_FACTOR_ORDER_ERROR)

    # 误差项协方差矩阵
    w_t = x_t[:, 1:] - A @ x_t[:, :-1]
    W = np.diag(np.diag(np.cov(w_t)))

    # 设置初始状态的无条件矩
    mu_0 = np.mean(x_t, axis=1)
    Sigma_0 = np.cov(x_t)

    # 放大初始协方差，允许更大的初始不确定性
    # 修复：原先基于训练期计算的Sigma_0可能过小，
    # 导致观察期数据偏离时滤波器响应过激
    Sigma_0 = Sigma_0 * 2.0

    # 特质项与因子不相关，特质项之间协方差为对角阵
    # 注意：先做结构约束，再添加正定性保护
    Sigma_0[:A_f.shape[1], A_f.shape[1]:] = 0
    Sigma_0[A_f.shape[1]:, :A_f.shape[1]] = 0
    Sigma_0[A_f.shape[1]:, A_f.shape[1]:] = np.diag(np.diag(Sigma_0[A_f.shape[1]:, A_f.shape[1]:]))

    # 确保正定性（最后执行，避免被结构约束覆盖）
    Sigma_0 = Sigma_0 + np.eye(Sigma_0.shape[0]) * 0.01

    return A, W, mu_0, Sigma_0, x_t


def get_idio(eps: np.ndarray, idx_no_missings: np.ndarray, min_obs: int = 20) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    估计特质项的AR(1)参数（支持混合频率数据）

    对于不同频率的变量，在其原始频率上估计AR(1)参数：
    - 周度变量：检查相邻行是否都非缺失
    - 月度变量：检查在原始频率上相邻的观测（即两个非空观测之间没有其他非空观测）

    Args:
        eps: 特质项序列 (T, n_variables)
        idx_no_missings: 非缺失值索引 (T, n_variables)
        min_obs: 最小观测数

    Returns:
        (AR系数矩阵, 均值, 标准差)
    """
    phi = np.zeros((eps.shape[1], eps.shape[1]))
    mu_eps = np.zeros(eps.shape[1])
    std_eps = np.zeros(eps.shape[1])

    # 诊断日志：输出eps范围
    logger.debug(f"[get_idio] eps范围: [{np.nanmin(eps):.2e}, {np.nanmax(eps):.2e}]")

    for j in range(eps.shape[1]):
        # 找出该变量的非空观测位置
        non_miss_indices = np.where(idx_no_missings[:, j])[0]

        # 检查eps是否全为NaN（关键修复：防止NaN传播）
        eps_col = eps[:, j]
        if np.all(np.isnan(eps_col)):
            mu_eps[j] = 0.0
            std_eps[j] = 1.0
            phi[j, j] = 0.0
            continue

        if len(non_miss_indices) < 2:
            # 观测太少，使用默认值
            mu_eps[j] = 0.0
            std_eps[j] = 1.0
            phi[j, j] = 0.0
            continue

        # 计算非空观测之间的间隔
        gaps = np.diff(non_miss_indices)
        median_gap = np.median(gaps)

        # 判断频率：间隔<=2视为周度，否则视为月度/其他低频
        is_weekly = median_gap <= 2

        if is_weekly:
            # 周度变量：检查相邻行都非空
            to_select = idx_no_missings[:, j]
            to_select = np.hstack((np.array([False]), to_select[:-1] * to_select[1:]))
            eps_t = eps[to_select, j]
            # 构造eps[t-1]序列
            to_select_prev = np.hstack((to_select[1:], np.array([False])))
            eps_t_1 = eps[to_select_prev, j]
        else:
            # 月度/低频变量：使用原始频率上的连续观测对
            eps_t = eps[non_miss_indices[1:], j]
            eps_t_1 = eps[non_miss_indices[:-1], j]

        # 过滤NaN值对（关键修复：防止NaN污染统计量）
        valid_pairs = ~(np.isnan(eps_t) | np.isnan(eps_t_1))
        eps_t = eps_t[valid_pairs]
        eps_t_1 = eps_t_1[valid_pairs]

        n_pairs = len(eps_t)

        if n_pairs >= min_obs:
            mu_eps[j] = np.mean(eps_t)
            std_eps[j] = np.std(eps_t)

            # 强制std_eps下界（关键修复：防止数值不稳定）
            std_eps[j] = np.maximum(std_eps[j], 1e-4)

            # 添加分母稳定性保护
            cov1_eps = np.cov(eps_t, eps_t_1)[0][1]
            variance = std_eps[j] ** 2
            phi_raw = cov1_eps / (variance + 1e-8)
            # 放宽裁剪范围，避免边界振荡（从[-0.99,0.99]改为[-0.90,0.90]）
            phi[j, j] = np.clip(phi_raw, -0.90, 0.90)
            # 诊断日志：每10个变量输出一次
            if j % 10 == 0:
                logger.debug(f"[get_idio] 变量{j}: n_pairs={n_pairs}, std_eps={std_eps[j]:.2e}, phi={phi[j,j]:.4f}")
        else:
            # 观测不足，使用默认值
            valid_eps = eps[idx_no_missings[:, j], j]
            if len(valid_eps) > 0:
                mu_eps[j] = np.mean(valid_eps)
                std_eps[j] = np.std(valid_eps) if len(valid_eps) > 1 else 1.0
                # 强制std_eps下界（与n_pairs >= min_obs分支保持一致）
                std_eps[j] = np.maximum(std_eps[j], 1e-4)
            else:
                mu_eps[j] = 0.0
                std_eps[j] = 1.0
            phi[j, j] = 0.0

    return phi, mu_eps, std_eps
