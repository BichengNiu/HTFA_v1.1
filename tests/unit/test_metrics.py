# -*- coding: utf-8 -*-
"""
评估指标单元测试

测试metrics模块的RMSE计算和模型比较功能
"""

import pytest
import numpy as np
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_average_reconstruction_rmse,
    compare_model_scores
)


class TestCalculateAverageReconstructionRMSE:
    """测试平均重构RMSE计算"""

    def test_rmse_calculation_basic(self):
        """测试基本RMSE计算"""
        # 创建简单的测试数据
        observation = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0]
        ])
        reconstructed = np.array([
            [1.1, 2.1, 3.1],
            [4.1, 5.1, 6.1],
            [7.1, 8.1, 9.1]
        ])

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        # 每个变量的RMSE应该是0.1
        expected_rmse = 0.1
        np.testing.assert_almost_equal(
            rmse, expected_rmse, decimal=5,
            err_msg=f"RMSE计算错误: 期望{expected_rmse}, 实际{rmse}"
        )

    def test_rmse_zero_error(self):
        """测试完美重构RMSE=0"""
        observation = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0]
        ])
        reconstructed = observation.copy()

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        assert rmse == 0.0, f"完美重构的RMSE应为0: 实际{rmse}"

    def test_rmse_positive(self):
        """测试RMSE为非负值"""
        np.random.seed(42)
        observation = np.random.randn(100, 10)
        reconstructed = np.random.randn(100, 10)

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        assert rmse >= 0, f"RMSE应为非负值: {rmse}"

    def test_rmse_with_nan(self):
        """测试包含NaN的数据"""
        observation = np.array([
            [1.0, 2.0, np.nan],
            [4.0, np.nan, 6.0],
            [7.0, 8.0, 9.0]
        ])
        reconstructed = np.array([
            [1.1, 2.1, 3.1],
            [4.1, 5.1, 6.1],
            [7.1, 8.1, 9.1]
        ])

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        # 应该能处理NaN并返回有限值
        assert np.isfinite(rmse), f"RMSE应为有限值: {rmse}"

    def test_rmse_single_variable(self):
        """测试单变量RMSE"""
        observation = np.array([[1.0], [2.0], [3.0], [4.0]])
        reconstructed = np.array([[1.5], [2.5], [3.5], [4.5]])

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        # RMSE = sqrt(mean(0.25)) = 0.5
        expected_rmse = 0.5
        np.testing.assert_almost_equal(
            rmse, expected_rmse, decimal=5,
            err_msg=f"单变量RMSE计算错误: 期望{expected_rmse}, 实际{rmse}"
        )

    def test_rmse_large_error(self):
        """测试大误差情况"""
        observation = np.zeros((10, 5))
        reconstructed = np.ones((10, 5)) * 10

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        expected_rmse = 10.0
        np.testing.assert_almost_equal(
            rmse, expected_rmse, decimal=5,
            err_msg=f"大误差RMSE计算错误: 期望{expected_rmse}, 实际{rmse}"
        )

    def test_rmse_different_scales(self):
        """测试不同尺度变量的平均RMSE"""
        # 变量1: 误差0.1, 变量2: 误差1.0
        observation = np.array([
            [1.0, 10.0],
            [2.0, 20.0],
            [3.0, 30.0]
        ])
        reconstructed = np.array([
            [1.1, 11.0],
            [2.1, 21.0],
            [3.1, 31.0]
        ])

        rmse = calculate_average_reconstruction_rmse(observation, reconstructed)

        # 变量1 RMSE = 0.1, 变量2 RMSE = 1.0, 平均 = 0.55
        expected_rmse = 0.55
        np.testing.assert_almost_equal(
            rmse, expected_rmse, decimal=5,
            err_msg=f"不同尺度RMSE计算错误: 期望{expected_rmse}, 实际{rmse}"
        )


