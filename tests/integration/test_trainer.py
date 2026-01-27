# -*- coding: utf-8 -*-
"""
训练器集成测试

测试DFMTrainer的完整训练流程
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
import os
import sys
from typing import Dict
from dataclasses import dataclass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.training.trainer import DFMTrainer
from dashboard.models.DFM.train.training.config import TrainingConfig
from dashboard.models.DFM.train.core.models import TrainingResult


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


@pytest.fixture
def temp_data_file():
    """创建临时数据文件"""
    # 生成合成数据
    data = generate_synthetic_dfm_data(n_time=100, n_obs=10, n_factors=2, seed=42)
    obs = data.observations

    # 保存到临时Excel文件
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        temp_path = f.name

    obs.to_excel(temp_path, sheet_name='data')

    yield temp_path, obs

    # 清理临时文件
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_output_dir():
    """创建临时输出目录"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


class TestDFMTrainerFullPipeline:
    """测试完整训练流程"""

    def test_trainer_returns_result(self, temp_data_file, temp_output_dir):
        """测试训练器返回TrainingResult"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert isinstance(result, TrainingResult), \
            f"返回类型错误: 期望TrainingResult, 实际{type(result)}"

    def test_trainer_result_has_model(self, temp_data_file, temp_output_dir):
        """测试训练结果包含模型"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.model_result is not None, "模型结果不应为None"
        assert result.model_result.factors is not None, "因子不应为None"
        assert result.model_result.H is not None, "载荷矩阵不应为None"

    def test_trainer_result_has_metrics(self, temp_data_file, temp_output_dir):
        """测试训练结果包含评估指标"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.metrics is not None, "评估指标不应为None"
        assert np.isfinite(result.metrics.average_rmse), \
            f"训练期RMSE应为有限值: {result.metrics.average_rmse}"

    def test_trainer_progress_callback(self, temp_data_file, temp_output_dir):
        """测试进度回调"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=3,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        progress_messages = []

        def callback(msg):
            progress_messages.append(msg)

        trainer = DFMTrainer(config)
        trainer.train(progress_callback=callback, enable_export=False)

        assert len(progress_messages) > 0, "应该有进度消息"


class TestDFMTrainerExport:
    """测试导出功能"""

    def test_trainer_export_files(self, temp_data_file, temp_output_dir):
        """测试导出文件生成"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=True, export_dir=temp_output_dir)

        assert result.export_files is not None, "导出文件路径不应为None"
        assert len(result.export_files) > 0, "应该有导出文件"

    def test_trainer_export_model_file_exists(self, temp_data_file, temp_output_dir):
        """测试模型文件存在"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=True, export_dir=temp_output_dir)

        # 检查至少有一个导出文件存在
        existing_files = [
            path for path in result.export_files.values()
            if path and os.path.exists(path)
        ]
        assert len(existing_files) > 0, "至少应有一个导出文件存在"


class TestDFMTrainerMetadata:
    """测试元数据内容"""

    def test_trainer_selected_variables(self, temp_data_file, temp_output_dir):
        """测试选定变量列表"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.selected_variables is not None, "选定变量不应为None"
        assert len(result.selected_variables) == obs.shape[1], \
            f"变量数错误: 期望{obs.shape[1]}, 实际{len(result.selected_variables)}"

    def test_trainer_k_factors_stored(self, temp_data_file, temp_output_dir):
        """测试因子数存储"""
        temp_path, obs = temp_data_file
        k_factors = 3

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=k_factors,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.k_factors == k_factors, \
            f"因子数错误: 期望{k_factors}, 实际{result.k_factors}"

    def test_trainer_training_time_recorded(self, temp_data_file, temp_output_dir):
        """测试训练时间记录"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.training_time > 0, \
            f"训练时间应大于0: {result.training_time}"


class TestDFMTrainerFactorSelection:
    """测试因子数选择"""

    def test_fixed_factor_selection(self, temp_data_file, temp_output_dir):
        """测试固定因子数选择"""
        temp_path, obs = temp_data_file
        k_factors = 2

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=k_factors,
            factor_selection_method='fixed',
            max_iterations=5,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert result.k_factors == k_factors, \
            f"固定因子数应为{k_factors}, 实际{result.k_factors}"
        assert result.factor_selection_method == 'fixed', \
            f"因子选择方法应为'fixed', 实际'{result.factor_selection_method}'"


