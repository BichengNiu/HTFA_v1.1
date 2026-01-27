# -*- coding: utf-8 -*-
"""
参数估计单元测试

测试estimator模块的载荷估计、转移矩阵估计和协方差矩阵估计
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.core.estimator import (
    estimate_loadings,
    estimate_transition_matrix,
    estimate_covariance_matrices,
    _ensure_positive_definite
)
from dashboard.models.DFM.train.core.kalman import KalmanFilter


# 辅助函数
def assert_no_nan_inf(arr: np.ndarray, name: str = "array"):
    """断言数组不包含NaN或Inf"""
    assert not np.any(np.isnan(arr)), f"{name} 包含NaN值"
    assert not np.any(np.isinf(arr)), f"{name} 包含Inf值"


def assert_positive_definite(matrix: np.ndarray, name: str = "matrix"):
    """断言矩阵正定"""
    eigenvalues = np.linalg.eigvalsh(matrix)
    assert np.all(eigenvalues > 0), f"{name} 不是正定矩阵，最小特征值: {eigenvalues.min()}"


def assert_shape(arr: np.ndarray, expected_shape, name: str = "array"):
    """断言数组形状"""
    assert arr.shape == expected_shape, f"{name} 形状错误: 期望 {expected_shape}, 实际 {arr.shape}"


class TestEstimateLoadings:
    """测试载荷矩阵估计"""

    def test_loadings_shape_dataframe(self, sample_observation_data, sample_factors):
        """测试DataFrame输入的载荷矩阵形状"""
        n_obs = sample_observation_data.shape[1]
        n_factors = sample_factors.shape[1]

        loadings = estimate_loadings(sample_observation_data, sample_factors)

        assert loadings.shape == (n_obs, n_factors), \
            f"载荷矩阵形状错误: 期望({n_obs}, {n_factors}), 实际{loadings.shape}"

    def test_loadings_shape_series(self, sample_factors):
        """测试Series输入的载荷向量形状"""
        n_factors = sample_factors.shape[1]

        # 创建单个变量的Series
        np.random.seed(42)
        single_var = pd.Series(
            np.random.randn(len(sample_factors)),
            index=sample_factors.index,
            name='SingleVar'
        )

        loadings = estimate_loadings(single_var, sample_factors)

        assert loadings.shape == (n_factors,), \
            f"载荷向量形状错误: 期望({n_factors},), 实际{loadings.shape}"

    def test_loadings_no_nan(self, sample_observation_data, sample_factors):
        """测试载荷矩阵无NaN"""
        loadings = estimate_loadings(sample_observation_data, sample_factors)

        assert_no_nan_inf(loadings, "载荷矩阵")

    def test_loadings_with_train_end(self, sample_observation_data, sample_factors):
        """测试使用训练期截止日期"""
        train_end = '2026-06-01'

        loadings = estimate_loadings(
            sample_observation_data,
            sample_factors,
            train_end=train_end,
            use_train_only=True
        )

        assert_no_nan_inf(loadings, "载荷矩阵(训练期)")

    def test_loadings_recovers_true_loadings(self, synthetic_data):
        """测试载荷估计能恢复真实载荷（近似）"""
        true_H = synthetic_data.true_params['H']
        true_factors = synthetic_data.true_factors

        # 创建因子DataFrame
        factors_df = pd.DataFrame(
            true_factors,
            index=synthetic_data.observations.index,
            columns=[f'Factor{i+1}' for i in range(true_factors.shape[1])]
        )

        # 中心化观测数据
        obs_centered = synthetic_data.observations - synthetic_data.observations.mean()

        estimated_H = estimate_loadings(obs_centered, factors_df)

        # 检查相关性（因为符号可能不同）
        for i in range(true_H.shape[1]):
            corr = np.abs(np.corrcoef(true_H[:, i], estimated_H[:, i])[0, 1])
            assert corr > 0.5, \
                f"因子{i+1}的载荷估计相关性过低: {corr:.3f}"

    def test_loadings_insufficient_samples_raises(self, sample_factors):
        """测试样本不足时抛出异常"""
        n_factors = sample_factors.shape[1]

        # 创建样本数少于因子数的数据
        short_obs = pd.DataFrame(
            np.random.randn(n_factors, 5),
            index=sample_factors.index[:n_factors],
            columns=[f'Var{i+1}' for i in range(5)]
        )
        short_factors = sample_factors.iloc[:n_factors]

        with pytest.raises(ValueError):
            estimate_loadings(short_obs, short_factors)


class TestEstimateTransitionMatrix:
    """测试状态转移矩阵估计"""

    def test_transition_matrix_shape_lag1(self, synthetic_data):
        """测试AR(1)转移矩阵形状"""
        factors = synthetic_data.true_factors
        n_factors = factors.shape[1]

        A = estimate_transition_matrix(factors, max_lags=1)

        assert A.shape == (n_factors, n_factors), \
            f"转移矩阵形状错误: 期望({n_factors}, {n_factors}), 实际{A.shape}"

    def test_transition_matrix_shape_lag2(self, synthetic_data):
        """测试AR(2)转移矩阵形状（companion form）"""
        factors = synthetic_data.true_factors
        n_factors = factors.shape[1]
        max_lags = 2
        n_states = n_factors * max_lags

        A = estimate_transition_matrix(factors, max_lags=max_lags)

        assert A.shape == (n_states, n_states), \
            f"转移矩阵形状错误: 期望({n_states}, {n_states}), 实际{A.shape}"

    def test_transition_matrix_no_nan(self, synthetic_data):
        """测试转移矩阵无NaN"""
        factors = synthetic_data.true_factors

        A = estimate_transition_matrix(factors, max_lags=1)

        assert_no_nan_inf(A, "转移矩阵")

    def test_transition_matrix_stable(self, synthetic_data):
        """测试转移矩阵稳定性（特征值模小于1）"""
        factors = synthetic_data.true_factors

        A = estimate_transition_matrix(factors, max_lags=1)

        eigenvalues = np.linalg.eigvals(A)
        max_eigenvalue_mod = np.max(np.abs(eigenvalues))

        # 稳定系统的特征值模应小于1
        assert max_eigenvalue_mod < 1.5, \
            f"转移矩阵可能不稳定: 最大特征值模={max_eigenvalue_mod:.3f}"

    def test_transition_matrix_recovers_true_A(self, synthetic_data):
        """测试转移矩阵估计能恢复真实A（近似）"""
        true_A = synthetic_data.true_params['A']
        factors = synthetic_data.true_factors

        estimated_A = estimate_transition_matrix(factors, max_lags=1)

        # 检查对角元素的相对误差
        for i in range(true_A.shape[0]):
            rel_error = np.abs(estimated_A[i, i] - true_A[i, i]) / np.abs(true_A[i, i])
            assert rel_error < 0.5, \
                f"A[{i},{i}]估计误差过大: 真实={true_A[i,i]:.3f}, 估计={estimated_A[i,i]:.3f}"

    def test_transition_matrix_companion_form(self, synthetic_data):
        """测试AR(2)的companion form结构"""
        factors = synthetic_data.true_factors
        n_factors = factors.shape[1]
        max_lags = 2

        A = estimate_transition_matrix(factors, max_lags=max_lags)

        # 检查companion form的下半部分是单位矩阵
        lower_block = A[n_factors:, :n_factors]
        expected_lower = np.eye(n_factors)

        np.testing.assert_array_almost_equal(
            lower_block, expected_lower, decimal=10,
            err_msg="Companion form下半部分不是单位矩阵"
        )


class TestEstimateCovarianceMatrices:
    """测试协方差矩阵估计"""

    def test_covariance_matrices_shapes(self, synthetic_data):
        """测试协方差矩阵形状"""
        obs = synthetic_data.observations
        true_params = synthetic_data.true_params
        n_factors = true_params['A'].shape[0]
        n_obs = obs.shape[1]

        # 创建模拟的平滑结果
        factors_df = pd.DataFrame(
            synthetic_data.true_factors,
            index=obs.index,
            columns=[f'Factor{i+1}' for i in range(n_factors)]
        )

        # 中心化数据
        obs_centered = obs - obs.mean()

        # 估计载荷
        Lambda = estimate_loadings(obs_centered, factors_df)

        # 创建卡尔曼滤波器并运行
        n_states = n_factors
        kf = KalmanFilter(
            A=true_params['A'],
            B=np.eye(n_states) * 0.1,
            H=Lambda,
            Q=true_params['Q'],
            R=true_params['R'],
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        filter_result = kf.filter(obs_centered.values)
        smoother_result = kf.smooth(filter_result)

        # 估计协方差矩阵
        B, Q, R = estimate_covariance_matrices(
            smoother_result,
            obs_centered,
            Lambda,
            n_factors,
            A=true_params['A'],
            n_shocks=n_factors
        )

        # 验证形状
        assert B.shape == (n_factors, n_factors), \
            f"B矩阵形状错误: 期望({n_factors}, {n_factors}), 实际{B.shape}"
        assert Q.shape == (n_factors, n_factors), \
            f"Q矩阵形状错误: 期望({n_factors}, {n_factors}), 实际{Q.shape}"
        assert R.shape == (n_obs, n_obs), \
            f"R矩阵形状错误: 期望({n_obs}, {n_obs}), 实际{R.shape}"

    def test_Q_positive_definite(self, synthetic_data):
        """测试Q矩阵正定"""
        obs = synthetic_data.observations
        true_params = synthetic_data.true_params
        n_factors = true_params['A'].shape[0]

        factors_df = pd.DataFrame(
            synthetic_data.true_factors,
            index=obs.index,
            columns=[f'Factor{i+1}' for i in range(n_factors)]
        )

        obs_centered = obs - obs.mean()
        Lambda = estimate_loadings(obs_centered, factors_df)

        n_states = n_factors
        kf = KalmanFilter(
            A=true_params['A'],
            B=np.eye(n_states) * 0.1,
            H=Lambda,
            Q=true_params['Q'],
            R=true_params['R'],
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        filter_result = kf.filter(obs_centered.values)
        smoother_result = kf.smooth(filter_result)

        B, Q, R = estimate_covariance_matrices(
            smoother_result,
            obs_centered,
            Lambda,
            n_factors,
            A=true_params['A'],
            n_shocks=n_factors
        )

        assert_positive_definite(Q, "Q矩阵")

    def test_R_diagonal_positive(self, synthetic_data):
        """测试R矩阵对角元素为正"""
        obs = synthetic_data.observations
        true_params = synthetic_data.true_params
        n_factors = true_params['A'].shape[0]

        factors_df = pd.DataFrame(
            synthetic_data.true_factors,
            index=obs.index,
            columns=[f'Factor{i+1}' for i in range(n_factors)]
        )

        obs_centered = obs - obs.mean()
        Lambda = estimate_loadings(obs_centered, factors_df)

        n_states = n_factors
        kf = KalmanFilter(
            A=true_params['A'],
            B=np.eye(n_states) * 0.1,
            H=Lambda,
            Q=true_params['Q'],
            R=true_params['R'],
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        filter_result = kf.filter(obs_centered.values)
        smoother_result = kf.smooth(filter_result)

        B, Q, R = estimate_covariance_matrices(
            smoother_result,
            obs_centered,
            Lambda,
            n_factors,
            A=true_params['A'],
            n_shocks=n_factors
        )

        R_diag = np.diag(R)
        assert np.all(R_diag > 0), \
            f"R矩阵对角元素应全为正: min={R_diag.min()}"


class TestEnsurePositiveDefinite:
    """测试正定性保证函数"""

    def test_already_positive_definite(self):
        """测试已正定矩阵不变"""
        A = np.array([[2.0, 0.5],
                      [0.5, 1.0]])

        result = _ensure_positive_definite(A)

        # 结果应该接近原矩阵
        np.testing.assert_array_almost_equal(result, A, decimal=5)

    def test_makes_positive_definite(self):
        """测试将非正定矩阵转为正定"""
        # 创建一个有负特征值的矩阵
        A = np.array([[1.0, 2.0],
                      [2.0, 1.0]])  # 特征值为3和-1

        result = _ensure_positive_definite(A)

        # 验证结果正定
        eigenvalues = np.linalg.eigvalsh(result)
        assert np.all(eigenvalues > 0), \
            f"结果矩阵不是正定: 特征值={eigenvalues}"

    def test_preserves_symmetry(self):
        """测试保持对称性"""
        A = np.array([[1.0, 0.5],
                      [0.5, 1.0]])

        result = _ensure_positive_definite(A)

        np.testing.assert_array_almost_equal(
            result, result.T, decimal=10,
            err_msg="结果矩阵不对称"
        )

    def test_custom_epsilon(self):
        """测试自定义epsilon参数"""
        A = np.array([[0.0, 0.0],
                      [0.0, 0.0]])  # 零矩阵

        epsilon = 0.01
        result = _ensure_positive_definite(A, epsilon=epsilon)

        eigenvalues = np.linalg.eigvalsh(result)
        assert np.all(eigenvalues >= epsilon - 1e-10), \
            f"最小特征值应>=epsilon: {eigenvalues.min()} < {epsilon}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
