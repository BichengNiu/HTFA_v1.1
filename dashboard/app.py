# -*- coding: utf-8 -*-
"""
经济运行分析平台 - 主dashboard
优化版本：使用统一初始化器和懒加载机制
"""

import sys
import os
import time
import warnings
import logging
import multiprocessing

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if multiprocessing.current_process().name != 'MainProcess':
    # 如果这是子进程，立即退出，不执行任何UI相关代码
    sys.exit(0)

# 在导入Streamlit之前抑制Plotly警告
warnings.filterwarnings('ignore', message='.*keyword arguments have been deprecated.*')
warnings.filterwarnings('ignore', message='.*Use `config` instead.*')
warnings.filterwarnings('ignore', message='.*use_container_width.*')

# Dashboard状态管理使用st.session_state

# 在任何其他导入之前立即抑制 Streamlit 警告
def _suppress_streamlit_warnings():
    """在模块导入前抑制 Streamlit 警告"""
    # 设置环境变量 - 包括日志级别优化
    os.environ.update({
        'STREAMLIT_LOGGER_LEVEL': 'CRITICAL',
        'STREAMLIT_CLIENT_TOOLBAR_MODE': 'minimal',
        'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false',
        'STREAMLIT_CLIENT_SHOW_ERROR_DETAILS': 'false',
        'PYTHONWARNINGS': 'ignore',
        'STREAMLIT_SILENT_IMPORTS': 'true',
        'STREAMLIT_SUPPRESS_WARNINGS': 'true',
        # 优化日志输出级别 - 减少冗余日志
        'LOG_LEVEL': 'WARNING',  # 设置为WARNING级别减少DEBUG/INFO日志
        'ENVIRONMENT': 'production'  # 设置为生产环境模式
    })

    # 抑制所有警告
    warnings.filterwarnings("ignore")

    # 特别抑制Plotly的弃用警告
    warnings.filterwarnings("ignore", message=".*keyword arguments have been deprecated.*")
    warnings.filterwarnings("ignore", message=".*Use.*config.*instead.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="plotly")
    warnings.filterwarnings("ignore", category=FutureWarning, module="plotly")

    # 预先配置 Streamlit 日志器
    streamlit_loggers = [
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner_utils",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.caching",
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.state",
        "streamlit.runtime.state.session_state_proxy",
        "streamlit.web",
        "streamlit.web.server",
        "streamlit.web.bootstrap"
    ]

    # 创建自定义日志过滤器，过滤Plotly相关警告
    class PlotlyWarningFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage()
            # 过滤Plotly废弃警告
            if "keyword arguments have been deprecated" in message:
                return False
            if "Use `config` instead to specify Plotly configuration options" in message:
                return False
            if "Please replace `use_container_width` with `width`" in message:
                return False
            return True

    for logger_name in streamlit_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.addFilter(PlotlyWarningFilter())
        logger.disabled = True
        logger.propagate = False

    # 为根logger也添加过滤器
    logging.root.addFilter(PlotlyWarningFilter())

# 立即执行警告抑制
_suppress_streamlit_warnings()

# 配置全局日志级别，抑制INFO级别日志
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s',
    force=True
)
# 禁用dashboard模块的INFO日志
logging.getLogger('dashboard').setLevel(logging.WARNING)

# 添加项目根目录到Python路径，确保能正确导入dashboard包
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # 上一级目录
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 立即导入streamlit并设置页面配置 - 必须在任何其他操作之前
import streamlit as st

# Monkey patch Streamlit的警告显示函数来过滤Plotly相关警告
_original_warning = st.warning

def _filtered_warning(body, *args, **kwargs):
    """过滤后的warning函数"""
    if isinstance(body, str):
        # 过滤Plotly相关警告
        if "keyword arguments have been deprecated" in body:
            return None
        if "Use `config` instead" in body:
            return None
    return _original_warning(body, *args, **kwargs)

st.warning = _filtered_warning