class TestDFMTrainerNumericalStability:
    """测试数值稳定性"""

    def test_no_nan_in_model_result(self, temp_data_file, temp_output_dir):
        """测试模型结果无NaN"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=10,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        model = result.model_result
        assert_no_nan_inf(model.factors, "因子")
        assert_no_nan_inf(model.H, "载荷矩阵")
        assert_no_nan_inf(model.A, "转移矩阵")
        assert_no_nan_inf(model.Q, "Q矩阵")
        assert_no_nan_inf(model.R, "R矩阵")

    def test_metrics_finite(self, temp_data_file, temp_output_dir):
        """测试评估指标为有限值"""
        temp_path, obs = temp_data_file

        config = TrainingConfig(
            data_path=temp_path,
            training_start=obs.index[0].strftime('%Y-%m-%d'),
            train_end=obs.index[70].strftime('%Y-%m-%d'),
            validation_start=obs.index[71].strftime('%Y-%m-%d'),
            validation_end=obs.index[99].strftime('%Y-%m-%d'),
            k_factors=2,
            max_iterations=10,
            enable_variable_selection=False,
            output_dir=temp_output_dir
        )

        trainer = DFMTrainer(config)
        result = trainer.train(enable_export=False)

        assert np.isfinite(result.metrics.average_rmse), \
            f"训练期RMSE应为有限值: {result.metrics.average_rmse}"
        assert np.isfinite(result.metrics.average_rmse_validation), \
            f"验证期RMSE应为有限值: {result.metrics.average_rmse_validation}"
        assert np.isfinite(result.metrics.weighted_average_rmse), \
            f"加权RMSE应为有限值: {result.metrics.weighted_average_rmse}"


class TestTrainingConfigValidation:
    """测试训练配置验证"""

    def test_invalid_k_factors_raises(self, temp_data_file, temp_output_dir):
        """测试无效因子数抛出异常"""
        temp_path, obs = temp_data_file

        with pytest.raises(ValueError):
            TrainingConfig(
                data_path=temp_path,
                training_start=obs.index[0].strftime('%Y-%m-%d'),
                train_end=obs.index[70].strftime('%Y-%m-%d'),
                validation_start=obs.index[71].strftime('%Y-%m-%d'),
                validation_end=obs.index[99].strftime('%Y-%m-%d'),
                k_factors=0,
                output_dir=temp_output_dir
            )

    def test_invalid_max_iterations_raises(self, temp_data_file, temp_output_dir):
        """测试无效迭代次数抛出异常"""
        temp_path, obs = temp_data_file

        with pytest.raises(ValueError):
            TrainingConfig(
                data_path=temp_path,
                training_start=obs.index[0].strftime('%Y-%m-%d'),
                train_end=obs.index[70].strftime('%Y-%m-%d'),
                validation_start=obs.index[71].strftime('%Y-%m-%d'),
                validation_end=obs.index[99].strftime('%Y-%m-%d'),
                max_iterations=0,
                output_dir=temp_output_dir
            )

    def test_nonexistent_data_file_raises(self, temp_output_dir):
        """测试不存在的数据文件抛出异常"""
        with pytest.raises(FileNotFoundError):
            TrainingConfig(
                data_path='/nonexistent/path/data.xlsx',
                training_start='2020-01-01',
                train_end='2026-06-01',
                validation_start='2026-07-01',
                validation_end='2028-04-01',
                output_dir=temp_output_dir
            )

    def test_invalid_factor_selection_method_raises(self, temp_data_file, temp_output_dir):
        """测试无效因子选择方法抛出异常"""
        temp_path, obs = temp_data_file

        with pytest.raises(ValueError):
            TrainingConfig(
                data_path=temp_path,
                training_start=obs.index[0].strftime('%Y-%m-%d'),
                train_end=obs.index[70].strftime('%Y-%m-%d'),
                validation_start=obs.index[71].strftime('%Y-%m-%d'),
                validation_end=obs.index[99].strftime('%Y-%m-%d'),
                factor_selection_method='invalid_method',
                output_dir=temp_output_dir
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
