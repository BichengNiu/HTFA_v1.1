# -*- coding: utf-8 -*-
"""
训练摘要信息生成模块

生成用户可读的训练信息文本文件，包含：
- 目标变量
- 预测变量（进入训练、最终保留）
- 模型参数
- 评估指标
- 训练统计
"""

from typing import Optional, Dict, Any
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
    lines.append("")

    # 目标变量
    lines.append("[目标变量]")
    lines.append(f"  目标变量: {config.target_variable}")
    lines.append("")

    # 预测变量信息
    lines.append("[预测变量]")
    # 预测变量统计
    initial_indicators = config.selected_indicators
    lines.append(f"  进入训练的预测变量数: {len(initial_indicators)}")
    if initial_indicators:
        lines.append("  进入训练的预测变量明细:")
        for var in initial_indicators:
            lines.append(f"    - {var}")

    lines.append("")
    final_predictors = [v for v in result.selected_variables if v != config.target_variable]
    lines.append(f"  最终保留的预测变量数: {len(final_predictors)}")
    if final_predictors:
        lines.append("  最终保留的预测变量明细:")
        for var in final_predictors:
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
    lines.append(f"    目标频率: {config.target_freq}")

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

    # 目标配对模式
    alignment_desc = "下月值" if config.target_alignment_mode == 'next_month' else "本月值"
    lines.append(f"    目标配对模式: {alignment_desc} ({config.target_alignment_mode})")

    lines.append("")

    # 训练期/观察期设置（根据算法类型调整术语）
    period_label = "观察期" if is_ddfm else "验证期"
    section_title = "训练与观察期设置" if is_ddfm else "训练与验证期设置"
    lines.append(f"[{section_title}]")
    lines.append(f"  训练期: {config.training_start} 至 {config.train_end}")
    lines.append(f"  {period_label}: {config.validation_start} 至 {config.validation_end}")
    lines.append("")

    # 评估指标
    lines.append("[评估指标]")
    # 评估指标（区分DDFM和经典DFM）
    oos_label = "观察期" if is_ddfm else "验证期"

    if result.metrics:
        metrics = result.metrics
        lines.append(f"  训练期RMSE: {metrics.is_rmse:.4f}")

        # DDFM使用obs指标，经典DFM使用oos指标
        if is_ddfm:
            # DDFM：输出obs指标作为"观察期"
            if metrics.obs_rmse != np.inf:
                lines.append(f"  {oos_label}RMSE: {metrics.obs_rmse:.4f}")
                lines.append(f"  训练期MAE: {metrics.is_mae:.4f}")
                lines.append(f"  {oos_label}MAE: {metrics.obs_mae:.4f}")

                is_wr = metrics.is_win_rate
                obs_wr = metrics.obs_win_rate
                is_wr_str = f"{is_wr:.2f}%" if not np.isnan(is_wr) and not np.isinf(is_wr) else "N/A"
                obs_wr_str = f"{obs_wr:.2f}%" if not np.isnan(obs_wr) and not np.isinf(obs_wr) else "N/A"

                lines.append(f"  训练期胜率: {is_wr_str}")
                lines.append(f"  {oos_label}胜率: {obs_wr_str}")
            else:
                lines.append(f"  {oos_label}RMSE: N/A")
                lines.append(f"  训练期MAE: {metrics.is_mae:.4f}")
                lines.append(f"  {oos_label}MAE: N/A")

                is_wr = metrics.is_win_rate
                is_wr_str = f"{is_wr:.2f}%" if not np.isnan(is_wr) and not np.isinf(is_wr) else "N/A"

                lines.append(f"  训练期胜率: {is_wr_str}")
                lines.append(f"  {oos_label}胜率: N/A")
        else:
            # 经典DFM：输出oos指标作为"验证期"
            lines.append(f"  {oos_label}RMSE: {metrics.oos_rmse:.4f}")
            lines.append(f"  训练期MAE: {metrics.is_mae:.4f}")
            lines.append(f"  {oos_label}MAE: {metrics.oos_mae:.4f}")

            # Win Rate处理
            is_wr = metrics.is_win_rate
            oos_wr = metrics.oos_win_rate
            is_wr_str = f"{is_wr:.2f}%" if not np.isnan(is_wr) and not np.isinf(is_wr) else "N/A"
            oos_wr_str = f"{oos_wr:.2f}%" if not np.isnan(oos_wr) and not np.isinf(oos_wr) else "N/A"

            lines.append(f"  训练期胜率: {is_wr_str}")
            lines.append(f"  {oos_label}胜率: {oos_wr_str}")

            # 观察期指标（经典DFM才有）
            if metrics.obs_rmse != np.inf:
                obs_wr = metrics.obs_win_rate
                obs_wr_str = f"{obs_wr:.2f}%" if not np.isnan(obs_wr) and not np.isinf(obs_wr) else "N/A"
                lines.append(f"  观察期RMSE: {metrics.obs_rmse:.4f}")
                lines.append(f"  观察期MAE: {metrics.obs_mae:.4f}")
                lines.append(f"  观察期胜率: {obs_wr_str}")

    lines.append("")

    # 训练统计
    lines.append("[训练统计]")
    lines.append(f"  训练耗时: {result.training_time:.2f} 秒")
    if result.model_result:
        lines.append(f"  模型迭代次数: {result.model_result.iterations}")
        lines.append(f"  模型收敛状态: {'已收敛' if result.model_result.converged else '未收敛'}")

    if result.total_evaluations > 0:
        lines.append(f"  变量选择评估次数: {result.total_evaluations}")
    if result.svd_error_count > 0:
        lines.append(f"  SVD错误次数: {result.svd_error_count}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("摘要结束")
    lines.append("=" * 80)

    return "\n".join(lines)


__all__ = ['generate_training_summary']
