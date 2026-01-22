# -*- coding: utf-8 -*-
"""
训练环境配置模块

配置训练环境：BLAS线程、随机种子、日志级别
"""

import os
import random
import logging
import warnings
import multiprocessing

logger = logging.getLogger(__name__)


def setup_training_environment(
    seed: int = 42,
    silent_mode: bool = False,
    enable_debug_logging: bool = True
) -> None:
    """
    配置训练环境

    Args:
        seed: 随机种子（默认42）
        silent_mode: 是否抑制警告信息
        enable_debug_logging: 是否启用metrics模块DEBUG日志
    """
    # 1. 配置多线程BLAS
    cpu_count = multiprocessing.cpu_count()
    for env_var in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
                    'VECLIB_MAXIMUM_THREADS', 'OPENBLAS_NUM_THREADS']:
        os.environ[env_var] = str(cpu_count)
    logger.info(f"配置BLAS线程数: {cpu_count}")

    # 2. 设置随机种子
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    logger.info(f"设置随机种子: {seed}")

    # 3. 静默模式
    if silent_mode:
        warnings.filterwarnings('ignore', category=UserWarning)
        warnings.filterwarnings('ignore', category=RuntimeWarning)
        logger.info("静默模式已启用")

    # 4. DEBUG日志
    if enable_debug_logging:
        metrics_logger = logging.getLogger('dashboard.models.DFM.train.evaluation.metrics')
        metrics_logger.setLevel(logging.DEBUG)
        if not metrics_logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
            metrics_logger.addHandler(handler)
        logger.info("已启用Hit Rate DEBUG日志")


__all__ = ['setup_training_environment']
