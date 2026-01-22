# -*- coding: utf-8 -*-
"""
DFM数据准备并行配置模块

提供数据准备流程的并行计算配置和工具
"""

import os
import multiprocessing
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_cpu_count() -> int:
    """获取CPU核心数

    Returns:
        int: CPU核心数，检测失败时返回默认值4
    """
    count = os.cpu_count()
    return count if count is not None and count > 0 else 4


@dataclass
class PrepParallelConfig:
    """
    数据准备并行配置

    控制各并行化点的行为：
    1. 频率级处理并行（6个频率独立处理）
    2. ADF平稳性检验并行（逐列独立）
    3. 缺失值检测并行（逐列独立）
    4. Sheet读取并行（多工作表独立）

    Attributes:
        enable_parallel: 全局并行开关
        n_jobs: 并行任务数（-1=cpu_count-1, 1=串行）
        backend: 并行后端（loky/multiprocessing/threading）
        enable_frequency_parallel: 是否启用频率级并行
        min_frequencies_for_parallel: 启用频率并行的最小频率数
        enable_adf_parallel: 是否启用ADF检验并行
        min_columns_for_adf_parallel: 启用ADF并行的最小列数
        enable_missing_parallel: 是否启用缺失值检测并行
        min_columns_for_missing_parallel: 启用缺失值并行的最小列数
        enable_sheet_parallel: 是否启用Sheet读取并行
        min_sheets_for_parallel: 启用Sheet并行的最小工作表数
    """
    # 全局开关
    enable_parallel: bool = True
    n_jobs: int = -1  # -1=所有核心-1, 1=串行
    backend: str = 'loky'  # loky, multiprocessing, threading

    # 频率级并行配置
    enable_frequency_parallel: bool = True
    min_frequencies_for_parallel: int = 3  # 至少3个频率才启用并行

    # ADF检验并行配置
    enable_adf_parallel: bool = True
    min_columns_for_adf_parallel: int = 10  # 至少10列才启用ADF并行

    # 缺失值检测并行配置
    enable_missing_parallel: bool = True
    min_columns_for_missing_parallel: int = 15  # 至少15列才启用缺失值并行

    # Sheet读取并行配置
    enable_sheet_parallel: bool = True
    min_sheets_for_parallel: int = 4  # 至少4个sheet才启用并行
    sheet_backend: str = 'threading'  # Sheet读取是I/O密集型，使用线程

    def __post_init__(self):
        """验证配置"""
        if self.n_jobs == 0:
            raise ValueError("n_jobs不能为0，使用-1表示所有核心-1，1表示串行")

        valid_backends = ['loky', 'multiprocessing', 'threading']
        if self.backend not in valid_backends:
            raise ValueError(f"backend必须是{valid_backends}之一")
        if self.sheet_backend not in valid_backends:
            raise ValueError(f"sheet_backend必须是{valid_backends}之一")

    def get_effective_n_jobs(self) -> int:
        """获取实际并行任务数

        Returns:
            int: 实际使用的并行任务数
        """
        if not self.enable_parallel:
            return 1

        cpu_count = get_cpu_count()

        if self.n_jobs == -1:
            # 使用所有核心减1，保留一个核心给系统
            return max(1, cpu_count - 1)
        elif self.n_jobs < -1:
            # 负数表示 cpu_count + n_jobs + 1
            return max(1, cpu_count + self.n_jobs + 1)
        else:
            # 正数直接使用，但不超过cpu_count-1
            return min(max(1, self.n_jobs), cpu_count - 1)

    def should_parallelize_frequencies(self, n_freqs: int) -> bool:
        """判断是否应对频率处理启用并行

        Args:
            n_freqs: 有数据的频率数量

        Returns:
            bool: 是否启用并行
        """
        if not self.enable_parallel or not self.enable_frequency_parallel:
            return False
        return n_freqs >= self.min_frequencies_for_parallel

    def should_parallelize_adf(self, n_cols: int) -> bool:
        """判断是否应对ADF检验启用并行

        Args:
            n_cols: 需要检验的列数

        Returns:
            bool: 是否启用并行
        """
        if not self.enable_parallel or not self.enable_adf_parallel:
            return False
        return n_cols >= self.min_columns_for_adf_parallel

    def should_parallelize_missing(self, n_cols: int) -> bool:
        """判断是否应对缺失值检测启用并行

        Args:
            n_cols: 需要检测的列数

        Returns:
            bool: 是否启用并行
        """
        if not self.enable_parallel or not self.enable_missing_parallel:
            return False
        return n_cols >= self.min_columns_for_missing_parallel

    def should_parallelize_sheets(self, n_sheets: int) -> bool:
        """判断是否应对Sheet读取启用并行

        Args:
            n_sheets: 工作表数量

        Returns:
            bool: 是否启用并行
        """
        if not self.enable_parallel or not self.enable_sheet_parallel:
            return False
        return n_sheets >= self.min_sheets_for_parallel

    def to_serializable_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典（用于传递给子进程）

        Returns:
            Dict: 可序列化的配置字典
        """
        return {
            'enable_parallel': self.enable_parallel,
            'n_jobs': self.n_jobs,
            'backend': self.backend,
            'enable_frequency_parallel': self.enable_frequency_parallel,
            'min_frequencies_for_parallel': self.min_frequencies_for_parallel,
            'enable_adf_parallel': self.enable_adf_parallel,
            'min_columns_for_adf_parallel': self.min_columns_for_adf_parallel,
            'enable_missing_parallel': self.enable_missing_parallel,
            'min_columns_for_missing_parallel': self.min_columns_for_missing_parallel,
            'enable_sheet_parallel': self.enable_sheet_parallel,
            'min_sheets_for_parallel': self.min_sheets_for_parallel,
            'sheet_backend': self.sheet_backend,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'PrepParallelConfig':
        """从字典创建配置

        Args:
            config_dict: 配置字典

        Returns:
            PrepParallelConfig: 配置实例
        """
        return cls(**config_dict)

    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"PrepParallelConfig(enable={self.enable_parallel}, "
            f"n_jobs={self.get_effective_n_jobs()}, backend={self.backend})"
        )


def create_default_prep_config() -> PrepParallelConfig:
    """创建默认的数据准备并行配置

    Returns:
        PrepParallelConfig: 默认配置实例
    """
    return PrepParallelConfig()


def create_serial_prep_config() -> PrepParallelConfig:
    """创建串行处理配置（禁用所有并行）

    Returns:
        PrepParallelConfig: 串行配置实例
    """
    return PrepParallelConfig(enable_parallel=False)


__all__ = [
    'PrepParallelConfig',
    'get_cpu_count',
    'create_default_prep_config',
    'create_serial_prep_config'
]
