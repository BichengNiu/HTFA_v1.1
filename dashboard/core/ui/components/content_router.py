# -*- coding: utf-8 -*-
"""
主内容路由组件
提供主内容区域的路由和渲染功能
"""

import streamlit as st
import logging
from typing import Dict, Any, Optional
from dashboard.explore.ui.univariate_page import render_univariate_analysis_page
from dashboard.explore.ui.bivariate_page import render_bivariate_analysis_page
from dashboard.explore.ui.pages import DataExplorationWelcomePage
from dashboard.auth.ui.pages.user_management_module import UserManagementWelcomePage, render_user_management_sub_module
from dashboard.core import get_current_main_module, get_current_sub_module

logger = logging.getLogger(__name__)

PREVIEW_MODULE_MAPPING = {
    '工业': 'industrial',
    '阿联酋': 'uae',
}


def check_user_permission(module_name: str) -> tuple[bool, Optional[str]]:
    """
    检查用户是否有访问指定模块的权限

    委托给auth模块的PermissionManager进行权限检查

    Args:
        module_name: 模块名称

    Returns:
        tuple[bool, Optional[str]]: (是否有权限, 错误信息)
    """
    try:
        # 调试模式：直接放行
        debug_mode = st.session_state.get('auth.debug_mode', True)
        if debug_mode:
            logger.debug(f"调试模式：允许访问模块 {module_name}")
            return True, None

        # 正常模式：委托给auth模块检查
        current_user = st.session_state.get('auth.current_user', None)
        if not current_user:
            error_msg = f"请先登录后访问「{module_name}」模块"
            logger.warning(f"权限检查失败：{error_msg}")
            return False, error_msg

        # 使用auth模块的权限管理器
        from dashboard.auth.ui.middleware import get_auth_middleware
        auth_middleware = get_auth_middleware()
        permission_manager = auth_middleware.permission_manager

        is_admin = permission_manager.is_admin(current_user)

        # 用户管理模块：仅管理员可访问
        if module_name == '用户管理':
            if is_admin:
                return True, None
            else:
                return False, f"只有管理员才能访问「{module_name}」模块"

        # 其他模块：管理员不可访问
        if is_admin:
            return False, f"管理员账户无法访问「{module_name}」模块，仅可访问用户管理"

        # 普通用户：使用PermissionManager检查模块访问权限
        if permission_manager.check_module_access(current_user, module_name):
            logger.debug(f"权限检查通过：用户可以访问模块 {module_name}")
            return True, None
        else:
            return False, f"您没有访问「{module_name}」模块的权限，请联系管理员"

    except Exception as e:
        logger.error(f"权限检查失败: {e}")
        return False, f"权限检查失败: {e}"


def render_permission_denied(module_name: str, error_message: str = None) -> Dict[str, Any]:
    """
    渲染权限拒绝页面
    
    Args:
        module_name: 模块名称
        error_message: 错误信息
        
    Returns:
        Dict[str, Any]: 渲染结果
    """
    # 只显示一个简洁的红色提示信息
    st.error("无访问权限")
    
    return {
        'status': 'permission_denied',
        'content_type': 'permission_denied',
        'main_module': module_name,
        'error_message': error_message
    }


def render_main_content() -> Dict[str, Any]:
    """
    渲染主内容区域

    Returns:
        Dict[str, Any]: 渲染结果
    """
    # 获取当前导航状态
    current_main_module = get_current_main_module()
    current_sub_module = get_current_sub_module()

    # 如果没有选择主模块，显示欢迎页面
    if not current_main_module:
        render_welcome_page(None, None)
        return {
            'main_module': None,
            'sub_module': None,
            'content_type': 'welcome',
            'status': 'success'
        }

    # 检查用户权限
    has_permission, permission_error = check_user_permission(current_main_module)
    if not has_permission:
        return render_permission_denied(current_main_module, permission_error)

    logger.debug(f"渲染主内容 - 主模块: {current_main_module}, 子模块: {current_sub_module}")

    # 获取内容配置
    content_config = get_content_config(current_main_module, current_sub_module)
    
    if not validate_content_config(content_config):
        st.error("内容配置无效")
        return {
            'main_module': current_main_module,
            'sub_module': current_sub_module,
            'content_type': 'error',
            'status': 'error'
        }
    
    # 路由到具体内容（平台标题只在欢迎页面显示）
    content_result = route_to_content(content_config)

    return {
        'main_module': current_main_module,
        'sub_module': current_sub_module,
        'content_type': content_config['content_type'],
        'status': 'success',
        'content_result': content_result
    }


