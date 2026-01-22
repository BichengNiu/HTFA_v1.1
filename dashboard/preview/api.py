# -*- coding: utf-8 -*-
"""
数据预览模块 - 统一API接口

提供前后端分离的数据加载和预览API
"""

import pandas as pd
from typing import Dict, Any, Union
import logging

from dashboard.preview.modules.industrial.loader import load_and_process_data, LoadedIndustrialData

logger = logging.getLogger(__name__)


def load_preview_data(uploaded_file: Union[str, Any]) -> Dict[str, Any]:
    """
    加载并处理预览数据

    Args:
        uploaded_file: Excel文件路径或文件对象

    Returns:
        dict: {
            'status': str,
            'message': str,
            'data': LoadedIndustrialData,
            'metadata': {
                'total_indicators': int,
                'frequencies': Dict[str, int],
                'industries': list
            }
        }
    """
    try:
        logger.info("加载预览数据...")

        result = load_and_process_data(uploaded_file)

        if result is None:
            return {
                'status': 'error',
                'message': '数据加载失败',
                'data': None,
                'metadata': None
            }

        total_indicators = sum(
            len(df.columns) for df in result.get_all_dataframes().values()
            if not df.empty
        )

        frequencies = {
            freq: len(df.columns)
            for freq, df in result.get_all_dataframes().items()
            if not df.empty
        }

        industries = list(set(result.indicator_industry_map.values()))

        logger.info(f"数据加载成功，共 {total_indicators} 个指标")

        return {
            'status': 'success',
            'message': f'成功加载 {total_indicators} 个指标',
            'data': result,
            'metadata': {
                'total_indicators': total_indicators,
                'frequencies': frequencies,
                'industries': industries
            }
        }

    except Exception as e:
        logger.error(f"加载数据失败: {e}", exc_info=True)
        return {
            'status': 'error',
            'message': f'加载数据失败: {str(e)}',
            'data': None,
            'metadata': None
        }


__all__ = ['load_preview_data']
