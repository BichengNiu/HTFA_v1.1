# -*- coding: utf-8 -*-
"""
Preview模块UI组件
可复用的Streamlit UI组件
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple

from dashboard.preview.core.calculation_rules import (
    group_indicators_by_calculation,
    uses_difference_calculation,
)
from dashboard.preview.core.summary_export import build_summary_workbook
from dashboard.preview.shared.config import COLORS, UI_TEXT


def _get_industry_indicators(selected_industry, df, indicator_industry_map):
    """获取某行业的指标列表（辅助函数）

    Args:
        selected_industry: 选中的行业
        df: 数据DataFrame
        indicator_industry_map: 指标名称到行业的映射，来自指标字典

    Returns:
        List[str]: 指标列表
    """
    if selected_industry == UI_TEXT['all_option']:
        return list(df.columns)

    return [
        indicator for indicator in df.columns
        if indicator_industry_map.get(indicator) == selected_industry
    ]


def _get_available_types(indicators, indicator_type_map):
    """获取指标列表的可用类型（辅助函数）

    Args:
        indicators: 指标列表
        indicator_type_map: 指标类型映射

    Returns:
        List[str]: 排序后的类型列表
    """
    available_types = set()
    for indicator in indicators:
        indicator_type = indicator_type_map.get(indicator, "未分类")
        available_types.add(indicator_type)
    return sorted(available_types)


def _filter_by_type(indicators, selected_type, indicator_type_map):
    """根据类型筛选指标（辅助函数）

    Args:
        indicators: 指标列表
        selected_type: 选中的类型
        indicator_type_map: 指标类型映射

    Returns:
        List[str]: 筛选后的指标列表
    """
    if selected_type == UI_TEXT['all_option']:
        return indicators

    return [
        ind for ind in indicators
        if indicator_type_map.get(ind, "未分类") == selected_type
    ]


def create_filter_ui(
    st,
    industries: List[str],
    df: pd.DataFrame,
    indicator_type_map: Dict[str, str],
    indicator_industry_map: Dict[str, str],
    key_prefix: str
) -> Tuple[str, str, List[str], str]:
    """创建统一的行业和类型筛选UI

    Args:
        st: streamlit模块
        industries: 行业列表
        df: 数据DataFrame
        indicator_type_map: 指标类型映射
        indicator_industry_map: 指标名称到行业的映射，来自指标字典
        key_prefix: 组件key前缀

    Returns:
        Tuple[str, str, List[str], str]: (选中的行业, 选中的类型, 筛选后的指标列表, 显示名称)
    """
    ui_text = UI_TEXT
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**{ui_text['select_industry']}**")
        industry_options = [ui_text['all_option']] + industries
        selected_industry = st.selectbox(
            f"select_industry_{key_prefix}",
            industry_options,
            key=f"industry_select_{key_prefix}",
            label_visibility="collapsed"
        )

    with col2:
        # 根据选择的行业确定可用的类型（使用辅助函数）
        industry_indicators = _get_industry_indicators(
            selected_industry, df, indicator_industry_map
        )
        available_types = _get_available_types(industry_indicators, indicator_type_map)

        st.markdown(f"**{ui_text['select_type']}**")
        type_options = [ui_text['all_option']] + available_types
        selected_type = st.selectbox(
            f"select_type_{key_prefix}",
            type_options,
            key=f"type_select_{key_prefix}",
            label_visibility="collapsed"
        )

    # 根据行业和类型双重筛选指标（使用辅助函数）
    industry_indicators = _get_industry_indicators(
        selected_industry, df, indicator_industry_map
    )
    filtered_indicators = _filter_by_type(
        industry_indicators, selected_type, indicator_type_map
    )

    # 构建显示名称
    industry_display = selected_industry if selected_industry != ui_text['all_option'] else f"{ui_text['all_option']}行业"
    type_display = selected_type if selected_type != ui_text['all_option'] else f"{ui_text['all_option']}类型"
    display_name = f"{industry_display}-{type_display}"

    return selected_industry, selected_type, filtered_indicators, display_name


def display_summary_table(
    st,
    summary_table: pd.DataFrame,
    sort_column: str,
    highlight_columns: List[str],
    percentage_columns: List[str],
    download_prefix: str
) -> None:
    """显示带样式的摘要表并提供下载功能

    Args:
        st: streamlit模块
        summary_table: 摘要表DataFrame
        sort_column: 排序列名
        highlight_columns: 需要高亮的列
        percentage_columns: 百分比格式列
        download_prefix: 下载文件名前缀
    """
    if summary_table.empty:
        st.info("摘要表为空或无法计算。")
        return

    # 排序
    summary_sorted = _sort_summary_table(summary_table, sort_column, st)

    # 应用样式
    try:
        # 如果有单位和类型列，需要进行条件格式化
        has_metadata = ('单位' in summary_sorted.columns and '类型' in summary_sorted.columns)

        if has_metadata:
            # 创建一个完全字符串化的副本用于显示（避免Arrow序列化问题）
            display_df = summary_sorted.copy()

            # 先获取所有数值列的列表
            numeric_cols = list(display_df.select_dtypes(include=np.number).columns)

            # 遍历每一行，根据单位和类型格式化数值列
            for idx in display_df.index:
                unit = display_df.loc[idx, '单位']
                indicator_type = display_df.loc[idx, '类型']
                use_difference = uses_difference_calculation(unit, indicator_type)

                # 格式化每个数值列（使用之前保存的列表）
                for col in numeric_cols:
                    val = summary_sorted.loc[idx, col]  # 从原始数据读取，避免已转换的字符串
                    if pd.notna(val):
                        if col in percentage_columns:
                            # 环比同比列
                            if use_difference:
                                # 差值：显示为百分点
                                display_df.at[idx, col] = f"{val:.2f}%"
                            else:
                                # 比率：显示为百分比
                                display_df.at[idx, col] = f"{val:.2%}"
                        elif unit == '%':
                            # 原始值列（单位为%）
                            display_df.at[idx, col] = f"{val:.2f}%"
                        else:
                            # 其他数值列
                            display_df.at[idx, col] = f"{val:.2f}"
                    else:
                        display_df.at[idx, col] = 'N/A'

            # 直接显示（已经是字符串，不再使用styler）
            st.dataframe(display_df, hide_index=True)
        else:
            # 没有元数据：使用标准格式化和高亮
            format_dict = {}
            for col in summary_sorted.select_dtypes(include=np.number).columns:
                if col in percentage_columns:
                    format_dict[col] = '{:.2%}'
                else:
                    format_dict[col] = '{:.2f}'

            styled_table = summary_sorted.style.format(format_dict, na_rep='N/A')

            # 应用高亮
            if highlight_columns:
                styled_table = styled_table.apply(
                    lambda x: x.map(_highlight_positive_negative),
                    subset=highlight_columns
                )

            st.dataframe(styled_table, hide_index=True)
    except KeyError as e:
        st.error(f"格式化/高亮摘要表时出错,列名可能不匹配: {e}")
        st.dataframe(summary_sorted, hide_index=True)

    _display_summary_calculation_note(st, summary_sorted)

    # 添加下载按钮（放在表格左下角）
    from datetime import datetime

    workbook_data = build_summary_workbook(summary_sorted)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    st.download_button(
        label="下载数据摘要",
        data=workbook_data,
        file_name=f"{download_prefix}_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )


def _display_summary_calculation_note(st, summary_table: pd.DataFrame) -> None:
    """在摘要表下说明当前指标实际采用的变化计算口径。"""
    growth_indicators, difference_indicators = group_indicators_by_calculation(
        summary_table
    )
    if not growth_indicators and not difference_indicators:
        return

    with st.expander("摘要计算口径说明", expanded=False):
        st.markdown(
            "**按增速计算**  \n"
            "公式：`（本期值 - 对比期值）/ 对比期值`。  \n"
            f"指标：{_format_indicator_names(growth_indicators)}"
        )
        st.markdown(
            "**按减差形式计算**  \n"
            "公式：`本期值 - 对比期值`；单位为 `%` 的指标，其结果按百分点理解。  \n"
            f"指标：{_format_indicator_names(difference_indicators)}"
        )


def _format_indicator_names(indicators: List[str]) -> str:
    """将指标名称格式化为适合折叠说明展示的文本。"""
    if not indicators:
        return "无"
    return "、".join(f"`{indicator}`" for indicator in indicators)


def _sort_summary_table(
    summary_table: pd.DataFrame,
    sort_column: str,
    st
) -> pd.DataFrame:
    """对摘要表按指定列排序

    Args:
        summary_table: 摘要表DataFrame
        sort_column: 排序列名
        st: streamlit模块

    Returns:
        pd.DataFrame: 排序后的DataFrame
    """
    try:
        summary_sorted = summary_table.copy()

        # 转换为数值类型用于排序
        if pd.api.types.is_numeric_dtype(summary_sorted[sort_column]):
            summary_sorted[f'{sort_column}_numeric'] = summary_sorted[sort_column]
        else:
            summary_sorted[f'{sort_column}_numeric'] = pd.to_numeric(
                summary_sorted[sort_column].astype(str).str.replace('%', ''),
                errors='coerce'
            )

        summary_sorted = summary_sorted.sort_values(
            by=f'{sort_column}_numeric',
            ascending=False,
            na_position='last'
        ).drop(columns=[f'{sort_column}_numeric'])

        return summary_sorted
    except KeyError:
        st.warning(f"无法按 '{sort_column}' 排序,该列不存在。")
        return summary_table
    except Exception as e:
        st.warning(f"按 '{sort_column}' 排序时出错: {e}")
        return summary_table


def _highlight_positive_negative(val) -> str:
    """为正负值添加颜色高亮

    Args:
        val: 单元格值

    Returns:
        str: CSS样式字符串
    """
    try:
        val_float = float(str(val).replace('%', ''))
        if val_float > 0:
            return f'background-color: {COLORS["positive"]}'
        elif val_float < 0:
            return f'background-color: {COLORS["negative"]}'
        return ''
    except (ValueError, TypeError):
        return ''