def get_content_config(main_module: str, sub_module: Optional[str] = None) -> Dict[str, Any]:
    """
    获取内容配置
    
    Args:
        main_module: 主模块名称
        sub_module: 子模块名称
        
    Returns:
        Dict[str, Any]: 内容配置
    """
    # 基础配置
    config = {
        'title': main_module,
        'icon': get_module_icon(main_module),
        'description': get_module_description(main_module, sub_module),
        'main_module': main_module,
        'sub_module': sub_module
    }
    
    # 根据主模块设置内容类型
    if main_module == '数据预览':
        config['content_type'] = 'data_preview'
    elif main_module == '监测分析':
        config['content_type'] = 'monitoring_analysis'
    elif main_module == '模型分析':
        config['content_type'] = 'model_analysis'
    elif main_module == '数据探索':
        config['content_type'] = 'data_exploration'
    elif main_module == '用户管理':
        config['content_type'] = 'user_management'
    else:
        config['content_type'] = 'unknown'

    return config


def route_to_content(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    路由到具体内容

    Args:
        config: 内容配置

    Returns:
        Dict[str, Any]: 内容渲染结果
    """
    content_type = config['content_type']
    main_module = config.get('main_module')
    sub_module = config.get('sub_module')

    # 检测导航层次
    navigation_level = detect_navigation_level(main_module, sub_module)

    try:
        # 根据导航层次决定渲染内容
        if navigation_level == 'MAIN_MODULE_ONLY':
            # 特殊处理：用户管理模块没有子模块时直接显示内容
            if main_module == '用户管理':
                return render_user_management_content(sub_module)
            # 特殊处理：数据探索模块显示欢迎页面
            elif main_module == '数据探索':
                return render_data_exploration_welcome()
            # 第一层：只选择了主模块，显示子模块选择界面
            return render_module_selection_guide(main_module, 'sub_module')
        elif navigation_level == 'SUB_MODULE_ONLY':
            # 第二层：选择了子模块，但没有活跃的第三层tab
            # 对于数据探索模块，直接显示tab界面
            if main_module == '数据探索':
                return render_data_exploration_content(sub_module)
            # 对于模型分析模块，直接显示tab界面而不是功能选择指导
            elif main_module == '模型分析' and sub_module:
                return render_model_analysis_content(sub_module)
            else:
                # 其他模块显示功能选择界面
                return render_module_selection_guide(main_module, 'function', sub_module)
        elif navigation_level == 'FUNCTION_ACTIVE':
            # 第三层：有活跃的功能tab，渲染具体内容
            if content_type == 'data_preview':
                return render_data_preview_content(sub_module)
            elif content_type == 'monitoring_analysis':
                return render_monitoring_analysis_content(sub_module)
            elif content_type == 'model_analysis':
                return render_model_analysis_content(sub_module)
            elif content_type == 'data_exploration':
                return render_data_exploration_content(sub_module)
            elif content_type == 'user_management':
                return render_user_management_content(sub_module)
            else:
                st.warning(f"未知的内容类型: {content_type}")
                return {'status': 'warning', 'message': f'未知的内容类型: {content_type}'}
        else:
            # 默认情况，显示欢迎页面
            return render_welcome_page(main_module, sub_module)

    except Exception as e:
        st.error(f"内容渲染失败: {e}")
        logger.error(f"渲染{content_type}失败: {e}")
        return {'status': 'error', 'message': str(e)}


def render_data_preview_content(sub_module: Optional[str]) -> Dict[str, Any]:
    """
    渲染数据预览内容 - 支持多子模块

    Args:
        sub_module: 子模块名称 ('工业', '能源', 等)

    Returns:
        Dict[str, Any]: 渲染结果
    """
    from dashboard.preview.modules import PreviewModuleRegistry

    if not sub_module:
        st.info("请在左侧选择一个数据预览子模块")
        return {'status': 'info', 'message': '未选择子模块'}

    module_id = PREVIEW_MODULE_MAPPING.get(sub_module)
    if not module_id:
        st.error(f"未知的数据预览子模块: {sub_module}")
        return {'status': 'error', 'message': f'未知子模块: {sub_module}'}

    try:
        # 使用注册表创建渲染器
        renderer = PreviewModuleRegistry.create_renderer(module_id)
        renderer.render()

        return {
            'status': 'success',
            'content_type': 'data_preview',
            'sub_module': sub_module,
            'module_id': module_id
        }
    except Exception as e:
        st.error(f"渲染数据预览内容失败: {e}")
        logger.error(f"渲染数据预览失败: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def render_monitoring_analysis_content(sub_module: Optional[str]) -> Dict[str, Any]:
    """
    渲染监测分析内容

    Args:
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 渲染结果
    """
    if sub_module == '工业':
        # 调用实际的工业分析模块
        from dashboard.analysis.industrial import render_industrial_analysis
        render_industrial_analysis(st)
    else:
        st.info("请选择一个子模块以开始监测分析")

    return {'status': 'success', 'content_type': 'monitoring_analysis', 'sub_module': sub_module}


def render_model_analysis_content(sub_module: Optional[str]) -> Dict[str, Any]:
    """
    渲染模型分析内容

    Args:
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 渲染结果
    """
    try:
        # 如果选择了DFM模型，显示DFM功能的tab界面
        if sub_module == "DFM 模型":
            # 导入DFM页面渲染函数
            from dashboard.models.DFM.prep.ui.pages import render_dfm_data_prep_page
            from dashboard.models.DFM.train.ui.pages import render_dfm_model_training_page
            from dashboard.models.DFM.results.ui.pages import render_dfm_model_analysis_page
            from dashboard.models.DFM.decomp.ui.pages import render_dfm_news_analysis_page

            # 根据权限过滤Tab
            debug_mode = st.session_state.get("auth.debug_mode", False)
            current_user = st.session_state.get("auth.current_user", None)

            # 定义所有Tab及其对应的权限和渲染函数
            all_tabs = [
                ("数据准备", "model_analysis.dfm.prep", lambda: render_dfm_data_prep_page(st)),
                ("模型训练", "model_analysis.dfm.train", lambda: render_dfm_model_training_page(st)),
                ("模型分析", "model_analysis.dfm.analysis", lambda: render_dfm_model_analysis_page(st)),
                ("影响分解", "model_analysis.dfm.news", lambda: render_dfm_news_analysis_page(st))
            ]

            # 过滤Tab
            if debug_mode or not current_user:
                # 调试模式或未登录：显示所有Tab
                visible_tabs = all_tabs
            else:
                # 正常模式：根据权限过滤
                from dashboard.auth.ui.middleware import get_auth_middleware
                auth_middleware = get_auth_middleware()

                visible_tabs = []
                for tab_name, permission_code, render_func in all_tabs:
                    if auth_middleware.permission_manager.check_granular_access(
                        current_user, "模型分析", "DFM 模型", tab_name
                    ):
                        visible_tabs.append((tab_name, permission_code, render_func))

            # 如果没有可访问的Tab
            if not visible_tabs:
                st.warning("您没有权限访问任何Tab")
                return {'status': 'warning', 'content_type': 'model_analysis', 'sub_module': sub_module}

            # 创建可见的标签页
            tab_names = [tab[0] for tab in visible_tabs]
            tabs = st.tabs(tab_names)

            # 渲染每个Tab
            for i, (tab_name, permission_code, render_func) in enumerate(visible_tabs):
                with tabs[i]:
                    render_func()
        else:
            st.info("请选择一个模型分析子模块以开始分析")

        return {'status': 'success', 'content_type': 'model_analysis', 'sub_module': sub_module}
    except Exception as e:
        st.error(f"加载DFM模块时出错: {str(e)}")
        return {'status': 'error', 'content_type': 'model_analysis', 'sub_module': sub_module, 'error': str(e)}


def render_data_exploration_welcome() -> Dict[str, Any]:
    """
    渲染数据探索欢迎页面

    Returns:
        Dict[str, Any]: 渲染结果
    """
    welcome_page = DataExplorationWelcomePage()
    welcome_page.render(st)
    return {'status': 'success', 'content_type': 'data_exploration', 'sub_module': None}


def render_data_exploration_content(sub_module: Optional[str]) -> Dict[str, Any]:
    """
    渲染数据探索内容

    Args:
        sub_module: 子模块名称（时序性质、时序关系）

    Returns:
        Dict[str, Any]: 渲染结果
    """
    if sub_module == '时序性质':
        render_univariate_analysis_page()
        return {'status': 'success', 'content_type': 'data_exploration', 'sub_module': sub_module}
    elif sub_module == '时序关系':
        render_bivariate_analysis_page()
        return {'status': 'success', 'content_type': 'data_exploration', 'sub_module': sub_module}
    else:
        st.warning(f"未知的数据探索子模块: {sub_module}")
        return {'status': 'warning', 'message': f'未知的数据探索子模块: {sub_module}'}


def get_module_icon(main_module: str) -> str:
    """
    获取模块图标
    
    Args:
        main_module: 主模块名称
        
    Returns:
        str: 模块图标
    """
    icons = {
        '数据预览': '📊',
        '监测分析': '📈',
        '模型分析': '🤖',
        '数据探索': '🔍'
    }
    return icons.get(main_module, 'ℹ️')


def get_module_description(main_module: str, sub_module: Optional[str] = None) -> str:
    """
    获取模块描述
    
    Args:
        main_module: 主模块名称
        sub_module: 子模块名称
        
    Returns:
        str: 模块描述
    """
    descriptions = {
        '数据预览': '查看和预览工业领域的经济数据',
        '监测分析': '对经济运行数据进行深度监测和分析，提供专业的分析报告',
        '模型分析': '使用先进的数学模型对经济数据进行建模和预测分析',
        '数据探索': '深入探索时间序列数据的统计特性和内在规律，包括平稳性检验和相关性分析'
    }
    
    base_desc = descriptions.get(main_module, '经济数据分析功能')
    
    if sub_module:
        return f"{base_desc} - {sub_module}"
    else:
        return base_desc


def validate_content_config(config: Optional[Dict[str, Any]]) -> bool:
    """
    验证内容配置的有效性
    
    Args:
        config: 内容配置
        
    Returns:
        bool: 配置是否有效
    """
    if not config or not isinstance(config, dict):
        return False
    
    required_fields = ['title', 'icon', 'description', 'content_type']
    for field in required_fields:
        if field not in config:
            return False
    
    return True


def detect_navigation_level(main_module: str, sub_module: Optional[str]) -> str:
    """
    检测当前导航层次

    Args:
        main_module: 主模块名称
        sub_module: 子模块名称

    Returns:
        str: 导航层次 ('MAIN_MODULE_ONLY', 'SUB_MODULE_ONLY', 'FUNCTION_ACTIVE')
    """
    try:
        # 对于用户管理模块，直接显示内容（管理员专属，无子模块）
        if main_module == '用户管理':
            return 'FUNCTION_ACTIVE'

        # 如果没有子模块，说明只选择了主模块
        if not sub_module:
            return 'MAIN_MODULE_ONLY'

        # 对于数据预览模块，如果已选择子模块，直接进入功能层
        if main_module == '数据预览' and sub_module in PREVIEW_MODULE_MAPPING:
            return 'FUNCTION_ACTIVE'

        # 对于监测分析模块，如果已选择子模块，直接进入功能层
        if main_module == '监测分析' and sub_module == '工业':
            return 'FUNCTION_ACTIVE'

        return 'SUB_MODULE_ONLY'

    except Exception as e:
        logger.error(f"导航层次检测失败: {e}")
        return 'SUB_MODULE_ONLY'


def render_module_selection_guide(main_module: str, guide_type: str, sub_module: Optional[str] = None) -> Dict[str, Any]:
    """
    渲染模块选择指导界面

    Args:
        main_module: 主模块名称
        guide_type: 指导类型 ('sub_module' 或 'function')
        sub_module: 子模块名称（当guide_type为'function'时需要）

    Returns:
        Dict[str, Any]: 渲染结果
    """
    # 所有主模块都显示统一的欢迎页面样式
    if guide_type == 'sub_module':
        # 显示简洁的欢迎页（居中显示）
        st.markdown(f"""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 60vh;
            text-align: center;
        ">
            <h1 style="font-size: 3em; margin-bottom: 1rem;">欢迎使用{main_module}</h1>
            <hr style="width: 50%; border: 1px solid #ccc; margin-top: 1rem;">
        </div>
        """, unsafe_allow_html=True)

        return {
            'status': 'success',
            'content_type': f'{main_module}_welcome',
            'guide_type': guide_type,
            'main_module': main_module,
            'sub_module': sub_module
        }
    else:
        st.markdown("")

    return {
        'status': 'success',
        'content_type': 'selection_guide',
        'guide_type': guide_type,
        'main_module': main_module,
        'sub_module': sub_module
    }


def render_platform_header() -> None:
    """
    渲染平台标题头部 - 经济运行分析平台标题、分割线、机构信息
    """
    st.markdown("""
    <div class="platform-header">
        <h1 class="platform-title">经济运行分析平台</h1>
        <hr class="platform-divider">
        <p class="platform-subtitle">国家信息中心经济预测部政策仿真实验室</p>
    </div>
    """, unsafe_allow_html=True)


def render_welcome_page(main_module: str, sub_module: Optional[str] = None) -> Dict[str, Any]:
    """
    渲染欢迎页面 - 只在首页显示平台标题和机构信息

    Args:
        main_module: 主模块名称
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 渲染结果
    """
    # 只在欢迎页面显示平台标题和机构信息
    render_platform_header()

    return {
        'status': 'success',
        'content_type': 'welcome',
        'main_module': main_module,
        'sub_module': sub_module
    }


def render_user_management_content(sub_module: Optional[str]) -> Dict[str, Any]:
    """
    渲染用户管理内容

    Args:
        sub_module: 子模块名称

    Returns:
        Dict[str, Any]: 渲染结果
    """
    try:
        # 如果有子模块，渲染对应的子模块内容
        if sub_module:
            result = render_user_management_sub_module(sub_module)
            if result == "success":
                return {
                    'status': 'success',
                    'content_type': 'user_management',
                    'main_module': '用户管理',
                    'sub_module': sub_module
                }
            else:
                return {
                    'status': 'error',
                    'content_type': 'user_management',
                    'main_module': '用户管理',
                    'sub_module': sub_module,
                    'message': result
                }
        else:
            # 没有子模块，显示用户管理主页
            UserManagementWelcomePage.render()
            return {
                'status': 'success',
                'content_type': 'user_management',
                'main_module': '用户管理',
                'sub_module': None
            }
            
    except Exception as e:
        st.error(f"用户管理模块渲染失败: {e}")
        logger.error(f"用户管理模块渲染失败: {e}")
        return {
            'status': 'error',
            'content_type': 'user_management',
            'main_module': '用户管理',
            'sub_module': sub_module,
            'message': str(e)
        }


__all__ = [
    'render_main_content', 'get_content_config',
    'route_to_content', 'render_data_preview_content', 'render_monitoring_analysis_content',
    'render_model_analysis_content', 'render_data_exploration_content', 'render_user_management_content',
    'get_module_icon', 'get_module_description',
    'validate_content_config', 'detect_navigation_level',
    'render_module_selection_guide', 'render_welcome_page', 'render_platform_header',
    'check_user_permission', 'render_permission_denied',
    'PREVIEW_MODULE_MAPPING'
]
