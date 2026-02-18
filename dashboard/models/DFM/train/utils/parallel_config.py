# -*- coding: utf-8 -*-
"""
并行计算配置模块

提供DFM训练过程中的并行计算配置和工具
"""

import os
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParallelConfig:
    """
    并行计算配置

    Attributes:
        enabled: 是否启用并行计算
        n_jobs: 并行任务数（-1表示使用所有可用核心，1表示串行）
        backend: 并行后端（'loky', 'multiprocessing', 'threading'）
        verbose: 是否显示并行进度（0=静默，1=简单，2=详细）
        min_variables_for_parallel: 启用并行的最小变量数阈值
    """
    enabled: bool = False
    n_jobs: int = -1
    backend: str = 'loky'
    verbose: int = 0
    min_variables_for_parallel: int = 5

    def __post_init__(self):
        """初始化后验证配置"""
        # 验证n_jobs
        if self.n_jobs == 0:
            raise ValueError("n_jobs不能为0，使用-1表示所有核心，1表示串行")

        # 验证backend
        valid_backends = ['loky', 'multiprocessing', 'threading']
        if self.backend not in valid_backends:
            raise ValueError(f"backend必须是{valid_backends}之一，当前值: {self.backend}")

        # 验证verbose
        if self.verbose not in [0, 1, 2]:
            raise ValueError(f"verbose必须是0, 1或2，当前值: {self.verbose}")

    def get_effective_n_jobs(self) -> int:
        """
        获取实际使用的并行任务数

        Returns:
            实际并行任务数（-1会被解析为CPU核心数-1）
        """
        if not self.enabled:
            return 1

        cpu_count = get_cpu_count()

        if self.n_jobs == -1:
            # -1表示使用所有核心减1（为系统保留1个核心）
            return max(1, cpu_count - 1)
        elif self.n_jobs < -1:
            # -2表示n-2个核心，-3表示n-3个核心...
            return max(1, cpu_count + self.n_jobs + 1)
        else:
            # 正数直接使用，但不超过cpu_count-1
            return min(max(1, self.n_jobs), cpu_count - 1)

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


def get_cpu_count() -> int:
    """
    获取CPU核心数

    Returns:
        可用的CPU核心数
    """
    count = os.cpu_count()
    if count is None or count < 1:
        raise RuntimeError("无法检测CPU核心数")
    return count


__all__ = [
    'ParallelConfig',
    'get_cpu_count',
]
