"""DFM 数据准备频率级并行配置。"""

from __future__ import annotations

from dataclasses import dataclass
import os


VALID_BACKENDS = {"loky", "multiprocessing", "threading"}


def get_cpu_count() -> int:
    """返回可用 CPU 核数；系统无法检测时使用 4。"""

    count = os.cpu_count()
    return count if count is not None and count > 0 else 4


@dataclass
class PrepParallelConfig:
    """控制频率分组处理使用的并行任务数和后端。"""

    enable_parallel: bool = True
    n_jobs: int = -1
    backend: str = "loky"

    def __post_init__(self) -> None:
        if self.n_jobs == 0:
            raise ValueError("n_jobs不能为0，使用-1表示所有核心减1，1表示串行")
        if self.backend not in VALID_BACKENDS:
            raise ValueError(f"backend必须是{sorted(VALID_BACKENDS)}之一")

    def get_effective_n_jobs(self) -> int:
        """将用户配置换算为至少一个、且不挤占全部 CPU 的任务数。"""

        if not self.enable_parallel:
            return 1
        cpu_count = get_cpu_count()
        max_jobs = max(1, cpu_count - 1)
        if self.n_jobs == -1:
            return max_jobs
        if self.n_jobs < -1:
            return max(1, min(cpu_count + self.n_jobs + 1, max_jobs))
        return min(max(1, self.n_jobs), max_jobs)


def create_default_prep_config() -> PrepParallelConfig:
    """创建默认频率级并行配置。"""

    return PrepParallelConfig()


__all__ = ["PrepParallelConfig", "create_default_prep_config", "get_cpu_count"]
