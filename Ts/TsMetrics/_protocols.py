"""Structural contracts used by forecast evaluation."""

from __future__ import annotations

from typing import Any, Protocol


class PredictionProtocol(Protocol):
    """Forecast arrays returned by a fitted model."""

    mean: Any
    lower: Any | None
    upper: Any | None


class FittedModelProtocol(Protocol):
    """Fitted model state required by the evaluation engine."""

    nobs: int
    model_type: str

    def predict(
        self,
        *,
        start: int,
        end: int,
        alpha: float,
        **kwargs: Any,
    ) -> PredictionProtocol:
        """Return forecasts over an inclusive range."""


class EvaluationCloneProtocol(Protocol):
    """Isolated model clone that can be fitted."""

    def fit(self) -> FittedModelProtocol:
        """Fit the isolated evaluation window."""


class EvaluationModelProtocol(Protocol):
    """Complete structural contract accepted by OOS and backtest."""

    data: Any
    _evaluation_target_name: str

    def _clone_for_evaluation(
        self,
        data: Any,
        exog: Any | None = None,
        *,
        dates: Any | None = None,
    ) -> EvaluationCloneProtocol:
        """Clone model configuration with isolated evaluation data."""

    def _evaluation_actual(self, observed: Any, train_data: Any) -> Any:
        """Return the observable target used for evaluation."""

    def _evaluation_predict_kwargs(
        self,
        start: int,
        stop: int,
    ) -> dict[str, Any]:
        """Return model-specific prediction context."""

    def _validate_evaluation(self, context: str) -> None:
        """Validate model-specific evaluation requirements."""
