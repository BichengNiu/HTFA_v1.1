# -*- coding: utf-8 -*-
"""
卡尔曼滤波单元测试

测试KalmanFilter类的滤波和平滑功能
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.core.kalman import KalmanFilter
from dashboard.models.DFM.train.core.models import KalmanFilterResult, KalmanSmootherResult


# 辅助函数（从conftest复制，避免导入问题）
def assert_no_nan_inf(arr: np.ndarray, name: str = "array"):
    """断言数组不包含NaN或Inf"""
    assert not np.any(np.isnan(arr)), f"{name} 包含NaN值"
    assert not np.any(np.isinf(arr)), f"{name} 包含Inf值"


class TestKalmanFilterDimensions:
    """测试卡尔曼滤波结果维度"""

    def test_filter_output_dimensions(self, kalman_matrices, synthetic_data):
        """测试滤波结果维度正确"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values
        n_time, n_obs = Z.shape
        n_states = kalman_matrices['A'].shape[0]

        result = kf.filter(Z)

        # 验证滤波状态维度
        assert result.x_filtered.shape == (n_time, n_states), \
            f"x_filtered形状错误: 期望({n_time}, {n_states}), 实际{result.x_filtered.shape}"

        # 验证预测状态维度
        assert result.x_predicted.shape == (n_time, n_states), \
            f"x_predicted形状错误: 期望({n_time}, {n_states}), 实际{result.x_predicted.shape}"

        # 验证协方差维度 (n_states, n_states, n_time)
        assert result.P_filtered.shape == (n_states, n_states, n_time), \
            f"P_filtered形状错误: 期望({n_states}, {n_states}, {n_time}), 实际{result.P_filtered.shape}"

        assert result.P_predicted.shape == (n_states, n_states, n_time), \
            f"P_predicted形状错误: 期望({n_states}, {n_states}, {n_time}), 实际{result.P_predicted.shape}"

        # 验证新息维度
        assert result.innovation.shape == (n_time, n_obs), \
            f"innovation形状错误: 期望({n_time}, {n_obs}), 实际{result.innovation.shape}"

    def test_smoother_output_dimensions(self, kalman_matrices, synthetic_data):
        """测试平滑结果维度正确"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values
        n_time = Z.shape[0]
        n_states = kalman_matrices['A'].shape[0]

        filter_result = kf.filter(Z)
        smoother_result = kf.smooth(filter_result)

        # 验证平滑状态维度 (n_states, n_time)
        assert smoother_result.x_smoothed.shape == (n_states, n_time), \
            f"x_smoothed形状错误: 期望({n_states}, {n_time}), 实际{smoother_result.x_smoothed.shape}"

        # 验证平滑协方差维度
        assert smoother_result.P_smoothed.shape == (n_states, n_states, n_time), \
            f"P_smoothed形状错误: 期望({n_states}, {n_states}, {n_time}), 实际{smoother_result.P_smoothed.shape}"

        # 验证滞后协方差维度
        assert smoother_result.P_lag_smoothed.shape == (n_states, n_states, n_time - 1), \
            f"P_lag_smoothed形状错误: 期望({n_states}, {n_states}, {n_time - 1}), 实际{smoother_result.P_lag_smoothed.shape}"


class TestKalmanFilterLoglikelihood:
    """测试对数似然计算"""

    def test_loglikelihood_is_finite(self, kalman_matrices, synthetic_data):
        """测试对数似然为有限值"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        result = kf.filter(Z)

        assert np.isfinite(result.loglikelihood), \
            f"对数似然不是有限值: {result.loglikelihood}"

    def test_loglikelihood_is_negative(self, kalman_matrices, synthetic_data):
        """测试对数似然为负值（概率密度的对数）"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        result = kf.filter(Z)

        # 对数似然通常为负值
        assert result.loglikelihood < 0, \
            f"对数似然应为负值: {result.loglikelihood}"

    def test_loglikelihood_increases_with_better_model(self, synthetic_data):
        """测试更好的模型参数产生更高的对数似然"""
        Z = synthetic_data.observations.values
        true_params = synthetic_data.true_params
        n_states = true_params['A'].shape[0]
        n_obs = true_params['H'].shape[0]

        # 使用真实参数
        kf_true = KalmanFilter(
            A=true_params['A'],
            B=np.eye(n_states) * 0.1,
            H=true_params['H'],
            Q=true_params['Q'],
            R=true_params['R'],
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        # 使用随机参数
        np.random.seed(999)
        kf_random = KalmanFilter(
            A=np.eye(n_states) * 0.5,
            B=np.eye(n_states) * 0.1,
            H=np.random.randn(n_obs, n_states),
            Q=np.eye(n_states),
            R=np.eye(n_obs),
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        result_true = kf_true.filter(Z)
        result_random = kf_random.filter(Z)

        # 真实参数应该产生更高的对数似然
        assert result_true.loglikelihood > result_random.loglikelihood, \
            f"真实参数的对数似然({result_true.loglikelihood:.2f})应大于随机参数({result_random.loglikelihood:.2f})"


class TestKalmanGainsHistory:
    """测试卡尔曼增益历史记录"""

    def test_kalman_gains_history_exists(self, kalman_matrices, synthetic_data):
        """测试卡尔曼增益历史存在"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        result = kf.filter(Z)

        assert result.kalman_gains_history is not None, \
            "卡尔曼增益历史不应为None"
        assert len(result.kalman_gains_history) > 0, \
            "卡尔曼增益历史不应为空"

    def test_kalman_gains_history_length(self, kalman_matrices, synthetic_data):
        """测试卡尔曼增益历史长度"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values
        n_time = Z.shape[0]

        result = kf.filter(Z)

        assert len(result.kalman_gains_history) == n_time, \
            f"卡尔曼增益历史长度错误: 期望{n_time}, 实际{len(result.kalman_gains_history)}"

    def test_kalman_gains_shape(self, kalman_matrices, synthetic_data):
        """测试卡尔曼增益矩阵形状"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values
        n_states = kalman_matrices['A'].shape[0]
        n_obs = kalman_matrices['H'].shape[0]

        result = kf.filter(Z)

        # 检查非None的增益矩阵形状
        for t, K_t in enumerate(result.kalman_gains_history):
            if K_t is not None:
                assert K_t.shape == (n_states, n_obs), \
                    f"时刻{t}的卡尔曼增益形状错误: 期望({n_states}, {n_obs}), 实际{K_t.shape}"


