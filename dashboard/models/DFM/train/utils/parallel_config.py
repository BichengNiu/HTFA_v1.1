# -*- coding: utf-8 -*-
"""
并行计算配置模块（train 侧转发）

统一实现位于 dashboard.models.DFM.utils.parallel_config，
train 侧保留此模块以维持既有导入路径。
"""

from dashboard.models.DFM.utils.parallel_config import (
    VALID_BACKENDS,
    ParallelConfig,
    get_cpu_count,
)

__all__ = [
    'ParallelConfig',
    'VALID_BACKENDS',
    'get_cpu_count',
]
