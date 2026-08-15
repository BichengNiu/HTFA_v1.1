# -*- coding: utf-8 -*-
"""
并行计算配置模块（DFM 共享）

提供 DFM 数据准备与模型训练共用的并行计算配置和工具。
数据准备（prep）与模型训练（train）共用这一实现，避免双轨配置漂移。
"""

import os
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

VALID_BACKENDS = {'loky', 'multiprocessing', 'threading'}


def get_cpu_count() -> int:
    """返回可用 CPU 核数；系统无法检测时使用 4。"""
    count = os.cpu_count()
    return count if count is not None and count > 0 else 4


@dataclass
class ParallelConfig:
    """
    并行计算配置

    Attributes:
        enabled: 是否启用并行计算
        n_jobs: 并行任务数（-1表示使用所有可用核心，1表示串行）
        backend: 并行后端（'loky', 'multiprocessing', 'threading'）
        min_variables_for_parallel: 启用并行的最小变量数阈值
    """
    enabled: bool = False
    n_jobs: int = -1
    backend: str = 'loky'
    min_variables_for_parallel: int = 5

    def __post_init__(self):
        """初始化后验证配置"""
        # 验证n_jobs
        if self.n_jobs == 0:
            raise ValueError("n_jobs不能为0，使用-1表示所有核心，1表示串行")

        # 验证backend
        if self.backend not in VALID_BACKENDS:
            raise ValueError(
                f"backend必须是{sorted(VALID_BACKENDS)}之一，当前值: {self.backend}"
            )

    def get_effective_n_jobs(self) -> int:
        """
        获取实际使用的并行任务数

        Returns:
            实际并行任务数（-1会被解析为CPU核心数-1）
        """
        if not self.enabled:
            return 1

        cpu_count = get_cpu_count()
        max_jobs = max(1, cpu_count - 1)

        if self.n_jobs == -1:
            # -1表示使用所有核心减1（为系统保留1个核心）
            return max_jobs
        elif self.n_jobs < -1:
            # -2表示n-2个核心，-3表示n-3个核心...
            return max(1, min(cpu_count + self.n_jobs + 1, max_jobs))
        else:
            # 正数直接使用，但不超过cpu_count-1
            return min(max(1, self.n_jobs), max_jobs)

    def should_use_parallel(self, n_variables: int) -> bool:
        """
        判断是否应该使用并行计算

        Args:
            n_variables: 待评估的变量数

        Returns:
            是否使用并行
        """
        if not self.enabled:
            return False

        if n_variables < self.min_variables_for_parallel:
            logger.debug(
                f"变量数({n_variables})小于并行阈值({self.min_variables_for_parallel})，"
                f"使用串行模式"
            )
            return False

        effective_jobs = self.get_effective_n_jobs()
        if effective_jobs <= 1:
            return False

        return True


def create_default_parallel_config() -> ParallelConfig:
    """创建默认并行配置（数据准备侧默认启用）。"""
    return ParallelConfig(enabled=True)


__all__ = [
    'ParallelConfig',
    'VALID_BACKENDS',
    'create_default_parallel_config',
    'get_cpu_count',
]
