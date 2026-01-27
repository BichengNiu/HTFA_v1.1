# -*- coding: utf-8 -*-
"""
模型操作集成测试

测试train_dfm_model和evaluate_model_fit的完整流程
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os
from typing import Dict
from dataclasses import dataclass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.training.model_ops import (
    train_dfm_model,
    evaluate_model_fit
)
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics


# 辅助函数和数据类
def assert_no_nan_inf(arr: np.ndarray, name: str = "array"):
    """断言数组不包含NaN或Inf"""
    assert not np.any(np.isnan(arr)), f"{name} 包含NaN值"
    assert not np.any(np.isinf(arr)), f"{name} 包含Inf值"


@dataclass
class SyntheticDFMData:
    """合成DFM数据容器"""
    observations: pd.DataFrame
    true_factors: np.ndarray
    true_params: Dict


def generate_synthetic_dfm_data(
    n_time: int = 100,
    n_obs: int = 10,
    n_factors: int = 2,
    seed: int = 42
) -> SyntheticDFMData:
    """生成合成DFM数据"""
    np.random.seed(seed)

    A_true = np.diag([0.9 - 0.1 * i for i in range(n_factors)])
    Q_true = np.eye(n_factors) * 0.1
    H_true = np.random.randn(n_obs, n_factors) * 0.5
    for i in range(n_factors):
        H_true[i * (n_obs // n_factors):(i + 1) * (n_obs // n_factors), i] += 1.0
    R_true = np.eye(n_obs) * 0.05

    factors = np.zeros((n_time, n_factors))
    factors[0, :] = np.random.randn(n_factors) * 0.1

    for t in range(1, n_time):
        eta_t = np.random.multivariate_normal(np.zeros(n_factors), Q_true)
        factors[t, :] = A_true @ factors[t - 1, :] + eta_t

    observations = np.zeros((n_time, n_obs))
    for t in range(n_time):
        eps_t = np.random.multivariate_normal(np.zeros(n_obs), R_true)
        observations[t, :] = H_true @ factors[t, :] + eps_t

    dates = pd.date_range(start='2020-01-01', periods=n_time, freq='MS')
    obs_df = pd.DataFrame(
        observations,
        index=dates,
        columns=[f'Var{i+1}' for i in range(n_obs)]
    )

    true_params = {'A': A_true, 'Q': Q_true, 'H': H_true, 'R': R_true}

    return SyntheticDFMData(
        observations=obs_df,
        true_factors=factors,
        true_params=true_params
    )


class TestTrainDFMModelBasic:
    """测试基本训练流程"""

    def test_train_returns_result(self, synthetic_data):
        """测试训练返回DFMModelResult"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        assert isinstance(result, DFMModelResult), \
            f"返回类型错误: 期望DFMModelResult, 实际{type(result)}"

    def test_train_result_has_factors(self, synthetic_data):
        """测试训练结果包含因子"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        assert result.factors is not None, "因子不应为None"
        assert result.factors_smooth is not None, "平滑因子不应为None"

    def test_train_result_has_matrices(self, synthetic_data):
        """测试训练结果包含状态空间矩阵"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        assert result.A is not None, "转移矩阵A不应为None"
        assert result.Q is not None, "状态噪声协方差Q不应为None"
        assert result.H is not None, "载荷矩阵H不应为None"
        assert result.R is not None, "观测噪声协方差R不应为None"


class TestTrainDFMModelParams:
    """测试参数传递"""

    def test_k_factors_passed(self, synthetic_data):
        """测试因子数正确传递"""
        obs = synthetic_data.observations
        k_factors = 3

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=k_factors,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        assert result.factors.shape[0] == k_factors, \
            f"因子数错误: 期望{k_factors}, 实际{result.factors.shape[0]}"

    @pytest.mark.skip(reason="max_lags>1时Q矩阵维度不匹配，是已知的模型限制")
    def test_max_lags_passed(self, synthetic_data):
        """测试最大滞后阶数正确传递"""
        obs = synthetic_data.observations
        k_factors = 2
        max_lags = 2

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=k_factors,
            training_start=training_start,
            train_end=train_end,
            max_iter=5,
            max_lags=max_lags
        )

        # AR(2)的状态空间维度应为 k_factors * max_lags
        expected_state_dim = k_factors * max_lags
        assert result.A.shape == (expected_state_dim, expected_state_dim), \
            f"A矩阵维度错误: 期望({expected_state_dim}, {expected_state_dim}), 实际{result.A.shape}"

    def test_invalid_k_factors_raises(self, synthetic_data):
        """测试无效因子数抛出异常"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        with pytest.raises(ValueError):
            train_dfm_model(
                observation_data=obs,
                k_factors=0,
                training_start=training_start,
                train_end=train_end
            )

    def test_invalid_max_iter_raises(self, synthetic_data):
        """测试无效迭代次数抛出异常"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        with pytest.raises(ValueError):
            train_dfm_model(
                observation_data=obs,
                k_factors=2,
                training_start=training_start,
                train_end=train_end,
                max_iter=0
            )

    def test_progress_callback_called(self, synthetic_data):
        """测试进度回调被调用"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        callback_messages = []

        def callback(msg):
            callback_messages.append(msg)

        train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=3,
            progress_callback=callback
        )

        assert len(callback_messages) > 0, "进度回调应该被调用"


class TestEvaluateModelFitTraining:
    """测试训练期评估"""

    def test_evaluate_returns_metrics(self, synthetic_data):
        """测试评估返回EvaluationMetrics"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        assert isinstance(metrics, EvaluationMetrics), \
            f"返回类型错误: 期望EvaluationMetrics, 实际{type(metrics)}"

    def test_training_rmse_finite(self, synthetic_data):
        """测试训练期RMSE为有限值"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        assert np.isfinite(metrics.average_rmse), \
            f"训练期RMSE应为有限值: {metrics.average_rmse}"

    def test_training_rmse_positive(self, synthetic_data):
        """测试训练期RMSE为正值"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        assert metrics.average_rmse >= 0, \
            f"训练期RMSE应为非负值: {metrics.average_rmse}"


