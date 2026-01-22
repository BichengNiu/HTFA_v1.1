"""
格式检测模块

负责检测和解析不同来源的Excel表格格式
支持同花顺、Wind、Mysteel等不同数据源的格式
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def detect_sheet_format(excel_file, sheet_name: str) -> Dict[str, Any]:
    """
    简化的格式检测函数 - 现在所有数据sheet都使用统一格式
    统一格式：第一行是列名，第一列是时间列，第二列开始是数据变量
    
    Args:
        excel_file: Excel文件对象
        sheet_name: 表格名称
        
    Returns:
        Dict[str, Any]: 包含格式信息的字典
            - format: 格式类型
            - skiprows: 需要跳过的行
            - header: 标题行位置
            - data_start_row: 数据开始行
            - source: 数据源
    """
    try:
        # 特殊处理：指标字典sheet
        if sheet_name == '指标字典':
            return {
                'format': 'indicator_system',
                'skiprows': None,
                'header': 0,
                'data_start_row': 1,
                'source': 'system'
            }

        # 所有其他数据sheet都使用统一格式
        logger.debug("[格式检测] 使用统一格式处理数据sheet: %s", sheet_name)
        return {
            'format': 'unified_new',
            'skiprows': None,      # 不跳过任何行
            'header': 0,           # 第一行是列名
            'data_start_row': 1,   # 数据从第二行开始
            'source': 'unified'
        }

    except Exception as e:
        logger.warning("[格式检测] 检测格式时出错: %s，使用统一格式", e)
        return {
            'format': 'unified_new',
            'skiprows': None,
            'header': 0,
            'data_start_row': 1,
            'source': 'unified'
        }

def parse_sheet_info(sheet_name: str, target_sheet_name: str) -> Dict[str, Optional[str]]:
    """
    解析表格名称，提取行业、频率和数据源信息

    处理格式如 '行业_频率_数据来源' 或目标表格

    Args:
        sheet_name: 表格名称
        target_sheet_name: 目标表格名称

    Returns:
        Dict[str, Optional[str]]: 包含以下键的字典
            - industry: 行业信息
            - freq_type: 频率类型 ('daily', 'weekly', 'dekad', 'monthly', 'monthly_target', 'monthly_predictor')
            - source: 数据源
    """
    info: Dict[str, Optional[str]] = {'industry': None, 'freq_type': None, 'source': None}

    if not isinstance(sheet_name, str):
        return info

    # 进行大小写不敏感的比较，检查是否为目标表格
    is_target_sheet = False
    if isinstance(target_sheet_name, str):
        if sheet_name.lower() == target_sheet_name.lower():
            is_target_sheet = True

    if is_target_sheet:
        # 尝试从目标名称提取行业 (可选)
        parts_target = sheet_name.split('_')
        if len(parts_target) > 0:
            # 假设第一个部分是行业相关
            industry_part = parts_target[0].replace('-月度', '').replace('_月度','').strip() # 同时替换 - 和 _
            info['industry'] = industry_part if industry_part else 'Macro' # 默认为 Macro
        else:
            info['industry'] = 'Macro' # 默认
        info['freq_type'] = 'monthly_target'  # 目标表格标记为月度目标
        return info

    # 通用格式解析
    parts = sheet_name.split('_')
    if len(parts) >= 2: # 至少需要 行业_频率
        info['industry'] = parts[0].strip()
        freq_part = parts[1].strip()

        if freq_part == '日度':
            info['freq_type'] = 'daily'
        elif freq_part == '周度':
            info['freq_type'] = 'weekly'
        elif freq_part == '旬度':
            info['freq_type'] = 'dekad'
        elif freq_part == '月度':
            # 其他月度预测变量表格
            info['freq_type'] = 'monthly_predictor'
        # 可以根据需要添加其他频率

        if len(parts) >= 3:
            info['source'] = '_'.join(parts[2:]).strip() # 允许来源包含下划线

    # 如果未能解析出行业，给个默认值
    if info['industry'] is None and info['freq_type'] is not None:
         info['industry'] = "Uncategorized"

    return info
