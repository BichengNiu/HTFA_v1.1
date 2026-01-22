# -*- coding: utf-8 -*-
"""
训练结果导出模块（合并版）

提供训练结果的文件导出功能:
- 模型文件导出（.joblib）
- 元数据文件导出（.pkl）

所有功能已整合到TrainingResultExporter类中
"""

from .exporter import TrainingResultExporter

__all__ = ['TrainingResultExporter']
