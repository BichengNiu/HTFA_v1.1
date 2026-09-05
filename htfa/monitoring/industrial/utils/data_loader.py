"""
Data Loader Utility
数据加载工具 - 统一的Excel数据加载函数

所有 Excel sheet 读取共享同一套清洗流程：
1. 文件输入归一化（上传对象 / 路径）
2. read_excel（第一行列名、第一列时间索引）
3. 删除全空行列、清理 NaT/重复索引
4. 日期索引标准化为月初并再次去重
"""

import pandas as pd
from typing import Optional
import logging
from io import BytesIO

import numpy as np

from htfa.data.economic_workbook import EconomicWorkbookReader
from htfa.monitoring.industrial.constants import (
    SHEET_NAME_ENTERPRISE_PROFIT,
    SHEET_NAME_MACRO_DATA,
    SHEET_NAME_OVERALL_INDUSTRIAL,
)

logger = logging.getLogger(__name__)
_WORKBOOK_READER = EconomicWorkbookReader(
    "industrial_monitoring",
    "monitoring.industrial",
)

def clean_dataframe_index(df: pd.DataFrame, data_name: str = "数据") -> pd.DataFrame:
    """
    清理DataFrame索引：删除NaT值和重复索引

    Args:
        df: 待清理的DataFrame
        data_name: 数据名称（用于日志）

    Returns:
        清理后的DataFrame
    """
    # 删除索引为NaT的行（无法解析的日期）
    if isinstance(df.index, pd.DatetimeIndex):
        nat_count = df.index.isna().sum()
        if nat_count > 0:
            logger.warning(f"{data_name}: 发现{nat_count}个无效日期(NaT)，将删除这些行")
            df = df[~df.index.isna()]
            logger.info(f"{data_name}: 删除无效日期后数据形状: {df.shape}")

    # 检查并处理重复索引（在删除NaT之后）
    if df.index.duplicated().any():
        dup_count = df.index.duplicated().sum()
        dup_dates = df.index[df.index.duplicated()].unique()
        logger.warning(f"{data_name}: 发现{dup_count}个重复日期索引: {dup_dates.tolist()}")
        logger.warning(f"{data_name}: 将保留第一次出现的数据，删除重复行")
        df = df[~df.index.duplicated(keep='first')]
        logger.info(f"{data_name}: 去重后数据形状: {df.shape}")

    return df


def _resolve_file_input(uploaded_file):
    """归一化文件输入：上传对象 -> BytesIO，路径对象 -> 路径字符串。"""
    if hasattr(uploaded_file, 'getvalue'):
        return BytesIO(uploaded_file.getvalue())
    if hasattr(uploaded_file, 'path'):
        return uploaded_file.path
    return uploaded_file