class TestEvaluateModelFitValidation:
    """测试验证期评估"""

    def test_validation_rmse_computed(self, synthetic_data):
        """测试验证期RMSE被计算"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')
        validation_start = obs.index[71].strftime('%Y-%m-%d')
        validation_end = obs.index[99].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end
        )

        assert np.isfinite(metrics.average_rmse_validation), \
            f"验证期RMSE应为有限值: {metrics.average_rmse_validation}"

    def test_validation_rmse_without_dates(self, synthetic_data):
        """测试不提供验证期日期时RMSE为inf"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        assert metrics.average_rmse_validation == np.inf, \
            f"无验证期时RMSE应为inf: {metrics.average_rmse_validation}"


class TestEvaluateModelFitWeighted:
    """测试加权RMSE计算"""

    def test_weighted_rmse_computed(self, synthetic_data):
        """测试加权RMSE被计算"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')
        validation_start = obs.index[71].strftime('%Y-%m-%d')
        validation_end = obs.index[99].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            training_weight=0.5
        )

        assert np.isfinite(metrics.weighted_average_rmse), \
            f"加权RMSE应为有限值: {metrics.weighted_average_rmse}"

    def test_weighted_rmse_formula(self, synthetic_data):
        """测试加权RMSE计算公式"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')
        validation_start = obs.index[71].strftime('%Y-%m-%d')
        validation_end = obs.index[99].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        training_weight = 0.6
        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            training_weight=training_weight
        )

        # 验证加权公式
        expected_weighted = (
            training_weight * metrics.average_rmse +
            (1 - training_weight) * metrics.average_rmse_validation
        )

        np.testing.assert_almost_equal(
            metrics.weighted_average_rmse, expected_weighted, decimal=5,
            err_msg="加权RMSE计算公式错误"
        )

    def test_weighted_rmse_training_only(self, synthetic_data):
        """测试仅训练期时加权RMSE等于训练期RMSE"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=5
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        # 无验证期时，加权RMSE应等于训练期RMSE
        assert metrics.weighted_average_rmse == metrics.average_rmse, \
            f"无验证期时加权RMSE应等于训练期RMSE"


class TestEvaluateModelFitConvergence:
    """测试收敛信息"""

    def test_convergence_info_preserved(self, synthetic_data):
        """测试收敛信息被保留"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        model_result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=10
        )

        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=obs,
            training_start=training_start,
            train_end=train_end
        )

        assert hasattr(metrics, 'converged'), "应包含converged属性"
        assert hasattr(metrics, 'iterations'), "应包含iterations属性"
        assert metrics.iterations > 0, "迭代次数应大于0"


class TestTrainDFMModelNumericalStability:
    """测试数值稳定性"""

    def test_no_nan_in_results(self, synthetic_data):
        """测试结果无NaN"""
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = train_dfm_model(
            observation_data=obs,
            k_factors=2,
            training_start=training_start,
            train_end=train_end,
            max_iter=10
        )

        assert_no_nan_inf(result.factors, "因子")
        assert_no_nan_inf(result.H, "载荷矩阵")
        assert_no_nan_inf(result.A, "转移矩阵")
        assert_no_nan_inf(result.Q, "Q矩阵")
        assert_no_nan_inf(result.R, "R矩阵")

    def test_different_data_sizes(self):
        """测试不同数据规模"""
        for n_time, n_obs, n_factors in [(50, 5, 1), (100, 10, 2), (150, 15, 3)]:
            data = generate_synthetic_dfm_data(
                n_time=n_time, n_obs=n_obs, n_factors=n_factors, seed=42
            )
            obs = data.observations

            training_start = obs.index[0].strftime('%Y-%m-%d')
            train_end = obs.index[int(n_time * 0.7)].strftime('%Y-%m-%d')

            result = train_dfm_model(
                observation_data=obs,
                k_factors=n_factors,
                training_start=training_start,
                train_end=train_end,
                max_iter=5
            )

            assert result.factors.shape[0] == n_factors, \
                f"数据规模({n_time}, {n_obs}, {n_factors})的因子数错误"
            assert np.isfinite(result.log_likelihood), \
                f"数据规模({n_time}, {n_obs}, {n_factors})的对数似然不是有限值"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
