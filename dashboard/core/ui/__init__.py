# -*- coding: utf-8 -*-
"""
统一UI组件库
提供标准化的UI组件和页面模板，包含静态资源管理
"""

__version__ = "1.0.0"
__author__ = "HFTA Development Team"

# 静态资源路径
from pathlib import Path
STATIC_DIR = Path(__file__).parent / "static"
