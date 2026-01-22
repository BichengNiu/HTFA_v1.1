# -*- coding: utf-8 -*-
"""
侧边栏渲染器
包含主渲染函数和工具函数
"""

import streamlit as st
import logging
from typing import Dict, Any, List
from contextlib import contextmanager
from dashboard.core.ui.components.module_selector import render_main_module_selector, render_sub_module_selector
from dashboard.core.ui.utils.state_helpers import clear_button_state_cache
from dashboard.core import get_current_main_module, get_current_sub_module, set_current_main_module

logger = logging.getLogger(__name__)


def render_complete_sidebar(
    module_config: Dict[str, Any],
    key_prefix: str = "sidebar"
) -> Dict[str, Any]:
    """
    渲染完整的侧边栏，包括标题、模块选择器等

    Args:
        module_config: 模块配置字典
        key_prefix: 组件key前缀

    Returns:
        Dict[str, Any]: 侧边栏渲染结果
    """
    # 验证配置有效性
    if not module_config or not isinstance(module_config, dict) or len(module_config) == 0:
        return {'error': 'Invalid module configuration'}

    with create_sidebar_container():
        # === 调试模式徽章 ===
        debug_mode = st.session_state.get("auth.debug_mode", True)
        if debug_mode:
            st.warning("调试模式：认证和权限检查已禁用")
            st.markdown("")

        # === 第一层：主模块选择器 ===
        st.markdown("### 主模块")

        # 根据用户角色决定显示的模块
        current_user = st.session_state.get("auth.current_user", None)

        if debug_mode:
            # 调试模式：显示所有模块
            main_module_options = list(module_config.keys())
        elif current_user:
            # 正常模式：根据管理员身份决定模块列表
            from dashboard.auth.ui.middleware import get_auth_middleware
            auth_middleware = get_auth_middleware()

            if auth_middleware.permission_manager.is_admin(current_user):
                # 管理员：只显示用户管理模块
                main_module_options = ['用户管理']
            else:
                # 非管理员：显示除用户管理外的所有模块（按权限过滤）
                all_non_admin_modules = [m for m in module_config.keys() if m != '用户管理']
                main_module_options = filter_modules_by_permission(all_non_admin_modules)
        else:
            # 未登录且非调试模式：不应该到这里，但为了安全返回空列表
            main_module_options = []

        # 获取当前状态，初次进入时可能为None
        current_main_module = get_current_main_module()

        try:
            clear_button_state_cache()
        except Exception as e:
            logger.error(f"清除按钮状态缓存失败: {e}")

        # 只有在current_main_module不为None且不在选项中时才设置默认值
        if current_main_module is not None and current_main_module not in main_module_options:
            current_main_module = main_module_options[0]
            set_current_main_module(current_main_module)

        # 渲染主模块选择器
        main_module_result = render_main_module_selector(
            main_module_options, current_main_module, f"{key_prefix}_main"
        )

        # 获取更新后的主模块状态用于子模块选择器
        updated_main_module = main_module_result.get('selected_module', current_main_module)

        # === 视觉分割线 ===
        st.markdown("---")

        # === 第二层：子模块选择器 ===
        current_sub_module = get_current_sub_module()
        sub_module_result = None

        # 只有当选择了主模块时才显示子模块选择器
        if updated_main_module and updated_main_module in module_config:
            sub_config = module_config[updated_main_module]
            if isinstance(sub_config, dict):  # 有子模块
                st.markdown("### 子模块")
                st.caption(f"当前主模块：{updated_main_module}")

                # 添加一些间距来实现视觉分割
                st.markdown("")  # 空行

                sub_module_options = list(sub_config.keys())

                # 根据细粒度权限过滤子模块
                if not debug_mode and current_user:
                    from dashboard.auth.ui.middleware import get_auth_middleware
                    auth_middleware = get_auth_middleware()

                    # 获取用户在当前主模块下可访问的子模块
                    accessible_submodules = auth_middleware.permission_manager.get_accessible_submodules(
                        current_user, updated_main_module
                    )

                    # 过滤子模块选项
                    sub_module_options = [sub for sub in sub_module_options if sub in accessible_submodules]

                # 渲染子模块选择器
                sub_module_result = render_sub_module_selector(
                    sub_module_options, current_sub_module, updated_main_module,
                    f"{key_prefix}_sub"
                )

                st.markdown("")  # 空行
            else:
                # 没有子模块的情况，显示提示
                st.markdown("### 子模块")
        else:
            # 没有选择主模块时，显示提示
            st.markdown("### 子模块")
            st.info("请先选择一个主模块")

        # 渲染分隔线
        st.markdown("---")

        # 渲染数据上传部分（如果适用）
        upload_info = None
        if sub_module_result and sub_module_result.get('selected_sub_module'):
            upload_config = get_upload_section_config(
                updated_main_module, sub_module_result['selected_sub_module']
            )
            if upload_config['show_upload']:
                upload_info = render_data_upload_section(
                    updated_main_module, sub_module_result['selected_sub_module']
                )

    result = {
        'main_module_result': main_module_result,
        'sub_module_result': sub_module_result,
        'upload_info': upload_info
    }

    return result


