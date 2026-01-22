# -*- coding: utf-8 -*-
"""
模块选择器组件
提供主模块和子模块的选择界面组件
"""

import streamlit as st
import time
from typing import List, Dict, Any, Optional, Tuple
from dashboard.core.ui.utils.debug_helpers import debug_button_click, debug_navigation
from dashboard.core import (
    get_current_main_module,
    get_current_sub_module,
    set_current_main_module,
    set_current_sub_module,
    is_transitioning,
    set_transitioning
)


def render_main_module_selector(
    module_options: List[str],
    current_module: str,
    key_prefix: str = "main_module"
) -> Dict[str, Any]:
    """
    渲染主模块选择器

    Args:
        module_options: 模块选项列表
        current_module: 当前选中的模块
        key_prefix: 按钮key前缀

    Returns:
        Dict[str, Any]: 选择结果
    """
    if not validate_module_options(module_options):
        return {'selected_module': current_module, 'has_change': False, 'success': False}

    # 获取模块分布
    col1_modules, col2_modules = get_module_distribution(module_options)

    # 创建两列布局
    col1, col2 = st.columns(2)

    selected_module = current_module
    has_change = False

    # 渲染第一列模块 - 使用secondary按钮样式
    with col1:
        for module in col1_modules:
            button_key = f"{key_prefix}_col1_{module}"

            if create_module_button(module, 'secondary', button_key):
                debug_button_click(f"主模块-第一列-{module}", f"从 {current_module} 切换到 {module}")
                selected_module = module
                has_change = True

    # 渲染第二列模块 - 使用secondary按钮样式
    with col2:
        for module in col2_modules:
            button_key = f"{key_prefix}_col2_{module}"

            if create_module_button(module, 'secondary', button_key):
                debug_button_click(f"主模块-第二列-{module}", f"从 {current_module} 切换到 {module}")
                selected_module = module
                has_change = True

    # 处理模块选择
    if has_change:
        result = handle_module_selection(selected_module, current_module, 'main')
    else:
        result = {
            'selected_module': current_module,
            'has_change': False,
            'success': True
        }

    return result


def render_sub_module_selector(
    sub_module_options: List[str],
    current_sub_module: Optional[str],
    main_module: str,
    key_prefix: str = "sub_module"
) -> Dict[str, Any]:
    """
    渲染子模块选择器

    Args:
        sub_module_options: 子模块选项列表
        current_sub_module: 当前选中的子模块
        main_module: 主模块名称
        key_prefix: 按钮key前缀

    Returns:
        Dict[str, Any]: 选择结果
    """
    if not validate_module_options(sub_module_options):
        return {'selected_sub_module': current_sub_module, 'has_change': False, 'success': False}

    # 获取模块分布
    col1_modules, col2_modules = get_module_distribution(sub_module_options)

    # 创建两列布局
    col1, col2 = st.columns(2)

    selected_sub_module = current_sub_module
    has_change = False

    # 渲染第一列子模块 - 使用secondary按钮样式
    with col1:
        for sub_module in col1_modules:
            button_key = f"{key_prefix}_col1_{sub_module}"

            if create_module_button(sub_module, 'secondary', button_key):
                debug_button_click(f"子模块-第一列-{sub_module}", f"在{main_module}中选择{sub_module}")
                selected_sub_module = sub_module
                has_change = True

    # 渲染第二列子模块 - 使用secondary按钮样式
    with col2:
        for sub_module in col2_modules:
            button_key = f"{key_prefix}_col2_{sub_module}"

            if create_module_button(sub_module, 'secondary', button_key):
                debug_button_click(f"子模块-第二列-{sub_module}", f"在{main_module}中选择{sub_module}")
                selected_sub_module = sub_module
                has_change = True

    # 处理子模块选择
    if has_change:
        result = handle_module_selection(selected_sub_module, current_sub_module, 'sub')
    else:
        result = {
            'selected_sub_module': current_sub_module,
            'has_change': False,
            'success': True
        }

    return result


def get_module_distribution(modules: List[str]) -> Tuple[List[str], List[str]]:
    """
    计算模块在两列中的分布 - 根据模块顺序要求特殊处理
    
    Args:
        modules: 模块列表
        
    Returns:
        Tuple[List[str], List[str]]: (第一列模块, 第二列模块)
    """
    if not modules:
        return [], []
    
    # 特殊处理：根据用户要求的布局
    # 第一行：数据预览、监测分析
    # 第二行：模型分析、数据探索
    # 第三行：用户管理

    # 定义布局映射
    layout_mapping = {
        "数据预览": (0, 0),  # 第一行第一列
        "监测分析": (0, 1),  # 第一行第二列
        "模型分析": (1, 0),  # 第二行第一列
        "数据探索": (1, 1),  # 第二行第二列
        "用户管理": (2, 0),  # 第三行第一列
    }
    
    col1_modules = []
    col2_modules = []
    
    # 按照指定顺序排列
    for module in modules:
        if module in layout_mapping:
            row, col = layout_mapping[module]
            if col == 0:  # 第一列
                col1_modules.append(module)
            else:  # 第二列  
                col2_modules.append(module)
        else:
            # 如果有未知模块，按默认分布处理
            if len(col1_modules) <= len(col2_modules):
                col1_modules.append(module)
            else:
                col2_modules.append(module)
    
    return col1_modules, col2_modules


