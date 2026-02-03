# -*- coding: utf-8 -*-
"""
混频RMSE计算单元测试

验证 calculate_mixed_frequency_rmse 和 _calculate_monthly_aggregated_rmse 的计算逻辑
"""

import pytest
import numpy as np
import pandas as pd
from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_mixed_frequency_rmse,
    _calculate_monthly_aggregated_rmse
)


class TestMonthlyAggregatedRMSE:
    """测试月度聚合RMSE计算"""

    def setup_method(self):
        """设置测试数据：8周，跨2个月"""
        # 时间索引：2024年1月和2月各4周
        self.time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')
        # ['2024-01-05', '2024-01-12', '2024-01-19', '2024-01-26',
        #  '2024-02-02', '2024-02-09', '2024-02-16', '2024-02-23']

        # 月度变量观测值（每月只有一个非NaN值）
        self.obs_monthly = np.array([
            np.nan, 5.2, np.nan, np.nan,   # 1月真实值5.2（在第2周）
            np.nan, np.nan, 6.1, np.nan    # 2月真实值6.1（在第3周）
        ])

        # 重构值（每周都有）
        self.recon_monthly = np.array([
            5.0, 5.1, 5.15, 5.18,   # 1月
            5.9, 6.0, 6.05, 6.08    # 2月
        ])

    def test_monthly_aggregated_rmse_current_alignment(self):
        """当月对齐：月度重构平均 vs 当月真实值"""
        rmse = _calculate_monthly_aggregated_rmse(
            self.obs_monthly,
            self.recon_monthly,
            self.time_index,
            alignment='current'
        )

        # 1月: mean([5.0, 5.1, 5.15, 5.18]) = 5.1075 vs 5.2 → 残差 = 0.0925
        # 2月: mean([5.9, 6.0, 6.05, 6.08]) = 6.0075 vs 6.1 → 残差 = 0.0925
        # RMSE = sqrt(mean([0.0925², 0.0925²])) = 0.0925
        jan_recon_mean = np.mean([5.0, 5.1, 5.15, 5.18])  # 5.1075
        feb_recon_mean = np.mean([5.9, 6.0, 6.05, 6.08])  # 6.0075
        jan_residual = 5.2 - jan_recon_mean  # 0.0925
        feb_residual = 6.1 - feb_recon_mean  # 0.0925
        expected_rmse = np.sqrt(np.mean([jan_residual**2, feb_residual**2]))

        assert abs(rmse - expected_rmse) < 1e-6, f"期望 {expected_rmse}, 实际 {rmse}"

    def test_monthly_aggregated_rmse_next_alignment(self):
        """下月对齐：月度重构平均 vs 下月真实值"""
        rmse = _calculate_monthly_aggregated_rmse(
            self.obs_monthly,
            self.recon_monthly,
            self.time_index,
            alignment='next'
        )

        # 1月: mean([5.0, 5.1, 5.15, 5.18]) = 5.1075 vs 2月真实值6.1 → 残差 = 0.9925
        # RMSE = sqrt(0.9925²) = 0.9925
        jan_recon_mean = np.mean([5.0, 5.1, 5.15, 5.18])  # 5.1075
        residual = 6.1 - jan_recon_mean  # 0.9925
        expected_rmse = abs(residual)

        assert abs(rmse - expected_rmse) < 1e-6, f"期望 {expected_rmse}, 实际 {rmse}"


class TestMixedFrequencyRMSE:
    """测试混频RMSE计算"""

    def setup_method(self):
        """设置测试数据"""
        self.time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')

        # 月度变量
        self.obs_monthly = np.array([
            np.nan, 5.2, np.nan, np.nan,
            np.nan, np.nan, 6.1, np.nan
        ])
        self.recon_monthly = np.array([5.0, 5.1, 5.15, 5.18, 5.9, 6.0, 6.05, 6.08])

        # 周度变量（每周都有值）
        self.obs_weekly = np.array([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7])
        self.recon_weekly = np.array([1.05, 1.08, 1.22, 1.28, 1.42, 1.48, 1.62, 1.68])

    def test_mixed_frequency_rmse_with_monthly_vars(self):
        """混频数据：月度变量使用聚合计算"""
        obs_data = np.column_stack([self.obs_monthly])
        recon_data = np.column_stack([self.recon_monthly])
        var_names = ['月度变量']
        var_freq_map = {'月度变量': '月'}

        avg_rmse, rmse_dict = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='current'
        )

        # 验证月度变量使用聚合计算
        jan_recon_mean = np.mean([5.0, 5.1, 5.15, 5.18])
        feb_recon_mean = np.mean([5.9, 6.0, 6.05, 6.08])
        jan_residual = 5.2 - jan_recon_mean
        feb_residual = 6.1 - feb_recon_mean
        expected_rmse = np.sqrt(np.mean([jan_residual**2, feb_residual**2]))

        assert abs(rmse_dict['月度变量'] - expected_rmse) < 1e-6

    def test_mixed_frequency_rmse_with_weekly_vars(self):
        """混频数据：周度变量直接计算"""
        obs_data = np.column_stack([self.obs_weekly])
        recon_data = np.column_stack([self.recon_weekly])
        var_names = ['周度变量']
        var_freq_map = {'周度变量': '周'}

        avg_rmse, rmse_dict = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='current'
        )

        # 周度变量直接逐周计算
        residuals = self.obs_weekly - self.recon_weekly
        expected_rmse = np.sqrt(np.nanmean(residuals**2))

        assert abs(rmse_dict['周度变量'] - expected_rmse) < 1e-6

    def test_mixed_frequency_rmse_alignment_param(self):
        """对齐参数正确传递"""
        obs_data = np.column_stack([self.obs_monthly])
        recon_data = np.column_stack([self.recon_monthly])
        var_names = ['月度变量']
        var_freq_map = {'月度变量': '月'}

        # 当月对齐
        _, rmse_current = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='current'
        )

        # 下月对齐
        _, rmse_next = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='next'
        )

        # 两种对齐方式结果应不同
        assert rmse_current['月度变量'] != rmse_next['月度变量']

    def test_mixed_frequency_combined(self):
        """混合月度和周度变量"""
        obs_data = np.column_stack([self.obs_monthly, self.obs_weekly])
        recon_data = np.column_stack([self.recon_monthly, self.recon_weekly])
        var_names = ['月度变量', '周度变量']
        var_freq_map = {'月度变量': '月', '周度变量': '周'}

        avg_rmse, rmse_dict = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='current'
        )

        # 验证两个变量都有RMSE
        assert '月度变量' in rmse_dict
        assert '周度变量' in rmse_dict
        assert np.isfinite(rmse_dict['月度变量'])
        assert np.isfinite(rmse_dict['周度变量'])

        # 平均RMSE应为两者平均
        expected_avg = np.mean([rmse_dict['月度变量'], rmse_dict['周度变量']])
        assert abs(avg_rmse - expected_avg) < 1e-6


