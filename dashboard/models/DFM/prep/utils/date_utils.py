"""
日期处理工具模块

提供统一的日期处理功能，包括日期标准化、解析和验证
"""

import logging
import pandas as pd
from typing import Union, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)


def standardize_date(
    date_param: Union[str, datetime, date, pd.Timestamp, None]
) -> Optional[pd.Timestamp]:
    """
    标准化日期参数，确保在整个流程中保持一致的格式

    Args:
        date_param: 日期参数，可以是字符串、datetime、date或pd.Timestamp

    Returns:
        pd.Timestamp或None: 标准化后的时间戳，解析失败返回None

    Examples:
        >>> standardize_date('2023-01-01')
        Timestamp('2023-01-01 00:00:00')
        >>> standardize_date(datetime(2023, 1, 1))
        Timestamp('2023-01-01 00:00:00')
        >>> standardize_date(None)
        None
    """
    if date_param is None:
        return None

    if isinstance(date_param, str):
        try:
            return pd.to_datetime(date_param)
        except (ValueError, TypeError) as e:
            logger.warning("无法解析日期字符串: %s, 错误: %s", date_param, e)
            return None
    elif isinstance(date_param, (datetime, date)):
        return pd.to_datetime(date_param)
    elif isinstance(date_param, pd.Timestamp):
        return date_param
    else:
        logger.warning("不支持的日期类型: %s", type(date_param))
        return None


__all__ = [
    'standardize_date'
]
