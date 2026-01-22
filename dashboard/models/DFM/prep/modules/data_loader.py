"""
数据加载模块

负责从Excel文件中加载不同类型的数据：
- 目标变量数据
- 日度/周度预测变量数据
- 月度预测变量数据
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import defaultdict

from dashboard.models.DFM.prep.modules.format_detection import detect_sheet_format, parse_sheet_info
from dashboard.models.DFM.prep.modules.data_cleaner import DataCleaner
from dashboard.models.DFM.prep.modules.config_constants import (
    MIN_VALID_DATE_RATIO, MIN_TARGET_VALID_RATIO, MIN_PREDICTOR_VALID_RATIO
)
from dashboard.models.DFM.utils.text_utils import normalize_text

class DataLoader:
    """数据加载器类"""

    def __init__(
        self,
        reference_industry_map: Optional[Dict[str, str]] = None,
        reference_frequency_map: Optional[Dict[str, str]] = None
    ):
        """
        初始化数据加载器

        Args:
            reference_industry_map: 从指标字典加载的行业映射（可选，用于校验）
            reference_frequency_map: 从指标字典加载的频率映射（用于数据分类）
        """
        self.cleaner = DataCleaner()
        self.var_industry_map = {}  # 从sheet名称推断的行业映射（保留用于校验）
        self.reference_industry_map = reference_industry_map or {}
        self.reference_frequency_map = reference_frequency_map or {}
        self.raw_columns_across_all_sheets = set()

    def _load_indexed_sheet(
        self,
        excel_file,
        sheet_name: str,
        freq_type: str,
        industry_name: str
    ) -> Optional[pd.DataFrame]:
        """
        通用的索引式sheet加载方法（日度/周度/旬度共用）

        Args:
            excel_file: Excel文件对象
            sheet_name: 表格名称
            freq_type: 频率类型（用于日志）
            industry_name: 行业名称

        Returns:
            Optional[pd.DataFrame]: 加载的数据，如果失败返回None
        """
        logger.info("检测到预测变量 Sheet ('%s', 行业: '%s')...", freq_type, industry_name)
        logger.info("[使用统一格式] 第一行为列名，第一列为时间列")

        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=0, index_col=0, parse_dates=True)
        df = self.cleaner.remove_unnamed_columns(df, f"[{freq_type}] ")

        logger.info("尝试将 '%s' 的索引转换为日期时间...", sheet_name)
        original_index_len = len(df.index)
        df.index = pd.to_datetime(df.index, errors='coerce')

        if df.empty:
            return None

        df = df.loc[df.index.notna()]
        filtered_index_len = len(df.index)

        if filtered_index_len < original_index_len:
            logger.warning("在 '%s' 中移除了 %d 行，因为它们的索引无法解析为有效日期。", sheet_name, original_index_len - filtered_index_len)

        if df.empty:
            return None

        df = df.dropna(axis=1, how='all')
        if df.empty:
            return None

        df_numeric = df.apply(pd.to_numeric, errors='coerce')
        if df_numeric.empty or df_numeric.isnull().all().all():
            raise ValueError(f"Sheet '{sheet_name}' 转换后数据为空或全为NaN")

        logger.info("Sheet '%s' (%s, %s) 加载完成。Shape: %s", sheet_name, industry_name, freq_type, df_numeric.shape)

        self._update_var_mappings(df_numeric.columns, industry_name)
        return df_numeric

    def _update_var_mappings(self, columns, industry_name: str):
        """更新变量映射"""
        for col in columns:
            norm_col = normalize_text(col)
            if norm_col:
                self.var_industry_map[norm_col] = industry_name
                self.raw_columns_across_all_sheets.add(norm_col)
    
    def load_target_sheet(
        self, 
        excel_file, 
        sheet_name: str,
        target_variable_name: str,
        industry_name: str = "Macro"
    ) -> Tuple[Optional[pd.Series], Optional[pd.Series], Optional[pd.DataFrame], Set[str]]:
        """
        加载目标表格数据
        
        Args:
            excel_file: Excel文件对象
            sheet_name: 表格名称
            target_variable_name: 目标变量名称
            industry_name: 行业名称
            
        Returns:
            Tuple: (发布日期, 目标变量值, 预测变量DataFrame, 目标表格列名集合)
        """
        logger.info("检测到目标 Sheet，行业: '%s'...", industry_name)

        # 删除try-except包装，让异常直接抛出
        # 使用统一格式读取数据
        logger.info("[目标Sheet读取] 使用统一格式，第一行为列名，第一列为时间列")

        df_raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=0)

        if df_raw.shape[1] < 2:
            raise ValueError(f"目标 Sheet '{sheet_name}' 列数 < 2，数据格式不正确")

        # 提取日期和目标变量
        date_col_name = df_raw.columns[0]
        actual_target_variable_name = df_raw.columns[1]
        target_sheet_cols = {actual_target_variable_name}

        logger.info("确认目标变量 (B列): '%s'", actual_target_variable_name)
        logger.info("解析发布日期 (A列: '%s')...", date_col_name)

        publication_dates = pd.to_datetime(df_raw[date_col_name], errors='coerce')
        valid_date_mask = publication_dates.notna()

        # 数据质量检查
        valid_date_ratio = valid_date_mask.sum() / len(df_raw)
        if valid_date_ratio < MIN_VALID_DATE_RATIO:
            raise ValueError(f"日期解析质量不合格：仅 {valid_date_ratio:.1%} 的日期有效（要求≥{MIN_VALID_DATE_RATIO:.0%}）")

        if not valid_date_mask.any():
            raise ValueError(f"无法从列 '{date_col_name}' 解析任何有效日期")

        publication_dates = publication_dates[valid_date_mask]

        # 提取目标变量值
        logger.info("提取目标变量原始值...")
        target_values = pd.to_numeric(df_raw.loc[valid_date_mask, actual_target_variable_name], errors='coerce')
        target_values.index = publication_dates

        # 检查目标变量转换质量
        target_valid_ratio = target_values.notna().sum() / len(target_values)
        if target_valid_ratio < MIN_TARGET_VALID_RATIO:
            raise ValueError(f"目标变量数值转换质量不合格：仅 {target_valid_ratio:.1%} 的值有效（要求≥{MIN_TARGET_VALID_RATIO:.0%}）")

        # 更新映射（同时记录sheet推断的行业用于后续校验）
        norm_target_name = normalize_text(actual_target_variable_name)
        self.var_industry_map[norm_target_name] = industry_name

        # 提取月度预测变量 (C列及以后)
        target_sheet_predictors = pd.DataFrame()
        if df_raw.shape[1] > 2:
            logger.info("提取目标 Sheet 的月度预测变量 (C列及以后)...")

            # 移除Unnamed列
            df_raw = self.cleaner.remove_unnamed_columns(df_raw, "[目标Sheet预测变量] ")

            # 重新验证列数（移除Unnamed列后可能变化）
            if df_raw.shape[1] <= 2:
                logger.info("移除Unnamed列后，目标 Sheet 仅含 A, B 列。")
                return publication_dates, target_values, target_sheet_predictors, target_sheet_cols

            temp_monthly_predictors = {}
            for col_idx in range(2, df_raw.shape[1]):
                col_name = df_raw.columns[col_idx]
                target_sheet_cols.add(col_name)

                # 清理值
                cleaned_series = df_raw[col_name].astype(str).str.replace('%', '', regex=False).str.replace(',', '', regex=False).str.strip()
                predictor_values = pd.to_numeric(cleaned_series, errors='coerce')

                # 检查预测变量转换质量
                if valid_date_mask.any():
                    pred_valid_ratio = predictor_values[valid_date_mask].notna().sum() / valid_date_mask.sum()
                    if pred_valid_ratio < MIN_PREDICTOR_VALID_RATIO:
                        logger.warning("变量 '%s' 数值转换质量较低 (%.1f%%)", col_name, pred_valid_ratio * 100)

                # 创建按发布日期索引的序列
                temp_monthly_predictors[col_name] = pd.Series(
                    predictor_values[valid_date_mask].values,
                    index=publication_dates
                )

                # 更新映射和跟踪
                norm_pred_col = normalize_text(col_name)
                if norm_pred_col:
                    self.var_industry_map[norm_pred_col] = industry_name
                    self.raw_columns_across_all_sheets.add(norm_pred_col)

            target_sheet_predictors = pd.DataFrame(temp_monthly_predictors).sort_index()
            target_sheet_predictors = target_sheet_predictors.dropna(axis=1, how='all')

            logger.info("提取了 %d 个有效的月度预测变量 (按发布日期索引)。", target_sheet_predictors.shape[1])
        else:
            logger.info("目标 Sheet 仅含 A, B 列。")

        return publication_dates, target_values, target_sheet_predictors, target_sheet_cols
    
    def load_daily_weekly_sheet(
        self,
        excel_file,
        sheet_name: str,
        freq_type: str,
        industry_name: str
    ) -> Optional[pd.DataFrame]:
        """
        加载日度/周度数据表格

        Args:
            excel_file: Excel文件对象
            sheet_name: 表格名称
            freq_type: 频率类型 ('daily' 或 'weekly')
            industry_name: 行业名称

        Returns:
            Optional[pd.DataFrame]: 加载的数据，如果失败返回None
        """
        return self._load_indexed_sheet(excel_file, sheet_name, freq_type, industry_name)

    def load_dekad_sheet(
        self,
        excel_file,
        sheet_name: str,
        industry_name: str
    ) -> Optional[pd.DataFrame]:
        """
        加载旬度数据表格（10日、20日、30日为旬日）

        Args:
            excel_file: Excel文件对象
            sheet_name: 表格名称
            industry_name: 行业名称

        Returns:
            Optional[pd.DataFrame]: 加载的数据，如果失败返回None
        """
        return self._load_indexed_sheet(excel_file, sheet_name, 'dekad', industry_name)

    def load_monthly_predictor_sheet(
        self,
        excel_file,
        sheet_name: str,
        industry_name: str
    ) -> Optional[pd.DataFrame]:
        """
        加载月度预测变量表格

        Args:
            excel_file: Excel文件对象
            sheet_name: 表格名称
            industry_name: 行业名称

        Returns:
            Optional[pd.DataFrame]: 加载的数据，如果失败返回None
        """
        logger.info("检测到非目标月度预测 Sheet，行业: '%s'...", industry_name)

        # 删除try-except包装，让异常直接抛出
        # 使用统一格式读取数据
        logger.info("[使用统一格式] 第一行为列名，第一列为时间列")

        df_raw_pred = pd.read_excel(excel_file, sheet_name=sheet_name, header=0)

        # 清理数据
        df_raw_pred = self.cleaner.remove_unnamed_columns(df_raw_pred, "[月度预测] ")

        if df_raw_pred.shape[1] < 2:
            raise ValueError(f"月度预测 Sheet '{sheet_name}' 列数 < 2，数据格式不正确")

        date_col_name_pred = df_raw_pred.columns[0]
        logger.info("解析发布日期 (A列: '%s')...", date_col_name_pred)

        publication_dates_predictor = pd.to_datetime(df_raw_pred[date_col_name_pred], errors='coerce')
        valid_date_mask_pred = publication_dates_predictor.notna()

        if not valid_date_mask_pred.any():
            raise ValueError(f"无法从列 '{date_col_name_pred}' 解析任何有效日期")

        publication_dates_predictor = publication_dates_predictor[valid_date_mask_pred]

        logger.info("提取月度预测变量 (B列及以后)...")
        temp_monthly_predictors_sheet = {}

        for col_idx_pred in range(1, df_raw_pred.shape[1]):  # 从B列开始
            col_name_pred = df_raw_pred.columns[col_idx_pred]

            # 清理值
            cleaned_series_pred = df_raw_pred[col_name_pred].astype(str).str.replace('%', '', regex=False).str.replace(',', '', regex=False).str.strip()
            predictor_values_pred = pd.to_numeric(cleaned_series_pred, errors='coerce')

            # 创建按发布日期索引的序列
            temp_monthly_predictors_sheet[col_name_pred] = pd.Series(
                predictor_values_pred[valid_date_mask_pred].values,
                index=publication_dates_predictor
            )

        df_monthly_pred_sheet = pd.DataFrame(temp_monthly_predictors_sheet).sort_index()
        df_monthly_pred_sheet = df_monthly_pred_sheet.dropna(axis=1, how='all')

        if not df_monthly_pred_sheet.empty:
            logger.info("提取了 %d 个有效的月度预测变量 (按发布日期索引)。", df_monthly_pred_sheet.shape[1])
            self._update_var_mappings(df_monthly_pred_sheet.columns, industry_name)
            return df_monthly_pred_sheet
        else:
            raise ValueError(f"Sheet '{sheet_name}' 未包含有效的月度预测变量数据")

    def get_var_industry_map(self) -> Dict[str, str]:
        """获取变量行业映射"""
        return self.var_industry_map.copy()

    def get_raw_columns_set(self) -> Set[str]:
        """获取所有加载的列名集合（标准化后）"""
        return self.raw_columns_across_all_sheets.copy()

    def get_removed_variables_log(self) -> List[Dict]:
        """获取移除变量的日志"""
        return self.cleaner.get_removed_variables_log()

# 导出的类
__all__ = [
    'DataLoader'
]
