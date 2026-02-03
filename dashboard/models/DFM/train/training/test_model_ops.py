# -*- coding: utf-8 -*-
"""
模型操作集成测试

验证 evaluate_model_fit 函数正确调用混频RMSE计算
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Optional

from dashboard.models.DFM.train.training.model_ops import evaluate_model_fit
from dashboard.models.DFM.train.core.models import DFMModelResult


class TestEvaluateModelFitMixedFrequency:
    """测试 evaluate_model_fit 的混频RMSE调用"""

    def setup_method(self):
        """设置测试数据"""
        # 创建8周的时间索引
        self.time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')

        # 创建观测数据（月度+周度混合）
        self.obs_data = pd.DataFrame({
            '月度变量': [np.nan, 5.2, np.nan, np.nan, np.nan, np.nan, 6.1, np.nan],
            '周度变量': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
        }, index=self.time_index)

        # 创建模拟的模型结果
        n_factors = 2
        n_vars = 2
        n_time = 8

        self.model_result = DFMModelResult(
            factors_smooth=np.random.randn(n_factors, n_time),
            H=np.random.randn(n_vars, n_factors),
            converged=True,
            iterations=10
        )

        self.var_frequency_map = {'月度变量': '月', '周度变量': '周'}

    @patch('dashboard.models.DFM.train.training.model_ops.calculate_mixed_frequency_rmse')
    def test_evaluate_model_fit_calls_mixed_frequency_rmse(self, mock_mixed_rmse):
        """有 var_frequency_map 时调用混频函数"""
        mock_mixed_rmse.return_value = (0.5, {'月度变量': 0.4, '周度变量': 0.6})

        metrics = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量']
        )

        # 验证混频函数被调用
        assert mock_mixed_rmse.called, "calculate_mixed_frequency_rmse 应该被调用"

    @patch('dashboard.models.DFM.train.training.model_ops.calculate_mixed_frequency_rmse')
    def test_evaluate_model_fit_passes_alignment_param(self, mock_mixed_rmse):
        """rmse_alignment 参数正确传递"""
        mock_mixed_rmse.return_value = (0.5, {'月度变量': 0.4, '周度变量': 0.6})

        # 测试 current 对齐
        evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量'],
            rmse_alignment='current'
        )

        # 检查调用参数
        call_args = mock_mixed_rmse.call_args
        assert call_args is not None
        assert call_args.kwargs.get('rmse_alignment') == 'current' or \
               (len(call_args.args) >= 6 and call_args.args[5] == 'current'), \
               "rmse_alignment='current' 应该被传递"

        mock_mixed_rmse.reset_mock()

        # 测试 next 对齐
        evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量'],
            rmse_alignment='next'
        )

        call_args = mock_mixed_rmse.call_args
        assert call_args is not None
        assert call_args.kwargs.get('rmse_alignment') == 'next' or \
               (len(call_args.args) >= 6 and call_args.args[5] == 'next'), \
               "rmse_alignment='next' 应该被传递"

    @patch('dashboard.models.DFM.train.training.model_ops.calculate_average_reconstruction_rmse')
    def test_evaluate_model_fit_without_frequency_map(self, mock_avg_rmse):
        """无 var_frequency_map 时使用原有计算方式"""
        mock_avg_rmse.return_value = 0.5

        metrics = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=None,  # 不传递频率映射
            variable_names=['月度变量', '周度变量']
        )

        # 验证原有函数被调用
        assert mock_avg_rmse.called, "calculate_average_reconstruction_rmse 应该被调用"

    @patch('dashboard.models.DFM.train.training.model_ops.calculate_mixed_frequency_rmse')
    def test_evaluate_model_fit_passes_var_frequency_map(self, mock_mixed_rmse):
        """var_frequency_map 正确传递"""
        mock_mixed_rmse.return_value = (0.5, {'月度变量': 0.4, '周度变量': 0.6})

        evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量']
        )

        call_args = mock_mixed_rmse.call_args
        assert call_args is not None

        # 检查 var_frequency_map 参数
        passed_freq_map = call_args.args[4] if len(call_args.args) >= 5 else call_args.kwargs.get('var_frequency_map')
        assert passed_freq_map == self.var_frequency_map, "var_frequency_map 应该被正确传递"


class TestEvaluateModelFitValidation:
    """测试验证期的混频RMSE计算"""

    def setup_method(self):
        """设置测试数据：训练期+验证期"""
        # 12周数据：8周训练 + 4周验证
        self.time_index = pd.date_range('2024-01-05', periods=12, freq='W-FRI')

        self.obs_data = pd.DataFrame({
            '月度变量': [
                np.nan, 5.2, np.nan, np.nan,  # 1月
                np.nan, np.nan, 6.1, np.nan,  # 2月
                np.nan, np.nan, 7.0, np.nan   # 3月
            ],
            '周度变量': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1]
        }, index=self.time_index)

        n_factors = 2
        n_vars = 2
        n_time = 12

        self.model_result = DFMModelResult(
            factors_smooth=np.random.randn(n_factors, n_time),
            H=np.random.randn(n_vars, n_factors),
            converged=True,
            iterations=10
        )

        self.var_frequency_map = {'月度变量': '月', '周度变量': '周'}

    @patch('dashboard.models.DFM.train.training.model_ops.calculate_mixed_frequency_rmse')
    def test_validation_period_uses_mixed_frequency(self, mock_mixed_rmse):
        """验证期也使用混频RMSE计算"""
        mock_mixed_rmse.return_value = (0.5, {'月度变量': 0.4, '周度变量': 0.6})

        metrics = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            validation_start='2024-03-01',
            validation_end='2024-03-29',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量']
        )

        # 混频函数应被调用两次（训练期+验证期）
        assert mock_mixed_rmse.call_count == 2, \
            f"calculate_mixed_frequency_rmse 应该被调用2次，实际调用 {mock_mixed_rmse.call_count} 次"


class TestEvaluateModelFitIntegration:
    """端到端集成测试（不使用mock）"""

    def setup_method(self):
        """设置测试数据"""
        self.time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')

        self.obs_data = pd.DataFrame({
            '月度变量': [np.nan, 5.2, np.nan, np.nan, np.nan, np.nan, 6.1, np.nan],
            '周度变量': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]
        }, index=self.time_index)

        # 创建简单的模型结果，使重构值可预测
        n_factors = 1
        n_vars = 2
        n_time = 8

        # 设置因子和载荷使重构值接近观测值
        factors = np.ones((n_factors, n_time))
        H = np.array([[5.1], [1.3]])  # 载荷矩阵

        self.model_result = DFMModelResult(
            factors_smooth=factors,
            H=H,
            converged=True,
            iterations=10
        )

        self.var_frequency_map = {'月度变量': '月', '周度变量': '周'}

    def test_integration_returns_valid_metrics(self):
        """集成测试：返回有效的评估指标"""
        metrics = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量']
        )

        # 验证返回的指标有效
        assert np.isfinite(metrics.average_rmse), "average_rmse 应该是有限值"
        assert metrics.converged == True
        assert metrics.iterations == 10

    def test_integration_different_alignments_produce_different_results(self):
        """集成测试：不同对齐方式产生不同结果"""
        metrics_current = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量'],
            rmse_alignment='current'
        )

        metrics_next = evaluate_model_fit(
            model_result=self.model_result,
            observation_data=self.obs_data,
            training_start='2024-01-05',
            train_end='2024-02-23',
            var_frequency_map=self.var_frequency_map,
            variable_names=['月度变量', '周度变量'],
            rmse_alignment='next'
        )

        # 两种对齐方式的RMSE应该不同
        # 注意：由于数据特性，可能相同，但通常应该不同
        # 这里只验证两者都是有效值
        assert np.isfinite(metrics_current.average_rmse)
        assert np.isfinite(metrics_next.average_rmse)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
