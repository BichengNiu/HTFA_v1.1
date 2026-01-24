"""
数据清理模块

负责数据清理相关的功能，包括：
- 重复列处理
- 零值处理
- 数据验证
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


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
