# -*- coding: utf-8 -*-
"""
应用初始化器 - 简化版
提供统一的初始化接口，遵循KISS原则
"""

import os
import sys
import warnings
import logging
import shutil
import glob
from pathlib import Path
import streamlit as st

logger = logging.getLogger(__name__)


# ==================== 环境初始化 ====================

def setup_environment():
    """设置环境变量和Python路径"""
    from dashboard.core.backend.config import get_core_config

    # 设置环境变量
    config = get_core_config()
    for key, value in config.get_env_vars().items():
        os.environ[key] = value

    # 忽略警告
    warnings.filterwarnings("ignore")

    # 配置Streamlit日志
    streamlit_logger = logging.getLogger("streamlit")
    streamlit_logger.setLevel(logging.CRITICAL)
    streamlit_logger.propagate = False

    # 设置项目路径
    current_dir = Path(__file__).parent.parent.parent
    project_root = current_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    logger.debug("环境初始化完成")


# ==================== Streamlit初始化 ====================

def configure_streamlit():
    """配置Streamlit页面"""
    if not st.session_state.get('core.streamlit_configured', False):
        st.session_state['core.streamlit_configured'] = True
        logger.info("Streamlit配置完成")


def load_styles():
    """加载应用样式"""
    from dashboard.core.ui.utils.style_initializer import get_ui_initializer

    ui_initializer = get_ui_initializer()
    ui_initializer.load_styles()
    logger.info("样式加载完成")


# ==================== 资源预加载 ====================

def preload_resources():
    """预加载关键资源"""
    from dashboard.core.backend.resource import get_resource_loader

    loader = get_resource_loader()
    loader.preload_critical_resources()
    logger.info("关键资源预加载完成")


# ==================== 缓存清理 ====================

def clear_cache_and_logs():
    """清理缓存、日志和临时文件"""
    try:
        current_dir = Path(__file__).parent.parent.parent
        project_root = current_dir.parent

        cleanup_targets = [
            project_root / "cache",
            current_dir / "cache",
            project_root / "logs",
            current_dir / "logs",
            project_root / "*.tmp",
            project_root / "*.log",
            current_dir / "*.tmp",
            current_dir / "*.log"
        ]

        cleaned_count = 0
        for target in cleanup_targets:
            if target.exists():
                if target.is_dir():
                    for item in target.iterdir():
                        if item.is_file():
                            item.unlink()
                            cleaned_count += 1
                        elif item.is_dir():
                            shutil.rmtree(item)
                            cleaned_count += 1
                elif target.is_file():
                    target.unlink()
                    cleaned_count += 1
            elif "*" in str(target):
                pattern_files = glob.glob(str(target))
                for file_path in pattern_files:
                    os.remove(file_path)
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"缓存清理完成，清理了 {cleaned_count} 项")
        else:
            logger.debug("没有需要清理的缓存或日志")

    except Exception as e:
        logger.error(f"缓存清理失败: {e}")


# ==================== 主初始化函数 ====================

def initialize_app(enable_cleanup=False):
    """
    应用初始化主函数

    Args:
        enable_cleanup: 是否启用启动时清理缓存（默认False）

    Returns:
        初始化状态字典
    """
    try:
        # 1. 清理缓存（可选）
        if enable_cleanup:
            clear_cache_and_logs()

        # 2. 环境初始化
        setup_environment()

        # 3. Streamlit配置
        configure_streamlit()

        # 4. 加载样式
        load_styles()

        # 5. 预加载资源
        preload_resources()

        logger.info("应用初始化完成")
        return {'status': 'success', 'message': '应用初始化成功'}

    except Exception as e:
        logger.error(f"应用初始化失败: {e}")
        return {'status': 'error', 'message': str(e)}


