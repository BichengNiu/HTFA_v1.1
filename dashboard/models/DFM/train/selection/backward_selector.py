# -*- coding: utf-8 -*-
"""
后向逐步变量选择器

实现后向逐步变量剔除算法，以目标变量加权RMSE作为优化目标（越小越好）。
支持目标变量保护：目标变量不会被剔除。
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Callable, Optional
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import SelectionResult
from dashboard.models.DFM.train.evaluation.metrics import compare_model_scores
from dashboard.models.DFM.train.utils.parallel_config import ParallelConfig
from dashboard.models.DFM.train.utils.formatting import generate_progress_bar

logger = get_logger(__name__)


class BackwardSelector:
    """
    后向逐步变量选择器

    算法流程:
    1. 从全部变量开始
    2. 逐个尝试剔除每个变量（目标变量除外）
    3. 评估剔除后的模型拟合质量（目标变量加权RMSE）
    4. 选择性能提升最大的变量剔除
    5. 重复直到无法提升

    优化目标: 最小化目标变量加权RMSE
    """

    def __init__(
        self,
        evaluator_func: Callable,
        min_variables: int = 1,
        parallel_config: ParallelConfig = None,
        target_variable: Optional[str] = None
    ):
        """
        Args:
            evaluator_func: 评估函数,签名为 (variables, **kwargs) -> float (加权RMSE，越小越好)
            min_variables: 最少保留的变量数
            parallel_config: 并行配置（必填）
            target_variable: 目标变量名称（不会被剔除）
        """
        if parallel_config is None:
            raise ValueError("parallel_config参数必填，请提供ParallelConfig对象")
        if min_variables < 1:
            raise ValueError(f"min_variables必须 >= 1, 当前值: {min_variables}")
        self.evaluator_func = evaluator_func
        self.min_variables = min_variables
        self.parallel_config = parallel_config
        self.target_variable = target_variable

    def select(
        self,
        initial_variables: List[str],
        full_data: pd.DataFrame,
        params: Dict,
        training_start_date: str,
        train_end_date: str,
        max_iter: int = 30,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> SelectionResult:
        """
        执行后向变量选择

        Args:
            initial_variables: 初始变量列表
            full_data: 完整数据DataFrame
            params: DFM参数字典(包含k_factors等)
            training_start_date: 训练集开始日期
            train_end_date: 训练集结束日期
            max_iter: 最大EM迭代次数
            progress_callback: 进度回调函数

        Returns:
            SelectionResult对象
        """
        # 验证params中的必需键
        required_param_keys = ['k_factors', 'factor_selection_method', 'pca_threshold',
                               'kaiser_threshold', 'tolerance']
        for key in required_param_keys:
            if key not in params:
                raise ValueError(f"params缺少必需参数: {key}")

        # 保存评估参数供辅助方法使用
        self._eval_params = {
            'full_data': full_data,
            'params': params,
            'training_start_date': training_start_date,
            'train_end_date': train_end_date,
            'max_iter': max_iter,
            'tolerance': params['tolerance'],
            'progress_callback': progress_callback
        }

        total_evaluations = 0
        svd_error_count = 0
        selection_history = []

        # 1. 初始化变量列表
        current_variables = list(initial_variables)
        if not current_variables:
            return SelectionResult(
                selected_variables=initial_variables,
                selection_history=[],
                final_score=np.inf,
                total_evaluations=0,
                svd_error_count=0
            )

        # 2. 计算初始基准性能
        current_best_score, eval_count, svd_count = self._evaluate_baseline(
            current_variables, progress_callback
        )
        total_evaluations += eval_count
        svd_error_count += svd_count

        # 保存基线值用于最终汇总
        baseline_score = current_best_score

        # 3. 迭代移除变量
        iteration = 0
        while self._should_continue_selection(current_variables, iteration):
            iteration += 1
            self._log_iteration_start(iteration, len(current_variables), progress_callback)

            # 找到本轮最佳移除候选
            best_removal, best_score_this_iter, eval_count, svd_count = self._find_best_removal_candidate(
                current_variables
            )
            total_evaluations += eval_count
            svd_error_count += svd_count

            # 检查是否找到有效的移除候选
            if best_removal is None:
                logger.warning("本轮无可行的移除候选，筛选结束")
                break

            # 检查是否有性能提升（目标变量RMSE越小越好）
            comparison = compare_model_scores(best_score_this_iter, current_best_score)
            if comparison <= 0:
                logger.warning(
                    f"移除任何变量都无法提升性能 "
                    f"(当前RMSE={current_best_score:.4f}; 最佳候选RMSE={best_score_this_iter:.4f})"
                )
                break

            # 应用移除并记录历史
            self._apply_removal_and_record(
                current_variables, best_removal, best_score_this_iter,
                current_best_score, iteration, selection_history, progress_callback
            )

            # 更新当前最佳得分
            current_best_score = best_score_this_iter

        # 4. 返回结果
        return self._build_selection_result(
            current_variables, selection_history,
            current_best_score, total_evaluations, svd_error_count,
            len(initial_variables), progress_callback,
            baseline_score
        )

    def _evaluate_baseline(
        self,
        current_variables: List[str],
        progress_callback: Optional[Callable]
    ) -> Tuple[float, int, int]:
        """计算初始基准性能"""
        logger.info(f"计算初始基准性能，变量数: {len(current_variables)}")

        try:
            score = self.evaluator_func(variables=current_variables, **self._eval_params)
            svd_count = 0

            if not np.isfinite(score):
                logger.warning(f"初始基准评估返回无效分数，使用最差分数")
                score = np.inf

            logger.info(
                f"初始基准得分 - 目标变量RMSE: {score:.4f}, "
                f"变量数: {len(current_variables)}"
            )

            # 输出基线信息
            target_info = f"（目标变量: {self.target_variable}）" if self.target_variable else ""
            baseline_msg = (
                f"========== 变量选择开始 ==========\n"
                f"初始变量数: {len(current_variables)}{target_info}\n"
                f"基线目标变量RMSE: {score:.4f}"
            )
            print(baseline_msg)
            if progress_callback:
                progress_callback(baseline_msg)

            return (score, 1, svd_count)

        except Exception as e:
            logger.error(f"计算初始基准性能时出错: {e}")
            raise RuntimeError(f"计算初始基准性能失败: {e}") from e

    def _should_continue_selection(
        self,
        current_variables: List[str],
        iteration: int
    ) -> bool:
        """判断是否应该继续变量选择"""
        return len(current_variables) > self.min_variables

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

        # 进度显示
        max_rounds = n_vars - self.min_variables
        progress_bar = generate_progress_bar(iteration, max_rounds)
        iter_msg = f"{progress_bar} 第{iteration}轮 (当前{n_vars}个变量)"
        print(iter_msg)
        if progress_callback:
            progress_callback(iter_msg)

    def _find_best_removal_candidate(
        self,
        current_variables: List[str]
    ) -> Tuple[Optional[str], float, int, int]:
        """找到本轮最佳移除候选"""
        best_score = np.inf  # 目标变量RMSE越小越好
        best_var = None
        total_evals = 0
        total_svd_errors = 0

        k_factors = self._eval_params['params']['k_factors']
        progress_callback = self._eval_params['progress_callback']

        candidate_results = []

        for idx, var in enumerate(current_variables, 1):
            # 跳过目标变量，不允许剔除
            if self.target_variable and var == self.target_variable:
                msg = f"  [{idx}/{len(current_variables)}] 跳过目标变量'{var}'，不允许剔除"
                logger.debug(msg)
                if progress_callback:
                    progress_callback(msg)
                continue

            temp_variables = [v for v in current_variables if v != var]
            if not temp_variables:
                continue

            # 检查因子数约束
            if k_factors >= len(temp_variables):
                logger.debug(f"  [{idx}/{len(current_variables)}] 跳过'{var}': k_factors({k_factors}) >= 剩余变量数({len(temp_variables)})")
                continue

            # 打印正在尝试的变量
            msg = f"  [{idx}/{len(current_variables)}] 尝试移除: '{var}'"
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

            # 评估移除后的性能
            try:
                score = self.evaluator_func(variables=temp_variables, **self._eval_params)
                total_evals += 1

                # 打印评估结果
                msg = f"    目标变量RMSE: {score:.4f}"
                logger.info(msg)
                if progress_callback:
                    progress_callback(msg)

                # 记录候选结果
                candidate_results.append({
                    'var': var,
                    'score': score
                })

            except Exception as e:
                logger.error(f"    评估移除'{var}'时出错: {e}")
                continue

        # 找出最佳候选（目标变量RMSE最小）
        for result in candidate_results:
            score = result['score']

            # 更新最佳候选
            comparison = compare_model_scores(score, best_score)
            if np.isfinite(score) and comparison > 0:
                best_score = score
                best_var = result['var']

                # 实时标记最佳候选
                msg = f"    *** 当前最佳候选 ***"
                logger.info(msg)
                if progress_callback:
                    progress_callback(msg)

        # 打印本轮汇总
        if candidate_results:
            summary_msg = f"\n  本轮候选汇总 (共{len(candidate_results)}个):"
            logger.info(summary_msg)
            if progress_callback:
                progress_callback(summary_msg)

            for res in candidate_results:
                is_best = " <- 最佳" if res['var'] == best_var else ""
                msg = f"    '{res['var']}': 目标变量RMSE={res['score']:.4f}{is_best}"
                logger.info(msg)
                if progress_callback:
                    progress_callback(msg)

        return (best_var, best_score, total_evals, total_svd_errors)

    def _apply_removal_and_record(
        self,
        current_variables: List[str],
        removed_var: str,
        new_score: float,
        old_score: float,
        iteration: int,
        history: List[Dict],
        progress_callback: Optional[Callable]
    ):
        """应用变量移除并记录历史"""
        if removed_var not in current_variables:
            raise RuntimeError(
                f"内部错误：变量'{removed_var}'不在current_variables中。"
            )
        current_variables.remove(removed_var)

        # 记录选择历史
        history.append({
            'iteration': iteration,
            'removed_variable': removed_var,
            'score': new_score,
            'remaining_vars': current_variables.copy(),
            'remaining_count': len(current_variables)
        })

        # 计算改善量（目标变量RMSE越小越好）
        delta = old_score - new_score
        improve_str = f"降低{delta:.4f}" if delta > 0 else f"上升{-delta:.4f}"

        logger.info(
            f"\n第{iteration}轮决策: 移除'{removed_var}', 剩余{len(current_variables)}个变量\n"
            f"  目标变量RMSE: {old_score:.4f} -> {new_score:.4f} ({improve_str})"
        )

        removal_msg = (
            f"第{iteration}轮: 移除'{removed_var}', 剩余{len(current_variables)}个变量\n"
            f"  目标变量RMSE: {old_score:.4f} -> {new_score:.4f} ({improve_str})"
        )
        print(removal_msg)
        if progress_callback:
            progress_callback(removal_msg)

    def _build_selection_result(
        self,
        final_variables: List[str],
        history: List[Dict],
        final_score: float,
        total_evals: int,
        svd_errors: int,
        n_initial_vars: int,
        progress_callback: Optional[Callable] = None,
        baseline_score: float = 0.0
    ) -> SelectionResult:
        """构建选择结果对象"""
        logger.info(
            f"变量选择完成: 从{n_initial_vars}个变量剔除到{len(final_variables)}个, "
            f"最终目标变量RMSE={final_score:.4f}"
        )

        # 输出最终汇总
        if len(history) > 0:
            removed_vars = [h['removed_variable'] for h in history]

            # 目标变量RMSE越小越好
            delta = baseline_score - final_score
            improve_str = f"降低{delta:.4f}" if delta > 0 else f"上升{-delta:.4f}"

            final_msg = (
                f"\n========== 变量选择完成 ==========\n"
                f"总轮次: {len(history)}\n"
                f"移除变量: {', '.join(removed_vars)}\n"
                f"目标变量RMSE总改善: {baseline_score:.4f} -> {final_score:.4f} ({improve_str})\n"
                f"最终变量数: {len(final_variables)}个"
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
