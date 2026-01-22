# -*- coding: utf-8 -*-
"""
DTW距离计算模块

动态时间规整(DTW)计算功能，使用dtaidistance库实现

修复记录：
- 2025-10-15: 修复窗口约束问题
  - 完全移除fastdtw（radius参数不起作用）
  - 使用dtaidistance（window参数真正有效）
  - 窗口约束功能完全可用
"""

import logging
from typing import Tuple, Optional, List
import numpy as np

from dashboard.explore.core.constants import DEFAULT_DTW_WINDOW

logger = logging.getLogger(__name__)

# 导入dtaidistance库
try:
    from dtaidistance import dtw as dtaidist_dtw
    DTW_AVAILABLE = True
except ImportError:
    DTW_AVAILABLE = False
    logger.error("dtaidistance库未安装，DTW功能不可用")
    logger.error("请运行: pip install dtaidistance")


def calculate_dtw_distance(
    series1: np.ndarray,
    series2: np.ndarray,
    window_size: Optional[int] = None,
    use_window: bool = False
) -> Optional[float]:
    """
    计算两个序列之间的DTW距离

    Args:
        series1: 第一个序列（numpy数组）
        series2: 第二个序列（numpy数组）
        window_size: 窗口大小（Sakoe-Chiba约束）
        use_window: 是否使用窗口约束

    Returns:
        DTW距离值，失败则返回None
    """
    if not DTW_AVAILABLE:
        raise ImportError("dtaidistance库未安装，无法计算DTW距离")

    try:
        if use_window and window_size is not None and window_size > 0:
            distance = dtaidist_dtw.distance(series1, series2, window=window_size)
        else:
            distance = dtaidist_dtw.distance(series1, series2)

        return float(distance)

    except Exception as e:
        logger.error(f"DTW距离计算失败: {e}")
        raise


def calculate_dtw_path(
    series1: np.ndarray,
    series2: np.ndarray,
    window_size: Optional[int] = None,
    use_window: bool = False,
    radius: Optional[int] = None
) -> Tuple[float, Optional[List[Tuple[int, int]]]]:
    """
    计算DTW距离和对齐路径

    Args:
        series1: 第一个序列
        series2: 第二个序列
        window_size: 窗口大小（原有API）
        use_window: 是否使用窗口约束（原有API）
        radius: 半径约束（兼容旧API，等同于window_size）

    Returns:
        Tuple[DTW距离, 对齐路径列表]
        对齐路径中每个元素为(index1, index2)元组

    Note:
        dtaidistance库固定使用欧氏距离
    """
    if not DTW_AVAILABLE:
        raise ImportError("dtaidistance库未安装，无法计算DTW路径")

    # 参数适配：确定实际使用的窗口大小
    if radius is not None:
        actual_window = radius
    elif use_window and window_size is not None:
        actual_window = window_size
    else:
        actual_window = None  # 无约束

    try:
        # 计算DTW距离
        if actual_window is not None and actual_window > 0:
            logger.debug(f"[DTW] 使用窗口约束: window={actual_window}, 序列长度=({len(series1)}, {len(series2)})")
            distance = dtaidist_dtw.distance(series1, series2, window=actual_window)
            path = dtaidist_dtw.warping_path(series1, series2, window=actual_window)
        else:
            logger.debug(f"[DTW] 无窗口约束模式, 序列长度=({len(series1)}, {len(series2)})")
            distance = dtaidist_dtw.distance(series1, series2)
            path = dtaidist_dtw.warping_path(series1, series2)

        logger.debug(f"[DTW] 计算完成: distance={distance:.4f}, path_length={len(path) if path else 0}")
        return float(distance), path

    except Exception as e:
        logger.error(f"DTW路径计算失败: {e}")
        raise
