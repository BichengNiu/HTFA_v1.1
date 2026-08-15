"""DFM 数据准备频率级并行配置。

统一实现位于 dashboard.models.DFM.utils.parallel_config，
prep 侧保留此模块以维持既有导入路径。
"""

from dashboard.models.DFM.utils.parallel_config import (
    VALID_BACKENDS,
    ParallelConfig,
    create_default_parallel_config,
    get_cpu_count,
)

# 向后兼容别名：数据准备侧默认启用并行
PrepParallelConfig = ParallelConfig


def create_default_prep_config() -> ParallelConfig:
    """创建默认频率级并行配置。"""
    return create_default_parallel_config()


__all__ = [
    "PrepParallelConfig",
    "VALID_BACKENDS",
    "create_default_prep_config",
    "get_cpu_count",
]
