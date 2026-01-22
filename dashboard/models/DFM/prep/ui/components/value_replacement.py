# -*- coding: utf-8 -*-
"""
值替换UI组件

提供值替换功能的Streamlit UI界面。
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional
from datetime import date

from dashboard.models.DFM.prep.modules.value_replacer import (
    ValueReplacer, ReplacementRule, ReplacementResult
)
from dashboard.models.DFM.prep.ui.state import PrepStateKeys, prep_state


def render_value_replacement_section(prepared_data: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    渲染值替换功能区域

    Args:
        prepared_data: 当前处理后的DataFrame

    Returns:
        如果有更新，返回更新后的DataFrame；否则返回None
    """
    st.markdown("#### 值替换")

    # 变量选择
    variables = prepared_data.columns.tolist()
    selected_var = st.selectbox(
        "选择变量",
        options=variables,
        key="value_replace_var"
    )

    # 替换规则选择
    rule_type = st.radio(
        "替换规则",
        options=["按月份筛选", "按周次筛选", "按日期范围", "按条件表达式"],
        horizontal=True,
        key="value_replace_rule_type"
    )

    rule = None

    if rule_type == "按月份筛选":
        rule = _render_months_rule(selected_var)

    elif rule_type == "按周次筛选":
        rule = _render_weeks_rule(selected_var)

    elif rule_type == "按日期范围":
        rule = _render_date_range_rule(selected_var, prepared_data)

    elif rule_type == "按条件表达式":
        rule = _render_condition_rule(selected_var)

    # 替换目标
    replace_target = st.radio(
        "替换为",
        options=["缺失值(NaN)", "固定值"],
        horizontal=True,
        key="value_replace_target"
    )

    replace_with = 'nan'
    if replace_target == "固定值":
        replace_with = st.number_input("输入固定值", value=0.0, key="value_replace_fixed_val")

    if rule:
        rule.replace_with = replace_with

    # 操作按钮（应用替换和预览影响紧挨着）
    # 使用更精准的CSS选择器移除列间距
    st.markdown("""
    <style>
    /* 目标：包含primary按钮的水平块，移除flex间距 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-primary"]) {
        gap: 0 !important;
        justify-content: flex-start !important;
    }
    /* 目标：该水平块内的所有列，设为自适应宽度 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-primary"]) > div[data-testid="stColumn"] {
        width: auto !important;
        flex: 0 0 auto !important;
        min-width: 0 !important;
        padding: 0 !important;
    }
    /* 第一列右侧加小间距 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-primary"]) > div[data-testid="stColumn"]:first-child {
        padding-right: 0.5rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, _ = st.columns([1, 1, 10])

    with col1:
        apply_clicked = st.button("应用替换", type="primary", key="value_replace_apply_btn")

    with col2:
        preview_clicked = st.button("预览影响", key="value_replace_preview_btn")

    # 显示替换历史表格（紧跟在按钮下方）
    history_updated_data = _render_replacement_history_inline(prepared_data)

    # 预览结果显示
    if preview_clicked and rule:
        _handle_preview(prepared_data, rule, selected_var)

    # 分割线和处理结果标题
    st.markdown("---")
    st.markdown("#### 处理结果")

    # 应用替换
    updated_data = None
    if apply_clicked and rule:
        updated_data = _handle_apply(prepared_data, rule)

    # 如果历史操作触发了更新，优先返回
    if history_updated_data is not None:
        return history_updated_data

    return updated_data


def _render_months_rule(selected_var: str) -> Optional[ReplacementRule]:
    """渲染按月份筛选规则"""
    selected_months = st.multiselect(
        "选择月份（这些月份的数据将被替换）",
        options=list(range(1, 13)),
        format_func=lambda x: f"{x}月",
        key="value_replace_months"
    )
    if selected_months:
        return ReplacementRule(
            variable=selected_var,
            rule_type='months',
            months=selected_months
        )
    return None


def _render_weeks_rule(selected_var: str) -> Optional[ReplacementRule]:
    """渲染按周次筛选规则"""
    week_mode = st.radio(
        "周次模式",
        options=["每年第N周", "每月第N周"],
        horizontal=True,
        key="value_replace_week_mode"
    )

    if week_mode == "每年第N周":
        selected_weeks = st.multiselect(
            "选择周次（ISO周数，1-53）",
            options=list(range(1, 54)),
            format_func=lambda x: f"第{x}周",
            key="value_replace_weeks_yearly"
        )
        if selected_weeks:
            return ReplacementRule(
                variable=selected_var,
                rule_type='weeks_yearly',
                weeks=selected_weeks
            )
    else:  # 每月第N周
        selected_weeks = st.multiselect(
            "选择周次（1-5，基于日期计算）",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: f"第{x}周",
            key="value_replace_weeks_monthly"
        )
        if selected_weeks:
            return ReplacementRule(
                variable=selected_var,
                rule_type='weeks_monthly',
                weeks=selected_weeks
            )
    return None


def _render_date_range_rule(selected_var: str, prepared_data: pd.DataFrame) -> ReplacementRule:
    """渲染按日期范围规则"""
    col1, col2 = st.columns(2)

    # 获取默认日期范围
    if isinstance(prepared_data.index, pd.DatetimeIndex):
        default_start = prepared_data.index.min().date()
        default_end = prepared_data.index.max().date()
    else:
        default_start = date.today()
        default_end = date.today()

    with col1:
        start_date = st.date_input(
            "起始日期",
            value=default_start,
            key="value_replace_start_date"
        )
    with col2:
        end_date = st.date_input(
            "结束日期",
            value=default_end,
            key="value_replace_end_date"
        )

    return ReplacementRule(
        variable=selected_var,
        rule_type='date_range',
        start_date=start_date,
        end_date=end_date
    )


def _render_condition_rule(selected_var: str) -> ReplacementRule:
    """渲染按条件表达式规则"""
    condition = st.selectbox(
        "条件类型",
        options=["等于", "大于", "小于", "大于等于", "小于等于", "介于", "为空值"],
        key="value_replace_condition"
    )
    condition_map = {
        "等于": "eq",
        "大于": "gt",
        "小于": "lt",
        "大于等于": "gte",
        "小于等于": "lte",
        "介于": "between",
        "为空值": "isnull"
    }
    cond_type = condition_map[condition]

    cond_val = None
    cond_val2 = None

    if condition != "为空值":
        if condition == "介于":
            col1, col2 = st.columns(2)
            with col1:
                cond_val = st.number_input("最小值", key="value_replace_cond_min")
            with col2:
                cond_val2 = st.number_input("最大值", key="value_replace_cond_max")
        else:
            cond_val = st.number_input("条件值", key="value_replace_cond_val")

    return ReplacementRule(
        variable=selected_var,
        rule_type='condition',
        condition_type=cond_type,
        condition_value=cond_val,
        condition_value2=cond_val2
    )


def _handle_preview(prepared_data: pd.DataFrame, rule: ReplacementRule, selected_var: str) -> None:
    """处理预览操作"""
    replacer = ValueReplacer(prepared_data.copy())
    try:
        result = replacer.preview(rule)
        st.info(f"将影响 **{result.affected_count}** 行数据")

        if result.affected_count > 0:
            max_show = 50
            indices_to_show = result.affected_indices[:max_show]
            preview_df = prepared_data.loc[indices_to_show, [selected_var]].copy()

            # 处理new_value的类型，确保'NaN'字符串转换为实际的NaN值
            new_val = np.nan if result.new_value == 'NaN' else result.new_value
            preview_df['替换后'] = new_val

            # 保留变量名在列标题中
            preview_df.columns = [f'{selected_var}(原值)', '替换后']

            # 格式化时间索引为 年-月-日，并保留为列
            if isinstance(preview_df.index, pd.DatetimeIndex):
                preview_df.index.name = '日期'
                preview_df.index = preview_df.index.strftime('%Y-%m-%d')

            # 重置索引，保留日期作为列
            preview_df.reset_index(inplace=True)

            # 按日期降序排列（从新到旧）
            preview_df.sort_values(by='日期', ascending=False, inplace=True)

            if result.affected_count > max_show:
                st.caption(f"（仅显示前{max_show}条，共{result.affected_count}条）")

            # 隐藏数值索引
            st.dataframe(preview_df, hide_index=True, use_container_width=True)
    except ValueError as e:
        st.error(str(e))


def _handle_apply(prepared_data: pd.DataFrame, rule: ReplacementRule) -> Optional[pd.DataFrame]:
    """处理应用替换操作"""
    data_copy = prepared_data.copy()
    replacer = ValueReplacer(data_copy)

    try:
        result = replacer.apply(rule)
        if result.affected_count > 0:
            # 确保有基准数据（用于撤销所有）
            if prep_state.get(PrepStateKeys.BASE_PREPARED_DATA_DF) is None:
                prep_state.set(PrepStateKeys.BASE_PREPARED_DATA_DF, prepared_data.copy())

            # 保存替换历史
            history = prep_state.get(PrepStateKeys.VALUE_REPLACEMENT_HISTORY) or []
            history.append({
                'variable': result.variable,
                'rule': result.rule_description,
                'new_value': str(result.new_value),
                'affected_count': result.affected_count,
                'affected_indices': [str(idx) for idx in result.affected_indices],
                'original_values': result.original_values
            })
            prep_state.set(PrepStateKeys.VALUE_REPLACEMENT_HISTORY, history)

            st.success(f"已替换 {result.affected_count} 个值")
            return data_copy
        else:
            st.warning("没有符合条件的数据")
            return None
    except ValueError as e:
        st.error(str(e))
        return None


def _render_replacement_history_inline(prepared_data: pd.DataFrame) -> Optional[pd.DataFrame]:
    """渲染替换历史记录（紧跟在应用替换按钮下方）"""
    history = prep_state.get(PrepStateKeys.VALUE_REPLACEMENT_HISTORY) or []

    if not history:
        return None

    st.markdown("**已执行的替换操作**")

    history_df = pd.DataFrame([
        {
            '序号': i + 1,
            '变量': h['variable'],
            '规则': h['rule'],
            '替换为': h['new_value'],
            '影响行': h['affected_count']
        }
        for i, h in enumerate(history)
    ])
    st.dataframe(history_df, hide_index=True, width='stretch')

    # 使用与应用替换按钮相同的样式，让两个按钮紧挨着
    st.markdown("""
    <style>
    /* 目标：包含secondary按钮的水平块，移除flex间距 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-secondary"]) {
        gap: 0 !important;
        justify-content: flex-start !important;
    }
    /* 目标：该水平块内的所有列，设为自适应宽度 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-secondary"]) > div[data-testid="stColumn"] {
        width: auto !important;
        flex: 0 0 auto !important;
        min-width: 0 !important;
        padding: 0 !important;
    }
    /* 第一列右侧加小间距 */
    div[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-secondary"]) > div[data-testid="stColumn"]:first-child {
        padding-right: 0.5rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, _ = st.columns([1, 1, 10])

    with col1:
        if st.button("撤销最后一次", key="value_replace_undo"):
            if history:
                last = history.pop()
                # 恢复原始值
                for idx_str, orig_val in zip(last['affected_indices'], last['original_values']):
                    # 尝试解析索引
                    try:
                        idx = pd.Timestamp(idx_str)
                    except Exception:
                        idx = idx_str
                    prepared_data.loc[idx, last['variable']] = orig_val
                prep_state.set(PrepStateKeys.VALUE_REPLACEMENT_HISTORY, history)
                prep_state.set(PrepStateKeys.PREPARED_DATA_DF, prepared_data)
                st.rerun()

    with col2:
        if st.button("清空所有替换", key="value_replace_clear"):
            # 从BASE_PREPARED_DATA_DF恢复
            base_data = prep_state.get(PrepStateKeys.BASE_PREPARED_DATA_DF)
            if base_data is not None:
                prep_state.set(PrepStateKeys.PREPARED_DATA_DF, base_data.copy())
                prep_state.set(PrepStateKeys.VALUE_REPLACEMENT_HISTORY, [])
                st.rerun()
            else:
                st.warning("没有可恢复的基准数据")

    return None


def get_replacement_history() -> list:
    """获取当前的替换历史（用于导出）"""
    return prep_state.get(PrepStateKeys.VALUE_REPLACEMENT_HISTORY, [])
