# -*- coding: utf-8 -*-
"""
应用初始化模块
提供应用初始化核心功能
"""

from dashboard.core.backend.initialization.initializer import (
    initialize_app,
    setup_environment,
    configure_streamlit,
    load_styles,
    preload_resources,
    clear_cache_and_logs
)

__all__ = [
    'initialize_app',
    'setup_environment',
    'configure_streamlit',
    'load_styles',
    'preload_resources',
    'clear_cache_and_logs'
]
