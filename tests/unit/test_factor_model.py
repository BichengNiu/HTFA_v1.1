# -*- coding: utf-8 -*-
"""
DFM模型单元测试

测试DFMModel类的初始化、预处理、PCA初始化和拟合功能
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os
from typing import Tuple, Dict
from dataclasses import dataclass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.core.factor_model import DFMModel
from dashboard.models.DFM.train.core.models import DFMModelResult


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


class TestDFMModelInit:
    """测试DFM模型初始化"""

    def test_init_params_stored(self):
        """测试初始化参数正确存储"""
        n_factors = 3
        max_lags = 2
        max_iter = 50
        tolerance = 1e-5

        model = DFMModel(
            n_factors=n_factors,
            max_lags=max_lags,
            max_iter=max_iter,
            tolerance=tolerance
        )

        assert model.n_factors == n_factors, \
            f"n_factors存储错误: 期望{n_factors}, 实际{model.n_factors}"
        assert model.max_lags == max_lags, \
            f"max_lags存储错误: 期望{max_lags}, 实际{model.max_lags}"
        assert model.max_iter == max_iter, \
            f"max_iter存储错误: 期望{max_iter}, 实际{model.max_iter}"
        assert model.tolerance == tolerance, \
            f"tolerance存储错误: 期望{tolerance}, 实际{model.tolerance}"

    def test_init_default_params(self):
        """测试默认参数值"""
        model = DFMModel(n_factors=2)

        assert model.max_lags == 1, "默认max_lags应为1"
        assert model.max_iter == 30, "默认max_iter应为30"
        assert model.tolerance == 1e-6, "默认tolerance应为1e-6"
        assert model.random_seed == 42, "默认random_seed应为42"

    def test_init_results_none(self):
        """测试初始化后results_为None"""
        model = DFMModel(n_factors=2)

        assert model.results_ is None, "初始化后results_应为None"


class TestDFMModelPreprocess:
    """测试数据预处理"""

    def test_preprocess_output_shapes(self, synthetic_data):
        """测试预处理输出形状"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations
        n_time, n_obs = obs.shape

        obs_centered, Z_std, means, stds = model._preprocess_data(obs)

        assert obs_centered.shape == (n_time, n_obs), \
            f"中心化数据形状错误: {obs_centered.shape}"
        assert Z_std.shape == (n_time, n_obs), \
            f"标准化数据形状错误: {Z_std.shape}"
        assert means.shape == (n_obs,), \
            f"均值向量形状错误: {means.shape}"
        assert stds.shape == (n_obs,), \
            f"标准差向量形状错误: {stds.shape}"

    def test_preprocess_centering(self, synthetic_data):
        """测试中心化正确性"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        obs_centered, _, means, _ = model._preprocess_data(obs)

        # 中心化数据的均值应接近0
        centered_means = obs_centered.mean().values
        np.testing.assert_array_almost_equal(
            centered_means, np.zeros(obs.shape[1]), decimal=10,
            err_msg="中心化后均值不为0"
        )

    def test_preprocess_standardization(self, synthetic_data):
        """测试标准化正确性"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        _, Z_std, _, stds = model._preprocess_data(obs)

        # 标准化数据的标准差应接近1
        std_of_standardized = np.std(Z_std, axis=0)
        np.testing.assert_array_almost_equal(
            std_of_standardized, np.ones(obs.shape[1]), decimal=1,
            err_msg="标准化后标准差不为1"
        )

    def test_preprocess_no_nan(self, synthetic_data):
        """测试预处理结果无NaN"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        obs_centered, Z_std, means, stds = model._preprocess_data(obs)

        assert_no_nan_inf(obs_centered.values, "中心化数据")
        assert_no_nan_inf(Z_std, "标准化数据")
        assert_no_nan_inf(means, "均值")
        assert_no_nan_inf(stds, "标准差")


class TestDFMModelPCAInit:
    """测试PCA初始化"""

    def test_pca_init_factors_shape(self, synthetic_data):
        """测试PCA初始化因子形状"""
        n_factors = 2
        model = DFMModel(n_factors=n_factors)
        obs = synthetic_data.observations
        n_time = obs.shape[0]

        obs_centered, Z_std, means, stds = model._preprocess_data(obs)
        factors, loadings, V = model._initialize_factors_pca(
            Z_std, obs_centered, means, stds
        )

        assert factors.shape == (n_time, n_factors), \
            f"初始因子形状错误: 期望({n_time}, {n_factors}), 实际{factors.shape}"

    def test_pca_init_loadings_shape(self, synthetic_data):
        """测试PCA初始化载荷形状"""
        n_factors = 2
        model = DFMModel(n_factors=n_factors)
        obs = synthetic_data.observations
        n_obs = obs.shape[1]

        obs_centered, Z_std, means, stds = model._preprocess_data(obs)
        factors, loadings, V = model._initialize_factors_pca(
            Z_std, obs_centered, means, stds
        )

        assert loadings.shape == (n_obs, n_factors), \
            f"初始载荷形状错误: 期望({n_obs}, {n_factors}), 实际{loadings.shape}"

    def test_pca_init_no_nan(self, synthetic_data):
        """测试PCA初始化结果无NaN"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        obs_centered, Z_std, means, stds = model._preprocess_data(obs)
        factors, loadings, V = model._initialize_factors_pca(
            Z_std, obs_centered, means, stds
        )

        assert_no_nan_inf(factors.values, "初始因子")
        assert_no_nan_inf(loadings, "初始载荷")
        assert_no_nan_inf(V, "V矩阵")


