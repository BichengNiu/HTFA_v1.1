# -*- coding: utf-8 -*-
"""
统一数据模型定义

整合所有train模块使用的数据类，确保类型一致性和可维护性
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


# ==================== 评估指标相关 ====================

@dataclass
class EvaluationMetrics:
    """评估指标

    包含平均RMSE用于变量选择和模型评估。
    """
    # 平均RMSE指标
    average_rmse: float = np.inf              # 训练期平均RMSE
    average_rmse_validation: float = np.inf   # 验证期平均RMSE
    weighted_average_rmse: float = np.inf     # 加权平均RMSE

    # 目标变量RMSE指标 (2026-01新增)
    target_rmse: float = np.inf               # 目标变量训练期RMSE
    target_rmse_validation: float = np.inf    # 目标变量验证期RMSE
    weighted_target_rmse: float = np.inf      # 目标变量加权RMSE

    # 收敛信息
    converged: bool = False
    iterations: int = 0

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {
            'average_rmse': self.average_rmse,
            'average_rmse_validation': self.average_rmse_validation,
            'weighted_average_rmse': self.weighted_average_rmse,
            'target_rmse': self.target_rmse,
            'target_rmse_validation': self.target_rmse_validation,
            'weighted_target_rmse': self.weighted_target_rmse,
            'converged': self.converged,
            'iterations': self.iterations
        }


# ==================== DFM模型相关 ====================

@dataclass
class DFMModelResult:
    """DFM模型完整结果

    整合了原DFMResults和DFMModelResult的功能，
    提供统一的数据模型，避免重复和转换开销。

    字段命名说明：
    - A: 状态转移矩阵
    - Q: 状态噪声协方差
    - H: 观测矩阵（因子载荷）
    - R: 观测噪声协方差
    """
    # EM估计参数（统一命名：A/Q/H/R）
    A: np.ndarray = None  # 状态转移矩阵
    Q: np.ndarray = None  # 状态噪声协方差
    H: np.ndarray = None  # 观测矩阵（因子载荷）
    R: np.ndarray = None  # 观测噪声协方差

    # 卡尔曼滤波结果
    factors: np.ndarray = None  # 因子时间序列（滤波）
    factors_smooth: np.ndarray = None  # 平滑因子
    kalman_gains_history: Optional[List[np.ndarray]] = None  # 卡尔曼增益历史
    factor_states_predicted: Optional[np.ndarray] = None  # 先验因子状态 (n_time, n_factors)

    # 变量名列表（用于导出时H矩阵维度匹配）
    variable_names: Optional[List[str]] = None  # 训练时使用的变量名列表

    # 重构数据（用于评估）
    reconstructed_data: Optional[np.ndarray] = None

    # 训练信息
    converged: bool = False
    iterations: int = 0
    log_likelihood: float = -np.inf

    # 训练期索引范围（用于区分训练期/验证期因子）
    train_start_idx: Optional[int] = None
    train_end_idx: Optional[int] = None


# ==================== 卡尔曼滤波相关 ====================

@dataclass
class KalmanFilterResult:
    """卡尔曼滤波结果"""
    x_filtered: np.ndarray      # 滤波状态估计
    P_filtered: np.ndarray      # 滤波协方差
    x_predicted: np.ndarray     # 预测状态估计
    P_predicted: np.ndarray     # 预测协方差
    loglikelihood: float        # 对数似然
    innovation: np.ndarray      # 新息序列
    kalman_gains_history: Optional[List[np.ndarray]] = None  # 卡尔曼增益历史（每个时刻的K_t矩阵）


@dataclass
class KalmanSmootherResult:
    """卡尔曼平滑结果"""
    x_smoothed: np.ndarray      # 平滑状态估计
    P_smoothed: np.ndarray      # 平滑协方差
    P_lag_smoothed: np.ndarray  # 滞后协方差


# ==================== 变量选择相关 ====================

@dataclass
class SelectionResult:
    """变量选择结果"""
    selected_variables: List[str]  # 最终选中的变量列表
    selection_history: List[Dict]  # 选择历史记录
    final_score: float  # 最终得分（加权RMSE）
    total_evaluations: int  # 总评估次数


# ==================== 训练结果相关 ====================

@dataclass
class TrainingResult:
    """训练结果"""
    # 变量选择结果
    selected_variables: List[str] = field(default_factory=list)
    selection_history: List[Dict] = field(default_factory=list)

    # 因子数选择结果
    k_factors: int = 0
    factor_selection_method: str = 'fixed'
    pca_analysis: Optional[Dict] = None

    # 模型结果
    model_result: Optional[DFMModelResult] = None

    # 评估指标
    metrics: Optional[EvaluationMetrics] = None

    # 训练统计
    total_evaluations: int = 0
    training_time: float = 0.0

    # 导出文件路径
    export_files: Optional[Dict[str, str]] = None

    # 输出路径
    output_dir: Optional[str] = None

    @classmethod
    def build(
        cls,
        selected_variables: List[str],
        selection_history: List[Dict],
        k_factors: int,
        factor_selection_method: str,
        pca_analysis: Optional[Dict],
        model_result: DFMModelResult,
        metrics: EvaluationMetrics,
        total_evaluations: int,
        training_time: float,
        output_dir: Optional[str] = None
    ) -> 'TrainingResult':
        """
        构建训练结果对象

        Args:
            selected_variables: 选定的变量列表
            selection_history: 变量选择历史
            k_factors: 因子数
            factor_selection_method: 因子选择方法
            pca_analysis: PCA分析结果
            model_result: 模型结果
            metrics: 评估指标
            total_evaluations: 总评估次数
            training_time: 训练时间（秒）
            output_dir: 输出目录

        Returns:
            TrainingResult: 训练结果对象
        """
        return cls(
            selected_variables=selected_variables,
            selection_history=selection_history,
            k_factors=k_factors,
            factor_selection_method=factor_selection_method,
            pca_analysis=pca_analysis,
            model_result=model_result,
            metrics=metrics,
            total_evaluations=total_evaluations,
            training_time=training_time,
            output_dir=output_dir
        )


# ==================== 导出所有模型 ====================

__all__ = [
    # 评估指标
    'EvaluationMetrics',

    # DFM模型
    'DFMModelResult',

    # 卡尔曼滤波
    'KalmanFilterResult',
    'KalmanSmootherResult',

    # 变量选择
    'SelectionResult',

    # 训练结果
    'TrainingResult',
]