class TestKalmanNumericalStability:
    """测试数值稳定性"""

    def test_filter_no_nan(self, kalman_matrices, synthetic_data):
        """测试滤波结果无NaN"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        result = kf.filter(Z)

        assert_no_nan_inf(result.x_filtered, "x_filtered")
        assert_no_nan_inf(result.x_predicted, "x_predicted")
        assert_no_nan_inf(result.P_filtered, "P_filtered")
        assert_no_nan_inf(result.P_predicted, "P_predicted")

    def test_smoother_no_nan(self, kalman_matrices, synthetic_data):
        """测试平滑结果无NaN"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        filter_result = kf.filter(Z)
        smoother_result = kf.smooth(filter_result)

        assert_no_nan_inf(smoother_result.x_smoothed, "x_smoothed")
        assert_no_nan_inf(smoother_result.P_smoothed, "P_smoothed")
        assert_no_nan_inf(smoother_result.P_lag_smoothed, "P_lag_smoothed")

    def test_covariance_positive_semidefinite(self, kalman_matrices, synthetic_data):
        """测试协方差矩阵正半定"""
        kf = KalmanFilter(**kalman_matrices)
        Z = synthetic_data.observations.values

        result = kf.filter(Z)
        n_time = Z.shape[0]

        # 检查每个时刻的协方差矩阵
        for t in range(n_time):
            P_t = result.P_filtered[:, :, t]
            eigenvalues = np.linalg.eigvalsh(P_t)
            assert np.all(eigenvalues >= -1e-10), \
                f"时刻{t}的P_filtered不是正半定: 最小特征值={eigenvalues.min()}"

    def test_filter_with_missing_data(self, kalman_matrices):
        """测试处理缺失数据"""
        kf = KalmanFilter(**kalman_matrices)
        n_time = 50
        n_obs = kalman_matrices['H'].shape[0]

        # 创建带缺失值的数据
        np.random.seed(42)
        Z = np.random.randn(n_time, n_obs)
        # 随机设置一些NaN
        mask = np.random.random((n_time, n_obs)) < 0.1
        Z[mask] = np.nan

        result = kf.filter(Z)

        # 滤波结果不应包含NaN
        assert_no_nan_inf(result.x_filtered, "x_filtered (with missing data)")
        assert_no_nan_inf(result.x_predicted, "x_predicted (with missing data)")


class TestKalmanFilterEdgeCases:
    """测试边界情况"""

    def test_single_observation(self, kalman_matrices):
        """测试单个观测变量"""
        n_states = kalman_matrices['A'].shape[0]

        # 修改为单个观测变量
        H_single = kalman_matrices['H'][:1, :]
        R_single = kalman_matrices['R'][:1, :1]

        kf = KalmanFilter(
            A=kalman_matrices['A'],
            B=kalman_matrices['B'],
            H=H_single,
            Q=kalman_matrices['Q'],
            R=R_single,
            x0=kalman_matrices['x0'],
            P0=kalman_matrices['P0']
        )

        np.random.seed(42)
        Z = np.random.randn(50, 1)

        result = kf.filter(Z)

        assert result.x_filtered.shape == (50, n_states)
        assert np.isfinite(result.loglikelihood)

    def test_single_state(self):
        """测试单个状态变量"""
        n_time = 50
        n_obs = 5

        kf = KalmanFilter(
            A=np.array([[0.9]]),
            B=np.array([[0.1]]),
            H=np.random.randn(n_obs, 1),
            Q=np.array([[0.1]]),
            R=np.eye(n_obs) * 0.05,
            x0=np.array([0.0]),
            P0=np.array([[1.0]])
        )

        np.random.seed(42)
        Z = np.random.randn(n_time, n_obs)

        result = kf.filter(Z)

        assert result.x_filtered.shape == (n_time, 1)
        assert np.isfinite(result.loglikelihood)

    def test_identity_transition(self, synthetic_data):
        """测试单位转移矩阵（随机游走）"""
        Z = synthetic_data.observations.values
        n_obs = Z.shape[1]
        n_states = 2

        kf = KalmanFilter(
            A=np.eye(n_states),
            B=np.eye(n_states) * 0.1,
            H=np.random.randn(n_obs, n_states),
            Q=np.eye(n_states) * 0.1,
            R=np.eye(n_obs) * 0.05,
            x0=np.zeros(n_states),
            P0=np.eye(n_states)
        )

        result = kf.filter(Z)

        assert_no_nan_inf(result.x_filtered, "x_filtered (identity A)")
        assert np.isfinite(result.loglikelihood)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