class TestDFMModelFit:
    """测试DFM模型拟合"""

    def test_fit_returns_result(self, synthetic_data):
        """测试fit()返回DFMModelResult"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert isinstance(result, DFMModelResult), \
            f"返回类型错误: 期望DFMModelResult, 实际{type(result)}"

    def test_fit_factors_shape(self, synthetic_data):
        """测试拟合后因子形状"""
        n_factors = 2
        model = DFMModel(n_factors=n_factors, max_iter=5)
        obs = synthetic_data.observations
        n_time = obs.shape[0]

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        # 因子形状应为 (n_factors, n_time_full)
        assert result.factors.shape == (n_factors, n_time), \
            f"因子形状错误: 期望({n_factors}, {n_time}), 实际{result.factors.shape}"

    def test_fit_loadings_shape(self, synthetic_data):
        """测试拟合后载荷形状"""
        n_factors = 2
        model = DFMModel(n_factors=n_factors, max_iter=5)
        obs = synthetic_data.observations
        n_obs = obs.shape[1]

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.H.shape == (n_obs, n_factors), \
            f"载荷矩阵形状错误: 期望({n_obs}, {n_factors}), 实际{result.H.shape}"

    def test_fit_full_data_extension(self, synthetic_data):
        """测试因子扩展到完整时间范围"""
        n_factors = 2
        model = DFMModel(n_factors=n_factors, max_iter=5)
        obs = synthetic_data.observations
        n_time_full = obs.shape[0]

        # 训练期只用前70个点
        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[69].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        # 因子应该覆盖完整时间范围
        assert result.factors.shape[1] == n_time_full, \
            f"因子时间长度错误: 期望{n_time_full}, 实际{result.factors.shape[1]}"

    def test_fit_train_indices(self, synthetic_data):
        """测试训练期索引正确设置"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[69].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.train_start_idx == 0, \
            f"train_start_idx错误: 期望0, 实际{result.train_start_idx}"
        assert result.train_end_idx == 70, \
            f"train_end_idx错误: 期望70, 实际{result.train_end_idx}"

    def test_fit_no_nan_in_results(self, synthetic_data):
        """测试拟合结果无NaN"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert_no_nan_inf(result.factors, "因子")
        assert_no_nan_inf(result.factors_smooth, "平滑因子")
        assert_no_nan_inf(result.H, "载荷矩阵H")
        assert_no_nan_inf(result.A, "转移矩阵A")
        assert_no_nan_inf(result.Q, "状态噪声协方差Q")
        assert_no_nan_inf(result.R, "观测噪声协方差R")

    def test_fit_loglikelihood_finite(self, synthetic_data):
        """测试对数似然为有限值"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert np.isfinite(result.log_likelihood), \
            f"对数似然不是有限值: {result.log_likelihood}"

    def test_fit_variable_names_stored(self, synthetic_data):
        """测试变量名正确存储"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.variable_names is not None, "变量名不应为None"
        assert len(result.variable_names) == obs.shape[1], \
            f"变量名数量错误: 期望{obs.shape[1]}, 实际{len(result.variable_names)}"


class TestDFMModelConvergence:
    """测试EM算法收敛"""

    def test_convergence_with_sufficient_iterations(self, synthetic_data):
        """测试足够迭代次数下的收敛"""
        model = DFMModel(n_factors=2, max_iter=30, tolerance=1e-4)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        # 检查是否收敛或达到最大迭代次数
        assert result.iterations > 0, "迭代次数应大于0"
        assert result.iterations <= model.max_iter, \
            f"迭代次数超过最大值: {result.iterations} > {model.max_iter}"

    def test_convergence_iterations_recorded(self, synthetic_data):
        """测试迭代次数正确记录"""
        model = DFMModel(n_factors=2, max_iter=10)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert hasattr(result, 'iterations'), "结果应包含iterations属性"
        assert isinstance(result.iterations, int), "iterations应为整数"

    def test_convergence_flag_set(self, synthetic_data):
        """测试收敛标志正确设置"""
        model = DFMModel(n_factors=2, max_iter=30)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert hasattr(result, 'converged'), "结果应包含converged属性"
        assert isinstance(result.converged, bool), "converged应为布尔值"


class TestDFMModelEdgeCases:
    """测试边界情况"""

    def test_single_factor(self):
        """测试单因子模型"""
        data = generate_synthetic_dfm_data(n_time=80, n_obs=5, n_factors=1, seed=42)
        model = DFMModel(n_factors=1, max_iter=5)
        obs = data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[60].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.factors.shape[0] == 1, "单因子模型应只有1个因子"
        assert_no_nan_inf(result.factors, "单因子")

    def test_many_factors(self):
        """测试多因子模型"""
        data = generate_synthetic_dfm_data(n_time=100, n_obs=15, n_factors=3, seed=42)
        model = DFMModel(n_factors=3, max_iter=5)
        obs = data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.factors.shape[0] == 3, "应有3个因子"
        assert_no_nan_inf(result.factors, "多因子")

    def test_missing_training_dates_raises(self, synthetic_data):
        """测试缺少训练日期时抛出异常"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        with pytest.raises(ValueError):
            model.fit(obs, None, None)

    def test_invalid_date_range_raises(self, synthetic_data):
        """测试无效日期范围时抛出异常"""
        model = DFMModel(n_factors=2)
        obs = synthetic_data.observations

        # 使用超出数据范围的日期
        with pytest.raises(ValueError):
            model.fit(obs, '2030-01-01', '2030-12-31')

    def test_progress_callback(self, synthetic_data):
        """测试进度回调函数"""
        model = DFMModel(n_factors=2, max_iter=3)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        progress_messages = []

        def callback(msg):
            progress_messages.append(msg)

        result = model.fit(obs, training_start, train_end, progress_callback=callback)

        assert len(progress_messages) > 0, "应该有进度消息"


class TestDFMModelKalmanGains:
    """测试卡尔曼增益历史"""

    def test_kalman_gains_stored(self, synthetic_data):
        """测试卡尔曼增益历史存储"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.kalman_gains_history is not None, \
            "卡尔曼增益历史不应为None"

    def test_factor_states_predicted_stored(self, synthetic_data):
        """测试先验因子状态存储"""
        model = DFMModel(n_factors=2, max_iter=5)
        obs = synthetic_data.observations

        training_start = obs.index[0].strftime('%Y-%m-%d')
        train_end = obs.index[70].strftime('%Y-%m-%d')

        result = model.fit(obs, training_start, train_end)

        assert result.factor_states_predicted is not None, \
            "先验因子状态不应为None"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