def _normalize_monthly_index(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """标准化日期索引为月初并去重（解决图表时间轴错位问题）。"""
    if not isinstance(df.index, pd.DatetimeIndex):
        return df

    df.index = pd.to_datetime(df.index.to_period('M').to_timestamp())
    logger.info("日期已标准化为月初格式")

    # 标准化后再次检查重复（标准化可能导致不同日期变成相同月份）
    if df.index.duplicated().any():
        dup_count = df.index.duplicated().sum()
        logger.warning(f"{sheet_name}: 标准化后发现{dup_count}个重复月份，保留第一次出现的数据")
        df = df[~df.index.duplicated(keep='first')]
        logger.info(f"{sheet_name}: 最终数据形状: {df.shape}")

    return df


def _zero_to_nan(df: pd.DataFrame) -> pd.DataFrame:
    """将0值转换为NaN（新版本数据中0代表缺失值）。"""
    numeric_columns = df.select_dtypes(include=[np.number]).columns
    df[numeric_columns] = df[numeric_columns].replace(0, np.nan)
    logger.info("已将0值转换为NaN")
    return df


def _load_excel_sheet(uploaded_file, sheet_name: str) -> Optional[pd.DataFrame]:
    """读取并清洗 Excel 工作表；失败返回 None。

    统一格式：第一行是列名，第一列是时间列。
    """
    try:
        logger.info(f"读取{sheet_name}数据")

        tables = _WORKBOOK_READER.read_tables(_resolve_file_input(uploaded_file))
        if sheet_name not in tables:
            raise ValueError(f"工作簿缺少“{sheet_name}”sheet")
        df = tables[sheet_name]
        if df.shape[1] == 0:
            return None
        df = df.set_index(df.columns[0])
        df.index = pd.to_datetime(df.index, errors="coerce")

        df = df.dropna(how='all').dropna(axis=1, how='all')
        df = clean_dataframe_index(df, sheet_name)
        df = _normalize_monthly_index(df, sheet_name)

        logger.info(f"{sheet_name}数据形状: {df.shape}")
        return df

    except Exception as e:
        logger.error(f"读取{sheet_name}数据失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None


def load_macro_data(uploaded_file, sheet_name: str = SHEET_NAME_MACRO_DATA) -> Optional[pd.DataFrame]:
    """
    使用统一格式加载宏观工业数据：第一行是列名，第一列是时间列

    数据清洗：将0值转换为NaN（新版本数据中0代表缺失值）
    """
    df = _load_excel_sheet(uploaded_file, sheet_name)
    if df is None:
        return None
    return _zero_to_nan(df)


def read_weights_data() -> Optional[pd.DataFrame]:
    """
    加载权重数据：从内部CSV文件读取行业属性和权重

    内部数据文件：data/工业分行业属性及权重.csv
    包含列：指标名称、门类、出口依赖、上中下游、权重_2012、权重_2018、
           权重_2020、权重_2022、权重_2023、权重_2024、权重_2025

    Returns:
        DataFrame: 包含权重数据；如果失败返回None
    """
    try:
        from htfa.monitoring.industrial.constants import INTERNAL_WEIGHTS_FILE_PATH
        from pathlib import Path

        # 获取项目根目录（data_loader.py 位于 htfa/monitoring/industrial/utils/）
        # utils -> industrial -> monitoring -> 项目根目录
        project_root = Path(__file__).parent.parent.parent.parent.parent
        weights_file = project_root / INTERNAL_WEIGHTS_FILE_PATH

        logger.info(f"从内部文件读取权重数据: {weights_file}")

        if not weights_file.exists():
            logger.error(f"内部权重文件不存在: {weights_file}")
            return None

        # 读取CSV文件（使用utf-8-sig处理BOM）
        df_weights = pd.read_csv(weights_file, encoding='utf-8-sig')

        # 清理数据：删除全为空的行和列
        df_weights = df_weights.dropna(how='all').dropna(axis=1, how='all')

        logger.info(f"权重数据形状: {df_weights.shape}")
        logger.info(f"权重数据列名: {list(df_weights.columns)}")

        # 验证必要的列是否存在
        if '指标名称' in df_weights.columns:
            valid_indicators = df_weights['指标名称'].notna().sum()
            logger.info(f"找到 {valid_indicators} 个有效指标")
        else:
            logger.error("未找到'指标名称'列")
            return None

        return df_weights

    except Exception as e:
        logger.error(f"读取内部权重数据失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return None


def load_overall_industrial_data(uploaded_file, sheet_name: str = SHEET_NAME_OVERALL_INDUSTRIAL) -> Optional[pd.DataFrame]:
    """
    使用统一格式加载总体工业增加值数据：第一行是列名，第一列是时间列

    特殊处理：
    1. 对总体工业增加值当月同比的1月和2月数据设为NaN
    2. 将0值转换为NaN（新版本数据中0代表缺失值）
    """
    df = _load_excel_sheet(uploaded_file, sheet_name)
    if df is None:
        return None

    df = _zero_to_nan(df)

    # 特殊处理：对总体工业增加值当月同比的1月和2月数据设为NaN
    from htfa.monitoring.industrial.constants import TOTAL_INDUSTRIAL_GROWTH_COLUMN

    if TOTAL_INDUSTRIAL_GROWTH_COLUMN in df.columns and hasattr(df.index, 'month'):
        jan_feb_mask = (df.index.month == 1) | (df.index.month == 2)
        df.loc[jan_feb_mask, TOTAL_INDUSTRIAL_GROWTH_COLUMN] = np.nan
        logger.info(f"已将{TOTAL_INDUSTRIAL_GROWTH_COLUMN}的1月和2月数据设为NaN")

    return df


def load_enterprise_profit_data(uploaded_file, sheet_name: str = SHEET_NAME_ENTERPRISE_PROFIT) -> Optional[pd.DataFrame]:
    """使用统一格式读取工业企业利润数据：第一行是列名，第一列是时间列"""
    return _load_excel_sheet(uploaded_file, sheet_name)


def load_industry_profit_data(uploaded_file, sheet_name: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    加载分行业工业企业利润数据：第一行是列名，第一列是时间列

    列名格式：规模以上工业企业:利润总额:行业名称:累计值
    示例：规模以上工业企业:利润总额:专用设备制造业:累计值
    """
    from htfa.monitoring.industrial.constants import SHEET_NAME_INDUSTRY_PROFIT

    if sheet_name is None:
        sheet_name = SHEET_NAME_INDUSTRY_PROFIT

    return _load_excel_sheet(uploaded_file, sheet_name)


def load_enterprise_operations_data(uploaded_file, sheet_name: str = '工业企业经营') -> Optional[pd.DataFrame]:
    """
    使用统一格式读取工业企业经营数据：第一行是列名，第一列是时间列

    数据包含：
    - 中国:利润总额:规模以上工业企业:累计值
    - 中国:营业收入:规模以上工业企业:累计值
    - 中国:资产合计:规模以上工业企业
    - 中国:所有者权益合计:规模以上工业企业
    """
    return _load_excel_sheet(uploaded_file, sheet_name)
