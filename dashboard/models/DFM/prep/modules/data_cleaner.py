"""
数据清理模块

负责数据清理相关的功能，包括：
- 重复列处理
- 连续NaN值处理
- 零值处理
- 数据验证
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter

from dashboard.models.DFM.prep.utils.date_utils import filter_by_date_range


class DataCleaner:
    """数据清理器类"""
    
    def __init__(self):
        self.removed_variables_log = []
    
    def remove_duplicate_columns(self, df: pd.DataFrame, log_prefix: str = "") -> pd.DataFrame:
        """
        移除重复的列
        
        Args:
            df: 输入DataFrame
            log_prefix: 日志前缀
            
        Returns:
            pd.DataFrame: 移除重复列后的DataFrame
        """
        if df.empty:
            return df
            
        original_col_count = len(df.columns)
        duplicate_mask = df.columns.duplicated(keep='first')
        
        if duplicate_mask.any():
            removed_count = duplicate_mask.sum()
            removed_cols = df.columns[duplicate_mask].tolist()
            
            # 高效去除重复列
            df_cleaned = df.iloc[:, ~duplicate_mask]
            
            # 记录移除的列
            for col in removed_cols:
                self.removed_variables_log.append({
                    'Variable': col,
                    'Reason': f'{log_prefix}duplicate_column'
                })
            
            logger.info("%s移除重复列: %d → %d (减少了 %d 列)", log_prefix, original_col_count, len(df_cleaned.columns), removed_count)
            return df_cleaned
        else:
            logger.info("%s未发现重复列", log_prefix)
            return df
    
    def handle_consecutive_nans(
        self,
        df: pd.DataFrame,
        threshold: int,
        log_prefix: str = "",
        data_start_date: Optional[str] = None,
        data_end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        处理连续NaN值超过阈值的列

        Args:
            df: 输入DataFrame
            threshold: 连续NaN的阈值
            log_prefix: 日志前缀
            data_start_date: 用户选择的数据开始日期（可选）
            data_end_date: 用户选择的数据结束日期（可选）

        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        if df.empty or threshold is None or threshold <= 0:
            return df

        # 检查并处理重复列名
        if df.columns.duplicated().any():
            logger.warning("%s检测到重复列名，正在去重...", log_prefix)
            df = df.loc[:, ~df.columns.duplicated(keep='first')]
            logger.info("%s去重后形状: %s", log_prefix, df.shape)

        # 应用时间范围筛选（如果指定）
        if data_start_date or data_end_date:
            df_filtered = self._apply_time_range_filter(df, data_start_date, data_end_date)
            if df_filtered.empty:
                logger.warning("%s时间范围筛选后数据为空", log_prefix)
                return df
            logger.info("%s基于用户选择时间范围检查连续缺失值 (阈值 >= %d)...", log_prefix, threshold)
            logger.info("%s时间范围: %s 到 %s", log_prefix, data_start_date, data_end_date)
            logger.info("%s筛选后数据形状: %s (原始: %s)", log_prefix, df_filtered.shape, df.shape)
        else:
            df_filtered = df
            logger.info("%s开始检查连续缺失值 (阈值 >= %d)...", log_prefix, threshold)

        # 确保筛选后没有重复列名
        if df_filtered.columns.duplicated().any():
            logger.warning("%s筛选后发现重复列名，正在去重...", log_prefix)
            df_filtered = df_filtered.loc[:, ~df_filtered.columns.duplicated(keep='first')]
            df = df.loc[:, ~df.columns.duplicated(keep='first')]

        cols_to_remove = []

        for col in df_filtered.columns:
            series = df_filtered[col]
            max_consecutive_nan, nan_start_date, nan_end_date = self._find_max_consecutive_nan_period(series)

            if max_consecutive_nan is None:
                max_consecutive_nan = 0

            if max_consecutive_nan >= threshold:
                cols_to_remove.append(col)

                # 计算数据质量统计
                total_points = len(series)
                missing_points = series.isnull().sum()
                missing_ratio = missing_points / total_points * 100 if total_points > 0 else 0

                # 记录详细信息
                if nan_start_date is not None and nan_end_date is not None:
                    nan_period_str = f"{nan_start_date} to {nan_end_date}"
                    logger.info("%s标记移除变量: '%s' (最大连续NaN: %d >= %d, 缺失时间段: %s, 缺失率: %.1f%%)",
                                log_prefix, col, max_consecutive_nan, threshold, nan_period_str, missing_ratio)
                else:
                    nan_period_str = "未知"
                    logger.info("%s标记移除变量: '%s' (最大连续 NaN: %d >= %d, 缺失率: %.1f%%)",
                                log_prefix, col, max_consecutive_nan, threshold, missing_ratio)

                self.removed_variables_log.append({
                    'Variable': col,
                    'Reason': f'{log_prefix}consecutive_nan',
                    'Details': {
                        'time_range': f"{data_start_date} to {data_end_date}" if data_start_date or data_end_date else "全部数据",
                        'max_consecutive_nan': max_consecutive_nan,
                        'nan_start_date': str(nan_start_date) if nan_start_date else None,
                        'nan_end_date': str(nan_end_date) if nan_end_date else None,
                        'nan_period': nan_period_str,
                        'threshold': threshold,
                        'total_points': total_points,
                        'missing_points': missing_points,
                        'missing_ratio': missing_ratio
                    }
                })

        if cols_to_remove:
            logger.info("%s正在移除 %d 个连续缺失值超标的变量...", log_prefix, len(cols_to_remove))
            df_cleaned = df.drop(columns=cols_to_remove)
            logger.info("%s移除后 Shape: %s", log_prefix, df_cleaned.shape)
            return df_cleaned
        else:
            logger.info("%s所有变量的连续缺失值均低于阈值。", log_prefix)
            return df

    def _apply_time_range_filter(
        self,
        df: pd.DataFrame,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> pd.DataFrame:
        """应用时间范围筛选"""
        return filter_by_date_range(df, start_date, end_date)

    def _calculate_max_consecutive_nans(self, series: pd.Series) -> int:
        """计算最大连续NaN数量"""
        if series.empty:
            return 0

        # 找到第一个有效值
        first_valid_idx = series.first_valid_index()
        if first_valid_idx is None:
            return len(series)  # 全为NaN

        # 从第一个有效值开始分析
        series_after_first_valid = series.loc[first_valid_idx:]
        is_na = series_after_first_valid.isna()

        if not is_na.any():
            return 0  # 没有NaN

        # 计算连续NaN块
        na_blocks = is_na.ne(is_na.shift()).cumsum()[is_na]
        max_consecutive_nan = 0

        if not na_blocks.empty:
            block_counts = na_blocks.value_counts()
            if not block_counts.empty:
                max_consecutive_nan = block_counts.max()

        return max_consecutive_nan

    def _find_max_consecutive_nan_period(self, series: pd.Series) -> tuple:
        """
        找到最大连续NaN块的起止日期

        Returns:
            tuple: (max_consecutive_nan, start_date, end_date)
        """
        if series.empty:
            return 0, None, None

        # 找到第一个有效值
        first_valid_idx = series.first_valid_index()
        if first_valid_idx is None:
            # 全为NaN
            if len(series) > 0:
                return len(series), series.index[0], series.index[-1]
            return 0, None, None

        # 从第一个有效值开始分析
        series_after_first_valid = series.loc[first_valid_idx:]
        is_na = series_after_first_valid.isna()

        if not is_na.any():
            return 0, None, None  # 没有NaN

        # 计算连续NaN块
        na_blocks = is_na.ne(is_na.shift()).cumsum()[is_na]

        if na_blocks.empty:
            return 0, None, None

        # 找到最大连续NaN块的块ID
        block_counts = na_blocks.value_counts()
        if block_counts.empty:
            return 0, None, None

        max_consecutive_nan = block_counts.max()
        if max_consecutive_nan is None or pd.isna(max_consecutive_nan):
            return 0, None, None
        if not isinstance(max_consecutive_nan, (int, float, np.integer, np.floating)):
            raise TypeError(f"max_consecutive_nan类型错误: {type(max_consecutive_nan)}")
        max_consecutive_nan = int(max_consecutive_nan)
        max_block_id = block_counts.idxmax()

        # 找到该块的所有索引
        max_block_indices = na_blocks[na_blocks == max_block_id].index

        if len(max_block_indices) > 0:
            start_date = max_block_indices[0]
            end_date = max_block_indices[-1]
            return max_consecutive_nan, start_date, end_date
        else:
            return max_consecutive_nan, None, None

    def clean_zero_values(self, df: pd.DataFrame, log_prefix: str = "") -> pd.DataFrame:
        """
        将0值替换为NaN
        
        Args:
            df: 输入DataFrame
            log_prefix: 日志前缀
            
        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        if df.empty:
            return df
            
        df_cleaned = df.replace(0, np.nan)
        logger.info("%s将 0 值替换为 NaN。", log_prefix)
        return df_cleaned
    
    def remove_unnamed_columns(self, df: pd.DataFrame, log_prefix: str = "") -> pd.DataFrame:
        """
        移除Unnamed列
        
        Args:
            df: 输入DataFrame
            log_prefix: 日志前缀
            
        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        if df.empty:
            return df
            
        unnamed_cols = [col for col in df.columns if isinstance(col, str) and col.startswith('Unnamed:')]

        if unnamed_cols:
            logger.info("%s发现并移除 Unnamed 列: %s", log_prefix, unnamed_cols)
            df_cleaned = df.drop(columns=unnamed_cols)
            
            # 记录移除的列
            for col in unnamed_cols:
                self.removed_variables_log.append({
                    'Variable': col,
                    'Reason': f'{log_prefix}unnamed_column'
                })
            
            return df_cleaned
        
        return df
    
    def remove_all_nan_columns(self, df: pd.DataFrame, log_prefix: str = "") -> pd.DataFrame:
        """
        移除全为NaN的列

        Args:
            df: 输入DataFrame
            log_prefix: 日志前缀

        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        if df.empty:
            return df

        cols_before = set(df.columns)
        df_cleaned = df.dropna(axis=1, how='all')
        removed_cols = cols_before - set(df_cleaned.columns)

        if removed_cols:
            logger.info("%s移除了 %d 个全 NaN 列: %s%s", log_prefix, len(removed_cols), list(removed_cols)[:10], '...' if len(removed_cols)>10 else '')

            # 记录移除的列
            for col in removed_cols:
                self.removed_variables_log.append({
                    'Variable': col,
                    'Reason': f'{log_prefix}all_nan'
                })

        return df_cleaned
    
    def remove_all_nan_rows(self, df: pd.DataFrame, log_prefix: str = "") -> pd.DataFrame:
        """
        移除全为NaN的行
        
        Args:
            df: 输入DataFrame
            log_prefix: 日志前缀
            
        Returns:
            pd.DataFrame: 处理后的DataFrame
        """
        if df.empty:
            return df
            
        original_rows = df.shape[0]
        df_cleaned = df.dropna(how='all')

        if df_cleaned.shape[0] < original_rows:
            logger.info("%s移除全NaN行: %d → %d 行", log_prefix, original_rows, df_cleaned.shape[0])
        
        return df_cleaned
    
    def get_removed_variables_log(self) -> List[Dict]:
        """获取移除变量的日志"""
        return self.removed_variables_log.copy()
    
    def clear_log(self):
        """清空日志"""
        self.removed_variables_log.clear()

