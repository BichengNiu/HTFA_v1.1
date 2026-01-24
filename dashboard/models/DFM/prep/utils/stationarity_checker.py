"""
平稳性检验工具模块

提供单变量和批量变量的平稳性检验功能
"""

import logging
import warnings
from typing import Dict, Optional, List, Any, Tuple
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


class StationarityChecker:
    """平稳性检验工具类"""

    MIN_SAMPLES_ADF = 5

    @staticmethod
    def _run_adf_test(series: pd.Series, alpha: float = 0.05) -> Tuple[Optional[float], str]:
        """
        执行ADF平稳性检验（内部方法）

        Args:
            series: 时间序列数据（已清理NaN）
            alpha: 显著性水平

        Returns:
            Tuple[Optional[float], str]: (p值, 状态)
            状态: '是', '否', '数据不足', '常量序列', '计算失败(...)'
        """
        series_cleaned = series.dropna()

        # 数据量检查
        if series_cleaned.empty or len(series_cleaned) < StationarityChecker.MIN_SAMPLES_ADF:
            return None, '数据不足'

        # 常量检查：避免 "Invalid input, x is constant" 错误
        if series_cleaned.nunique() == 1:
            return None, '常量序列'

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = adfuller(series_cleaned, regression='ct')

            p_value = result[1]
            is_stationary = '是' if p_value < alpha else '否'
            return p_value, is_stationary

        except Exception as e:
            error_msg = str(e).lower()
            if "sample size" in error_msg or "regression" in error_msg:
                return None, '计算失败(样本不足)'
            return None, f'计算失败({type(e).__name__})'

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
                'status': str,              # '是', '否', '数据不足', '常量序列', '计算失败(...)'
                'formatted': str            # 格式化结果字符串
            }
        """
        try:
            var_name = getattr(series, 'name', 'unknown')
            logger.debug(f"检验变量 '{var_name}': 原始{len(series)}条")

            # 执行ADF检验（内部方法已包含数据清理和常量检查）
            p_value, status = StationarityChecker._run_adf_test(series, alpha=alpha)
            logger.debug(f"  -> ADF结果: p={p_value}, status={status}")

            # 判断是否平稳
            is_stationary = (status == '是')

            # 格式化结果字符串
            if status == '数据不足':
                formatted = '数据不足'
            elif status == '常量序列':
                formatted = '常量序列'
            elif status.startswith('计算失败'):
                formatted = status
            elif is_stationary:
                formatted = f"ADF-P={p_value:.3f} (平稳)" if p_value is not None else "平稳"
            else:
                formatted = f"ADF-P={p_value:.3f} (非平稳)" if p_value is not None else "非平稳"

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
        n_jobs: int = -1
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量检验多个变量的平稳性（并行执行）

        Args:
            df: 包含时间序列的DataFrame
            variables: 需要检验的变量列表，默认为None表示检验所有列
            alpha: 显著性水平，默认0.05
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

        logger.info(f"开始批量检验平稳性: {len(variables)}个变量, alpha={alpha}")
        results = {}

        from joblib import Parallel, delayed

        results_list = Parallel(n_jobs=n_jobs, backend='loky')(
            delayed(StationarityChecker.check_variable_stationarity)(
                df[var], alpha=alpha
            )
            for var in variables if var in df.columns
        )

        for var, result in zip([v for v in variables if v in df.columns], results_list):
            results[normalize_text(var)] = result
            logger.debug(f"检验完成: {var} -> {result['formatted']}")

        logger.info(f"平稳性检验完成: 共检验 {len(results)} 个变量, 成功 {len(results)}/{len(variables)}")
        return results


__all__ = ['StationarityChecker']
