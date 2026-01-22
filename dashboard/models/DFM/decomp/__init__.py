# -*- coding: utf-8 -*-
"""
DFM 影响分解后端模块

专注于分析新数据发布对已有nowcast值的影响，而非重新计算nowcast。
主要功能：
- 模型文件和数据提取
- 数据发布影响分析
- 影响贡献分解和归因
- 可视化报告生成
"""

from .api import execute_news_analysis

__version__ = "1.0.0"
__author__ = "HTFA Team"

# 导出的主要接口
__all__ = ['execute_news_analysis']