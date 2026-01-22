# -*- coding: utf-8 -*-
"""
DFM训练模块UI层

提供DFM模型训练的用户界面组件
"""

from dashboard.models.DFM.train.ui.pages import render_dfm_model_training_page
from dashboard.models.DFM.train.ui.components import (
    VariableSelectionComponent,
    DateRangeComponent,
    ModelParametersComponent,
    TrainingStatusComponent
)

__all__ = [
    'render_dfm_model_training_page',
    'VariableSelectionComponent',
    'DateRangeComponent',
    'ModelParametersComponent',
    'TrainingStatusComponent'
]

__version__ = '1.0.0'
