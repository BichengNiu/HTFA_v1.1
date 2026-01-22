"""
统计服务模块

提供数据文件分析和变量统计功能，从UI层提取的纯业务逻辑
"""

import pandas as pd
import numpy as np
import math
import io
from typing import Dict, Any, Optional, Tuple, List
from datetime import date
import logging

logger = logging.getLogger(__name__)

# 频率周期映射（从统一常量导入）
from dashboard.models.DFM.prep.modules.config_constants import FREQ_DAYS_MAP


class StatsService:
    """统计服务类"""

    @staticmethod
    def detect_date_range(
        file_content: bytes
    ) -> Tuple[Optional[date], Optional[date], int, Dict[str, int]]:
        """
        检测Excel文件的日期范围和变量统计

        Args:
            file_content: Excel文件字节内容

        Returns:
            (开始日期, 结束日期, 变量数, 频率统计字典)
        """
        try:
            excel_file = io.BytesIO(file_content)
            all_dates_found = []
            all_variables = set()

            xl_file = pd.ExcelFile(excel_file)
            sheet_names = xl_file.sheet_names

            # 读取指标字典获取频率映射
            var_frequency_map = {}
            if '指标字典' in sheet_names:
                excel_file.seek(0)
                df_mapping = pd.read_excel(excel_file, sheet_name='指标字典')
                df_mapping.columns = df_mapping.columns.str.strip()
                if '指标名称' in df_mapping.columns and '频率' in df_mapping.columns:
                    for _, row in df_mapping.iterrows():
                        var_name = str(row['指标名称']).strip()
                        freq = str(row['频率']).strip()
                        if var_name and var_name != 'nan' and freq and freq != 'nan':
                            var_frequency_map[var_name] = freq

            # 遍历数据工作表
            for sheet_name in sheet_names:
                if any(kw in str(sheet_name).lower() for kw in ['指标字典', 'mapping', 'meta', 'info']):
                    continue

                try:
                    excel_file.seek(0)
                    df_raw = pd.read_excel(excel_file, sheet_name=sheet_name)

                    if len(df_raw) < 5:
                        continue

                    # 收集变量名
                    if len(df_raw.columns) > 1:
                        for col in df_raw.columns[1:]:
                            if col and str(col).strip():
                                all_variables.add(str(col).strip())

                    # 检测日期
                    date_values = []
                    if 'Wind' in sheet_name or (len(df_raw) > 0 and df_raw.iloc[0, 0] == '指标名称'):
                        if len(df_raw) > 1:
                            date_values = pd.to_datetime(df_raw.iloc[1:, 0], errors='coerce')
                    else:
                        for col_idx in range(min(2, len(df_raw.columns))):
                            try:
                                test_dates = pd.to_datetime(df_raw.iloc[:, col_idx], errors='coerce')
                                valid_dates = test_dates[test_dates.notna()]
                                if len(valid_dates) > len(df_raw) * 0.5:
                                    date_values = valid_dates
                                    break
                            except (ValueError, TypeError):
                                continue

                    if len(date_values) > 0:
                        valid_dates = date_values[date_values.notna()]
                        if len(valid_dates) > 5:
                            all_dates_found.extend(valid_dates.tolist())

                except Exception as e:
                    logger.debug(f"处理工作表 {sheet_name} 时出错: {e}")
                    continue

            # 统计频率分布
            freq_counts = {'日度': 0, '周度': 0, '旬度': 0, '月度': 0, '季度': 0, '年度': 0, '其他': 0}
            for var in all_variables:
                freq = var_frequency_map.get(var, '')
                freq_lower = freq.lower()
                if '日' in freq or 'daily' in freq_lower:
                    freq_counts['日度'] += 1
                elif '周' in freq or 'weekly' in freq_lower:
                    freq_counts['周度'] += 1
                elif '旬' in freq or 'dekad' in freq_lower:
                    freq_counts['旬度'] += 1
                elif '月' in freq or 'monthly' in freq_lower:
                    freq_counts['月度'] += 1
                elif '季' in freq or 'quarterly' in freq_lower:
                    freq_counts['季度'] += 1
                elif '年' in freq or 'yearly' in freq_lower or 'annual' in freq_lower:
                    freq_counts['年度'] += 1
                elif freq:
                    freq_counts['其他'] += 1

            freq_counts = {k: v for k, v in freq_counts.items() if v > 0}

            # 计算日期范围
            if all_dates_found:
                all_dates = pd.to_datetime(all_dates_found)
                min_valid_date = pd.Timestamp('1900-01-01')
                max_valid_date = pd.Timestamp.now() + pd.DateOffset(years=10)
                valid_dates = all_dates[(all_dates >= min_valid_date) & (all_dates <= max_valid_date)]

                if len(valid_dates) > 0:
                    return (
                        valid_dates.min().date(),
                        valid_dates.max().date(),
                        len(all_variables),
                        freq_counts
                    )

            return None, None, len(all_variables), freq_counts

        except Exception as e:
            logger.error(f"日期检测异常: {e}")
            return None, None, 0, {}

    @staticmethod
    def compute_raw_stats(file_content: bytes) -> pd.DataFrame:
        """
        计算原始文件的变量统计信息

        Args:
            file_content: Excel文件字节内容

        Returns:
            DataFrame: [变量名, 频率, 缺失值占比, 开始日期, 结束日期]
        """
        try:
            excel_file = io.BytesIO(file_content)
            xl_file = pd.ExcelFile(excel_file)
            sheet_names = xl_file.sheet_names

            # 读取频率映射
            var_frequency_map = {}
            if '指标字典' in sheet_names:
                excel_file.seek(0)
                df_mapping = pd.read_excel(excel_file, sheet_name='指标字典')
                df_mapping.columns = df_mapping.columns.str.strip()
                if '指标名称' in df_mapping.columns and '频率' in df_mapping.columns:
                    for _, row in df_mapping.iterrows():
                        var_name = str(row['指标名称']).strip()
                        freq = str(row['频率']).strip()
                        if var_name and var_name != 'nan' and freq and freq != 'nan':
                            var_frequency_map[var_name] = freq

            # 收集变量数据
            var_data = {}
            for sheet_name in sheet_names:
                if any(kw in str(sheet_name).lower() for kw in ['指标字典', 'mapping', 'meta', 'info']):
                    continue

                try:
                    excel_file.seek(0)
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    if len(df) < 2 or len(df.columns) < 2:
                        continue

                    # 检测日期列
                    date_col_idx = None
                    for col_idx in range(min(2, len(df.columns))):
                        try:
                            test_dates = pd.to_datetime(df.iloc[:, col_idx], errors='coerce')
                            if test_dates.notna().sum() > len(df) * 0.5:
                                date_col_idx = col_idx
                                break
                        except (ValueError, TypeError):
                            continue

                    if date_col_idx is None:
                        continue

                    dates = pd.to_datetime(df.iloc[:, date_col_idx], errors='coerce')

                    for col_idx in range(len(df.columns)):
                        if col_idx == date_col_idx:
                            continue
                        col_name = str(df.columns[col_idx]).strip()
                        if not col_name or col_name == 'nan':
                            continue

                        if col_name not in var_data:
                            var_data[col_name] = []

                        for dt, val in zip(dates, df.iloc[:, col_idx]):
                            if pd.notna(dt):
                                var_data[col_name].append((dt, val))

                except Exception as e:
                    logger.debug(f"处理工作表 {sheet_name} 时出错: {e}")
                    continue

            # 计算统计信息
            stats_list = []
            for var_name, data_points in var_data.items():
                if not data_points:
                    continue

                freq = var_frequency_map.get(var_name, '-')
                valid_points = [(dt, val) for dt, val in data_points if pd.notna(val) and val != 0]

                if not valid_points:
                    stats_list.append({
                        '变量名': var_name,
                        '频率': freq,
                        '缺失值占比': '100.0%',
                        '开始日期': '-',
                        '结束日期': '-'
                    })
                    continue

                valid_dates = [dt for dt, _ in valid_points]
                start_date = min(valid_dates)
                end_date = max(valid_dates)

                days_span = (end_date - start_date).days + 1
                freq_lower = freq.lower() if freq else ''
                if freq_lower not in FREQ_DAYS_MAP:
                    raise ValueError(f"未知频率: {freq}")
                freq_days = FREQ_DAYS_MAP[freq_lower]
                theoretical_count = max(1, math.ceil(days_span / freq_days))

                valid_count = len(valid_points)
                missing_count = max(0, theoretical_count - valid_count)
                missing_ratio = missing_count / theoretical_count * 100 if theoretical_count > 0 else 0

                stats_list.append({
                    '变量名': var_name,
                    '频率': freq,
                    '缺失值占比': f'{missing_ratio:.1f}%',
                    '开始日期': start_date.strftime('%Y-%m-%d'),
                    '结束日期': end_date.strftime('%Y-%m-%d')
                })

            return pd.DataFrame(stats_list)

        except Exception as e:
            logger.error(f"计算变量统计失败: {e}")
            return pd.DataFrame()

    @staticmethod
    def compute_processed_stats(
        prepared_data: pd.DataFrame,
        var_frequency_map: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """
        计算处理后数据的变量统计信息

        Args:
            prepared_data: 处理后的DataFrame
            var_frequency_map: 变量频率映射

        Returns:
            DataFrame: [变量名, 频率, 缺失值占比, 负值占比, 开始日期, 结束日期]
        """
        from dashboard.models.DFM.utils.text_utils import normalize_text

        if prepared_data is None or prepared_data.empty:
            return pd.DataFrame()

        var_frequency_map = var_frequency_map or {}
        theoretical_count = len(prepared_data)
        stats_list = []

        for col in prepared_data.columns:
            series = prepared_data[col]
            col_normalized = normalize_text(col)
            original_freq = var_frequency_map.get(col_normalized, '')
            freq_display = original_freq if original_freq else '-'

            valid_mask = series.notna() & (series != 0)
            valid_count = valid_mask.sum()

            if theoretical_count > 0:
                nan_ratio = (theoretical_count - valid_count) / theoretical_count * 100
            else:
                nan_ratio = 100.0

            if valid_count > 0:
                valid_series = series[valid_mask]
                neg_count = (valid_series < 0).sum()
                neg_ratio = neg_count / valid_count * 100
                valid_indices = valid_series.index
                start_date = valid_indices.min().strftime('%Y-%m-%d')
                end_date = valid_indices.max().strftime('%Y-%m-%d')
            else:
                neg_ratio = 0
                start_date = '-'
                end_date = '-'

            stats_list.append({
                '变量名': col,
                '频率': freq_display,
                '缺失值占比': f'{nan_ratio:.1f}%',
                '负值占比': f'{neg_ratio:.1f}%',
                '开始日期': start_date,
                '结束日期': end_date
            })

        return pd.DataFrame(stats_list)


__all__ = ['StatsService', 'FREQ_DAYS_MAP']