class TestEdgeCases:
    """边界情况测试"""

    def test_edge_case_no_obs_value(self):
        """边界：某月无真实值"""
        time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')

        # 1月无真实值，2月有真实值
        obs = np.array([np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 6.1, np.nan])
        recon = np.array([5.0, 5.1, 5.15, 5.18, 5.9, 6.0, 6.05, 6.08])

        rmse = _calculate_monthly_aggregated_rmse(obs, recon, time_index, alignment='current')

        # 只有2月参与计算
        feb_recon_mean = np.mean([5.9, 6.0, 6.05, 6.08])
        expected_rmse = abs(6.1 - feb_recon_mean)

        assert abs(rmse - expected_rmse) < 1e-6

    def test_edge_case_single_month(self):
        """边界：单月数据+下月对齐"""
        time_index = pd.date_range('2024-01-05', periods=4, freq='W-FRI')

        obs = np.array([np.nan, 5.2, np.nan, np.nan])
        recon = np.array([5.0, 5.1, 5.15, 5.18])

        # 下月对齐但只有一个月，应返回inf
        rmse = _calculate_monthly_aggregated_rmse(obs, recon, time_index, alignment='next')

        assert rmse == np.inf

    def test_edge_case_all_nan_obs(self):
        """边界：所有观测值都是NaN"""
        time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')

        obs = np.array([np.nan] * 8)
        recon = np.array([5.0, 5.1, 5.15, 5.18, 5.9, 6.0, 6.05, 6.08])

        rmse = _calculate_monthly_aggregated_rmse(obs, recon, time_index, alignment='current')

        assert rmse == np.inf

    def test_frequency_detection_variants(self):
        """测试不同频率标识的识别"""
        time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')
        obs = np.array([np.nan, 5.2, np.nan, np.nan, np.nan, np.nan, 6.1, np.nan])
        recon = np.array([5.0, 5.1, 5.15, 5.18, 5.9, 6.0, 6.05, 6.08])

        obs_data = np.column_stack([obs])
        recon_data = np.column_stack([recon])

        # 测试不同的月度频率标识
        for freq_label in ['月', '月度', 'monthly', 'Monthly', 'm', 'M']:
            var_freq_map = {'var': freq_label}
            _, rmse_dict = calculate_mixed_frequency_rmse(
                obs_data, recon_data, time_index, ['var'], var_freq_map,
                rmse_alignment='current'
            )
            # 月度变量应使用聚合计算，RMSE应约为0.0925
            assert rmse_dict['var'] < 0.1, f"频率标识 '{freq_label}' 未被正确识别为月度"


class TestWeeklyVariableAlignment:
    """测试周度变量的对齐方式"""

    def setup_method(self):
        self.time_index = pd.date_range('2024-01-05', periods=8, freq='W-FRI')
        self.obs_weekly = np.array([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7])
        self.recon_weekly = np.array([1.05, 1.08, 1.22, 1.28, 1.42, 1.48, 1.62, 1.68])

    def test_weekly_current_alignment(self):
        """周度变量当月对齐"""
        obs_data = np.column_stack([self.obs_weekly])
        recon_data = np.column_stack([self.recon_weekly])
        var_names = ['周度变量']
        var_freq_map = {'周度变量': '周'}

        _, rmse_dict = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='current'
        )

        # 当月对齐：obs[t] vs recon[t]
        residuals = self.obs_weekly - self.recon_weekly
        expected_rmse = np.sqrt(np.nanmean(residuals**2))

        assert abs(rmse_dict['周度变量'] - expected_rmse) < 1e-6

    def test_weekly_next_alignment(self):
        """周度变量下月对齐"""
        obs_data = np.column_stack([self.obs_weekly])
        recon_data = np.column_stack([self.recon_weekly])
        var_names = ['周度变量']
        var_freq_map = {'周度变量': '周'}

        _, rmse_dict = calculate_mixed_frequency_rmse(
            obs_data, recon_data, self.time_index, var_names, var_freq_map,
            rmse_alignment='next'
        )

        # 下月对齐：obs[t+1] vs recon[t]
        obs_aligned = self.obs_weekly[1:]
        recon_aligned = self.recon_weekly[:-1]
        residuals = obs_aligned - recon_aligned
        expected_rmse = np.sqrt(np.nanmean(residuals**2))

        assert abs(rmse_dict['周度变量'] - expected_rmse) < 1e-6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