def render_data_upload_section(main_module: str, sub_module: str) -> Dict[str, Any]:
    """
    渲染数据上传部分 - 支持其他模块（DFM已移至数据准备tab）

    Args:
        main_module: 主模块名称
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 上传部分信息
    """
    upload_config = get_upload_section_config(main_module, sub_module)

    if not upload_config['show_upload']:
        return {'show_upload': False}

    # DFM模型的数据上传已移至数据准备tab，不在sidebar显示
    if main_module == "模型分析" and sub_module == "DFM 模型":
        return {'show_upload': False}

    if main_module != "数据探索":
        st.subheader(upload_config['title'])
        st.write(upload_config['description'])

    return {
        'show_upload': True,
        'main_module': main_module,
        'sub_module': sub_module,
        'upload_title': upload_config['title'],
        'upload_description': upload_config['description']
    }


@contextmanager
def create_sidebar_container():
    """
    创建侧边栏容器的上下文管理器

    Yields:
        侧边栏上下文
    """
    with st.sidebar:
        yield st.sidebar


def get_upload_section_config(main_module: str, sub_module: str) -> Dict[str, Any]:
    """
    获取上传部分的配置

    Args:
        main_module: 主模块名称
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 上传配置
    """
    # 定义支持上传的模块组合
    upload_configs = {
        ('数据探索', None): {
            'show_upload': True,
            'title': '数据探索 - 数据上传',
            'description': '上传数据文件进行探索性分析'
        }
        # DFM模型的数据上传已移至数据准备tab中
        # 监测分析模块已改为直接使用默认数据文件
    }

    key = (main_module, sub_module)
    return upload_configs.get(key, {'show_upload': False})


def filter_modules_by_permission(all_modules: List[str]) -> List[str]:
    """
    根据用户权限过滤模块列表

    Args:
        all_modules: 所有可用模块列表

    Returns:
        List[str]: 用户有权限的模块列表
    """
    # 读取调试模式状态
    debug_mode = st.session_state.get("auth.debug_mode", True)

    # 调试模式：显示所有模块
    if debug_mode:
        return all_modules

    # 正常模式：按权限过滤
    user_accessible_modules = st.session_state.get("auth.user_accessible_modules", set())
    current_user = st.session_state.get("auth.current_user", None)

    if not current_user:
        # 正常模式且未登录：不应该到达这里（app.py会强制登录）
        # 但为了安全起见，返回空列表
        return []

    # 过滤模块列表
    filtered_modules = []
    for module in all_modules:
        if module in user_accessible_modules:
            filtered_modules.append(module)

    return filtered_modules
