# -*- coding: utf-8 -*-
"""
DFM模型训练UI组件模块

提供模型训练相关的UI组件，包括：
- 变量选择组件
- 日期范围选择组件
- 参数配置组件
- 训练状态监控组件
"""

from dashboard.models.DFM.train.ui.components.variable_selection import VariableSelectionComponent
from dashboard.models.DFM.train.ui.components.date_range import DateRangeComponent
from dashboard.models.DFM.train.ui.components.model_parameters import ModelParametersComponent
from dashboard.models.DFM.train.ui.components.training_status import TrainingStatusComponent

__all__ = [
    'VariableSelectionComponent',
    'DateRangeComponent',
    'ModelParametersComponent',
    'TrainingStatusComponent'
]
