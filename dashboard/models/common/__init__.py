"""可复用模型估计工作流的公共协议。"""

from .contracts import (
    EstimationResultView,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
    ResidualDiagnosticView,
    SimulationRequest,
)
from .state import ModelStateLifecycle, StateStore
from .workflow import ModelAdapter, ModelWorkflow

__all__ = [
    "EstimationResultView",
    "ForecastContext",
    "ForecastRequest",
    "ForecastResult",
    "ModelingInput",
    "ResidualDiagnosticView",
    "SimulationRequest",
    "ModelStateLifecycle",
    "ModelAdapter",
    "ModelWorkflow",
    "StateStore",
]