class TestCompareModelScores:
    """测试模型得分比较"""

    def test_compare_a_better(self):
        """测试A模型更好（RMSE更小）"""
        score_a = 0.5
        score_b = 1.0

        result = compare_model_scores(score_a, score_b)

        assert result == 1, f"A更好时应返回1: 实际{result}"

    def test_compare_b_better(self):
        """测试B模型更好（RMSE更小）"""
        score_a = 1.0
        score_b = 0.5

        result = compare_model_scores(score_a, score_b)

        assert result == -1, f"B更好时应返回-1: 实际{result}"

    def test_compare_equal(self):
        """测试两模型相等"""
        score_a = 0.5
        score_b = 0.5

        result = compare_model_scores(score_a, score_b)

        assert result == 0, f"相等时应返回0: 实际{result}"

    def test_compare_a_inf(self):
        """测试A为无穷大"""
        score_a = np.inf
        score_b = 1.0

        result = compare_model_scores(score_a, score_b)

        assert result == -1, f"A为inf时B更好，应返回-1: 实际{result}"

    def test_compare_b_inf(self):
        """测试B为无穷大"""
        score_a = 1.0
        score_b = np.inf

        result = compare_model_scores(score_a, score_b)

        assert result == 1, f"B为inf时A更好，应返回1: 实际{result}"

    def test_compare_both_inf(self):
        """测试两者都为无穷大"""
        score_a = np.inf
        score_b = np.inf

        result = compare_model_scores(score_a, score_b)

        assert result == 0, f"两者都为inf时应返回0: 实际{result}"

    def test_compare_a_nan(self):
        """测试A为NaN"""
        score_a = np.nan
        score_b = 1.0

        result = compare_model_scores(score_a, score_b)

        assert result == -1, f"A为NaN时B更好，应返回-1: 实际{result}"

    def test_compare_b_nan(self):
        """测试B为NaN"""
        score_a = 1.0
        score_b = np.nan

        result = compare_model_scores(score_a, score_b)

        assert result == 1, f"B为NaN时A更好，应返回1: 实际{result}"

    def test_compare_both_nan(self):
        """测试两者都为NaN"""
        score_a = np.nan
        score_b = np.nan

        result = compare_model_scores(score_a, score_b)

        assert result == 0, f"两者都为NaN时应返回0: 实际{result}"

    def test_compare_negative_inf(self):
        """测试负无穷大（被视为无效值）"""
        score_a = -np.inf
        score_b = 1.0

        result = compare_model_scores(score_a, score_b)

        # -inf 不是有限值，被视为无效，所以B更好
        assert result == -1, f"A为-inf时（无效值）B更好，应返回-1: 实际{result}"

    def test_compare_small_difference(self):
        """测试微小差异"""
        score_a = 0.50001
        score_b = 0.50000

        result = compare_model_scores(score_a, score_b)

        # B略好
        assert result == -1, f"B略好时应返回-1: 实际{result}"

    def test_compare_zero_scores(self):
        """测试零分数"""
        score_a = 0.0
        score_b = 0.0

        result = compare_model_scores(score_a, score_b)

        assert result == 0, f"两者都为0时应返回0: 实际{result}"

    def test_compare_zero_vs_positive(self):
        """测试零与正数比较"""
        score_a = 0.0
        score_b = 0.1

        result = compare_model_scores(score_a, score_b)

        assert result == 1, f"A为0时A更好，应返回1: 实际{result}"


class TestRMSEProperties:
    """测试RMSE的数学性质"""

    def test_rmse_symmetry(self):
        """测试RMSE对称性（交换观测和重构）"""
        np.random.seed(42)
        a = np.random.randn(50, 5)
        b = np.random.randn(50, 5)

        rmse_ab = calculate_average_reconstruction_rmse(a, b)
        rmse_ba = calculate_average_reconstruction_rmse(b, a)

        np.testing.assert_almost_equal(
            rmse_ab, rmse_ba, decimal=10,
            err_msg="RMSE应该是对称的"
        )

    def test_rmse_triangle_inequality(self):
        """测试RMSE三角不等式（近似）"""
        np.random.seed(42)
        a = np.random.randn(50, 5)
        b = np.random.randn(50, 5)
        c = np.random.randn(50, 5)

        rmse_ac = calculate_average_reconstruction_rmse(a, c)
        rmse_ab = calculate_average_reconstruction_rmse(a, b)
        rmse_bc = calculate_average_reconstruction_rmse(b, c)

        # 三角不等式: d(a,c) <= d(a,b) + d(b,c)
        # 注意：平均RMSE不严格满足三角不等式，但应该近似满足
        assert rmse_ac <= rmse_ab + rmse_bc + 1e-10, \
            f"三角不等式不满足: {rmse_ac} > {rmse_ab} + {rmse_bc}"

    def test_rmse_scale_sensitivity(self):
        """测试RMSE对尺度的敏感性"""
        observation = np.array([[1.0, 2.0], [3.0, 4.0]])
        reconstructed = np.array([[1.1, 2.1], [3.1, 4.1]])

        rmse_original = calculate_average_reconstruction_rmse(observation, reconstructed)

        # 放大10倍
        rmse_scaled = calculate_average_reconstruction_rmse(
            observation * 10, reconstructed * 10
        )

        # RMSE应该也放大10倍
        np.testing.assert_almost_equal(
            rmse_scaled, rmse_original * 10, decimal=5,
            err_msg="RMSE应该与数据尺度成正比"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
