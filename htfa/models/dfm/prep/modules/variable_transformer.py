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

    def apply_log(self, series: pd.Series) -> pd.Series:
        """
        对数变换

        处理规则：
        - 全为正值：直接使用np.log
        - 包含零值：使用np.log1p (log(1+x))
        - 包含负值：将负值设为NaN后继续变换

        Args:
            series: 输入时间序列

        Returns:
            pd.Series: 对数变换后的序列
        """
        var_name = series.name or "未命名"

        # 获取有效值
        valid_values = series.dropna()
        if valid_values.empty:
            self.logger.warning(f"变量 '{var_name}' 全为NaN，跳过对数变换")
            return series.copy()

        min_val = valid_values.min()

        # 包含负值时，先将负值设为NaN
        if min_val < 0:
            result = series.copy()
            negative_mask = result < 0
            negative_count = negative_mask.sum()
            result[negative_mask] = np.nan
            self.logger.info(f"变量 '{var_name}' 将 {negative_count} 个负值设为缺失值（对数变换前）")

            # 重新计算最小值
            valid_values = result.dropna()
            if valid_values.empty:
                self.logger.warning(f"变量 '{var_name}' 处理负值后全为NaN，跳过对数变换")
                return result
            min_val = valid_values.min()
        else:
            result = series

        if min_val > 0:
            # 全为正值，直接取对数
            result = np.log(result)
            self.logger.debug(f"变量 '{var_name}' 应用对数变换 (np.log)")
        elif min_val >= 0:
            # 包含零值，使用log1p
            result = np.log1p(result)
            self.logger.debug(f"变量 '{var_name}' 应用对数变换 (np.log1p)")

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
        var_name = series.name or "未命名"
        result = series.diff(periods=periods)
        self.logger.debug(
            f"变量 '{var_name}' 应用{periods}期差分，"
            f"产生{periods}个头部NaN"
        )
        return result

    def _needs_smart_yoy_diff(self, freq: str) -> bool:
        """
        判断是否需要智能同比差分（旬度、周度）

        Args:
            freq: 原始数据频率

        Returns:
            bool: 是否需要智能同比差分
        """
        if not freq:
            return False
        freq_lower = freq.lower()
        return '旬' in freq_lower or 'dekad' in freq_lower or '周' in freq_lower or 'week' in freq_lower

    def apply_smart_yoy_diff(self, series: pd.Series) -> pd.Series:
        """
        智能同比差分（适用于旬度、周度）

        对每个周五：
        1. 计算去年同期对应的周五（不跨月）
        2. 如果该周五有数据则差分，否则为NaN

        这是确定性映射，不是搜索有数据的周五。

        Args:
            series: 输入时间序列（已对齐到周五）

        Returns:
            pd.Series: 智能同比差分后的序列
        """
        from htfa.models.dfm.prep.utils.friday_utils import get_yoy_friday_no_cross_month

        var_name = series.name or "未命名"
        result = pd.Series(index=series.index, dtype=float)
        result[:] = np.nan

        matched_count = 0
        unmatched_count = 0

        for current_friday in series.index:
            current_val = series.loc[current_friday]

            # 如果当前值为NaN，跳过
            if pd.isna(current_val):
                continue

            # 计算去年同期对应的周五（不跨月）
            yoy_friday = get_yoy_friday_no_cross_month(current_friday)

            # 检查去年同期周五是否在数据索引中且有值
            if yoy_friday in series.index:
                yoy_val = series.loc[yoy_friday]
                if pd.notna(yoy_val):
                    # 计算差分（假设已经取过对数）
                    result.loc[current_friday] = current_val - yoy_val
                    matched_count += 1
                else:
                    unmatched_count += 1
            else:
                unmatched_count += 1

        self.logger.debug(
            f"变量 '{var_name}' 智能同比差分: "
            f"成功匹配 {matched_count} 个，未匹配 {unmatched_count} 个"
        )

        return result

    def transform_variable(
        self,
        series: pd.Series,
        operations: List[str],
        original_freq: str = None
    ) -> pd.Series:
        """
        按顺序对单个变量应用多个转换操作

        注意：零值处理已在基础设置阶段完成，负值在对数变换时自动处理

        Args:
            series: 输入时间序列
            operations: 操作列表，按顺序执行
            original_freq: 原始数据频率（用于智能同比差分，如 '旬度'、'周度'）

        Returns:
            pd.Series: 转换后的序列
        """
        result = series.copy()

        # 如果没有操作，直接返回
        if not operations:
            return result

        # 过滤掉 'none' 操作
        valid_ops = [op for op in operations if op != 'none']
        if not valid_ops:
            return result

        applied_ops = []

        # 应用转换操作
        for op in valid_ops:
            if op == 'log':
                result = self.apply_log(result)
                applied_ops.append('log')
            elif op == 'diff_1':
                result = self.apply_diff(result, periods=1)
                applied_ops.append('diff_1')
            elif op == 'diff_yoy':
                # 判断是否需要智能同比差分（旬度、周度）
                if self._needs_smart_yoy_diff(original_freq):
                    result = self.apply_smart_yoy_diff(result)
                    applied_ops.append('diff_yoy_smart')
                else:
                    # 其他频率使用固定周期差分
                    result = self.apply_diff(result, periods=self.yoy_period)
                    applied_ops.append(f'diff_{self.yoy_period}')
            else:
                self.logger.warning(f"未知操作 '{op}'，跳过")

        # 记录转换详情
        var_name = series.name or "未命名"
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
    """
    from htfa.models.dfm.utils.text_utils import normalize_text

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
