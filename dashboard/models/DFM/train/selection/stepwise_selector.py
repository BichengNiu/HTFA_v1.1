# -*- coding: utf-8 -*-
"""
向前向后逐步变量选择器

实现Stepwise Forward-Backward变量选择算法，结合向前选择与向后消除。
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Callable, Optional
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import SelectionResult
from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_weighted_score,
    compare_scores_with_winrate
)
from dashboard.models.DFM.train.utils.parallel_config import ParallelConfig
from dashboard.models.DFM.train.utils.formatting import generate_progress_bar
from dashboard.models.DFM.train.selection.parallel_evaluator import evaluate_variable_changes

logger = get_logger(__name__)


class StepwiseSelector:
    """
    向前向后逐步变量选择器

    算法流程:
    1. 初始化：评估所有候选变量，选择单独RMSE最低的作为初始变量
    2. 前向步骤：从剩余变量中选择使RMSE下降最多的变量加入
    3. 后向步骤：检查是否有变量可移除（移除后RMSE仍能下降）
    4. 重复2-3直到无法添加新变量

    优化目标: 最小化RMSE
    """

    def __init__(
        self,
        evaluator_func: Callable,
        criterion: str = 'rmse',
        min_variables: int = 1,
        parallel_config: ParallelConfig = None
    ):
        """
        Args:
            evaluator_func: 评估函数,签名为 (variables, **kwargs) -> (
                is_rmse, oos_rmse, _, _, is_win_rate, oos_win_rate,
                is_svd_error, _, _
            )
            criterion: 优化准则,'rmse'(RMSE为主，Win Rate为辅)
            min_variables: 最少保留的变量数
            parallel_config: 并行配置（必填）
        """
        if parallel_config is None:
            raise ValueError("parallel_config参数必填，请提供ParallelConfig对象")
        self.evaluator_func = evaluator_func
        self.criterion = criterion
        self.min_variables = max(1, min_variables)
        self.parallel_config = parallel_config

    def select(
        self,
        initial_variables: List[str],
        target_variable: str,
        full_data: pd.DataFrame,
        params: Dict,
        validation_start: str,
        validation_end: str,
        target_freq: str,
        training_start_date: str,
        train_end_date: str,
        target_mean_original: float = 0.0,
        target_std_original: float = 1.0,
        max_iter: int = 30,
        max_lags: int = 1,
        progress_callback: Optional[Callable[[str], None]] = None,
        use_optimization: bool = False
    ) -> SelectionResult:
        """
        执行向前向后变量选择

        Args:
            initial_variables: 初始变量列表(包含目标变量)
            target_variable: 目标变量名称
            full_data: 完整数据DataFrame
            params: DFM参数字典(包含k_factors等)
            validation_start: 验证集开始日期（必填）
            validation_end: 验证集结束日期（必填）
            target_freq: 目标频率
            training_start_date: 训练集开始日期（必填）
            train_end_date: 训练集结束日期（必填）
            target_mean_original: 目标变量原始均值
            target_std_original: 目标变量原始标准差
            max_iter: 最大EM迭代次数
            max_lags: 最大滞后阶数
            progress_callback: 进度回调函数
            use_optimization: 是否使用预计算优化

        Returns:
            SelectionResult对象
        """
        # 保存评估参数供辅助方法使用
        self._eval_params = {
            'full_data': full_data,
            'target_variable': target_variable,
            'params': params,
            'validation_start': validation_start,
            'validation_end': validation_end,
            'target_freq': target_freq,
            'training_start_date': training_start_date,
            'train_end_date': train_end_date,
            'target_mean_original': target_mean_original,
            'target_std_original': target_std_original,
            'max_iter': max_iter,
            'max_lags': max_lags,
            'progress_callback': progress_callback,
            'rmse_tolerance_percent': params.get('rmse_tolerance_percent', 1.0),  # RMSE容忍度配置
            'win_rate_tolerance_percent': params.get('win_rate_tolerance_percent', 5.0),  # Win Rate容忍度配置
            'selection_criterion': params.get('selection_criterion', 'hybrid'),  # 筛选标准
            'prioritize_win_rate': params.get('prioritize_win_rate', True),  # 混合策略优先级
            'training_weight': params.get('training_weight', 0.5)  # 训练期权重（2025-12-20新增）
        }

        total_evaluations = 0
        svd_error_count = 0
        selection_history = []

        # 1. 初始化候选变量（排除目标变量）
        candidate_vars = sorted([v for v in initial_variables if v != target_variable])
        if not candidate_vars:
            logger.error("初始候选变量列表为空，无法进行筛选")
            return SelectionResult(
                selected_variables=initial_variables,
                selection_history=[],
                final_score=(np.nan, -np.inf, np.inf),
                total_evaluations=0,
                svd_error_count=0
            )

        # 输出开始信息（同时输出到控制台和回调）
        start_msg = (
            f"========== 变量选择开始（向前向后法）==========\n"
            f"候选变量数: {len(candidate_vars)}"
        )
        print(start_msg)
        if progress_callback:
            progress_callback(start_msg)

        logger.info(f"\n{'='*60}")
        logger.info(f"向前向后法变量选择 - 候选变量数: {len(candidate_vars)}")
        logger.info(f"{'='*60}")

        # 2. 找到最优初始变量（可能是单个变量或多个变量，取决于k_factors）
        initial_vars_list, current_score, eval_count, svd_count, current_is_rmse, current_oos_rmse = self._find_initial_variable(
            candidate_vars, progress_callback
        )
        total_evaluations += eval_count
        svd_error_count += svd_count

        if initial_vars_list is None:
            logger.error("无法找到有效的初始变量")
            return SelectionResult(
                selected_variables=initial_variables,
                selection_history=[],
                final_score=(np.nan, -np.inf, np.inf),
                total_evaluations=total_evaluations,
                svd_error_count=svd_error_count
            )

        current_vars = initial_vars_list.copy()
        remaining_vars = [v for v in candidate_vars if v not in initial_vars_list]

        # 保存基线值用于最终汇总
        baseline_is_rmse = current_is_rmse
        baseline_oos_rmse = current_oos_rmse
        baseline_var_count = len(current_vars)

        # 记录初始化历史
        selection_history.append({
            'iteration': 0,
            'action': 'init',
            'variable': initial_vars_list,  # 现在是列表
            'score': current_score,
            'current_vars': current_vars.copy(),
            'var_count': len(current_vars),
            'is_rmse': current_is_rmse,
            'oos_rmse': current_oos_rmse
        })

        # 输出初始变量信息（同时输出到控制台和回调）
        init_vars_str = ', '.join(f"'{v}'" for v in initial_vars_list)
        init_msg = (
            f"初始变量: [{init_vars_str}]\n"
            f"  基线训练期RMSE: {current_is_rmse:.4f}\n"
            f"  基线验证期RMSE: {current_oos_rmse:.4f}"
        )
        print(init_msg)
        if progress_callback:
            progress_callback(init_msg)

        # 3. 迭代：前向+后向
        iteration = 0
        while remaining_vars:
            iteration += 1
            self._log_iteration_start(iteration, len(current_vars), len(remaining_vars), progress_callback)

            # 3.1 前向步骤：尝试添加变量
            best_add, new_score, eval_count, svd_count, new_is_rmse, new_oos_rmse = self._forward_step(
                current_vars, remaining_vars, progress_callback
            )
            total_evaluations += eval_count
            svd_error_count += svd_count

            if best_add is None:
                # 无法添加新变量，终止
                logger.info("前向步骤：无法找到能降低RMSE的变量，筛选结束")
                if progress_callback:
                    progress_callback("  前向：无法找到能降低RMSE的变量，筛选结束")
                break

            # 检查是否有性能提升
            if new_score <= current_score:
                logger.info(
                    f"前向步骤：添加任何变量都无法提升性能 "
                    f"(当前验证期RMSE={-current_score[1]:.6f}; 最佳候选验证期RMSE={-new_score[1]:.6f})"
                )
                if progress_callback:
                    progress_callback(
                        f"  前向：添加任何变量都无法提升性能，筛选结束"
                    )
                break

            # 添加变量
            delta_oos_rmse = current_oos_rmse - new_oos_rmse
            current_vars.append(best_add)
            if best_add not in remaining_vars:
                raise RuntimeError(
                    f"内部错误：变量'{best_add}'不在remaining_vars中。"
                    f"这是一个逻辑错误，请报告此问题。"
                )
            remaining_vars.remove(best_add)

            # 记录前向步骤历史
            selection_history.append({
                'iteration': iteration,
                'action': 'add',
                'variable': best_add,
                'score': new_score,
                'current_vars': current_vars.copy(),
                'var_count': len(current_vars),
                'is_rmse': new_is_rmse,
                'oos_rmse': new_oos_rmse
            })

            logger.info(
                f"前向步骤：添加'{best_add}', 变量数: {len(current_vars)}, "
                f"验证期RMSE: {current_oos_rmse:.4f} -> {new_oos_rmse:.4f} (改善: {delta_oos_rmse:+.4f})"
            )
            # 输出前向步骤结果（同时输出到控制台和回调）
            rmse_improve_pct = (current_oos_rmse - new_oos_rmse) / current_oos_rmse * 100 if current_oos_rmse > 0 else 0
            rmse_change = f"降低{rmse_improve_pct:.1f}%" if rmse_improve_pct > 0 else f"上升{-rmse_improve_pct:.1f}%"
            forward_msg = (
                f"  前向：添加 '{best_add}', 当前{len(current_vars)}个变量\n"
                f"    验证期RMSE: {current_oos_rmse:.4f} -> {new_oos_rmse:.4f} ({rmse_change})"
            )
            print(forward_msg)
            if progress_callback:
                progress_callback(forward_msg)

            # 更新当前得分
            current_score = new_score
            current_is_rmse = new_is_rmse
            current_oos_rmse = new_oos_rmse

            # 3.2 后向步骤：检查并移除冗余变量
            if len(current_vars) > self.min_variables:
                vars_after_backward, backward_score, eval_count, svd_count, backward_is_rmse, backward_oos_rmse, removed_vars = self._backward_step(
                    current_vars, current_score, current_is_rmse, current_oos_rmse, progress_callback
                )
                total_evaluations += eval_count
                svd_error_count += svd_count

                if len(vars_after_backward) < len(current_vars):
                    # 有变量被移除，更新状态
                    for var in removed_vars:
                        # 记录后向步骤历史
                        selection_history.append({
                            'iteration': iteration,
                            'action': 'remove',
                            'variable': var,
                            'score': backward_score,
                            'current_vars': vars_after_backward.copy(),
                            'var_count': len(vars_after_backward),
                            'is_rmse': backward_is_rmse,
                            'oos_rmse': backward_oos_rmse
                        })

                    # 移除的变量回归候选池
                    remaining_vars.extend(removed_vars)
                    current_vars = vars_after_backward
                    current_score = backward_score
                    current_is_rmse = backward_is_rmse
                    current_oos_rmse = backward_oos_rmse

        # 4. 返回结果
        return self._build_selection_result(
            current_vars, selection_history,
            current_score, total_evaluations, svd_error_count,
            len(initial_variables),
            current_is_rmse, current_oos_rmse,
            baseline_is_rmse, baseline_oos_rmse, baseline_var_count
        )

    def _log_iteration_start(
        self,
        iteration: int,
        n_current: int,
        n_remaining: int,
        progress_callback: Optional[Callable]
    ):
        """记录迭代开始信息"""
        logger.info(f"\n{'='*60}")
        logger.info(f"向前向后法 - 第{iteration}轮 (当前{n_current}个变量, 剩余{n_remaining}个候选)")
        logger.info(f"{'='*60}")

        # 进度显示（同时输出到控制台和回调）
        estimated_max_rounds = n_current + n_remaining
        progress_bar = generate_progress_bar(n_current, estimated_max_rounds)
        iter_msg = f"\n{progress_bar} 第{iteration}轮 (当前{n_current}个变量, 剩余{n_remaining}个候选)"
        print(iter_msg)
        if progress_callback:
            progress_callback(iter_msg)

    def _find_initial_variable(
        self,
        candidate_vars: List[str],
        progress_callback: Optional[Callable]
    ) -> Tuple[Optional[List[str]], Tuple[float, float, float], int, int, float, float]:
        """
        找到最优初始变量集

        根据k_factors约束，选择满足约束的最少初始变量。
        如果k_factors=1，评估单个变量；如果k_factors>1，先用相关性预选，再评估组合。

        Returns:
            (最优变量列表, 得分, 评估次数, SVD错误数, is_rmse, oos_rmse)
        """
        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params'].get('k_factors', 1)
        full_data = self._eval_params['full_data']

        # 计算满足k_factors约束所需的最少预测变量数
        # 约束：k_factors < len([target] + predictors) = 1 + n_predictors
        # 即：n_predictors > k_factors - 1，即 n_predictors >= k_factors
        min_init_vars = max(1, k_factors)

        # 检查变量数是否足够
        if len(candidate_vars) < min_init_vars:
            logger.error(
                f"候选变量数({len(candidate_vars)})不足以满足k_factors({k_factors})约束，"
                f"需要至少{min_init_vars}个预测变量"
            )
            return (None, (np.nan, -np.inf, np.inf), 0, 0, np.inf, np.inf)

        logger.info(f"初始化：k_factors={k_factors}，需要至少{min_init_vars}个初始变量")
        if progress_callback:
            progress_callback(f"初始化：k_factors={k_factors}，需要至少{min_init_vars}个初始变量")

        # 准备可序列化的评估器配置
        evaluator_config = {
            'training_start': self._eval_params['training_start_date'],
            'train_end': self._eval_params['train_end_date'],
            'validation_start': self._eval_params['validation_start'],
            'validation_end': self._eval_params['validation_end'],
            'max_iterations': self._eval_params.get('max_iter', 30),
            'tolerance': self._eval_params.get('tolerance', 1e-4),
            'alignment_mode': self._eval_params.get('alignment_mode', 'next_month')
        }

        if min_init_vars == 1:
            # k_factors=1时，评估单个变量
            return self._find_single_initial_variable(
                candidate_vars, evaluator_config, progress_callback
            )
        else:
            # k_factors>1时，需要多个初始变量
            return self._find_multiple_initial_variables(
                candidate_vars, min_init_vars, evaluator_config, progress_callback
            )

    def _find_single_initial_variable(
        self,
        candidate_vars: List[str],
        evaluator_config: Dict,
        progress_callback: Optional[Callable]
    ) -> Tuple[Optional[List[str]], Tuple[float, float], int, int, float, float]:
        """当k_factors=1时，评估单个变量找最优"""
        logger.info(f"评估 {len(candidate_vars)} 个候选变量...")
        if progress_callback:
            progress_callback(f"评估 {len(candidate_vars)} 个候选变量...")

        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params'].get('k_factors', 1)

        # 判断是否使用并行
        use_parallel = self.parallel_config.should_use_parallel(len(candidate_vars))

        # 评估每个变量单独的性能
        candidate_results = evaluate_variable_changes(
            current_predictors=[],
            candidate_vars=candidate_vars,
            target_variable=target_variable,
            full_data=self._eval_params['full_data'],
            k_factors=k_factors,
            evaluator_config=evaluator_config,
            operation='add',
            n_jobs=self.parallel_config.get_effective_n_jobs() if use_parallel else 1,
            backend=self.parallel_config.backend,
            verbose=self.parallel_config.verbose,
            progress_callback=progress_callback
        )

        if not candidate_results:
            logger.error("所有候选变量评估失败")
            return (None, (np.nan, -np.inf, np.inf), len(candidate_vars), 0, np.inf, np.inf)

        # 找出最优变量
        best_var = None
        best_score = (np.nan, -np.inf, np.inf)
        best_is_rmse = np.inf
        best_oos_rmse = np.inf
        svd_error_count = 0

        for result in candidate_results:
            if result.get('is_svd_error', False):
                svd_error_count += 1

            # 使用加权得分计算（2025-12-20修改）
            score = calculate_weighted_score(
                result['is_rmse'],
                result['oos_rmse'],
                result.get('is_win_rate', np.nan),
                result.get('oos_win_rate', np.nan),
                training_weight=self._eval_params.get('training_weight', 0.5)
            )

            comparison = compare_scores_with_winrate(
                score,
                best_score,
                rmse_tolerance_percent=self._eval_params.get('rmse_tolerance_percent', 1.0),
                win_rate_tolerance_percent=self._eval_params.get('win_rate_tolerance_percent', 5.0),
                selection_criterion=self._eval_params.get('selection_criterion', 'hybrid'),
                prioritize_win_rate=self._eval_params.get('prioritize_win_rate', True)
            )
            if np.isfinite(score[1]) and comparison > 0:
                best_score = score
                best_var = result['var']
                best_is_rmse = result['is_rmse']
                best_oos_rmse = result['oos_rmse']

        # 打印汇总
        self._print_initial_summary(candidate_results, best_var, progress_callback)

        if best_var is None:
            return (None, (np.nan, -np.inf, np.inf), len(candidate_results), svd_error_count, np.inf, np.inf)

        return ([best_var], best_score, len(candidate_results), svd_error_count, best_is_rmse, best_oos_rmse)

    def _find_multiple_initial_variables(
        self,
        candidate_vars: List[str],
        min_init_vars: int,
        evaluator_config: Dict,
        progress_callback: Optional[Callable]
    ) -> Tuple[Optional[List[str]], Tuple[float, float], int, int, float, float]:
        """
        当k_factors>1时，使用相关性预选+贪婪搜索找最优初始变量集
        """
        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params'].get('k_factors', 1)
        full_data = self._eval_params['full_data']

        logger.info(f"k_factors={k_factors}，使用相关性预选{min_init_vars}个初始变量...")
        if progress_callback:
            progress_callback(f"k_factors={k_factors}，使用相关性预选{min_init_vars}个初始变量...")

        # 计算每个候选变量与目标变量的相关性
        target_data = full_data[target_variable].dropna()
        correlations = []
        for var in candidate_vars:
            var_data = full_data[var].dropna()
            # 对齐索引
            common_idx = target_data.index.intersection(var_data.index)
            if len(common_idx) > 10:
                corr = abs(target_data.loc[common_idx].corr(var_data.loc[common_idx]))
                if np.isfinite(corr):
                    correlations.append((var, corr))
                else:
                    correlations.append((var, 0.0))
            else:
                correlations.append((var, 0.0))

        # 按相关性排序，选择最相关的min_init_vars个变量
        correlations.sort(key=lambda x: x[1], reverse=True)
        initial_vars = [v[0] for v in correlations[:min_init_vars]]

        logger.info(f"预选初始变量（按相关性）: {initial_vars}")
        if progress_callback:
            progress_callback(f"预选初始变量: {', '.join(initial_vars)}")

        # 评估这个初始变量集的性能
        temp_variables = [target_variable] + initial_vars

        # 直接调用评估函数
        from dashboard.models.DFM.train.training.evaluator_strategy import _evaluate_variable_selection_model

        try:
            result_tuple = _evaluate_variable_selection_model(
                variables=temp_variables,
                target_variable=target_variable,
                full_data=full_data,
                k_factors=k_factors,
                training_start=evaluator_config['training_start'],
                train_end=evaluator_config['train_end'],
                validation_start=evaluator_config['validation_start'],
                validation_end=evaluator_config['validation_end'],
                max_iterations=evaluator_config['max_iterations'],
                tolerance=evaluator_config['tolerance'],
                alignment_mode=evaluator_config.get('alignment_mode', 'next_month')
            )

            if len(result_tuple) != 9:
                logger.error(f"初始变量集评估返回了{len(result_tuple)}个值")
                return (None, (np.nan, -np.inf, np.inf), 1, 0, np.inf, np.inf)

            is_rmse, oos_rmse, _, _, is_win_rate, oos_win_rate, is_svd_error, _, _ = result_tuple
            svd_count = 1 if is_svd_error else 0

            # 使用加权得分计算（2025-12-20修改）
            score = calculate_weighted_score(
                is_rmse, oos_rmse, is_win_rate, oos_win_rate,
                training_weight=self._eval_params.get('training_weight', 0.5)
            )

            win_rate_str = f", Win Rate={oos_win_rate:.1f}%" if np.isfinite(oos_win_rate) else ""
            logger.info(
                f"初始变量集评估完成: {len(initial_vars)}个变量, "
                f"训练期RMSE={is_rmse:.4f}, 验证期RMSE={oos_rmse:.4f}{win_rate_str}"
            )
            if progress_callback:
                progress_callback(
                    f"初始变量集: {len(initial_vars)}个变量, "
                    f"训练期RMSE={is_rmse:.4f}, 验证期RMSE={oos_rmse:.4f}"
                )

            return (initial_vars, score, 1, svd_count, is_rmse, oos_rmse)

        except Exception as e:
            logger.error(f"初始变量集评估失败: {e}")
            return (None, (np.nan, -np.inf, np.inf), 1, 0, np.inf, np.inf)

    def _print_initial_summary(
        self,
        candidate_results: List[Dict],
        best_var: Optional[str],
        progress_callback: Optional[Callable]
    ):
        """打印初始变量候选汇总"""
        if not candidate_results:
            return

        summary_msg = f"\n  初始变量候选汇总 (共{len(candidate_results)}个有效):"
        logger.info(summary_msg)
        if progress_callback:
            progress_callback(summary_msg)

        # 按RMSE排序显示前5个
        sorted_results = sorted(candidate_results, key=lambda x: x['oos_rmse'])
        for i, res in enumerate(sorted_results[:5]):
            is_best = " <- 最优" if res['var'] == best_var else ""
            msg = f"    {i+1}. '{res['var']}': 验证期RMSE={res['oos_rmse']:.4f}{is_best}"
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

    def _forward_step(
        self,
        current_vars: List[str],
        remaining_vars: List[str],
        progress_callback: Optional[Callable]
    ) -> Tuple[Optional[str], Tuple[float, float, float], int, int, float, float]:
        """
        前向步骤：找出最佳添加候选

        从remaining_vars中找出加入后使RMSE下降最多的变量

        Returns:
            (最佳变量名, 得分, 评估次数, SVD错误数, is_rmse, oos_rmse)
        """
        if not remaining_vars:
            return (None, (np.nan, -np.inf, np.inf), 0, 0, np.inf, np.inf)

        logger.info(f"  前向步骤：评估添加 {len(remaining_vars)} 个候选变量...")
        if progress_callback:
            progress_callback(f"  前向：评估添加 {len(remaining_vars)} 个候选变量...")

        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params'].get('k_factors', 1)

        # 准备可序列化的评估器配置
        evaluator_config = {
            'training_start': self._eval_params['training_start_date'],
            'train_end': self._eval_params['train_end_date'],
            'validation_start': self._eval_params['validation_start'],
            'validation_end': self._eval_params['validation_end'],
            'max_iterations': self._eval_params.get('max_iter', 30),
            'tolerance': self._eval_params.get('tolerance', 1e-4),
            'alignment_mode': self._eval_params.get('alignment_mode', 'next_month')
        }

        # 判断是否使用并行
        use_parallel = self.parallel_config.should_use_parallel(len(remaining_vars))

        # 评估添加每个候选变量的效果
        candidate_results = evaluate_variable_changes(
            current_predictors=current_vars,
            candidate_vars=remaining_vars,
            target_variable=target_variable,
            full_data=self._eval_params['full_data'],
            k_factors=k_factors,
            evaluator_config=evaluator_config,
            operation='add',
            n_jobs=self.parallel_config.get_effective_n_jobs() if use_parallel else 1,
            backend=self.parallel_config.backend,
            verbose=self.parallel_config.verbose,
            progress_callback=progress_callback
        )

        if not candidate_results:
            logger.warning("前向步骤：所有候选变量评估失败")
            return (None, (np.nan, -np.inf, np.inf), len(remaining_vars), 0, np.inf, np.inf)

        # 找出最优添加候选
        best_var = None
        best_score = (np.nan, -np.inf, np.inf)
        best_is_rmse = np.inf
        best_oos_rmse = np.inf
        svd_error_count = 0

        for result in candidate_results:
            if result.get('is_svd_error', False):
                svd_error_count += 1

            # 使用加权得分计算（2025-12-20修改）
            score = calculate_weighted_score(
                result['is_rmse'],
                result['oos_rmse'],
                result.get('is_win_rate', np.nan),
                result.get('oos_win_rate', np.nan),
                training_weight=self._eval_params.get('training_weight', 0.5)
            )

            comparison = compare_scores_with_winrate(
                score,
                best_score,
                rmse_tolerance_percent=self._eval_params.get('rmse_tolerance_percent', 1.0),
                win_rate_tolerance_percent=self._eval_params.get('win_rate_tolerance_percent', 5.0),
                selection_criterion=self._eval_params.get('selection_criterion', 'hybrid'),
                prioritize_win_rate=self._eval_params.get('prioritize_win_rate', True)
            )
            if np.isfinite(score[1]) and comparison > 0:
                best_score = score
                best_var = result['var']
                best_is_rmse = result['is_rmse']
                best_oos_rmse = result['oos_rmse']

        return (best_var, best_score, len(candidate_results), svd_error_count, best_is_rmse, best_oos_rmse)

    def _backward_step(
        self,
        current_vars: List[str],
        current_score: Tuple[float, float, float],
        current_is_rmse: float,
        current_oos_rmse: float,
        progress_callback: Optional[Callable]
    ) -> Tuple[List[str], Tuple[float, float, float], int, int, float, float, List[str]]:
        """
        后向步骤：移除冗余变量

        检查current_vars中是否有变量可移除（移除后RMSE仍能下降）
        连续检查直到无法移除

        Args:
            current_vars: 当前变量列表
            current_score: 当前得分
            current_is_rmse: 当前训练期RMSE
            current_oos_rmse: 当前验证期RMSE
            progress_callback: 进度回调函数

        Returns:
            (移除后的变量列表, 最终得分, 评估次数, SVD错误数, is_rmse, oos_rmse, 被移除的变量列表)
        """
        if len(current_vars) <= self.min_variables:
            return (current_vars, current_score, 0, 0, current_is_rmse, current_oos_rmse, [])

        logger.info(f"  后向步骤：检查 {len(current_vars)} 个变量是否可移除...")
        if progress_callback:
            progress_callback(f"  后向：检查 {len(current_vars)} 个变量是否可移除...")

        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params'].get('k_factors', 1)

        # 准备可序列化的评估器配置
        evaluator_config = {
            'training_start': self._eval_params['training_start_date'],
            'train_end': self._eval_params['train_end_date'],
            'validation_start': self._eval_params['validation_start'],
            'validation_end': self._eval_params['validation_end'],
            'max_iterations': self._eval_params.get('max_iter', 30),
            'tolerance': self._eval_params.get('tolerance', 1e-4),
            'alignment_mode': self._eval_params.get('alignment_mode', 'next_month')
        }

        total_evals = 0
        total_svd_errors = 0
        removed_vars = []
        working_vars = current_vars.copy()
        working_score = current_score
        working_is_rmse = current_is_rmse
        working_oos_rmse = current_oos_rmse

        # 连续检查直到无法移除
        while len(working_vars) > self.min_variables:
            # 判断是否使用并行
            use_parallel = self.parallel_config.should_use_parallel(len(working_vars))

            # 评估移除每个变量的效果
            candidate_results = evaluate_variable_changes(
                current_predictors=working_vars,
                candidate_vars=working_vars,
                target_variable=target_variable,
                full_data=self._eval_params['full_data'],
                k_factors=k_factors,
                evaluator_config=evaluator_config,
                operation='remove',
                n_jobs=self.parallel_config.get_effective_n_jobs() if use_parallel else 1,
                backend=self.parallel_config.backend,
                verbose=self.parallel_config.verbose,
                progress_callback=None  # 后向步骤不显示详细进度
            )

            total_evals += len(working_vars)

            if not candidate_results:
                break

            # 找出最优移除候选
            best_removal = None
            best_removal_score = (np.nan, -np.inf, np.inf)
            best_removal_is_rmse = np.inf
            best_removal_oos_rmse = np.inf

            for result in candidate_results:
                if result.get('is_svd_error', False):
                    total_svd_errors += 1

                # 使用加权得分计算（2025-12-20修改）
                score = calculate_weighted_score(
                    result['is_rmse'],
                    result['oos_rmse'],
                    result.get('is_win_rate', np.nan),
                    result.get('oos_win_rate', np.nan),
                    training_weight=self._eval_params.get('training_weight', 0.5)
                )

                comparison = compare_scores_with_winrate(
                    score,
                    best_removal_score,
                    rmse_tolerance_percent=self._eval_params.get('rmse_tolerance_percent', 1.0),
                    win_rate_tolerance_percent=self._eval_params.get('win_rate_tolerance_percent', 5.0),
                    selection_criterion=self._eval_params.get('selection_criterion', 'hybrid'),
                    prioritize_win_rate=self._eval_params.get('prioritize_win_rate', True)
                )
                if np.isfinite(score[1]) and comparison > 0:
                    best_removal_score = score
                    best_removal = result['var']
                    best_removal_is_rmse = result['is_rmse']
                    best_removal_oos_rmse = result['oos_rmse']

            # 检查移除后是否有改善
            if best_removal is None or best_removal_score <= working_score:
                # 无法移除任何变量
                logger.info("  后向步骤：无变量可移除")
                if progress_callback:
                    progress_callback("  后向：无变量可移除")
                break

            # 移除变量
            delta_oos_rmse = working_oos_rmse - best_removal_oos_rmse
            old_working_oos_rmse = working_oos_rmse  # 保存旧值用于百分比计算
            if best_removal not in working_vars:
                raise RuntimeError(
                    f"内部错误：变量'{best_removal}'不在working_vars中。"
                    f"这是一个逻辑错误，请报告此问题。"
                )
            working_vars.remove(best_removal)
            removed_vars.append(best_removal)
            working_score = best_removal_score
            working_is_rmse = best_removal_is_rmse
            working_oos_rmse = best_removal_oos_rmse

            logger.info(
                f"  后向步骤：移除'{best_removal}', 变量数: {len(working_vars)}, "
                f"验证期RMSE改善: {delta_oos_rmse:+.4f}"
            )
            # 输出后向步骤结果（同时输出到控制台和回调）
            rmse_improve_pct = (old_working_oos_rmse - best_removal_oos_rmse) / old_working_oos_rmse * 100 if old_working_oos_rmse > 0 else 0
            rmse_change = f"降低{rmse_improve_pct:.1f}%" if rmse_improve_pct > 0 else f"上升{-rmse_improve_pct:.1f}%"
            backward_msg = (
                f"  后向：移除 '{best_removal}', 剩余{len(working_vars)}个变量\n"
                f"    验证期RMSE: {old_working_oos_rmse:.4f} -> {best_removal_oos_rmse:.4f} ({rmse_change})"
            )
            print(backward_msg)
            if progress_callback:
                progress_callback(backward_msg)

        return (working_vars, working_score, total_evals, total_svd_errors, working_is_rmse, working_oos_rmse, removed_vars)

    def _build_selection_result(
        self,
        final_predictors: List[str],
        history: List[Dict],
        final_score: Tuple[float, float, float],
        total_evals: int,
        svd_errors: int,
        n_initial_vars: int,
        final_is_rmse: float,
        final_oos_rmse: float,
        baseline_is_rmse: float = 0.0,
        baseline_oos_rmse: float = 0.0,
        baseline_var_count: int = 0
    ) -> SelectionResult:
        """构建选择结果对象"""
        target_variable = self._eval_params['target_variable']
        final_variables = [target_variable] + final_predictors
        progress_callback = self._eval_params.get('progress_callback')

        logger.info(
            f"\n向前向后法变量选择完成: 从{n_initial_vars-1}个候选变量中选出{len(final_predictors)}个\n"
            f"  训练期RMSE: {final_is_rmse:.4f}\n"
            f"  验证期RMSE: {final_oos_rmse:.4f}"
        )

        # 输出最终汇总（同时输出到控制台和回调）
        # 统计操作历史
        added_vars = [h['variable'] for h in history if h.get('action') == 'add']
        removed_vars = [h['variable'] for h in history if h.get('action') == 'remove']

        # 计算总改善
        rmse_improve_pct = (baseline_oos_rmse - final_oos_rmse) / baseline_oos_rmse * 100 if baseline_oos_rmse > 0 else 0
        rmse_summary = f"降低{rmse_improve_pct:.1f}%" if rmse_improve_pct > 0 else f"上升{-rmse_improve_pct:.1f}%"

        final_msg = (
            f"\n========== 变量选择完成 ==========\n"
            f"总轮次: {len([h for h in history if h.get('action') in ['add', 'remove']])}\n"
            f"添加变量: {', '.join(added_vars) if added_vars else '无'}\n"
            f"移除变量: {', '.join(removed_vars) if removed_vars else '无'}\n"
            f"RMSE总改善: {baseline_oos_rmse:.4f} -> {final_oos_rmse:.4f} ({rmse_summary})\n"
            f"最终变量数: {len(final_predictors)}个"
        )
        print(final_msg)
        if progress_callback:
            progress_callback(final_msg)

        return SelectionResult(
            selected_variables=final_variables,
            selection_history=history,
            final_score=final_score,
            total_evaluations=total_evals,
            svd_error_count=svd_errors
        )


__all__ = ['StepwiseSelector']
