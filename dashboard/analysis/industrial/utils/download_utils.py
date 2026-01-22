"""
统一的Excel下载工具
Unified Excel Download Utility

目标：消除6处重复的Excel下载逻辑（约90行）
遵循DRY原则：统一Excel文件创建和下载按钮逻辑
"""

import pandas as pd
import streamlit as st
from typing import Optional, Dict, Tuple, List
import io
import logging

logger = logging.getLogger(__name__)


def create_excel_file(
    data: pd.DataFrame,
    sheet_name: str = "数据",
    additional_sheets: Optional[Dict[str, pd.DataFrame]] = None,
    add_notes: bool = False,
    notes_sheet_name: str = "注释说明",
    notes_content: Optional[list] = None
) -> bytes:
    """
    创建Excel文件（返回bytes）

    Args:
        data: 主数据DataFrame
        sheet_name: 主数据表名
        additional_sheets: 额外的sheet字典 {sheet名: DataFrame}
        add_notes: 是否添加注释说明sheet
        notes_sheet_name: 注释说明sheet名称
        notes_content: 注释内容列表（字符串列表，每个元素是一行注释）

    Returns:
        Excel文件的字节内容
    """
    try:
        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # 写入主数据（保留索引）
            data.to_excel(writer, sheet_name=sheet_name, index=True)

            # 写入额外的sheet
            if additional_sheets:
                for name, df in additional_sheets.items():
                    if df is not None and not df.empty:
                        df.to_excel(writer, sheet_name=name, index=False)

            # 添加注释说明sheet
            if add_notes and notes_content:
                _add_notes_sheet(writer, notes_sheet_name, notes_content)

        return excel_buffer.getvalue()

    except Exception as e:
        logger.error(f"创建Excel文件时出错: {e}")
        return None


def _add_notes_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    notes_content: list
) -> None:
    """
    添加注释说明sheet

    Args:
        writer: ExcelWriter对象
        sheet_name: sheet名称
        notes_content: 注释内容列表
    """
    try:
        # 创建空的DataFrame用于占位
        notes_df = pd.DataFrame()
        notes_df.to_excel(writer, sheet_name=sheet_name, index=False)

        # 获取worksheet对象
        worksheet = writer.sheets[sheet_name]

        # 逐行写入注释
        for i, note in enumerate(notes_content, start=1):
            worksheet.cell(row=i, column=1, value=note)

    except Exception as e:
        logger.warning(f"添加注释sheet时出错: {e}")


def create_excel_download_button(
    st_obj,
    data: pd.DataFrame,
    file_name: str,
    sheet_name: str = "数据",
    button_label: str = "下载数据",
    button_key: Optional[str] = None,
    additional_sheets: Optional[Dict[str, pd.DataFrame]] = None,
    add_notes: bool = False,
    notes_content: Optional[list] = None,
    column_ratio: tuple = (1, 3),
    type: str = "primary"
) -> None:
    """
    创建Excel下载按钮

    这个函数统一了以下重复代码：
    - macro_operations.py 中的3处下载逻辑（约45行）
    - enterprise_operations.py 中的3处下载逻辑（约45行）

    Args:
        st_obj: Streamlit对象
        data: 要下载的数据DataFrame
        file_name: 文件名（不含扩展名）
        sheet_name: 主数据表名
        button_label: 按钮文字
        button_key: 按钮key（唯一标识）
        additional_sheets: 额外的sheet字典
        add_notes: 是否添加注释说明sheet
        notes_content: 注释内容列表
        column_ratio: 列宽比例（按钮列, 空白列）
        type: 按钮类型（primary/secondary）

    Returns:
        None
    """
    if data is None or data.empty:
        logger.debug("数据为空，不创建下载按钮")
        return

    # 创建Excel文件
    excel_data = create_excel_file(
        data=data,
        sheet_name=sheet_name,
        additional_sheets=additional_sheets,
        add_notes=add_notes,
        notes_content=notes_content
    )

    if excel_data is None:
        st_obj.warning("无法创建下载文件")
        return

    # 创建下载按钮（放在左侧列）
    col_download, col_spacer = st_obj.columns(column_ratio)

    with col_download:
        st_obj.download_button(
            label=button_label,
            data=excel_data,
            file_name=f"{file_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=button_key or f"download_{file_name}",
            type=type
        )


