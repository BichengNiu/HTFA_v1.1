"""
Industrial Analysis Unified Module
工业分析统一模块 - 提供统一的文件上传和数据共享功能

This module provides:
- Unified file upload functionality
- Data caching and sharing between macro and enterprise modules
- State management integration
- Tab-based interface for macro operations and enterprise operations
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple
import logging

# 设置日志
logger = logging.getLogger(__name__)

# 导入统一的数据加载函数
from htfa.monitoring.industrial.utils.data_loader import load_macro_data, load_weights_data

from htfa.app.state.shared_dataset import get_shared_dataset_file, get_shared_dataset_name


def load_default_monitoring_data() -> Optional[str]:
    """
    获取默认监测分析数据文件路径

    Returns:
        Optional[str]: 文件路径或None
    """
    default_path = Path(__file__).parent.parent.parent.parent / "data" / "监测分析数据库.xlsx"

    if default_path.exists():
        return str(default_path)

    logger.warning(f"默认数据文件不存在: {default_path}")
    return None


def load_and_cache_data(uploaded_file) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    加载当前会话的数据；固定权重由 data_loader 的资源缓存复用。

    Returns:
        (df_macro, df_weights): 宏观数据和权重数据的元组
    """
    if uploaded_file is None:
        return None, None

    # 上传数据只在当前会话中流转，避免通过进程级缓存保存用户文件。
    with st.spinner("正在处理数据..."):
        df_macro = load_macro_data(uploaded_file)
        df_weights = load_weights_data()  # 从内部CSV文件读取

    # 错误提示
    if df_macro is None:
        st.error("分行业工业增加值同比增速数据加载失败，请检查文件是否包含'分行业工业增加值同比增速'工作表")
    if df_weights is None:
        st.error("内部权重数据加载失败，请联系管理员检查配置文件")

    return df_macro, df_weights


def render_macro_operations_with_data(st_obj, df_macro: Optional[pd.DataFrame], df_weights: Optional[pd.DataFrame], uploaded_file=None):
    """
    使用共享数据渲染分行业工业增加值同比增速分析
    """
    if df_macro is not None and df_weights is not None:
        # 调用宏观运行分析，传入数据和文件路径
        from htfa.monitoring.industrial.macro_analysis import render_macro_operations_analysis_with_data
        render_macro_operations_analysis_with_data(st_obj, df_macro, df_weights, uploaded_file)
    else:
        st_obj.info("数据加载失败，无法进行分析")


def render_enterprise_profit_with_data(st_obj, df_weights: Optional[pd.DataFrame], uploaded_file=None):
    """
    使用共享数据渲染工业企业利润分析
    """
    from htfa.monitoring.industrial.enterprise_analysis import render_enterprise_profit_analysis_with_data
    render_enterprise_profit_analysis_with_data(st_obj, df_weights, uploaded_file)


def render_enterprise_efficiency_with_data(st_obj, uploaded_file=None):
    """
    使用共享数据渲染工业企业经营效率分析
    """
    from htfa.monitoring.industrial.enterprise_analysis import render_enterprise_efficiency_analysis_with_data
    render_enterprise_efficiency_analysis_with_data(st_obj, uploaded_file)


def render_industrial_analysis(st_obj):
    """
    渲染统一的工业分析模块

    Args:
        st_obj: Streamlit对象
    """
    # 1. 优先使用侧边栏共享数据集；未上传时保留默认文件作为兜底。
    uploaded_file = get_shared_dataset_file() or load_default_monitoring_data()

    if uploaded_file is None:
        st_obj.error("请先在侧边栏上传数据集，或补充 data/监测分析数据库.xlsx")
        return

    source_name = get_shared_dataset_name() or "监测分析数据库.xlsx"
    st_obj.sidebar.success(f"当前监测数据：{source_name}")

    # 2. 加载和缓存数据
    df_macro, df_weights = load_and_cache_data(uploaded_file)

    # 3. 定义业务 Tab 及其渲染函数。
    all_tabs = [
        ("工业增加值分析", lambda: render_macro_operations_with_data(st_obj, df_macro, df_weights, uploaded_file)),
        ("工业企业利润分析", lambda: render_enterprise_profit_with_data(st_obj, df_weights, uploaded_file)),
        ("工业企业经营效率分析", lambda: render_enterprise_efficiency_with_data(st_obj, uploaded_file)),
    ]

    # 4. 创建标签页
    tab_names = [tab[0] for tab in all_tabs]
    tabs = st_obj.tabs(tab_names)

    # 5. 渲染每个Tab
    for i, (_, render_func) in enumerate(all_tabs):
        with tabs[i]:
            render_func()
