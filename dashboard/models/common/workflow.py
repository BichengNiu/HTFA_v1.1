"""跨模型估计工作流和适配器协议。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import pandas as pd

from .contracts import (
    EstimationResultView,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
    ResidualDiagnosticView,
)


class ModelAdapter(Protocol):
    """模型差异的唯一扩展点。"""

    model_name: str

    def fit(
        self,
        inputs: ModelingInput,
        options: Any,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Any:
        """按模型特有配置拟合并返回不透明的底层结果。"""

    def result_view(self, result: Any) -> EstimationResultView:
        """将底层结果转换为通用估计结果视图。"""

    def forecast(self, result: Any, request: ForecastRequest) -> ForecastResult:
        """按通用预测请求生成稳定的预测结果。"""

    def residual_diagnostics(self, result: Any) -> ResidualDiagnosticView:
        """准备残差诊断图和诊断上下文。"""

    def residual_test_table(self, result: Any, *, lags: int) -> pd.DataFrame:
        """执行残差检验并返回稳定的结构化结果表。"""


class ModelWorkflow:
    """把通用输入、适配器和稳定结果协议组合成一个工作流。

    Parameters
    ----------
    adapter : ModelAdapter
        承担模型特有拟合、结果转换和预测行为的适配器。
    """

    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    def fit(
        self,
        inputs: ModelingInput,
        options: Any,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Any:
        """通过适配器拟合模型。"""
        return self.adapter.fit(
            inputs,
            options,
            progress_callback=progress_callback,
        )

    def result_view(self, result: Any) -> EstimationResultView:
        """通过适配器生成通用估计结果视图。"""
        return self.adapter.result_view(result)

    def forecast(self, result: Any, request: ForecastRequest) -> ForecastResult:
        """通过适配器生成通用预测结果。"""
        return self.adapter.forecast(result, request)

    def residual_diagnostics(self, result: Any) -> ResidualDiagnosticView:
        """通过适配器准备残差诊断上下文。"""
        return self.adapter.residual_diagnostics(result)

    def residual_test_table(self, result: Any, *, lags: int) -> pd.DataFrame:
        """通过适配器执行残差检验。"""
        return self.adapter.residual_test_table(result, lags=lags)


__all__ = ["ModelAdapter", "ModelWorkflow"]