def create_download_with_annotation(
    st_obj,
    data: pd.DataFrame,
    file_name: str,
    annotation_data: Optional[pd.DataFrame],
    sheet_name: str = "数据",
    annotation_sheet_name: str = "注释说明",
    button_label: str = "下载数据",
    button_key: Optional[str] = None,
    additional_notes: Optional[list] = None,
    type = "primary"
) -> None:
    """
    创建带注释的Excel下载

    专门用于包含分组信息和权重的下载（如出口依赖分组、上中下游分组）

    Args:
        st_obj: Streamlit对象
        data: 主数据DataFrame
        file_name: 文件名
        annotation_data: 注释数据DataFrame（包含分组、指标名称、权重等）
        sheet_name: 主数据表名
        annotation_sheet_name: 注释表名
        button_label: 按钮文字
        button_key: 按钮key
        additional_notes: 额外的说明文字列表
        type: 按钮类型（primary/secondary）

    Returns:
        None
    """
    additional_sheets = {}

    # 添加注释数据
    if annotation_data is not None and not annotation_data.empty:
        additional_sheets[annotation_sheet_name] = annotation_data

    # 准备注释内容
    notes_content = []
    if additional_notes:
        notes_content.extend(additional_notes)

    # 如果有注释数据，添加标准说明
    if annotation_data is not None and not annotation_data.empty:
        notes_content.extend([
            "",  # 空行分隔
            "注：权重按年份动态选择",
            "2012-2017年使用权重_2012，2018-2019年使用权重_2018，2020年及以后使用权重_2020",
            "权重根据对应年份投入产出表各行业增加值占比计算"
        ])

    # 创建下载按钮
    create_excel_download_button(
        st_obj=st_obj,
        data=data,
        file_name=file_name,
        sheet_name=sheet_name,
        button_label=button_label,
        button_key=button_key,
        additional_sheets=additional_sheets,
        add_notes=bool(notes_content),
        notes_content=notes_content if notes_content else None,
        type=type
    )


def create_grouping_mappings(df_weights: pd.DataFrame) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    从权重数据创建分组映射

    此函数用于数据下载功能的注释生成，从权重数据中提取出口依赖和上中下游分组。

    Args:
        df_weights: 权重数据DataFrame，需包含'指标名称'、'出口依赖'、'上中下游'列

    Returns:
        (export_groups, stream_groups): 两个分组字典
            - export_groups: 出口依赖分组 {分组名: [指标列表]}
            - stream_groups: 上中下游分组 {分组名: [指标列表]}
    """
    export_groups = {}
    stream_groups = {}

    if not df_weights.empty and '出口依赖' in df_weights.columns and '上中下游' in df_weights.columns:
        # Group by export dependency
        for export_type in df_weights['出口依赖'].unique():
            if pd.notna(export_type):
                group_data = df_weights[df_weights['出口依赖'] == export_type]
                indicators = []
                for _, row in group_data.iterrows():
                    if pd.notna(row['指标名称']):
                        indicators.append(row['指标名称'])
                if indicators:
                    export_groups[export_type] = indicators

        # Group by upstream/downstream
        for stream_type in df_weights['上中下游'].unique():
            if pd.notna(stream_type):
                group_data = df_weights[df_weights['上中下游'] == stream_type]
                indicators = []
                for _, row in group_data.iterrows():
                    if pd.notna(row['指标名称']):
                        indicators.append(row['指标名称'])
                if indicators:
                    stream_groups[stream_type] = indicators

    return export_groups, stream_groups


def prepare_grouping_annotation_data(
    df_weights: pd.DataFrame,
    groups: Dict[str, list],
    group_type: str
) -> Optional[pd.DataFrame]:
    """
    准备分组注释数据

    用于创建包含分组、指标名称、权重的注释表

    Args:
        df_weights: 权重数据DataFrame
        groups: 分组字典 {分组名: [指标列表]}
        group_type: 分组类型（用于列名，如 "出口依赖" 或 "上中下游"）

    Returns:
        注释数据DataFrame，包含列：分组、指标名称、权重_2012、权重_2018、权重_2020
    """
    try:
        if not groups:
            return None

        # 创建权重映射
        weights_mapping = {}
        for _, row in df_weights.iterrows():
            indicator_name = row['指标名称']
            if pd.notna(indicator_name):
                weights_mapping[indicator_name] = row

        # 构建注释数据
        annotation_records = []

        for group_name, indicators in groups.items():
            for indicator in indicators:
                if indicator in weights_mapping:
                    weights_row = weights_mapping[indicator]

                    record = {
                        "分组": group_name,
                        "指标名称": indicator,
                        "权重_2012": f"{weights_row.get('权重_2012', 0.0):.4f}",
                        "权重_2018": f"{weights_row.get('权重_2018', 0.0):.4f}",
                        "权重_2020": f"{weights_row.get('权重_2020', 0.0):.4f}"
                    }

                    annotation_records.append(record)

        if annotation_records:
            return pd.DataFrame(annotation_records)
        else:
            return None

    except Exception as e:
        logger.error(f"准备分组注释数据时出错: {e}")
        return None
