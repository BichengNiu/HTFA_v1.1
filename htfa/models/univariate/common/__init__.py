"""可复用模型估计工作流的公共协议。"""

from .contracts import (
    EstimationResultView,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
    ResidualDiagnosticView,
)
from htfa.models.univariate.common.processing.state import ModelStateLifecycle, StateStore
from htfa.models.univariate.common.processing.workflow import ModelAdapter, ModelWorkflow

__all__ = [
    "EstimationResultView",
    "ForecastContext",
    "ForecastRequest",
    "ForecastResult",
    "ModelingInput",
    "ResidualDiagnosticView",
    "ModelStateLifecycle",
    "ModelAdapter",
    "ModelWorkflow",
    "StateStore",
]
