"""工业监测的工作簿和内部权重数据访问。"""
import logging
from typing import Optional
import pandas as pd
from htfa.preview.data.economic_workbook import EconomicWorkbookReader
logger = logging.getLogger(__name__)
_WORKBOOK_READER = EconomicWorkbookReader("industrial_monitoring", "monitoring.industrial")

def read_tables(file_input):
    """按经济工作簿协议读取表格。"""
    return _WORKBOOK_READER.read_tables(file_input)

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
        from htfa.monitoring.industrial.contracts.constants import INTERNAL_WEIGHTS_FILE_PATH
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
