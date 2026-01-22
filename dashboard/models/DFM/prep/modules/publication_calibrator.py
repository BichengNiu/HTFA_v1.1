# -*- coding: utf-8 -*-
"""
发布日期校准模块

负责根据变量的发布滞后天数校准数据日期。
从processor.py提取，遵循单一职责原则(SRP)。
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict

from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


class PublicationCalibrator:
    """发布日期校准器

    所有频率统一处理：数据日期 + 滞后天数 = 实际发布日期
    """

    def __init__(self, publication_lag_map: Dict[str, int]):
        """初始化校准器

        Args:
            publication_lag_map: 变量名到滞后天数的映射
        """
        self.lag_map = publication_lag_map or {}

    def calibrate(self, df: pd.DataFrame, freq_type: str) -> pd.DataFrame:
        """应用发布日期校准

        所有频率统一处理：数据日期 + 滞后天数 = 实际发布日期

        Args:
            df: 输入DataFrame，索引为数据日期
            freq_type: 频率类型（仅用于日志记录）

        Returns:
            pd.DataFrame: 索引为校准后日期的DataFrame
        """
        if not self.lag_map:
            return df

        if df is None or df.empty:
            return df

        logger.info(f"  应用发布日期校准 ({freq_type})...")
        calibration_count = 0
        result_columns = {}

        for col in df.columns:
            col_norm = normalize_text(col)
            lag_days = self.lag_map.get(col_norm)

            if lag_days is not None and lag_days != 0:
                # 验证lag_days类型和范围
                if not isinstance(lag_days, (int, np.integer)):
                    raise TypeError(f"lag_days必须是整数，实际类型: {type(lag_days)}")
                if lag_days < 0 or lag_days > 365:
                    raise ValueError(f"lag_days超出合理范围 [0, 365]: {lag_days}")

                series = df[col].dropna()
                if series.empty:
                    result_columns[col] = df[col]
                    continue

                # 所有频率统一处理：直接加滞后天数
                new_index = series.index + pd.Timedelta(days=lag_days)

                calibrated_series = pd.Series(series.values, index=new_index, name=col)
                result_columns[col] = calibrated_series
                calibration_count += 1
                logger.debug(f"    {col}: 滞后{lag_days}天 ({freq_type})")
            else:
                result_columns[col] = df[col]

        if calibration_count > 0:
            result_df = pd.DataFrame(result_columns)
            result_df = result_df.sort_index()
            logger.info(f"  发布日期校准完成: {calibration_count}个变量 ({freq_type})")
            return result_df
        else:
            return df


def calibrate_publication_dates(
    df: pd.DataFrame,
    freq_type: str,
    publication_lag_map: Dict[str, int]
) -> pd.DataFrame:
    """便利函数：校准发布日期

    Args:
        df: 输入DataFrame
        freq_type: 频率类型
        publication_lag_map: 变量名到滞后天数的映射

    Returns:
        pd.DataFrame: 校准后的DataFrame
    """
    calibrator = PublicationCalibrator(publication_lag_map)
    return calibrator.calibrate(df, freq_type)


__all__ = [
    'PublicationCalibrator',
    'calibrate_publication_dates'
]