# 直接设置页面配置，避免导入问题
if 'dashboard_page_config_set' not in st.session_state:
    st.set_page_config(
        page_title="经济运行分析平台",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.session_state['dashboard_page_config_set'] = True

# 基础库导入
import pandas as pd
import re
import altair as alt
from datetime import datetime
import inspect
import traceback as tb

# 应用初始化将在页面配置后进行
# 延迟导入避免触发 @st.cache_resource

# === 导入UI调试工具 ===
from dashboard.core.ui.utils.debug_helpers import (
    debug_log, debug_state_change, debug_navigation, debug_button_click
)

# === 导入核心模块 ===
from dashboard.core import get_resource_loader
from dashboard.core import (
    get_current_main_module,
    get_current_sub_module,
    set_current_sub_module,
    is_transitioning,
    set_transitioning
)
from dashboard.core.ui.utils.style_loader import inject_cached_styles

# 简化初始化，避免循环导入
lazy_loader = None

# 第二阶段优化：导入资源加载器
def initialize_resource_loading():
    """初始化资源加载系统"""
    # 获取资源加载器
    resource_loader = get_resource_loader()

    # 预加载关键资源
    resource_loader.preload_critical_resources()

    return resource_loader

# 注释：已使用统一的 navigation_manager，不再需要额外的状态同步函数

# 延迟初始化函数
def get_resource_manager():
    """延迟获取资源管理器实例 - 简化版本"""
    global lazy_loader

    # 获取当前进程ID用于缓存键
    process_id = os.getpid()

    # 检查缓存
    current_time = time.time()
    cached_loader = st.session_state.get('dashboard.resource_loader_cache', None)
    cached_time = st.session_state.get('dashboard.resource_loader_cache_time', 0)

    # 如果缓存在30分钟内，使用缓存
    if cached_loader and cached_time and current_time - cached_time < 1800:
        return cached_loader

    # 重新初始化资源加载器
    if lazy_loader is None:
        lazy_loader = get_resource_loader()
        # 预加载关键资源
        lazy_loader.preload_critical_resources()

    # 缓存到session_state
    st.session_state['dashboard.resource_loader_cache'] = lazy_loader
    st.session_state['dashboard.resource_loader_cache_time'] = current_time

    return lazy_loader


# 注释：已使用统一的 navigation_manager，不再需要 check_navigation_change 函数


# 配置Altair数据转换器
alt.data_transformers.enable("vegafusion")

# st.sidebar.title("[CHART] 经济运行分析平台")


# extract_industry_name函数已移至utils模块，避免重复定义

from dashboard.core.ui.utils.state_helpers import get_staged_data


# extract_industry_name函数已移至dashboard.utils.industry_utils模块，避免重复定义


MODULE_CONFIG = {
    "数据预览": {
        "工业": None  # 工业数据预览子模块
    },
    "监测分析": {
        "工业": ["工业增加值", "工业企业利润"]
    },
    "模型分析": {
        "DFM 模型": ["数据准备", "模型训练", "模型分析", "新闻分析"]
    },
    "数据探索": {
        "时序性质": ["平稳性分析"],
        "时序关系": ["相关分析", "领先滞后分析"]
    },
    "用户管理": None  # 直接显示用户管理功能
}


def _perform_intelligent_state_cleanup():
    """执行智能状态清理，避免循环渲染"""
    try:
        # 获取所有状态键
        all_keys = list(st.session_state.keys())

        # 清理导航相关的临时状态
        navigation_patterns = ['navigate_to', 'temp_selected', 'rerun', '_transition', '_loading']
        navigation_keys = [k for k in all_keys if any(pattern in str(k) for pattern in navigation_patterns)]

        for key in navigation_keys:
            if key in st.session_state:
                del st.session_state[key]

        # 清理可能导致循环的组件状态
        component_patterns = ['_preview_data', '_processed_data', '_analysis_result', '_cached_']
        component_keys = [k for k in all_keys if any(pattern in str(k) for pattern in component_patterns)]

        for key in component_keys:
            if key in st.session_state:
                del st.session_state[key]

        print(f"[DEBUG Recovery] 清理了 {len(navigation_keys + component_keys)} 个状态键")

    except Exception as e:
        print(f"[DEBUG Recovery] 状态清理失败: {e}")


# 每次都注入CSS样式以确保样式一致性（修复模块切换时样式变化问题）
inject_cached_styles()

# 初始化资源管理器
lazy_loader = get_resource_manager()

# 集成认证中间件
from dashboard.auth.ui.middleware import get_auth_middleware
from dashboard.auth.config import AuthConfig
from dashboard.auth.ui.utils.storage import get_auth_storage_manager

auth_middleware = get_auth_middleware()

# 根据调试模式决定是否需要认证
if AuthConfig.is_debug_mode():
    # 调试模式：跳过认证，使用None作为当前用户
    current_user = None
    debug_log("调试模式已启用，跳过认证环节", "INFO")
else:
    # 生产模式：强制要求认证
    current_user = auth_middleware.require_authentication(show_login=True)

# 如果用户已认证，渲染用户信息到侧边栏
if current_user:
    # 在侧边栏显示用户信息和登出按钮
    from dashboard.auth.ui.components.user_info_panel import render_user_info_panel

    def handle_logout():
        auth_middleware.logout()
        st.rerun()

    render_user_info_panel(current_user, on_logout_callback=handle_logout)

# time模块已在顶部导入
current_time = time.time()

# 检查是否有模块正在加载
all_keys = list(st.session_state.keys())
loading_modules = [key for key in all_keys if key.startswith('_loading_')]
if loading_modules:
    st.stop()

# 检测快速连续重新渲染（回弹检测）- 改进版本
last_render_time = st.session_state.get('dashboard.last_render_time', 0)
render_interval = current_time - last_render_time

# 检查是否是用户主动导航操作导致的重新渲染
is_navigation_triggered = is_transitioning()

# 检查是否在导航操作的时间窗口内（2秒内的导航操作都认为是用户主动的）
if not is_navigation_triggered:
    last_nav_time = st.session_state.get('dashboard.last_navigation_time', 0)
    if current_time - last_nav_time < 2.0:  # 2秒的导航操作窗口
        is_navigation_triggered = True

# 只有在非导航触发且间隔很短的情况下才视为回弹
if render_interval < 0.05 and last_render_time > 0 and not is_navigation_triggered:  # 50ms阈值，排除导航触发
    st.stop()

st.session_state['dashboard.last_render_time'] = current_time

# 如果资源加载器正在初始化，跳过本次渲染
if lazy_loader is None:
    st.info("系统正在初始化，请稍候...")
    st.stop()

try:
    st.session_state['dashboard.initialized'] = True
    st.session_state['dashboard.start_time'] = datetime.now()
except Exception as e:
    st.error(f"状态初始化失败: {e}")
    st.stop()

# 管理器初始化结果已在get_managers()函数中打印，避免重复

# 确保键的唯一性和防止重复渲染
if not st.session_state.get('dashboard.sidebar.rendered', False):
    st.session_state['dashboard.sidebar.rendered'] = True
    st.session_state['dashboard.sidebar.key_counter'] = 0
    st.session_state['dashboard.main_content.rendered'] = False

# 改进的循环渲染检测机制
current_time = time.time()

# 获取渲染跟踪数据
default_tracking = {'count': 0, 'last_reset': time.time(), 'last_render': 0}
tracking = st.session_state.get('dashboard.render_tracking', default_tracking)

# 每30秒重置计数器，避免正常使用被误判
if current_time - tracking['last_reset'] > 30:
    current_ts = time.time()
    tracking = {'count': 0, 'last_reset': current_ts, 'last_render': current_ts}
    st.session_state['dashboard.render_tracking'] = tracking

# 增加渲染计数
tracking['count'] += 1
render_interval = current_time - tracking['last_render']
tracking['last_render'] = time.time()
st.session_state['dashboard.render_tracking'] = tracking

# 改进循环渲染检测：更严格的条件，避免误判用户正常操作
# 只有在极短时间内（<0.05秒）连续渲染超过10次且非导航触发时才认为是循环渲染
is_user_navigation = (is_transitioning() or
                     (current_time - st.session_state.get('dashboard.last_navigation_time', 0) < 3.0))

if (render_interval and render_interval < 0.05 and tracking and tracking['count'] > 10 and
    not is_user_navigation):
    # 只在真正的循环渲染时显示警告，避免对用户造成困扰
    st.warning("检测到异常的页面渲染循环，正在自动修复...")

    # 智能状态清理
    _perform_intelligent_state_cleanup()

    # 重置渲染计数
    current_ts = time.time()
    tracking = {'count': 0, 'last_reset': current_ts, 'last_render': current_ts}
    st.session_state['dashboard.render_tracking'] = tracking

    # 简化恢复信息，减少对用户的干扰
    with st.expander("系统状态", expanded=False):
        st.info("系统已自动修复渲染问题")
        st.info("如果页面仍有异常，请刷新页面")
        if st.button("刷新页面", key="manual_refresh_button"):
            st.rerun()

# 确保key稳定性
stable_key_prefix = st.session_state.get('dashboard.sidebar.stable_key_prefix')
if not stable_key_prefix:
    # 使用更长的时间戳和随机数确保唯一性
    import time
    import random
    import uuid
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    session_id = str(uuid.uuid4())[:8]  # 使用UUID的前8个字符
    stable_key_prefix = f"sidebar_{timestamp}_{random_suffix}_{session_id}"
    st.session_state['dashboard.sidebar.stable_key_prefix'] = stable_key_prefix
key_prefix = stable_key_prefix

# 使用UI模块的完整侧边栏组件
from dashboard.core.ui.components.sidebar import render_complete_sidebar

# 获取用户可访问的模块信息
user_accessible_modules = set()
if current_user and auth_middleware:
    try:
        # 正常模式：使用权限管理器获取用户可访问的模块列表
        accessible_modules_list = auth_middleware.permission_manager.get_accessible_modules(current_user)
        user_accessible_modules = set(accessible_modules_list)
        debug_navigation("权限检查", f"用户 {current_user.username} 可访问 {len(user_accessible_modules)} 个模块: {user_accessible_modules}")
    except Exception as e:
        print(f"[ERROR] 模块权限检查失败: {e}")
        # 如果检查失败，不给任何默认权限，让用户联系管理员
        user_accessible_modules = set()
else:
    # 调试模式：没有用户时给所有权限
    if AuthConfig.is_debug_mode():
        # 获取所有模块名称
        user_accessible_modules = set(MODULE_CONFIG.keys())
        debug_navigation("权限检查", f"调试模式：允许访问所有模块 ({len(user_accessible_modules)} 个)")
    else:
        # 正常模式且未登录：无权限
        user_accessible_modules = set()

# 将权限信息和调试模式状态存储到session_state
st.session_state['auth.debug_mode'] = AuthConfig.is_debug_mode()
st.session_state['auth.user_accessible_modules'] = user_accessible_modules
st.session_state['auth.current_user'] = current_user

# 渲染完整侧边栏（始终渲染，无论是否有选中的模块）
sidebar_result = render_complete_sidebar(MODULE_CONFIG, key_prefix)

# 提取结果
main_selector_result = sidebar_result.get('main_module_result', {})
sub_selector_result = sidebar_result.get('sub_module_result')

selected_main_module_val = main_selector_result.get('selected_module', None)
change_result = main_selector_result.get('success', True)

if sub_selector_result:
    selected_sub_module_val = sub_selector_result.get('selected_sub_module')
else:
    selected_sub_module_val = None

# 处理临时状态恢复
temp_main = st.session_state.get('navigation.temp_selected_main_module')
if temp_main:
    selected_main_module_val = temp_main
    if 'navigation.temp_selected_main_module' in st.session_state:
        del st.session_state['navigation.temp_selected_main_module']
    debug_navigation("临时状态恢复", f"恢复主模块选择: {selected_main_module_val}")

temp_sub = st.session_state.get('navigation.temp_selected_sub_module')
if temp_sub:
    selected_sub_module_val = temp_sub
    st.session_state['navigation.last_clicked_sub_module'] = selected_sub_module_val
    if 'navigation.temp_selected_sub_module' in st.session_state:
        del st.session_state['navigation.temp_selected_sub_module']

# 获取当前状态用于后续逻辑
current_main_module = get_current_main_module()
current_sub_module = get_current_sub_module()

# 立即更新当前模块变量以确保按钮状态同步
if selected_main_module_val != current_main_module:
    debug_state_change("主模块切换", current_main_module, selected_main_module_val, "用户点击按钮")

# 处理主模块切换逻辑
if selected_main_module_val != current_main_module:
    # 设置导航状态为转换中
    set_transitioning(True)
    debug_navigation("转换状态设置", "设置transitioning=True")

    current_main_module = selected_main_module_val

    # 主模块切换时，清除子模块状态以避免状态污染
    debug_navigation("状态清除", "主模块切换，开始清除子模块状态")
    set_current_sub_module(None)

    # 避免重复渲染，只在必要时重新运行
    # 检查是否真的需要重新渲染
    last_change = st.session_state.get('dashboard.last_main_module_change')
    if last_change != selected_main_module_val:
        st.session_state['dashboard.last_main_module_change'] = selected_main_module_val
        debug_navigation("重新渲染", f"主模块切换到 {selected_main_module_val}，触发重新渲染")
else:
    # 确保非切换时清除transitioning状态
    set_transitioning(False)


# 使用UI模块的主内容路由组件
from dashboard.core.ui.components.content_router import render_main_content

# 渲染主内容
content_result = render_main_content()

debug_navigation(
    "主内容渲染",
    f"内容渲染完成 - 模块: {content_result.get('main_module')}, "
    f"子模块: {content_result.get('sub_module')}, "
    f"状态: {content_result.get('status')}"
)

# 在内容渲染完成后清除transitioning状态
set_transitioning(False)

# (End of script)

# ========================================
# 直接启动支持
# ========================================
if __name__ == '__main__':
    import subprocess
    import shutil
    from pathlib import Path

    # 检查是否已经通过启动脚本启动，避免重复执行
    if os.environ.get('HTFA_LAUNCHER_ACTIVE') != 'true':
        # 设置启动标记
        os.environ['HTFA_LAUNCHER_ACTIVE'] = 'true'

        print("=" * 40)
        print("HTFA Dashboard Startup")
        print("=" * 40)
        print()

        # 1. 清理Python缓存
        print("[1/4] 清理Python缓存文件...")
        project_root = Path(__file__).parent.parent
        for pycache in project_root.rglob('__pycache__'):
            shutil.rmtree(pycache, ignore_errors=True)
        for pyc in project_root.rglob('*.pyc'):
            pyc.unlink(missing_ok=True)
        for pyo in project_root.rglob('*.pyo'):
            pyo.unlink(missing_ok=True)
        print("[完成] Python缓存已清理")
        print()

        # 2. 检查并清理端口8501
        print("[2/4] 检查端口占用情况...")
        try:
            result = subprocess.run(
                'netstat -ano | findstr ":8501"',
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout:
                print("[警告] 端口8501已被占用，正在关闭占用进程...")
                # 提取PID并关闭
                for line in result.stdout.strip().split('\n'):
                    if 'LISTENING' in line:
                        parts = line.split()
                        if parts:
                            pid = parts[-1]
                            subprocess.run(f'taskkill /F /PID {pid}',
                                         shell=True,
                                         capture_output=True)
                            print(f"[信息] 已关闭进程 PID: {pid}")
                time.sleep(2)
                print("[完成] 端口已清理")
            else:
                print("[完成] 端口8501空闲")
        except Exception as e:
            print(f"[警告] 端口检查失败: {e}")
        print()

        # 3. 设置环境变量
        print("[3/4] 配置运行环境...")
        os.environ['HTFA_DEBUG_MODE'] = 'true'
        print("[信息] 调试模式: true")
        print()

        # 4. 启动Streamlit
        print("[4/4] 启动应用程序...")
        print()
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run',
            __file__,
            '--server.port=8501'
        ])