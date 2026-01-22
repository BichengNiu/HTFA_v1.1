# -*- coding: utf-8 -*-
"""
影响分析器

计算新数据发布对nowcast值的边际影响，基于卡尔曼增益权重
进行影响分析和贡献分解。
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from ..utils.exceptions import ComputationError, ValidationError
from ..utils.constants import CONFIDENCE_INTERVAL_Z_SCORE, DEFAULT_MEASUREMENT_ERROR
from ..utils.helpers import get_month_date_range
from .nowcast_extractor import NowcastExtractor

logger = logging.getLogger(__name__)


@dataclass
class DataRelease:
    """数据发布事件"""
    timestamp: pd.Timestamp
    variable_name: str
    observed_value: float
    expected_value: float
    measurement_error: Optional[float] = None
    variable_index: Optional[int] = None


@dataclass
class ImpactResult:
    """单次影响计算结果"""
    release: DataRelease
    impact_on_target: float
    contribution_percentage: float
    kalman_weight: float
    confidence_interval: Optional[Tuple[float, float]] = None
    calculation_details: Optional[Dict[str, Any]] = None


@dataclass
class SequentialImpactResult:
    """时序影响分析结果"""
    target_date: pd.Timestamp
    baseline_value: float
    final_value: float
    total_impact: float
    cumulative_impacts: pd.Series
    individual_impacts: List[ImpactResult]
    positive_impact_sum: float
    negative_impact_sum: float


class ImpactAnalyzer:
    """
    数据发布影响分析器

    基于卡尔曼滤波理论计算新数据发布对nowcast预测的边际影响。
    核心公式（修正版）：Δy = λ_y' × K_t[:, i] × v_i

    其中：
    - λ_y: 目标变量的因子载荷向量 (n_factors,)
    - K_t: 时刻t的卡尔曼增益矩阵 (n_factors, n_variables)
    - K_t[:, i]: 第i个观测变量对应的卡尔曼增益列向量 (n_factors,)
    - v_i: 第i个变量的新息（观测值 - 期望值）
    """

    def __init__(self, nowcast_extractor: NowcastExtractor):
        """
        初始化影响分析器

        Args:
            nowcast_extractor: Nowcast提取器实例
        """
        self.extractor = nowcast_extractor

        # 验证数据完整性
        if self.extractor.data.kalman_gains_history is None:
            logger.warning("卡尔曼增益历史不可用，影响分析功能受限")
        if self.extractor.data.variable_index_map is None:
            logger.warning("变量索引映射不可用，可能无法正确识别变量")

    def calculate_single_release_impact(self, release: DataRelease) -> ImpactResult:
        """
        计算单个数据发布的影响（修正版）

        使用正确的新闻分解公式：
        Δy = λ_y' × K_t[:, i] × v_i

        Args:
            release: 数据发布事件

        Returns:
            影响计算结果

        Raises:
            ComputationError: 计算失败时抛出
            ValidationError: 数据验证失败时抛出
        """
        try:
            # 调试日志：输入参数
            logger.debug(f"=== {release.variable_name} @ {release.timestamp} ===")
            logger.debug(f"observed={release.observed_value:.4f}, expected={release.expected_value:.4f}")
            logger.debug(f"innovation={release.observed_value - release.expected_value:.4f}")

            # 检查数据完整性
            if self.extractor.data.kalman_gains_history is None:
                raise ComputationError(
                    "影响分解功能需要卡尔曼增益历史数据。\n"
                    "当前模型是使用旧版本训练模块生成的。\n"
                    "请使用新版本训练模块重新训练模型以支持此功能。"
                )

            # 1. 获取目标变量的因子载荷向量 λ_y
            lambda_y = self._get_target_variable_loading()  # (n_factors,)

            # 2. 获取观测变量在向量中的索引
            variable_index = self._get_variable_index(release.variable_name)

            # 3. 获取发布时刻的卡尔曼增益矩阵 K_t
            K_t = self._get_kalman_gain_at_time(release.timestamp)  # (n_factors, n_variables)

            # 4. 提取第i个变量对应的卡尔曼增益列向量
            K_col = K_t[:, variable_index]  # (n_factors,)

            # 5. 计算新息 v_i
            innovation = release.observed_value - release.expected_value

            # 6. 正确的影响计算公式：Δy = λ_y' × K_t[:, i] × v_i
            # 步骤：K_col * innovation → (n_factors,) 因子状态变化
            delta_f = K_col * innovation  # (n_factors,) 因子状态的变化量

            # 步骤：λ_y' × delta_f → 标量（标准化尺度）
            impact_standardized = np.dot(lambda_y, delta_f)  # 标量，标准化尺度

            # 7. 反标准化到原始尺度
            target_std = self._get_target_std()
            impact_on_target = impact_standardized * target_std  # 原始尺度

            # 8. 计算有效卡尔曼权重（用于报告）
            effective_kalman_weight = np.linalg.norm(K_col)  # 向量的范数

            # 调试日志：计算结果
            logger.debug(f"影响计算: standardized={impact_standardized:.4f}, "
                  f"std={target_std:.4f}, original={impact_on_target:.4f}")

            # 9. 贡献百分比在NewsImpactCalculator中基于总影响计算
            # 此处设为0.0作为占位符
            contribution_percentage = 0.0

            # 10. 计算置信区间
            confidence_interval = self._calculate_confidence_interval(
                impact_on_target, release.measurement_error
            )

            # 11. 构建详细的计算信息
            calculation_details = {
                'innovation': float(innovation),
                'variable_index': int(variable_index),
                'kalman_gain_vector': K_col.tolist(),  # 完整的K_t[:, i]向量
                'factor_loading_vector': lambda_y.tolist(),  # λ_y向量
                'factor_state_change': delta_f.tolist(),  # Δf向量
                'effective_kalman_weight': float(effective_kalman_weight),
                'calculation_formula': 'Δy = λ_y\' × K_t[:, i] × v_i',
                'formula_explanation': {
                    'lambda_y': 'Target variable factor loadings (n_factors,)',
                    'K_t_col': 'Kalman gain vector for variable i (n_factors,)',
                    'v_i': 'Innovation (observed - expected)',
                    'delta_f': 'Factor state change K_t[:, i] * v_i',
                    'impact': 'Final impact λ_y\' × delta_f'
                }
            }

            result = ImpactResult(
                release=release,
                impact_on_target=impact_on_target,
                contribution_percentage=contribution_percentage,
                kalman_weight=effective_kalman_weight,  # 使用向量范数作为权重
                confidence_interval=confidence_interval,
                calculation_details=calculation_details
            )

            logger.debug(f"单次影响计算: {release.variable_name} = {impact_on_target:.4f} "
                  f"(innovation={innovation:.4f}, ||K||={effective_kalman_weight:.4f})")
            return result

        except (ComputationError, ValidationError):
            raise
        except (KeyError, IndexError) as e:
            raise ComputationError(f"数据访问错误: {str(e)}", "single_impact_calculation")
        except (TypeError, ValueError) as e:
            raise ComputationError(f"数值计算错误: {str(e)}", "single_impact_calculation")

    def analyze_sequential_impacts(
        self,
        releases: List[DataRelease],
        target_date: pd.Timestamp
    ) -> SequentialImpactResult:
        """
        分析时序累积影响

        Args:
            releases: 数据发布列表（按时间排序）
            target_date: 目标分析日期

        Returns:
            时序影响分析结果

        Raises:
            ComputationError: 分析失败时抛出
        """
        try:
            # 按时间排序数据发布
            sorted_releases = sorted(releases, key=lambda x: x.timestamp)

            # 获取基准值
            baseline_value = self.extractor.compute_baseline_prediction(target_date)

            # 计算各次发布的影响
            individual_impacts = []
            cumulative_values = []

            current_value = baseline_value
            cumulative_impact = 0.0

            # 计算目标月份的日期范围
            target_month_start, target_month_end = get_month_date_range(target_date)

            for release in sorted_releases:
                # 只处理目标月份范围内的数据发布
                if release.timestamp < target_month_start or release.timestamp > target_month_end:
                    continue

                impact_result = self.calculate_single_release_impact(release)
                individual_impacts.append(impact_result)

                # 更新累积影响
                cumulative_impact += impact_result.impact_on_target
                current_value = baseline_value + cumulative_impact
                cumulative_values.append({
                    'timestamp': release.timestamp,
                    'cumulative_impact': cumulative_impact,
                    'current_value': current_value,
                    'individual_impact': impact_result.impact_on_target
                })

            # 创建累积影响序列
            if cumulative_values:
                cumulative_df = pd.DataFrame(cumulative_values)
                cumulative_df.set_index('timestamp', inplace=True)
                cumulative_series = cumulative_df['cumulative_impact']
            else:
                cumulative_series = pd.Series([], dtype=float)

            # 计算正负影响总和
            positive_impact_sum = sum(imp.impact_on_target for imp in individual_impacts if imp.impact_on_target > 0)
            negative_impact_sum = sum(imp.impact_on_target for imp in individual_impacts if imp.impact_on_target < 0)

            result = SequentialImpactResult(
                target_date=target_date,
                baseline_value=baseline_value,
                final_value=current_value,
                total_impact=cumulative_impact,
                cumulative_impacts=cumulative_series,
                individual_impacts=individual_impacts,
                positive_impact_sum=positive_impact_sum,
                negative_impact_sum=negative_impact_sum
            )

            logger.info(f"时序影响分析完成: 总影响 = {cumulative_impact:.4f}")
            return result

        except (ComputationError, ValidationError):
            raise
        except (KeyError, IndexError) as e:
            raise ComputationError(f"时序影响分析数据访问错误: {str(e)}", "sequential_impact_analysis")
        except (TypeError, ValueError) as e:
            raise ComputationError(f"时序影响分析数值错误: {str(e)}", "sequential_impact_analysis")

    def decompose_total_impact(
        self,
        target_date: pd.Timestamp,
        releases: List[DataRelease]
    ) -> Dict[str, Any]:
        """
        分解总影响为各数据发布的具体贡献

        Args:
            target_date: 目标日期
            releases: 数据发布列表

        Returns:
            影响分解结果

        Raises:
            ComputationError: 分解失败时抛出
        """
        try:
            # 计算时序影响
            sequential_result = self.analyze_sequential_impacts(releases, target_date)

            # 按变量分组影响
            variable_impacts = {}
            for impact in sequential_result.individual_impacts:
                var_name = impact.release.variable_name
                if var_name not in variable_impacts:
                    variable_impacts[var_name] = []
                variable_impacts[var_name].append(impact)

            # 计算每个变量的总影响
            variable_summary = {}
            total_abs_impact = sum(abs(imp.impact_on_target) for imp in sequential_result.individual_impacts)

            for var_name, impacts in variable_impacts.items():
                total_impact = sum(imp.impact_on_target for imp in impacts)
                contribution_pct = (abs(total_impact) / total_abs_impact * 100) if total_abs_impact > 0 else 0

                # 统计该变量的发布次数
                release_count = len(impacts)

                # 计算平均影响
                avg_impact = total_impact / release_count if release_count > 0 else 0

                variable_summary[var_name] = {
                    'total_impact': total_impact,
                    'contribution_percentage': contribution_pct,
                    'release_count': release_count,
                    'average_impact': avg_impact,
                    'impacts': impacts
                }

            # 按贡献度排序
            sorted_variables = sorted(
                variable_summary.items(),
                key=lambda x: abs(x[1]['total_impact']),
                reverse=True
            )

            # 构建分解结果
            decomposition_result = {
                'target_date': target_date,
                'total_impact': sequential_result.total_impact,
                'positive_impact_sum': sequential_result.positive_impact_sum,
                'negative_impact_sum': sequential_result.negative_impact_sum,
                'variable_contributions': dict(sorted_variables),
                'top_contributors': [var for var, _ in sorted_variables[:5]],
                'sequential_result': sequential_result,
                'impact_count': len(sequential_result.individual_impacts)
            }

            logger.info(f"影响分解完成: {len(variable_summary)} 个变量")
            return decomposition_result

        except (ComputationError, ValidationError):
            raise
        except (KeyError, IndexError) as e:
            raise ComputationError(f"影响分解数据访问错误: {str(e)}", "impact_decomposition")
        except (TypeError, ValueError) as e:
            raise ComputationError(f"影响分解数值错误: {str(e)}", "impact_decomposition")


    def _get_target_variable_loading(self) -> np.ndarray:
        """
        获取目标变量的因子载荷向量 λ_y

        Returns:
            目标变量的载荷向量 (n_factors,)

        Raises:
            ValidationError: 数据不可用时抛出
        """
        if self.extractor.data.target_factor_loading is None:
            raise ValidationError(
                "目标变量因子载荷不可用。\n"
                "请使用新版本训练模块重新训练模型以支持影响分解功能。"
            )

        return self.extractor.data.target_factor_loading

    def _get_kalman_gain_at_time(self, timestamp: pd.Timestamp) -> np.ndarray:
        """
        获取指定时刻最近的卡尔曼增益矩阵 K_t

        Args:
            timestamp: 目标时间戳

        Returns:
            卡尔曼增益矩阵 (n_factors, n_variables)

        Raises:
            ComputationError: 无法找到有效的卡尔曼增益时抛出
        """
        if self.extractor.data.kalman_gains_history is None:
            raise ComputationError("卡尔曼增益历史不可用")

        if self.extractor.data.nowcast_series is None:
            raise ComputationError("nowcast时间序列不可用")

        # 找到时间戳对应的索引
        nowcast_series = self.extractor.data.nowcast_series
        available_dates = nowcast_series.index[nowcast_series.index <= timestamp]

        if len(available_dates) == 0:
            raise ComputationError(f"未找到 {timestamp} 之前的卡尔曼增益")

        # 获取最接近的日期索引
        closest_date_index = len(available_dates) - 1

        # 边界检查
        if closest_date_index >= len(self.extractor.data.kalman_gains_history):
            closest_date_index = len(self.extractor.data.kalman_gains_history) - 1

        K_t = self.extractor.data.kalman_gains_history[closest_date_index]

        # 卡尔曼增益为None时直接报错（不使用fallback）
        if K_t is None:
            raise ComputationError(
                f"时刻 {closest_date_index} 的卡尔曼增益为None（目标时间: {timestamp}）。\n"
                "请确保模型训练时正确保存了所有时刻的卡尔曼增益。"
            )

        # K_t的原始形状是(n_states, n_obs)，其中n_states = n_factors * max_lags
        # 影响分析只需要前n_factors行（当前因子的增益）
        # 从target_factor_loading获取n_factors
        if self.extractor.data.target_factor_loading is None:
            raise ComputationError(
                "目标变量因子载荷不可用，无法确定因子数量。\n"
                "请使用新版本训练模块重新训练模型。"
            )

        n_factors = len(self.extractor.data.target_factor_loading)

        if K_t.shape[0] > n_factors:
            # 只取前n_factors行
            original_rows = K_t.shape[0]
            K_t = K_t[:n_factors, :]
            logger.debug(f"K_t从({original_rows}, {K_t.shape[1]})截取为({n_factors}, {K_t.shape[1]})")

        return K_t

    def _get_variable_index(self, variable_name: str) -> int:
        """
        从映射中获取变量索引（修正版）

        Args:
            variable_name: 变量名

        Returns:
            变量在观测向量中的索引

        Raises:
            ValidationError: 变量不在映射中时抛出
        """
        if self.extractor.data.variable_index_map is None:
            raise ValidationError(
                "变量索引映射不可用。\n"
                "这可能是因为模型元数据不完整。\n"
                "请确保模型包含完整的变量列表信息。"
            )

        if variable_name not in self.extractor.data.variable_index_map:
            # 提供详细的错误信息
            available_vars = list(self.extractor.data.variable_index_map.keys())
            raise ValidationError(
                f"变量 '{variable_name}' 不在变量映射中。\n"
                f"可用变量数: {len(available_vars)}\n"
                f"前5个可用变量: {available_vars[:5]}"
            )

        return self.extractor.data.variable_index_map[variable_name]

    def _calculate_confidence_interval(
        self,
        impact: float,
        measurement_error: Optional[float] = None
    ) -> Tuple[float, float]:
        """计算置信区间"""
        # 简化的置信区间计算
        # 实际应用中应该基于完整的协方差矩阵
        if measurement_error is None:
            measurement_error = DEFAULT_MEASUREMENT_ERROR

        standard_error = measurement_error * abs(impact) if impact != 0 else measurement_error
        margin = CONFIDENCE_INTERVAL_Z_SCORE * standard_error  # 95% 置信区间

        return (impact - margin, impact + margin)

    def _get_target_std(self) -> float:
        """
        获取目标变量标准差（用于反标准化）

        Returns:
            目标变量训练期标准差

        Raises:
            ValidationError: 数据不可用或无效时抛出
        """
        target_std = self.extractor.data.target_std_original

        if target_std is None:
            raise ValidationError(
                "目标变量标准差不可用。\n"
                "请使用新版本训练模块重新训练模型以支持影响分解功能。"
            )

        if target_std <= 0:
            raise ValidationError(
                f"目标变量标准差={target_std}不是正数。\n"
                "标准差必须大于0才能进行反标准化。"
            )

        return target_std

    def get_analysis_summary(self) -> Dict[str, Any]:
        """
        获取影响分析器摘要

        Returns:
            分析器摘要字典
        """
        data = self.extractor.data

        # 获取K_t维度信息
        kt_shape = None
        latest_kt = None
        if data.kalman_gains_history:
            for K_t in data.kalman_gains_history:
                if K_t is not None:
                    kt_shape = K_t.shape
                    latest_kt = K_t
                    break

        summary = {
            'kalman_gains_available': data.kalman_gains_history is not None,
            'kalman_gains_timesteps': len(data.kalman_gains_history) if data.kalman_gains_history else 0,
            'kalman_gains_shape': kt_shape,
            'variable_mapping_count': len(data.variable_index_map) if data.variable_index_map else 0,
        }

        if kt_shape is not None:
            # K_t形状为(n_factors, n_variables)
            summary.update({
                'n_factors': kt_shape[0],
                'n_variables': kt_shape[1],
            })

        if latest_kt is not None:
            summary.update({
                'max_kalman_weight': float(np.max(np.abs(latest_kt))),
                'mean_kalman_weight': float(np.mean(np.abs(latest_kt))),
            })

        return summary