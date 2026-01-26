# -*- coding: utf-8 -*-
"""
训练摘要信息生成模块

生成用户可读的训练信息文本文件，包含：
- 变量信息
- 模型参数
- 评估指标（平均RMSE）
- 训练统计

经典DFM：所有变量平等参与因子提取，无目标变量概念
"""

from typing import Optional
import numpy as np
from datetime import datetime


def generate_training_summary(
    result,  # TrainingResult
    config,  # TrainingConfig
    timestamp: Optional[str] = None
) -> str:
    """
    生成训练摘要文本

    Args:
        result: 训练结果对象（TrainingResult）
        config: 训练配置对象
        timestamp: 时间戳字符串（可选）

    Returns:
        str: 格式化的训练摘要文本
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 判断是否为DDFM（深度学习算法）
    is_ddfm = (getattr(config, 'algorithm', 'classical') == 'deep_learning')

    lines = []
    lines.append("=" * 80)
    lines.append("DFM 模型训练摘要")
    lines.append("=" * 80)
    lines.append(f"生成时间: {timestamp}")
    lines.append(f"算法类型: {'深度学习DFM (DDFM)' if is_ddfm else '经典DFM (EM算法)'}")
    lines.append("")

    # 变量信息
    lines.append("[变量信息]")
    initial_indicators = config.selected_indicators
    lines.append(f"  进入训练的变量数: {len(initial_indicators)}")
    if initial_indicators:
        lines.append("  进入训练的变量明细:")
        for var in initial_indicators:
            lines.append(f"    - {var}")

    lines.append("")
    final_variables = result.selected_variables
    lines.append(f"  最终保留的变量数: {len(final_variables)}")
    if final_variables:
        lines.append("  最终保留的变量明细:")
        for var in final_variables:
            lines.append(f"    - {var}")

    lines.append("")

    # 模型参数
    lines.append("[模型参数]")
    lines.append(f"  因子数: {result.k_factors}")
    lines.append(f"  因子选择策略: {result.factor_selection_method}")

    # 通用参数
    lines.append("")
    lines.append("  通用参数:")
    lines.append(f"    最大迭代次数: {config.max_iterations}")
    lines.append(f"    因子AR阶数: {config.max_lags}")
    lines.append(f"    收敛容差: {config.tolerance}")

    # 变量选择方法
    if config.enable_variable_selection:
        lines.append(f"    变量选择方法: {config.variable_selection_method}")
    else:
        lines.append("    变量选择方法: 无筛选（使用全部已选变量）")

    # 并行配置
    if config.enable_parallel:
        lines.append(f"    并行计算: 启用 (n_jobs={config.n_jobs}, backend={config.parallel_backend})")
    else:
        lines.append("    并行计算: 未启用")

    lines.append("")

    # 训练期设置
    lines.append("[训练期设置]")
    lines.append(f"  训练期: {config.training_start} 至 {config.train_end}")
    lines.append(f"  验证期: {config.validation_start} 至 {config.validation_end}")
    lines.append("")

    # 评估指标（平均RMSE）
    lines.append("[模型拟合指标]")
    if result.metrics:
        metrics = result.metrics

        # 训练期平均RMSE
        avg_rmse = getattr(metrics, 'average_rmse', None)
        if avg_rmse is not None and np.isfinite(avg_rmse):
            lines.append(f"  训练期平均RMSE: {avg_rmse:.4f}")
        else:
            lines.append("  训练期平均RMSE: N/A")

        # 验证期平均RMSE
        avg_rmse_val = getattr(metrics, 'average_rmse_validation', None)
        if avg_rmse_val is not None and np.isfinite(avg_rmse_val):
            lines.append(f"  验证期平均RMSE: {avg_rmse_val:.4f}")
        else:
            lines.append("  验证期平均RMSE: N/A")

        # 加权平均RMSE
        weighted_rmse = getattr(metrics, 'weighted_average_rmse', None)
        if weighted_rmse is not None and np.isfinite(weighted_rmse):
            lines.append(f"  加权平均RMSE: {weighted_rmse:.4f}")
        else:
            lines.append("  加权平均RMSE: N/A")

        # 收敛信息
        lines.append(f"  模型收敛: {'是' if metrics.converged else '否'}")
        lines.append(f"  迭代次数: {metrics.iterations}")

    else:
        lines.append("  评估指标不可用")

    lines.append("")

    # 训练统计
    lines.append("[训练统计]")
    lines.append(f"  训练耗时: {result.training_time:.2f} 秒")
    if result.model_result:
        lines.append(f"  模型迭代次数: {result.model_result.iterations}")
        lines.append(f"  模型收敛状态: {'已收敛' if result.model_result.converged else '未收敛'}")

    if result.total_evaluations > 0:
        lines.append(f"  变量选择评估次数: {result.total_evaluations}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("摘要结束")
    lines.append("=" * 80)

    return "\n".join(lines)


__all__ = ['generate_training_summary']