def create_module_button(
    module_name: str,
    button_type: str = 'primary',
    key: str = None
) -> bool:
    """
    创建模块按钮

    Args:
        module_name: 模块名称
        button_type: 按钮类型 ('primary' 或 'secondary')
        key: 按钮的唯一key

    Returns:
        bool: 按钮是否被点击
    """
    if key is None or not key or not isinstance(key, str):
        key = f"module_btn_{module_name.replace(' ', '_')}"

    from dashboard.core.ui.utils.debug_helpers import debug_log
    debug_log(f"创建按钮: {module_name}, key: {key}", "DEBUG")

    button_clicked = st.button(
        module_name,
        type=button_type,
        key=key,
        width='stretch'
    )

    if button_clicked:
        debug_log(f"按钮被点击: {module_name}, key: {key}", "DEBUG")

    return button_clicked


def handle_module_selection(
    selected_module: str,
    current_module: Optional[str],
    module_type: str = 'main'
) -> Dict[str, Any]:
    """
    处理模块选择逻辑

    Args:
        selected_module: 选中的模块
        current_module: 当前模块
        module_type: 模块类型 ('main' 或 'sub')

    Returns:
        Dict[str, Any]: 处理结果
    """
    # 添加调试输出（受环境变量控制）
    from dashboard.core.ui.utils.debug_helpers import debug_log
    debug_log(f"处理模块选择: {module_type}, {current_module} -> {selected_module}", "DEBUG")

    # 检查是否有变化
    if selected_module == current_module:
        debug_log(f"模块没有变化: {selected_module}", "DEBUG")
        return {
            'selected_module' if module_type == 'main' else 'selected_sub_module': selected_module,
            'has_change': False,
            'success': True
        }

    # 执行导航状态更新
    success = True
    try:
        # 设置导航过渡状态，标记用户正在进行导航操作
        set_transitioning(True)

        # 记录导航时间戳，用于循环渲染检测
        current_time = time.time()
        st.session_state["dashboard.last_navigation_time"] = current_time
        debug_navigation("导航时间戳", f"设置导航时间戳: {current_time}")

        if module_type == 'main':
            debug_log(f"调用 set_current_main_module({selected_module})", "DEBUG")
            success = set_current_main_module(selected_module)
            debug_log(f"主模块设置结果: {success}", "DEBUG")
            debug_navigation(
                "主模块选择",
                f"设置主模块: {current_module} -> {selected_module}, 成功: {success}"
            )
            # 验证设置结果
            actual_main = get_current_main_module()
            debug_log(f"验证主模块设置: 期望={selected_module}, 实际={actual_main}", "DEBUG")
        else:
            debug_log(f"调用 set_current_sub_module({selected_module})", "DEBUG")
            success = set_current_sub_module(selected_module)
            debug_log(f"子模块设置结果: {success}", "DEBUG")
            debug_navigation(
                "子模块选择",
                f"设置子模块: {current_module} -> {selected_module}, 成功: {success}"
            )
            # 验证设置结果
            actual_sub = get_current_sub_module()
            debug_log(f"验证子模块设置: 期望={selected_module}, 实际={actual_sub}", "DEBUG")

        # 清除导航过渡状态
        set_transitioning(False)

    except Exception as e:
        debug_navigation("模块选择失败", f"设置{module_type}模块失败: {e}")
        success = False
        # 确保在出错时也清除过渡状态
        try:
            set_transitioning(False)
        except:
            pass

    result_key = 'selected_module' if module_type == 'main' else 'selected_sub_module'
    return {
        result_key: selected_module,
        'has_change': True,
        'success': success
    }


def validate_module_options(module_options: Optional[List[str]]) -> bool:
    """
    验证模块选项的有效性
    
    Args:
        module_options: 模块选项列表
        
    Returns:
        bool: 是否有效
    """
    if not module_options:
        return False
    
    if not isinstance(module_options, list):
        return False
    
    # 检查是否包含空字符串或None
    for option in module_options:
        if not option or not isinstance(option, str) or option.strip() == '':
            return False
    
    return True


__all__ = [
    'render_main_module_selector',
    'render_sub_module_selector',
    'get_module_distribution',
    'create_module_button',
    'handle_module_selection',
    'validate_module_options',
]
