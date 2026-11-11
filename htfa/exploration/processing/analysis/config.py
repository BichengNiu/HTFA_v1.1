"""
分析配置类

提供统一的配置管理，简化函数参数，遵循KISS原则

公共配置在构造时完成验证，避免 UI 与程序化调用产生不同语义。
"""

from dataclasses import dataclass
from numbers import Integral


@dataclass
class LeadLagAnalysisConfig:
    """
    领先滞后分析配置

    使用配置类封装参数，简化函数调用
    """

    # 核心参数
    max_lags: int

    # 标准化配置
    standardize_for_kl: bool = True
    standardization_method: str = 'zscore'

    # 频率对齐配置
    enable_frequency_alignment: bool = True
    target_frequency: str | None = None
    freq_agg_method: str = 'mean'
    time_column: str | None = None

    def __post_init__(self):
        """公共配置在进入分析链路前必须完成验证。"""
        self.validate()

    def validate(self):
        """
        手动验证配置参数

        UI 和外部调用使用同一约束，避免静默改变统计含义。
        """
        if (
            isinstance(self.max_lags, bool)
            or not isinstance(self.max_lags, Integral)
            or self.max_lags < 1
        ):
            raise ValueError("max_lags必须大于0且为整数")

        if self.standardization_method not in ['zscore', 'minmax', 'none']:
            raise ValueError(
                f"不支持的标准化方法: {self.standardization_method}，"
                f"请使用 'zscore', 'minmax' 或 'none'"
            )

        valid_freq_agg = ['mean', 'last', 'first', 'sum', 'median']
        if self.freq_agg_method not in valid_freq_agg:
            raise ValueError(
                f"不支持的聚合方法: {self.freq_agg_method}，"
                f"请使用 {valid_freq_agg} 之一"
            )

        valid_freqs = [
            None,
            'Daily',
            'Weekly',
            'Ten_Day',
            'Monthly',
            'Quarterly',
            'Annual',
        ]
        if self.target_frequency not in valid_freqs:
            raise ValueError(
                f"不支持的目标频率: {self.target_frequency}，"
                f"请使用 {[f for f in valid_freqs if f is not None]} 之一或None"
            )


