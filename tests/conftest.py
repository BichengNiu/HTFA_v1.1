# -*- coding: utf-8 -*-
"""
pytest配置和共享fixtures

为DFM模型测试提供合成数据和模型参数fixtures
"""

import pytest
import numpy as np
import pandas as pd
from typing import Tuple, Dict
from dataclasses import dataclass


@dataclass
class SyntheticDFMData:
    """合成DFM数据容器"""
    observations: pd.DataFrame  # 观测数据 (n_time, n_obs)
    true_factors: np.ndarray    # 真实因子 (n_time, n_factors)
    true_params: Dict           # 真实参数 {A, Q, H, R}


def generate_synthetic_dfm_data(
    n_time: int = 100,
    n_obs: int = 10,
    n_factors: int = 2,
    seed: int = 42
) -> SyntheticDFMData:
    """
    生成合成DFM数据

    真实模型:
        Z_t = H * F_t + eps_t,  eps_t ~ N(0, R)
        F_t = A * F_{t-1} + eta_t,  eta_t ~ N(0, Q)

    Args:
        n_time: 时间点数量
        n_obs: 观测变量数量
        n_factors: 因子数量
        seed: 随机种子

    Returns:
        SyntheticDFMData: 包含观测数据、真实因子和真实参数
    """
    np.random.seed(seed)

    # 状态转移矩阵 A (AR(1)系数，对角矩阵)
    A_true = np.diag([0.9 - 0.1 * i for i in range(n_factors)])

    # 状态噪声协方差 Q
    Q_true = np.eye(n_factors) * 0.1

    # 载荷矩阵 H (n_obs, n_factors)
    H_true = np.random.randn(n_obs, n_factors) * 0.5
    # 确保载荷矩阵有合理的结构
    for i in range(n_factors):
        H_true[i * (n_obs // n_factors):(i + 1) * (n_obs // n_factors), i] += 1.0

    # 观测噪声协方差 R (对角矩阵)
    R_true = np.eye(n_obs) * 0.05

    # 生成因子序列
    factors = np.zeros((n_time, n_factors))
    factors[0, :] = np.random.randn(n_factors) * 0.1

    for t in range(1, n_time):
        eta_t = np.random.multivariate_normal(np.zeros(n_factors), Q_true)
        factors[t, :] = A_true @ factors[t - 1, :] + eta_t

    # 生成观测数据
    observations = np.zeros((n_time, n_obs))
    for t in range(n_time):
        eps_t = np.random.multivariate_normal(np.zeros(n_obs), R_true)
        observations[t, :] = H_true @ factors[t, :] + eps_t

    # 创建DataFrame
    dates = pd.date_range(start='2020-01-01', periods=n_time, freq='MS')
    obs_df = pd.DataFrame(
        observations,
        index=dates,
        columns=[f'Var{i+1}' for i in range(n_obs)]
    )

    true_params = {
        'A': A_true,
        'Q': Q_true,
        'H': H_true,
        'R': R_true
    }

    return SyntheticDFMData(
        observations=obs_df,
        true_factors=factors,
        true_params=true_params
    )


# ==================== Fixtures ====================

@pytest.fixture
def synthetic_data() -> SyntheticDFMData:
    """生成标准合成测试数据 (100时间点 x 10变量 x 2因子)"""
    return generate_synthetic_dfm_data(
        n_time=100,
        n_obs=10,
        n_factors=2,
        seed=42
    )


@pytest.fixture
def small_synthetic_data() -> SyntheticDFMData:
    """生成小规模合成测试数据 (50时间点 x 5变量 x 1因子)"""
    return generate_synthetic_dfm_data(
        n_time=50,
        n_obs=5,
        n_factors=1,
        seed=123
    )


@pytest.fixture
def large_synthetic_data() -> SyntheticDFMData:
    """生成大规模合成测试数据 (200时间点 x 20变量 x 3因子)"""
    return generate_synthetic_dfm_data(
        n_time=200,
        n_obs=20,
        n_factors=3,
        seed=456
    )


@pytest.fixture
def dfm_params() -> Dict:
    """生成DFM模型参数 (A, Q, H, R)"""
    n_factors = 2
    n_obs = 10

    A = np.array([[0.9, 0.0],
                  [0.0, 0.8]])
    Q = np.eye(n_factors) * 0.1
    H = np.random.RandomState(42).randn(n_obs, n_factors) * 0.5
    R = np.eye(n_obs) * 0.05

    return {'A': A, 'Q': Q, 'H': H, 'R': R}


@pytest.fixture
def kalman_matrices(dfm_params) -> Dict:
    """生成卡尔曼滤波所需的完整矩阵集"""
    n_states = dfm_params['A'].shape[0]
    n_obs = dfm_params['H'].shape[0]

    return {
        'A': dfm_params['A'],
        'B': np.eye(n_states) * 0.1,
        'H': dfm_params['H'],
        'Q': dfm_params['Q'],
        'R': dfm_params['R'],
        'x0': np.zeros(n_states),
        'P0': np.eye(n_states)
    }


@pytest.fixture
def sample_observation_data() -> pd.DataFrame:
    """生成示例观测数据DataFrame"""
    np.random.seed(42)
    n_time = 100
    n_obs = 10

    dates = pd.date_range(start='2020-01-01', periods=n_time, freq='MS')
    data = np.random.randn(n_time, n_obs)

    return pd.DataFrame(
        data,
        index=dates,
        columns=[f'Var{i+1}' for i in range(n_obs)]
    )


@pytest.fixture
def training_dates() -> Dict[str, str]:
    """生成训练日期范围"""
    return {
        'training_start': '2020-01-01',
        'train_end': '2026-06-01',
        'validation_start': '2026-07-01',
        'validation_end': '2028-04-01'
    }


@pytest.fixture
def sample_factors() -> pd.DataFrame:
    """生成示例因子DataFrame"""
    np.random.seed(42)
    n_time = 100
    n_factors = 2

    dates = pd.date_range(start='2020-01-01', periods=n_time, freq='MS')
    factors = np.random.randn(n_time, n_factors)

    return pd.DataFrame(
        factors,
        index=dates,
        columns=[f'Factor{i+1}' for i in range(n_factors)]
    )


# ==================== 辅助函数 ====================

def assert_no_nan_inf(arr: np.ndarray, name: str = "array"):
    """断言数组不包含NaN或Inf"""
    assert not np.any(np.isnan(arr)), f"{name} 包含NaN值"
    assert not np.any(np.isinf(arr)), f"{name} 包含Inf值"


def assert_positive_definite(matrix: np.ndarray, name: str = "matrix"):
    """断言矩阵正定"""
    eigenvalues = np.linalg.eigvalsh(matrix)
    assert np.all(eigenvalues > 0), f"{name} 不是正定矩阵，最小特征值: {eigenvalues.min()}"


def assert_shape(arr: np.ndarray, expected_shape: Tuple, name: str = "array"):
    """断言数组形状"""
    assert arr.shape == expected_shape, f"{name} 形状错误: 期望 {expected_shape}, 实际 {arr.shape}"
