# -*- coding: utf-8 -*-
"""
Sheet读取并行处理器

并行读取Excel工作表，I/O密集型优化
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional, Any
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)


def _fix_invalid_dates(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """
    修正无效日期（如2月30日、4月31日等）

    某些数据源（如电网旬度数据）可能包含无效日期，
    将其修正为该月的最后一天。

    Args:
        df: 原始DataFrame，第一列为日期
        sheet_name: 工作表名称（用于日志）

    Returns:
        pd.DataFrame: 修正后的DataFrame
    """
    date_col = df.columns[0]
    fixed_count = 0

    # 遍历检查日期列
    for idx, val in df[date_col].items():
        if pd.isna(val):
            continue

        # 尝试解析日期字符串
        val_str = str(val)

        # 检查常见的无效日期模式（如 2025/2/30, 2025-2-30 等）
        for sep in ['/', '-']:
            if sep in val_str:
                parts = val_str.split(sep)
                if len(parts) >= 3:
                    try:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2].split()[0])  # 处理可能的时间部分

                        # 获取该月的最后一天
                        last_day = monthrange(year, month)[1]

                        if day > last_day:
                            # 修正为该月最后一天
                            fixed_date = f"{year}{sep}{month:02d}{sep}{last_day:02d}"
                            df.at[idx, date_col] = fixed_date
                            fixed_count += 1
                            logger.debug(f"    修正无效日期: {val_str} -> {fixed_date}")
                    except (ValueError, IndexError):
                        pass
                break

    if fixed_count > 0:
        logger.info(f"    {sheet_name}: 修正了 {fixed_count} 个无效日期")

    return df


# ========== 可序列化的顶层函数 ==========

def _read_single_sheet(
    excel_path: str,
    sheet_name: str,
    reference_frequency_map: Dict[str, str]
) -> Tuple[str, Optional[Dict[str, Dict[str, Tuple[np.ndarray, np.ndarray]]]], Dict[str, str]]:
    """
    读取单个工作表（可序列化顶层函数）

    Args:
        excel_path: Excel文件路径
        sheet_name: 工作表名称
        reference_frequency_map: 频率映射字典（标准化后的变量名 -> 频率）

    Returns:
        Tuple[str, Optional[Dict], Dict]:
            - 工作表名称
            - 按频率分类的数据字典 {freq: {var: (values, index)}}
            - 变量-行业映射
    """
    try:
        from dashboard.models.DFM.utils.text_utils import normalize_text

        if sheet_name == '指标字典':
            return (sheet_name, None, {})

        logger.debug(f"  [Sheet并行] 读取: {sheet_name}")

        # 读取工作表
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=0)
        if df.shape[1] < 2:
            logger.debug(f"    {sheet_name}: 列数不足，跳过")
            return (sheet_name, None, {})

        # 修正无效日期（如电网数据中的2月30日）
        df = _fix_invalid_dates(df, sheet_name)

        # 解析日期列
        date_col = pd.to_datetime(df.iloc[:, 0], errors='coerce')
        valid_mask = date_col.notna()

        if not valid_mask.any():
            logger.debug(f"    {sheet_name}: 无有效日期，跳过")
            return (sheet_name, None, {})

        # 按频率分类数据
        data_by_freq = {
            'daily': {},
            'weekly': {},
            'dekad': {},
            'monthly': {},
            'quarterly': {},
            'yearly': {}
        }
        var_industry_map = {}

        for col_idx in range(1, df.shape[1]):
            var_name = str(df.columns[col_idx])
            norm_var_name = normalize_text(var_name)

            # 从映射表获取频率
            freq = reference_frequency_map.get(norm_var_name, '').lower()
            if not freq:
                continue

            # 提取数据
            values = pd.to_numeric(df.loc[valid_mask, var_name], errors='coerce')
            series = pd.Series(values.values, index=date_col[valid_mask], name=var_name)

            # 序列化为 (values, index)
            serialized = (series.values, series.index.values)

            # 按频率分类
            if '日' in freq or 'daily' in freq:
                data_by_freq['daily'][var_name] = serialized
            elif '周' in freq or 'weekly' in freq:
                data_by_freq['weekly'][var_name] = serialized
            elif '旬' in freq or 'dekad' in freq:
                data_by_freq['dekad'][var_name] = serialized
            elif '月' in freq or 'monthly' in freq:
                data_by_freq['monthly'][var_name] = serialized
            elif '季' in freq or 'quarterly' in freq:
                data_by_freq['quarterly'][var_name] = serialized
            elif '年' in freq or 'yearly' in freq or 'annual' in freq:
                data_by_freq['yearly'][var_name] = serialized

            # 从sheet名称推断行业
            var_industry_map[norm_var_name] = sheet_name

        # 清理空的频率字典
        data_by_freq = {k: v for k, v in data_by_freq.items() if v}

        if not data_by_freq:
            return (sheet_name, None, {})

        var_count = sum(len(v) for v in data_by_freq.values())
        logger.debug(f"    {sheet_name}: 读取 {var_count} 个变量")

        return (sheet_name, data_by_freq, var_industry_map)

    except Exception as e:
        logger.warning(f"  [Sheet并行] 读取 '{sheet_name}' 失败: {e}")
        return (sheet_name, None, {})


def parallel_read_sheets(
    excel_path: str,
    sheet_names: List[str],
    reference_frequency_map: Dict[str, str],
    n_jobs: int = -1,
    backend: str = 'threading'
) -> Tuple[Dict[str, Dict[str, pd.Series]], Dict[str, str]]:
    """
    并行读取所有工作表

    Args:
        excel_path: Excel文件路径
        sheet_names: 工作表名称列表
        reference_frequency_map: 频率映射字典
        n_jobs: 并行任务数
        backend: 并行后端（默认threading，因为是I/O密集型）

    Returns:
        Tuple[Dict, Dict]:
            - 按频率分类的合并数据 {freq: {var: Series}}
            - 变量-行业映射
    """
    from joblib import Parallel, delayed

    # 过滤掉指标字典sheet
    sheets_to_read = [s for s in sheet_names if s != '指标字典']

    if not sheets_to_read:
        return {}, {}

    logger.info(f"  [Sheet并行] 读取 {len(sheets_to_read)} 个工作表 (n_jobs={n_jobs}, backend={backend})...")

    # 并行执行（使用threading后端，因为是I/O密集型）
    results = Parallel(n_jobs=n_jobs, backend=backend, prefer='threads')(
        delayed(_read_single_sheet)(excel_path, sheet_name, reference_frequency_map)
        for sheet_name in sheets_to_read
    )

    # 聚合结果
    merged_data = {
        'daily': {},
        'weekly': {},
        'dekad': {},
        'monthly': {},
        'quarterly': {},
        'yearly': {}
    }
    all_var_industry_map = {}

    for sheet_name, data_by_freq, var_map in results:
        if data_by_freq is None:
            continue

        for freq_name, freq_data in data_by_freq.items():
            for var_name, (values, index) in freq_data.items():
                # 重建Series
                series = pd.Series(values, index=pd.to_datetime(index), name=var_name)
                merged_data[freq_name][var_name] = series

        all_var_industry_map.update(var_map)

    # 清理空的频率字典
    merged_data = {k: v for k, v in merged_data.items() if v}

    # 统计
    total_vars = sum(len(d) for d in merged_data.values())
    logger.info(f"  [Sheet并行] 读取完成, 共 {total_vars} 个变量")

    return merged_data, all_var_industry_map


__all__ = [
    '_read_single_sheet',
    'parallel_read_sheets'
]
