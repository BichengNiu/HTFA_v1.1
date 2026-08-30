"""SARIMAX 族的模型适配器。

该模块是 SARIMAX 页面与通用模型工作流之间的适配层；通用 UI 不需要
识别 Ts 的具体结果类型。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from dashboard.models.common.contracts import (
    EstimationResultView,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
)
from dashboard.models.SARIMAX.core.modeling import (
    build_auto_sarimax_criterion_table,
    fit_dynamic_model,
    format_sarimax_order,
    produce_forecast,
    select_auto_sarimax_result,
)
from dashboard.models.SARIMAX.core.model_config import (
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    RDLConfig,
    SARIMAXConfig,
)


def best_result(result: Any) -> Any:
    """取得自动选阶结果的最佳拟合对象，不暴露具体 Ts 类。"""
    return getattr(result, "best_result", result)


def is_automatic_config(options: Any) -> bool:
    """判断配置是否会执行候选模型搜索。"""
    return isinstance(options, (AutoSARIMAXConfig, AutoRDLConfig, AutoARDLConfig))


def _float_attribute(result: Any, best: Any, name: str) -> float:
    value = getattr(result, name, getattr(best, name, np.nan))
    return float(value)


class _TsResultAdapter:
    """共享 Ts 结果转换行为的内部适配器基类。"""

    model_name = "动态回归模型"
    config_types: tuple[type, ...] = ()

    def fit(
        self,
        inputs: ModelingInput,
        options: Any,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Any:
        """使用现有 Ts 编排拟合模型。"""
        if self.config_types and not isinstance(options, self.config_types):
            names = ", ".join(item.__name__ for item in self.config_types)
            raise TypeError(
                f"{self.model_name} 适配器只接受 {names}；"
                f"收到 {type(options).__name__}"
            )
        return fit_dynamic_model(
            inputs.series,
            inputs.exog,
            options,
            progress_callback=progress_callback,
        )

    def result_view(self, result: Any) -> EstimationResultView:
        """将 SARIMAX 族结果转换为通用估计视图。"""
        best = best_result(result)
        selection_table = None
        selection_title = None
        selection_message = None
        selected_label = None
        selection_options: tuple[str, ...] = ()
        selection_value = None
        selection_help = None
        metadata: dict[str, Any] = {}

        candidate_orders = getattr(result, "candidate_orders", None)
        if candidate_orders is not None:
            selection_title = "自动选阶结果"
            attempted = getattr(result, "n_attempted", None) or len(
                getattr(result, "candidate_results", ())
            )
            successful = len(getattr(result, "candidate_results", ()))
            selection_message = (
                f"候选评估完成：共尝试 {attempted} 个，成功 {successful} 个，"
                f"失败 {max(0, attempted - successful)} 个。"
            )
            selection_table = build_auto_sarimax_criterion_table(result)
            selected_label = format_sarimax_order(
                result.best_order,
                getattr(result, "best_seasonal_order", None),
            )
            metadata["selection_criterion"] = getattr(
                result, "selection_criterion", None
            )
            selection_options = ("aic", "bic", "hqic", "aicc")
            selection_value = getattr(result, "selection_criterion", "aic")
            selection_help = (
                "从上方结果表中选择一个信息准则，采用该列最小值对应的模型。"
            )
            metadata["search_metadata"] = getattr(result, "search_metadata", {})
        elif hasattr(result, "criterion_table") and hasattr(result, "ar_lags"):
            selection_title = "自动选阶结果"
            table = result.criterion_table.copy()
            criterion = getattr(result, "selection_criterion", "bic")
            selection_message = (
                f"候选评估完成：共评估 {len(table)} 个 ARDL 候选模型。"
            )
            selection_table = table.rename(
                columns={
                    "criterion": str(criterion).upper(),
                    "target_lags": "目标滞后",
                    "input_lags": "输入滞后",
                }
            )
            selected_label = (
                f"最优 ARDL：目标滞后 {result.ar_lags}；"
                f"输入滞后 {result.distributed_lags}"
            )
            metadata["selection_criterion"] = criterion
            metadata["search_method"] = getattr(result, "search_method", None)

        return EstimationResultView(
            model_name=str(getattr(best, "model_type", self.model_name)),
            result=result,
            converged=bool(getattr(best, "converged", False)),
            effective_nobs=int(
                getattr(best, "effective_nobs", getattr(best, "nobs", 0))
            ),
            optimizer=getattr(best, "optimizer", None),
            aic=_float_attribute(result, best, "aic"),
            bic=_float_attribute(result, best, "bic"),
            log_likelihood=_float_attribute(result, best, "log_likelihood"),
            summary=str(best.summary()),
            metadata=metadata,
            selection_title=selection_title,
            selection_message=selection_message,
            selection_table=selection_table,
            selected_label=selected_label,
            selection_options=selection_options,
            selection_value=selection_value,
            selection_help=selection_help,
        )

    def select_result(self, result: Any, criterion: str) -> Any:
        """按信息准则重新选择自动 SARIMAX 结果。"""
        if hasattr(result, "candidate_orders"):
            return select_auto_sarimax_result(result, criterion)
        raise ValueError("当前模型结果不支持重新选择信息准则")

    def forecast(self, result: Any, request: ForecastRequest) -> ForecastResult:
        """使用 Ts 预测并转换为稳定预测结果。"""
        best = best_result(result)
        raw = produce_forecast(
            best,
            start=request.start,
            end=request.end,
            alpha=request.alpha,
            dynamic=request.dynamic,
            future_exog=request.future_exog,
            future_dates=request.future_dates,
        )
        return ForecastResult(
            dates=raw.get("dates"),
            mean=raw["mean"],
            lower=raw["lower"],
            upper=raw["upper"],
            alpha=raw["alpha"],
            steps=raw["steps"],
            start=raw["start"],
            end=raw["end"],
            prediction=raw["prediction"],
        )


class SARIMAXAdapter(_TsResultAdapter):
    """仅承载手动和自动 SARIMAX 的模型特有配置。"""

    model_name = "SARIMAX"
    config_types = (SARIMAXConfig, AutoSARIMAXConfig)


class RDLAdapter(_TsResultAdapter):
    """仅承载固定传递函数加 SARIMAX 误差的 RDL 配置。"""

    model_name = "RDL"
    config_types = (RDLConfig, AutoRDLConfig)


class ARDLAdapter(_TsResultAdapter):
    """仅承载标准 ARDL 的模型特有配置。"""

    model_name = "ARDL"
    config_types = (ARDLConfig, AutoARDLConfig)


class DynamicRegressionAdapter(_TsResultAdapter):
    """按配置选择具体模型适配器，供统一页面工作流使用。"""

    _adapters = (SARIMAXAdapter(), RDLAdapter(), ARDLAdapter())

    @classmethod
    def _adapter_for(cls, options: Any) -> _TsResultAdapter:
        for adapter in cls._adapters:
            if isinstance(options, adapter.config_types):
                return adapter
        raise TypeError(f"不支持的动态回归配置：{type(options).__name__}")

    def fit(
        self,
        inputs: ModelingInput,
        options: Any,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Any:
        """将拟合请求路由到配置所属的模型适配器。"""
        return self._adapter_for(options).fit(
            inputs,
            options,
            progress_callback=progress_callback,
        )


__all__ = [
    "ARDLAdapter",
    "DynamicRegressionAdapter",
    "RDLAdapter",
    "SARIMAXAdapter",
    "best_result",
    "is_automatic_config",
]
