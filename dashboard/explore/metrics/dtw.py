"""
DTW距离计算模块

动态时间规整(DTW)计算功能，使用dtaidistance库实现

实现说明：dtaidistance 的 ``window`` 参数提供 Sakoe-Chiba 窗口约束。
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

from dtaidistance import dtw as dtaidist_dtw


def calculate_dtw_path(
    series1: np.ndarray,
    series2: np.ndarray,
    radius: int | None = None
) -> tuple[float, list[tuple[int, int]] | None]:
    """
    计算DTW距离和对齐路径

    Args:
        series1: 第一个序列
        series2: 第二个序列
        radius: Sakoe-Chiba 窗口半径；为 None 时不限制窗口

    Returns:
        Tuple[DTW距离, 对齐路径列表]
        对齐路径中每个元素为(index1, index2)元组

    Note:
        dtaidistance库固定使用欧氏距离
    """
    # 计算DTW距离
    if radius is not None:
        logger.debug(f"[DTW] 使用窗口约束: window={radius}, 序列长度=({len(series1)}, {len(series2)})")
        distance = dtaidist_dtw.distance(series1, series2, window=radius)
        path = dtaidist_dtw.warping_path(series1, series2, window=radius)
    else:
        logger.debug(f"[DTW] 无窗口约束模式, 序列长度=({len(series1)}, {len(series2)})")
        distance = dtaidist_dtw.distance(series1, series2)
        path = dtaidist_dtw.warping_path(series1, series2)

    logger.debug(f"[DTW] 计算完成: distance={distance:.4f}, path_length={len(path) if path else 0}")
    return float(distance), path
