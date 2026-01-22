"""
平稳性检验工具模块

提供单变量和批量变量的平稳性检验功能，
集成explore模块的ADF检验工具
"""

import logging
from typing import Dict, Optional, List, Any
import pandas as pd

logger = logging.getLogger(__name__)


class StationarityChecker:
    """平稳性检验工具类"""

    MIN_SAMPLES_ADF = 5

    @staticmethod
    def check_variable_stationarity(
        series: pd.Series,
        alpha: float = 0.05
    ) -> Dict[str, Any]:
        """
        检验单个变量的平稳性

        Args:
            series: 时间序列数据
            alpha: 显著性水平，默认0.05

        Returns:
            {
                'p_value': float or None,
                'is_stationary': bool,
                'status': str,              # '是', '否', '数据不足', '计算失败(...)'
                'formatted': str            # 格式化结果字符串
            }
        """
        from dashboard.explore.analysis.stationarity import run_adf_test

        try:
            # 清理数据
            series_clean = series.dropna()
            var_name = getattr(series, 'name', 'unknown')

            logger.debug(f"检验变量 '{var_name}': 原始{len(series)}条, 清理后{len(series_clean)}条")

            # 检查数据量
            if len(series_clean) < StationarityChecker.MIN_SAMPLES_ADF:
                logger.debug(f"  -> 数据不足 ({len(series_clean)} < {StationarityChecker.MIN_SAMPLES_ADF})")
                return {
                    'p_value': None,
                    'is_stationary': False,
                    'status': '数据不足',
                    'formatted': '数据不足'
                }

            # 执行ADF检验
            logger.debug(f"  -> 执行ADF检验...")
            p_value, status = run_adf_test(series_clean, alpha=alpha)
            logger.debug(f"  -> ADF结果: p={p_value}, status={status}")

            # 判断是否平稳
            is_stationary = (status == '是')

            # 格式化结果字符串：ADF-P=0.001 (平稳) 或 ADF-P=0.250 (非平稳)
            if status == '数据不足':
                formatted = '数据不足'
            elif status.startswith('计算失败'):
                formatted = status  # 保留错误信息，如 '计算失败(滞后阶数不足)'
            elif is_stationary:
                if p_value is not None:
                    formatted = f"ADF-P={p_value:.3f} (平稳)"
                else:
                    formatted = "平稳"
            else:
                if p_value is not None:
                    formatted = f"ADF-P={p_value:.3f} (非平稳)"
                else:
                    formatted = "非平稳"

            return {
                'p_value': p_value,
                'is_stationary': is_stationary,
                'status': status,
                'formatted': formatted
            }
        except Exception as e:
            logger.error(f"检验变量 '{getattr(series, 'name', 'unknown')}' 失败: {e}", exc_info=True)
            return {
                'p_value': None,
                'is_stationary': False,
                'status': f'计算失败({type(e).__name__})',
                'formatted': f'计算失败({type(e).__name__})'
            }

    @staticmethod
    def batch_check_variables(
        df: pd.DataFrame,
        variables: Optional[List[str]] = None,
        alpha: float = 0.05,
        parallel: bool = False,
        n_jobs: int = -1
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量检验多个变量的平稳性

        Args:
            df: 包含时间序列的DataFrame
            variables: 需要检验的变量列表，默认为None表示检验所有列
            alpha: 显著性水平，默认0.05
            parallel: 是否使用并行，默认False
            n_jobs: 并行任务数，-1表示使用所有CPU核心

        Returns:
            Dict[str, Dict]: {
                'var1': {'p_value': 0.001, 'is_stationary': True, 'status': '是', 'formatted': 'ADF-P=0.001 (平稳)'},
                'var2': {'p_value': 0.25, 'is_stationary': False, 'status': '否', 'formatted': 'ADF-P=0.250 (非平稳)'},
                ...
            }
        """
        if variables is None:
            variables = df.columns.tolist()

        logger.info(f"开始批量检验平稳性: {len(variables)}个变量, alpha={alpha}, parallel={parallel}")
        results = {}

        if parallel:
            # 并行执行（使用joblib）
            try:
                from joblib import Parallel, delayed

                results_list = Parallel(n_jobs=n_jobs, backend='loky')(
                    delayed(StationarityChecker.check_variable_stationarity)(
                        df[var], alpha=alpha
                    )
                    for var in variables if var in df.columns
                )

                for var, result in zip([v for v in variables if v in df.columns], results_list):
                    results[var] = result
                    logger.debug(f"检验完成: {var} -> {result['formatted']}")

            except Exception as e:
                logger.warning(f"并行检验失败，降级到串行模式: {e}")
                parallel = False

        if not parallel:
            # 串行执行
            logger.info(f"串行执行检验...")
            for i, var in enumerate(variables, 1):
                if var not in df.columns:
                    logger.warning(f"  [{i}/{len(variables)}] 变量 '{var}' 不在DataFrame中，跳过")
                    continue

                logger.debug(f"  [{i}/{len(variables)}] 检验变量: {var}")
                result = StationarityChecker.check_variable_stationarity(
                    df[var], alpha=alpha
                )
                results[var] = result
                logger.info(f"  [{i}/{len(variables)}] {var}: {result['formatted']}")

        logger.info(f"平稳性检验完成: 共检验 {len(results)} 个变量, 成功 {len(results)}/{len(variables)}")
        return results


__all__ = ['StationarityChecker']