# 便利函数
def clean_dataframe(
    df: pd.DataFrame,
    remove_duplicates: bool = True,
    remove_zeros: bool = True,
    remove_unnamed: bool = True,
    remove_all_nan_cols: bool = True,
    remove_all_nan_rows: bool = True,
    consecutive_nan_threshold: Optional[int] = None,
    data_start_date: Optional[str] = None,
    data_end_date: Optional[str] = None,
    log_prefix: str = ""
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    一站式数据清理函数

    Args:
        df: 输入DataFrame
        remove_duplicates: 是否移除重复列
        remove_zeros: 是否将0值替换为NaN
        remove_unnamed: 是否移除Unnamed列
        remove_all_nan_cols: 是否移除全NaN列
        remove_all_nan_rows: 是否移除全NaN行
        consecutive_nan_threshold: 连续NaN阈值，None表示不检查
        data_start_date: 用户选择的数据开始日期（可选）
        data_end_date: 用户选择的数据结束日期（可选）
        log_prefix: 日志前缀

    Returns:
        Tuple[pd.DataFrame, List[Dict]]: (清理后的DataFrame, 移除变量日志)
    """
    cleaner = DataCleaner()
    result_df = df.copy()
    
    if remove_zeros:
        result_df = cleaner.clean_zero_values(result_df, log_prefix)
    
    if remove_unnamed:
        result_df = cleaner.remove_unnamed_columns(result_df, log_prefix)
    
    if remove_duplicates:
        result_df = cleaner.remove_duplicate_columns(result_df, log_prefix)
    
    if consecutive_nan_threshold is not None:
        result_df = cleaner.handle_consecutive_nans(
            result_df, consecutive_nan_threshold, log_prefix, data_start_date, data_end_date
        )
    
    if remove_all_nan_cols:
        result_df = cleaner.remove_all_nan_columns(result_df, log_prefix)
    
    if remove_all_nan_rows:
        result_df = cleaner.remove_all_nan_rows(result_df, log_prefix)
    
    return result_df, cleaner.get_removed_variables_log()

# 导出的类和函数
__all__ = [
    'DataCleaner',
    'clean_dataframe'
]
