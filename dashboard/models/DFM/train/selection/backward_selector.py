# -*- coding: utf-8 -*-
"""
后向逐步变量选择器

实现后向逐步变量剔除算法,以RMSE作为优化目标。
参考train_model/variable_selection.py的核心逻辑,但简化为更清晰的面向对象设计。
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


class BackwardSelector:
    """
    后向逐步变量选择器

    算法流程:
    1. 从全部变量开始
    2. 逐个尝试剔除每个变量
    3. 评估剔除后的模型性能
    4. 选择性能提升最大的变量剔除
    5. 重复直到无法提升

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
        if min_variables < 1:
            raise ValueError(f"min_variables必须 >= 1, 当前值: {min_variables}")
        self.evaluator_func = evaluator_func
        self.criterion = criterion
        self.min_variables = min_variables
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
        max_iter: int = 30,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> SelectionResult:
        """
        执行后向变量选择

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
            max_iter: 最大EM迭代次数
            progress_callback: 进度回调函数

        Returns:
            SelectionResult对象
        """
        # 验证params中的必需键
        required_param_keys = ['k_factors', 'rmse_tolerance_percent', 'win_rate_tolerance_percent',
                               'selection_criterion', 'prioritize_win_rate', 'training_weight',
                               'factor_selection_method', 'pca_threshold', 'kaiser_threshold',
                               'tolerance', 'alignment_mode']
        for key in required_param_keys:
            if key not in params:
                raise ValueError(f"params缺少必需参数: {key}")

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
            'max_iter': max_iter,
            'tolerance': params['tolerance'],
            'alignment_mode': params['alignment_mode'],
            'progress_callback': progress_callback,
            'rmse_tolerance_percent': params['rmse_tolerance_percent'],
            'win_rate_tolerance_percent': params['win_rate_tolerance_percent'],
            'selection_criterion': params['selection_criterion'],
            'prioritize_win_rate': params['prioritize_win_rate'],
            'training_weight': params['training_weight']
        }

        total_evaluations = 0
        svd_error_count = 0
        selection_history = []

        # 1. 初始化预测变量
        current_predictors = self._initialize_predictors(initial_variables, target_variable)
        if not current_predictors:
            return SelectionResult(
                selected_variables=initial_variables,
                selection_history=[],
                final_score=(np.nan, -np.inf, np.inf),
                total_evaluations=0,
                svd_error_count=0
            )

        # 2. 计算初始基准性能
        current_best_score, eval_count, svd_count, current_is_rmse, current_oos_rmse, current_is_win_rate, current_oos_win_rate = self._evaluate_baseline(
            current_predictors, progress_callback
        )
        total_evaluations += eval_count
        svd_error_count += svd_count

        # 保存基线值用于最终汇总
        baseline_oos_rmse = current_oos_rmse
        baseline_oos_win_rate = current_oos_win_rate

        # 3. 迭代移除变量
        iteration = 0
        while self._should_continue_selection(current_predictors, iteration):
            iteration += 1
            self._log_iteration_start(iteration, len(current_predictors), progress_callback)

            # 找到本轮最佳移除候选
            best_removal, best_score_this_iter, eval_count, svd_count, best_is_rmse, best_oos_rmse, best_is_win_rate, best_oos_win_rate = self._find_best_removal_candidate(
                current_predictors
            )
            total_evaluations += eval_count
            svd_error_count += svd_count

            # 检查是否找到有效的移除候选
            if best_removal is None:
                logger.warning("本轮无可行的移除候选，筛选结束")
                break

            # 检查是否有性能提升（根据筛选策略）
            comparison = compare_scores_with_winrate(
                best_score_this_iter,
                current_best_score,
                rmse_tolerance_percent=self._eval_params['rmse_tolerance_percent'],
                win_rate_tolerance_percent=self._eval_params['win_rate_tolerance_percent'],
                selection_criterion=self._eval_params['selection_criterion'],
                prioritize_win_rate=self._eval_params['prioritize_win_rate']
            )
            if comparison < 0:
                logger.warning(
                    f"移除任何变量都无法提升性能 "
                    f"(当前验证期RMSE={-current_best_score[1]:.6f}; 最佳候选验证期RMSE={-best_score_this_iter[1]:.6f})"
                )
                break

            # 应用移除并记录历史
            self._apply_removal_and_record(
                current_predictors, best_removal, best_score_this_iter,
                current_best_score, iteration, selection_history, progress_callback,
                current_is_rmse, current_oos_rmse, best_is_rmse, best_oos_rmse,
                current_is_win_rate, current_oos_win_rate, best_is_win_rate, best_oos_win_rate
            )

            # 更新当前最佳得分和指标
            current_best_score = best_score_this_iter
            current_is_rmse = best_is_rmse
            current_oos_rmse = best_oos_rmse
            current_is_win_rate = best_is_win_rate
            current_oos_win_rate = best_oos_win_rate

        # 4. 返回结果
        return self._build_selection_result(
            current_predictors, selection_history,
            current_best_score, total_evaluations, svd_error_count,
            len(initial_variables), progress_callback,
            baseline_oos_rmse, baseline_oos_win_rate,
            current_oos_rmse, current_oos_win_rate
        )

    def _initialize_predictors(
        self,
        initial_variables: List[str],
        target_variable: str
    ) -> List[str]:
        """初始化预测变量列表"""
        predictors = sorted([v for v in initial_variables if v != target_variable])
        if not predictors:
            logger.error("初始预测变量列表为空，无法进行筛选")
        return predictors

    def _evaluate_baseline(
        self,
        current_predictors: List[str],
        progress_callback: Optional[Callable]
    ) -> Tuple[Tuple[float, float, float], int, int, float, float, float, float]:
        """计算初始基准性能（扩展返回RMSE和Win Rate）"""
        logger.info(f"计算初始基准性能，变量数: {len(current_predictors)}")

        target_variable = self._eval_params['target_variable']
        initial_vars = [target_variable] + current_predictors

        try:
            result_tuple = self.evaluator_func(variables=initial_vars, **self._eval_params)

            if len(result_tuple) != 9:
                raise ValueError(
                    f"评估函数返回了{len(result_tuple)}个值(预期9)。"
                    f"请检查评估函数实现是否正确。"
                )

            is_rmse, oos_rmse, _, _, is_win_rate, oos_win_rate, is_svd_error, _, _ = result_tuple
            svd_count = 1 if is_svd_error else 0

            # 使用加权得分计算（2025-12-20修改）
            score = calculate_weighted_score(
                is_rmse, oos_rmse, is_win_rate, oos_win_rate,
                training_weight=self._eval_params['training_weight']
            )

            if not np.isfinite(score[1]):
                logger.warning(f"初始基准评估返回无效分数（加权RMSE无效），使用最差分数")
                score = (np.nan, -np.inf, np.inf)

            win_rate_str = f", Win Rate: {oos_win_rate:.1f}%" if np.isfinite(oos_win_rate) else ""
            logger.info(
                f"初始基准得分 - 训练期RMSE: {is_rmse:.4f}, 验证期RMSE: {oos_rmse:.4f}{win_rate_str}, "
                f"变量数: {len(current_predictors)}"
            )

            # 输出基线模型RMSE和Win Rate（同时输出到控制台和回调）
            wr_display = f"{oos_win_rate:.1f}%" if np.isfinite(oos_win_rate) else "N/A"
            baseline_msg = (
                f"========== 变量选择开始 ==========\n"
                f"初始变量数: {len(current_predictors)}\n"
                f"基线验证期RMSE: {oos_rmse:.4f}\n"
                f"基线验证期胜率: {wr_display}"
            )
            print(baseline_msg)
            if progress_callback:
                progress_callback(baseline_msg)

            return (score, 1, svd_count, is_rmse, oos_rmse, is_win_rate, oos_win_rate)

        except Exception as e:
            logger.error(f"计算初始基准性能时出错: {e}")
            raise RuntimeError(f"计算初始基准性能失败: {e}") from e

    def _should_continue_selection(
        self,
        current_predictors: List[str],
        iteration: int
    ) -> bool:
        """判断是否应该继续变量选择"""
        # 变量数大于最小要求时继续选择
        return len(current_predictors) > self.min_variables

    def _log_iteration_start(
        self,
        iteration: int,
        n_vars: int,
        progress_callback: Optional[Callable]
    ):
        """记录迭代开始信息"""
        logger.info(f"\n{'='*60}")
        logger.info(f"变量选择 - 第{iteration}轮 (当前{n_vars}个变量)")
        logger.info(f"{'='*60}")

        # 进度显示（同时输出到控制台和回调）
        max_rounds = n_vars - self.min_variables
        progress_bar = generate_progress_bar(iteration, max_rounds)
        iter_msg = f"{progress_bar} 第{iteration}轮 (当前{n_vars}个变量)"
        print(iter_msg)
        if progress_callback:
            progress_callback(iter_msg)

    def _find_best_removal_candidate(
        self,
        current_predictors: List[str]
    ) -> Tuple[Optional[str], Tuple[float, float, float], int, int, Optional[float], Optional[float], float, float]:
        """找到本轮最佳移除候选（扩展返回is_rmse和oos_rmse）"""
        best_score = (np.nan, -np.inf, np.inf)
        best_var = None
        best_is_rmse = None
        best_oos_rmse = None
        total_evals = 0
        total_svd_errors = 0

        target_variable = self._eval_params['target_variable']
        k_factors = self._eval_params['params']['k_factors']
        progress_callback = self._eval_params['progress_callback']

        # 判断是否使用并行
        use_parallel = self.parallel_config.should_use_parallel(len(current_predictors))

        if use_parallel:
            # 准备可序列化的评估器配置（从eval_params提取，移除不可序列化的progress_callback）
            evaluator_config = {
                'training_start': self._eval_params['training_start_date'],
                'train_end': self._eval_params['train_end_date'],
                'validation_start': self._eval_params['validation_start'],
                'validation_end': self._eval_params['validation_end'],
                'max_iterations': self._eval_params['max_iter'],
                'tolerance': self._eval_params['tolerance'],
                'alignment_mode': self._eval_params['alignment_mode'],
                'factor_selection_method': self._eval_params['params']['factor_selection_method'],
                'pca_threshold': self._eval_params['params']['pca_threshold'],
                'kaiser_threshold': self._eval_params['params']['kaiser_threshold']
            }

            # 并行评估
            n_jobs = self.parallel_config.get_effective_n_jobs()
            logger.info(f"  使用并行评估 ({n_jobs} 核心)")
            candidate_results = evaluate_variable_changes(
                current_predictors=current_predictors,
                candidate_vars=current_predictors,
                target_variable=target_variable,
                full_data=self._eval_params['full_data'],
                k_factors=k_factors,
                evaluator_config=evaluator_config,
                operation='remove',
                n_jobs=n_jobs,
                backend=self.parallel_config.backend,
                verbose=self.parallel_config.verbose,
                progress_callback=progress_callback
            )
        else:
            # 串行评估（原有逻辑）
            candidate_results = []

            for idx, var in enumerate(current_predictors, 1):
                temp_predictors = [v for v in current_predictors if v != var]
                if not temp_predictors:
                    continue

                temp_variables = [target_variable] + temp_predictors

                # 检查因子数约束
                if k_factors >= len(temp_variables):
                    logger.debug(f"  [{idx}/{len(current_predictors)}] 跳过'{var}': k_factors({k_factors}) >= 剩余变量数({len(temp_variables)})")
                    continue

                # 打印正在尝试的变量（同时输出到UI和日志）
                msg = f"  [{idx}/{len(current_predictors)}] 尝试移除: '{var}'"
                logger.info(msg)
                if progress_callback:
                    progress_callback(msg)

                # 评估移除后的性能
                try:
                    result_tuple = self.evaluator_func(variables=temp_variables, **self._eval_params)
                    total_evals += 1

                    if len(result_tuple) != 9:
                        logger.warning(f"    评估返回了{len(result_tuple)}个值，跳过'{var}'")
                        continue

                    is_rmse, oos_rmse, _, _, is_win_rate, oos_win_rate, is_svd_error, _, _ = result_tuple
                    if is_svd_error:
                        total_svd_errors += 1
                        logger.warning(f"    SVD警告")

                    # 使用加权得分计算（2025-12-20修改）
                    score = calculate_weighted_score(
                        is_rmse, oos_rmse, is_win_rate, oos_win_rate,
                        training_weight=self._eval_params['training_weight']
                    )

                    # 打印评估结果（同时输出到UI和日志）
                    win_rate_str = f", Win Rate={oos_win_rate:.1f}%" if np.isfinite(oos_win_rate) else ""
                    msg = f"    训练期RMSE: {is_rmse:.4f}, 验证期RMSE: {oos_rmse:.4f}{win_rate_str}"
                    logger.info(msg)
                    if progress_callback:
                        progress_callback(msg)

                    # 记录候选结果
                    candidate_results.append({
                        'var': var,
                        'is_rmse': is_rmse,
                        'oos_rmse': oos_rmse,
                        'is_win_rate': is_win_rate,
                        'oos_win_rate': oos_win_rate,
                        'is_svd_error': is_svd_error
                    })

                except Exception as e:
                    logger.error(f"    评估移除'{var}'时出错: {e}")
                    continue

        # 获取容忍度配置
        rmse_tolerance = self._eval_params['rmse_tolerance_percent']
        win_rate_tolerance = self._eval_params['win_rate_tolerance_percent']

        # 处理评估结果，计算得分并找出最佳候选
        best_is_win_rate = np.nan
        best_oos_win_rate = np.nan
        for result in candidate_results:
            # 仅并行模式在此处计数（串行模式已在评估时计数）
            if use_parallel:
                total_evals += 1
                if result['is_svd_error']:
                    total_svd_errors += 1

            # 使用加权得分计算（2025-12-20修改）
            score = calculate_weighted_score(
                result['is_rmse'],
                result['oos_rmse'],
                result['is_win_rate'],
                result['oos_win_rate'],
                training_weight=self._eval_params['training_weight']
            )
            result['score'] = score

            # 更新最佳候选（根据筛选策略）
            comparison = compare_scores_with_winrate(
                score,
                best_score,
                rmse_tolerance_percent=rmse_tolerance,
                win_rate_tolerance_percent=win_rate_tolerance,
                selection_criterion=self._eval_params['selection_criterion'],
                prioritize_win_rate=self._eval_params['prioritize_win_rate']
            )
            if np.isfinite(score[1]) and comparison > 0:
                best_score = score
                best_var = result['var']
                best_is_rmse = result['is_rmse']
                best_oos_rmse = result['oos_rmse']
                best_is_win_rate = result['is_win_rate']
                best_oos_win_rate = result['oos_win_rate']

                if not use_parallel:
                    # 串行模式下实时标记最佳候选
                    msg = f"    *** 当前最佳候选 ***"
                    logger.info(msg)
                    if progress_callback:
                        progress_callback(msg)

        # 打印本轮汇总（同时输出到UI和日志）
        if candidate_results:
            summary_msg = f"\n  本轮候选汇总 (共{len(candidate_results)}个):"
            logger.info(summary_msg)
            if progress_callback:
                progress_callback(summary_msg)

            for res in candidate_results:
                is_best = " <- 最佳" if res['var'] == best_var else ""
                win_rate_str = f", Win Rate={res['oos_win_rate']:.1f}%" if np.isfinite(res['oos_win_rate']) else ""
                msg = (
                    f"    '{res['var']}': 训练期RMSE={res['is_rmse']:.4f}, "
                    f"验证期RMSE={res['oos_rmse']:.4f}{win_rate_str}{is_best}"
                )
                logger.info(msg)
                if progress_callback:
                    progress_callback(msg)

        return (best_var, best_score, total_evals, total_svd_errors, best_is_rmse, best_oos_rmse, best_is_win_rate, best_oos_win_rate)

    def _apply_removal_and_record(
        self,
        current_predictors: List[str],
        removed_var: str,
        new_score: Tuple[float, float, float],
        old_score: Tuple[float, float, float],
        iteration: int,
        history: List[Dict],
        progress_callback: Optional[Callable],
        old_is_rmse: float,
        old_oos_rmse: float,
        new_is_rmse: float,
        new_oos_rmse: float,
        old_is_win_rate: float,
        old_oos_win_rate: float,
        new_is_win_rate: float,
        new_oos_win_rate: float
    ):
        """应用变量移除并记录历史"""
        if removed_var not in current_predictors:
            raise RuntimeError(
                f"内部错误：变量'{removed_var}'不在current_predictors中。"
                f"这是一个逻辑错误，请报告此问题。"
            )
        current_predictors.remove(removed_var)

        # 记录选择历史
        history.append({
            'iteration': iteration,
            'removed_variable': removed_var,
            'score': new_score,
            'remaining_vars': current_predictors.copy(),
            'remaining_count': len(current_predictors)
        })

        # 计算改善量
        delta_is_rmse = old_is_rmse - new_is_rmse
        delta_oos_rmse = old_oos_rmse - new_oos_rmse

        # Win Rate变化字符串
        win_rate_change_str = ""
        if np.isfinite(old_oos_win_rate) or np.isfinite(new_oos_win_rate):
            old_wr_str = f"{old_oos_win_rate:.1f}%" if np.isfinite(old_oos_win_rate) else "N/A"
            new_wr_str = f"{new_oos_win_rate:.1f}%" if np.isfinite(new_oos_win_rate) else "N/A"
            win_rate_change_str = f"\n  Win Rate: {old_wr_str} -> {new_wr_str}"

        logger.info(
            f"\n第{iteration}轮决策: 移除'{removed_var}', 剩余{len(current_predictors)}个变量\n"
            f"  训练期RMSE: {old_is_rmse:.4f} -> {new_is_rmse:.4f} (改善: {delta_is_rmse:+.4f})\n"
            f"  验证期RMSE: {old_oos_rmse:.4f} -> {new_oos_rmse:.4f} (改善: {delta_oos_rmse:+.4f}){win_rate_change_str}"
        )

        # 精简的回调输出格式（带改善百分比，同时输出到控制台）
        # 计算改善百分比
        rmse_improve_pct = (old_oos_rmse - new_oos_rmse) / old_oos_rmse * 100 if old_oos_rmse > 0 else 0
        rmse_change = f"降低{rmse_improve_pct:.1f}%" if rmse_improve_pct > 0 else f"上升{-rmse_improve_pct:.1f}%"

        # Win Rate改善
        wr_line = ""
        if np.isfinite(old_oos_win_rate) and np.isfinite(new_oos_win_rate):
            wr_improve = new_oos_win_rate - old_oos_win_rate
            wr_change = f"提升{wr_improve:.1f}%" if wr_improve > 0 else f"下降{-wr_improve:.1f}%"
            wr_line = f"\n  验证期胜率: {old_oos_win_rate:.1f}% -> {new_oos_win_rate:.1f}% ({wr_change})"

        removal_msg = (
            f"第{iteration}轮: 移除'{removed_var}', 剩余{len(current_predictors)}个变量\n"
            f"  验证期RMSE: {old_oos_rmse:.4f} -> {new_oos_rmse:.4f} ({rmse_change}){wr_line}"
        )
        print(removal_msg)
        if progress_callback:
            progress_callback(removal_msg)

    def _build_selection_result(
        self,
        final_predictors: List[str],
        history: List[Dict],
        final_score: Tuple[float, float, float],
        total_evals: int,
        svd_errors: int,
        n_initial_vars: int,
        progress_callback: Optional[Callable] = None,
        baseline_oos_rmse: float = 0.0,
        baseline_oos_win_rate: float = 0.0,
        final_oos_rmse: float = 0.0,
        final_oos_win_rate: float = 0.0
    ) -> SelectionResult:
        """构建选择结果对象"""
        target_variable = self._eval_params['target_variable']
        final_variables = [target_variable] + final_predictors

        logger.info(
            f"变量选择完成: 从{n_initial_vars-1}个变量剔除到{len(final_predictors)}个, "
            f"最终验证期RMSE={-final_score[1]:.6f}"
        )

        # 输出最终汇总（同时输出到控制台和回调）
        if len(history) > 0:
            # 获取移除的变量列表
            removed_vars = [h['removed_variable'] for h in history]

            # 计算总改善百分比
            rmse_improve_pct = (baseline_oos_rmse - final_oos_rmse) / baseline_oos_rmse * 100 if baseline_oos_rmse > 0 else 0
            rmse_summary = f"降低{rmse_improve_pct:.1f}%" if rmse_improve_pct > 0 else f"上升{-rmse_improve_pct:.1f}%"

            wr_summary = ""
            if np.isfinite(baseline_oos_win_rate) and np.isfinite(final_oos_win_rate):
                wr_improve = final_oos_win_rate - baseline_oos_win_rate
                wr_change = f"提升{wr_improve:.1f}%" if wr_improve > 0 else f"下降{-wr_improve:.1f}%"
                wr_summary = f"\n胜率总改善: {baseline_oos_win_rate:.1f}% -> {final_oos_win_rate:.1f}% ({wr_change})"

            final_msg = (
                f"\n========== 变量选择完成 ==========\n"
                f"总轮次: {len(history)}\n"
                f"移除变量: {', '.join(removed_vars)}\n"
                f"RMSE总改善: {baseline_oos_rmse:.4f} -> {final_oos_rmse:.4f} ({rmse_summary}){wr_summary}\n"
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

