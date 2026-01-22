# -*- coding: utf-8 -*-
"""
变量转换处理器模块

提供基于变量性质的数据转换功能，包括：
- 对数变换
- 环比差分（1期）
- 同比差分（根据频率动态计算：周度52期、月度12期等）

作者: Claude Code
创建时间: 2025-12-01
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

# 频率-同比周期映射
FREQUENCY_PERIOD_MAP = {
    'D': 365,      # 日度 -> 365期同比
    'W-FRI': 52,   # 周度-周五 -> 52期同比
    'W-MON': 52,   # 周度-周一 -> 52期同比
    'MS': 12,      # 月度 -> 12期同比
    'QS': 4,       # 季度 -> 4期同比
    'AS': 1,       # 年度 -> 1期同比（无意义）
}


class VariableTransformer:
    """
    变量转换处理器

    根据变量性质自动推荐转换操作，并支持用户自定义配置。
    转换结果直接替换原变量。
    """

    # 可用的转换操作
    OPERATIONS = {
        'none': '不处理',
        'log': '对数',
        'diff_1': '环比差分',
        'diff_yoy': '同比差分',
    }

    # 基于性质的默认推荐规则 (第一次处理, 第二次处理)
    DEFAULT_RECOMMENDATIONS = {
        '流量': ('log', 'diff_yoy'),   # 先对数再同比差分
        '率': ('none', 'none'),         # 无操作
        '存量': ('log', 'diff_yoy'),    # 先对数再同比差分（消除季节性）
        '同比': ('none', 'none'),       # 无操作
    }

    def __init__(self, freq: str = 'W-FRI', logger: Optional[logging.Logger] = None):
        """
        初始化变量转换处理器

        Args:
            freq: 目标频率（用于计算同比差分周期），默认周度
            logger: 日志记录器（可选）
        """
        self.freq = freq
        self.yoy_period = FREQUENCY_PERIOD_MAP.get(freq, 52)
        self.logger = logger or logging.getLogger(__name__)
        self._transform_details = {}

    def get_transform_details(self) -> Dict[str, Any]:
        """获取转换详情字典"""
        return self._transform_details.copy()

    def get_recommended_operations(self, nature: str) -> Tuple[str, str]:
        """
        获取基于性质的推荐操作

        Args:
            nature: 变量性质（流量、率、存量、同比）

        Returns:
            Tuple[str, str]: (第一次处理, 第二次处理)
        """
        return self.DEFAULT_RECOMMENDATIONS.get(nature, ('none', 'none'))

    def preprocess_zeros(self, series: pd.Series, method: str) -> pd.Series:
        """
        0值预处理

        Args:
            series: 输入序列
            method: 处理方法 ('none', 'missing', 'adjust')

        Returns:
            处理后的序列
        """
        if method == 'none':
            return series.copy()

        var_name = series.name if series.name else "未命名"
        result = series.copy()
        zero_mask = result == 0
        zero_count = zero_mask.sum()

        if zero_count == 0:
            return result

        if method == 'missing':
            result[zero_mask] = np.nan
            self.logger.info(f"变量 '{var_name}' 将 {zero_count} 个0值设为缺失值")
        elif method == 'adjust':
            result[zero_mask] = 1
            self.logger.info(f"变量 '{var_name}' 将 {zero_count} 个0值调正为1")

        return result

    def apply_log(self, series: pd.Series) -> pd.Series:
        """
        对数变换

        处理规则：
        - 全为正值：直接使用np.log
        - 包含零值：使用np.log1p (log(1+x))
        - 包含负值：抛出ValueError异常

        Args:
            series: 输入时间序列

        Returns:
            pd.Series: 对数变换后的序列

        Raises:
            ValueError: 当序列包含负值时抛出
        """
        var_name = series.name if series.name else "未命名"

        # 获取有效值
        valid_values = series.dropna()
        if valid_values.empty:
            self.logger.warning(f"变量 '{var_name}' 全为NaN，跳过对数变换")
            return series.copy()

        min_val = valid_values.min()

        if min_val > 0:
            # 全为正值，直接取对数
            result = np.log(series)
            self.logger.debug(f"变量 '{var_name}' 应用对数变换 (np.log)")
        elif min_val >= 0:
            # 包含零值，使用log1p
            result = np.log1p(series)
            self.logger.debug(f"变量 '{var_name}' 应用对数变换 (np.log1p)")
        else:
            # 包含负值，抛出异常
            raise ValueError(
                f"变量 '{var_name}' 包含负值(min={min_val:.4f})，"
                f"无法进行对数变换。请先使用值替换功能处理负值，"
                f"或选择其他转换方式（如差分）。"
            )

        return result

    def apply_diff(self, series: pd.Series, periods: int = 1) -> pd.Series:
        """
        差分变换

        Args:
            series: 输入时间序列
            periods: 差分周期数（1=环比，52=同比）

        Returns:
            pd.Series: 差分后的序列
        """
        var_name = series.name if series.name else "未命名"
        result = series.diff(periods=periods)
        self.logger.debug(
            f"变量 '{var_name}' 应用{periods}期差分，"
            f"产生{periods}个头部NaN"
        )
        return result

    def transform_variable(
        self,
        series: pd.Series,
        operations: List[str],
        zero_method: str = 'none'
    ) -> pd.Series:
        """
        按顺序对单个变量应用多个转换操作

        Args:
            series: 输入时间序列
            operations: 操作列表，按顺序执行
            zero_method: 0值处理方法 ('none', 'missing', 'adjust')

        Returns:
            pd.Series: 转换后的序列
        """
        # 1. 预处理0值
        result = self.preprocess_zeros(series, zero_method)

        # 如果没有后续操作，直接返回预处理后的结果
        if not operations:
            # 只有预处理时也记录详情
            if zero_method != 'none':
                var_name = series.name if series.name else "未命名"
                preprocess_ops = [f'zero_{zero_method}']
                self._transform_details[var_name] = {
                    'operations': preprocess_ops,
                    'original_stats': {
                        'mean': float(series.mean()) if not series.isna().all() else None,
                        'std': float(series.std()) if not series.isna().all() else None,
                        'min': float(series.min()) if not series.isna().all() else None,
                        'max': float(series.max()) if not series.isna().all() else None,
                    },
                    'transformed_stats': {
                        'mean': float(result.mean()) if not result.isna().all() else None,
                        'std': float(result.std()) if not result.isna().all() else None,
                        'min': float(result.min()) if not result.isna().all() else None,
                        'max': float(result.max()) if not result.isna().all() else None,
                    },
                    'nan_count_before': int(series.isna().sum()),
                    'nan_count_after': int(result.isna().sum()),
                }
            return result

        # 过滤掉 'none' 操作
        valid_ops = [op for op in operations if op != 'none']
        if not valid_ops and zero_method == 'none':
            return series.copy()

        applied_ops = []
        # 记录预处理操作
        if zero_method != 'none':
            applied_ops.append(f'zero_{zero_method}')

        # 3. 应用转换操作
        for op in valid_ops:
            if op == 'log':
                result = self.apply_log(result)
                applied_ops.append('log')
            elif op == 'diff_1':
                result = self.apply_diff(result, periods=1)
                applied_ops.append('diff_1')
            elif op == 'diff_yoy':
                # 使用动态周期
                result = self.apply_diff(result, periods=self.yoy_period)
                applied_ops.append(f'diff_{self.yoy_period}')
            else:
                self.logger.warning(f"未知操作 '{op}'，跳过")

        # 记录转换详情
        var_name = series.name if series.name else "未命名"
        self._transform_details[var_name] = {
            'operations': applied_ops,
            'original_stats': {
                'mean': float(series.mean()) if not series.isna().all() else None,
                'std': float(series.std()) if not series.isna().all() else None,
                'min': float(series.min()) if not series.isna().all() else None,
                'max': float(series.max()) if not series.isna().all() else None,
            },
            'transformed_stats': {
                'mean': float(result.mean()) if not result.isna().all() else None,
                'std': float(result.std()) if not result.isna().all() else None,
                'min': float(result.min()) if not result.isna().all() else None,
                'max': float(result.max()) if not result.isna().all() else None,
            },
            'nan_count_before': int(series.isna().sum()),
            'nan_count_after': int(result.isna().sum()),
        }

        return result

    def transform_dataframe(
        self,
        df: pd.DataFrame,
        transform_config: Dict[str, Any]
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        对DataFrame应用变换配置

        Args:
            df: 输入DataFrame
            transform_config: 变换配置字典 {变量名: {'zero_method': str, 'operations': list}}

        Returns:
            Tuple[pd.DataFrame, Dict]:
                - 转换后的DataFrame
                - 转换详情字典
        """
        if df.empty:
            self.logger.warning("输入DataFrame为空，跳过转换")
            return df.copy(), {}

        self._transform_details = {}
        result_df = df.copy()

        # 统计
        total_vars = len(transform_config)
        processed_vars = 0
        skipped_vars = 0

        self.logger.info(f"开始变量转换：共{total_vars}个变量需要处理")

        for var_name, config in transform_config.items():
            if var_name not in result_df.columns:
                self.logger.warning(f"变量 '{var_name}' 不在数据中，跳过")
                skipped_vars += 1
                continue

            # 解析配置
            zero_method = config.get('zero_method', 'none')
            operations = config.get('operations', [])

            if not operations and zero_method == 'none':
                # 无任何操作，直接复制原始数据（确保变量被包含在输出中以进行平稳性检验）
                if var_name in df.columns:
                    result_df[var_name] = df[var_name].copy()
                continue

            # 应用转换
            original_series = result_df[var_name]
            transformed_series = self.transform_variable(
                original_series,
                operations,
                zero_method=zero_method
            )

            # 替换原变量
            result_df[var_name] = transformed_series
            processed_vars += 1

            # 构建操作描述
            ops_parts = []
            if zero_method != 'none':
                ops_parts.append(f'0值:{zero_method}')
            for op in operations:
                ops_parts.append(self.OPERATIONS.get(op, op))
            ops_str = ' -> '.join(ops_parts)
            self.logger.info(f"  {var_name}: {ops_str}")

        self.logger.info(
            f"变量转换完成：处理{processed_vars}个，跳过{skipped_vars}个"
        )

        return result_df, self._transform_details

    def get_transform_summary(self) -> Dict:
        """
        获取转换摘要信息

        Returns:
            Dict: 转换摘要
        """
        if not self._transform_details:
            return {
                'total_transformed': 0,
                'operations_count': {},
                'details': {}
            }

        # 统计各操作的使用次数
        ops_count = {}
        for var_info in self._transform_details.values():
            for op in var_info.get('operations', []):
                ops_count[op] = ops_count.get(op, 0) + 1

        return {
            'total_transformed': len(self._transform_details),
            'operations_count': ops_count,
            'details': self._transform_details
        }


def get_default_transform_config(
    variables: List[str],
    var_nature_map: Dict[str, str],
    freq: str = 'W-FRI'
) -> List[Dict]:
    """
    根据变量性质生成默认转换配置（用于表格显示）

    Args:
        variables: 变量名列表
        var_nature_map: 变量-性质映射
        freq: 目标频率

    Returns:
        List[Dict]: 配置列表，每项包含 {变量名, 性质, 第一次处理, 第二次处理, 第三次处理}
        注：零值处理已在基础设置中全局配置，无需单独配置
    """
    from dashboard.models.DFM.utils.text_utils import normalize_text

    transformer = VariableTransformer(freq=freq)
    config_list = []

    for var in variables:
        # 标准化变量名以匹配映射表
        var_norm = normalize_text(var)
        nature = var_nature_map.get(var_norm, '未知')

        # 获取推荐操作
        first_op, second_op = transformer.get_recommended_operations(nature)

        config_list.append({
            '变量名': var,
            '性质': nature,
            '第一次处理': transformer.OPERATIONS.get(first_op, '不处理'),
            '第二次处理': transformer.OPERATIONS.get(second_op, '不处理'),
            '第三次处理': '不处理'
        })

    return config_list
