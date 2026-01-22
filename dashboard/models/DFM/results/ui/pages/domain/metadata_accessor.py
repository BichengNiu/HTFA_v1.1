"""
DFM Metadata Accessor
DFM元数据访问器 - 封装重复的元数据访问模式
"""

from dataclasses import dataclass
from typing import Optional, Any, Dict
import math
import pandas as pd
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)


@dataclass
class ModelMetrics:
    """模型评估指标数据类"""
    mae: Optional[float] = None
    rmse: Optional[float] = None
    hit_rate: Optional[float] = None


@dataclass
class TrainingInfo:
    """训练信息数据类"""
    training_start: str = 'N/A'
    training_end: str = 'N/A'
    validation_start: str = 'N/A'
    validation_end: str = 'N/A'
    target_variable: str = ''
    estimation_method: str = 'N/A'
    n_industries: Any = 'N/A'
    n_variables: Any = 'N/A'
    n_factors: Any = 'N/A'


class DFMMetadataAccessor:
    """
    DFM元数据访问器

    封装所有元数据访问，消除重复的metadata.get()调用模式。
    提供类型安全和默认值处理。
    """

    def __init__(self, metadata: Dict[str, Any]):
        """
        初始化元数据访问器

        Args:
            metadata: 从pkl文件加载的元数据字典
        """
        self._metadata = metadata
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def training_info(self) -> TrainingInfo:
        """获取训练信息"""
        best_variables = self._metadata.get('best_variables')
        if best_variables is None:
            raise KeyError("元数据中缺少'best_variables'字段")
        if not isinstance(best_variables, list):
            raise TypeError(f"'best_variables'应为list类型，实际为{type(best_variables)}")
        n_vars = len(best_variables)

        # 计算最终行业数
        n_industries = self._get_n_industries(best_variables)

        return TrainingInfo(
            training_start=self._get_date_str('training_start_date'),
            training_end=self._get_date_str('train_end_date'),
            validation_start=self._get_date_str('validation_start_date'),
            validation_end=self._get_date_str('validation_end_date'),
            target_variable=self._metadata.get('target_variable', ''),
            estimation_method=self._metadata.get('estimation_method', 'N/A'),
            n_industries=n_industries,
            n_variables=n_vars,
            n_factors=self._get_k_factors()
        )

    def _get_k_factors(self) -> Any:
        """从metadata中获取k_factors"""
        best_params = self._metadata.get('best_params')
        if best_params is None:
            raise KeyError("元数据中缺少'best_params'字段")
        if not isinstance(best_params, dict):
            raise TypeError(f"'best_params'应为dict类型，实际为{type(best_params)}")
        if 'k_factors' not in best_params:
            raise KeyError("'best_params'中缺少'k_factors'字段")
        return best_params['k_factors']

    def _get_n_industries(self, best_variables: list) -> Any:
        """计算最终行业数"""
        var_industry_map = self._metadata.get('var_industry_map')
        if not var_industry_map or not isinstance(var_industry_map, dict):
            return 'N/A'
        industries = set()
        for var in best_variables:
            industry = var_industry_map.get(var)
            if industry:
                industries.add(industry)
        return len(industries) if industries else 'N/A'

    @property
    def training_metrics(self) -> ModelMetrics:
        """获取训练期指标"""
        return ModelMetrics(
            mae=self._get_metric('is_mae'),
            rmse=self._get_metric('is_rmse'),
            hit_rate=self._get_metric('is_win_rate')
        )

    @property
    def validation_metrics(self) -> ModelMetrics:
        """获取验证期指标"""
        return ModelMetrics(
            mae=self._get_metric('oos_mae'),
            rmse=self._get_metric('oos_rmse'),
            hit_rate=self._get_metric('oos_win_rate')
        )

    @property
    def observation_metrics(self) -> ModelMetrics:
        """获取观察期指标"""
        return ModelMetrics(
            mae=self._get_metric('obs_mae'),
            rmse=self._get_metric('obs_rmse'),
            hit_rate=self._get_metric('obs_win_rate')
        )

    def _get_metric(self, base_key: str) -> Optional[float]:
        """获取指标值，字段不存在时返回None"""
        return self._metadata.get(base_key)

    @property
    def has_observation_metrics(self) -> bool:
        """检查是否有观察期指标"""
        metrics = self.observation_metrics
        return any([
            metrics.rmse is not None,
            metrics.mae is not None,
            metrics.hit_rate is not None
        ])

    @property
    def has_valid_validation_metrics(self) -> bool:
        """
        检查验证期指标是否有效（非inf且非NaN）

        DDFM模型的验证期指标为inf，应该隐藏不显示
        """
        metrics = self.validation_metrics

        def is_valid_number(val: Optional[float]) -> bool:
            """检查数值是否有效（非None、非inf、非NaN）"""
            if val is None:
                return False
            return not (math.isinf(val) or math.isnan(val))

        # 只要RMSE或MAE有一个有效，就认为验证期指标有效
        return is_valid_number(metrics.rmse) or is_valid_number(metrics.mae)

    @property
    def is_ddfm(self) -> bool:
        """判断是否为DDFM模型"""
        best_params = self._metadata.get('best_params', {})
        algorithm = best_params.get('algorithm', 'classical')
        return algorithm == 'deep_learning'

    @property
    def complete_aligned_table(self) -> Optional[pd.DataFrame]:
        """获取完整对齐表"""
        return self._metadata.get('complete_aligned_table')

    @property
    def nowcast_comparison(self) -> Optional[pd.DataFrame]:
        """获取Nowcast对比数据"""
        return self._metadata.get('nowcast_comparison')

    @property
    def factor_loadings_df(self) -> Optional[pd.DataFrame]:
        """获取因子载荷矩阵"""
        return self._metadata.get('factor_loadings_df')

    @property
    def smoothed_factors(self) -> Optional[pd.DataFrame]:
        """获取平滑因子"""
        return self._metadata.get('smoothed_factors')

    @property
    def factor_series(self) -> Optional[pd.DataFrame]:
        """获取因子时间序列"""
        return self._metadata.get('factor_series')

    @property
    def observation_period_start(self) -> Optional[str]:
        """获取观察期开始日期"""
        return self._get_date_str('observation_period_start')

    @property
    def observation_period_end(self) -> Optional[str]:
        """获取观察期结束日期"""
        return self._get_date_str('observation_period_end')

    @property
    def pca_results_df(self) -> Optional[pd.DataFrame]:
        """获取PCA结果"""
        pca_df = self._metadata.get('pca_results_df')
        if pca_df is not None and isinstance(pca_df, pd.DataFrame) and not pca_df.empty:
            return pca_df
        return None

    def get(self, key: str, default: Any = None) -> Any:
        """
        通用元数据获取方法

        Args:
            key: 元数据键
            default: 默认值

        Returns:
            元数据值或默认值
        """
        return self._metadata.get(key, default)

    def _get_date_str(self, key: str) -> str:
        """
        获取日期字符串

        Args:
            key: 日期键

        Returns:
            格式化的日期字符串或'N/A'

        Raises:
            TypeError: 日期值类型不支持
        """
        date_val = self._metadata.get(key)
        if date_val is None:
            return 'N/A'

        if isinstance(date_val, str):
            return date_val

        if isinstance(date_val, (pd.Timestamp, datetime, date)):
            return date_val.strftime('%Y-%m-%d')

        # Raise error for unsupported types instead of silent str() conversion
        raise TypeError(f"Unsupported date type for key '{key}': {type(date_val).__name__}")

    @staticmethod
    def format_metric(val: Any, is_percent: bool = False, precision: int = 2) -> str:
        """
        格式化指标值

        Args:
            val: 原始值
            is_percent: 是否为百分比
            precision: 小数精度

        Returns:
            格式化字符串
        """
        if isinstance(val, (int, float)) and pd.notna(val):
            if is_percent:
                return f"{val:.{precision}f}%"
            return f"{val:.{precision}f}"
        return 'N/A' if val == 'N/A' or pd.isna(val) else str(val)
