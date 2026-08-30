"""SARIMAX 族的模型适配器。

该模块是 SARIMAX 页面与通用模型工作流之间的适配层；通用 UI 不需要
识别 Ts 的具体结果类型。模型结果视图和模拟能力分别由模型族 adapter
拥有，共享 adapter 只承载真正中性的结果行为。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from dashboard.models.common.contracts import (
    EstimationResultView,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    ModelingInput,
    ResidualDiagnosticView,
    SimulationRequest,
)
from dashboard.models.SARIMAX.core.model_config import (
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    RDLConfig,
    SARIMAXConfig,
)
from dashboard.models.SARIMAX.core.diagnostics import (
    recommended_residual_diagnostic_lags,
    run_residual_diagnostics,
)
from dashboard.models.SARIMAX.core.forecasting import produce_forecast
from dashboard.models.SARIMAX.core.forecast_planning import normalise_model_dates
from dashboard.models.SARIMAX.core.modeling import (
    fit_dynamic_model,
    select_auto_sarimax_candidate,
    select_auto_sarimax_result,
    translate_ts_error,
)
from dashboard.models.SARIMAX.core.result_views import (
    _best_result,
    _candidate_labels,
    build_ardl_result_view,
    build_rdl_result_view,
    build_sarimax_result_view,
)
from dashboard.models.SARIMAX.core.simulation import (
    build_sarimax_simulation_comparison,
)


def is_automatic_config(options: Any) -> bool:
    """判断配置是否会执行候选模型搜索。"""
    return isinstance(options, (AutoSARIMAXConfig, AutoRDLConfig, AutoARDLConfig))


def _select_auto_sarimax_result(
    result: Any,
    selection: str | tuple[str, Any],
) -> Any:
    """按自动 SARIMAX/RDL 的信息准则或候选模型重新选择结果。"""
    if not hasattr(result, "candidate_orders"):
        raise ValueError("当前模型结果不支持重新选择信息准则")
    if isinstance(selection, tuple):
        kind, value = selection
        if kind == "candidate":
            labels = _candidate_labels(result)
            try:
                candidate_index = labels.index(str(value))
            except ValueError as exc:
                raise ValueError("未找到所选候选模型") from exc
            return select_auto_sarimax_candidate(result, candidate_index)
        if kind != "criterion":
            raise ValueError(f"不支持的模型选择类型：{kind!r}")
        selection = value
    return select_auto_sarimax_result(result, selection)


class _TsResultAdapter:
    """共享 Ts 结果中性行为的内部适配器基类。

    这里仅保留所有模型族都需要的拟合、预测和残差诊断行为；模型族
    选阶视图与模拟能力由具体 adapter 自己拥有。
    """

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

    def forecast_context(self, result: Any) -> ForecastContext:
        """提取预测规划需要的日期、样本数和外生变量名称。"""
        best = _best_result(result)
        return ForecastContext(
            model_dates=normalise_model_dates(getattr(best, "dates", None)),
            model_nobs=int(getattr(best, "nobs", 0)),
            exog_names=tuple(getattr(best, "exog_names", ())),
        )

    def forecast(self, result: Any, request: ForecastRequest) -> ForecastResult:
        """使用 Ts 预测并转换为稳定预测结果。"""
        best = _best_result(result)
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

    def residual_diagnostics(self, result: Any) -> ResidualDiagnosticView:
        """准备残差诊断图和页面所需的稳定诊断上下文。"""
        best = _best_result(result)
        residuals = np.asarray(best.residuals, dtype=float)
        nobs = int(np.isfinite(residuals).sum())
        lags = recommended_residual_diagnostic_lags(nobs)
        figure = None
        figure_error = None
        try:
            figure, _ = best.plot_diagnostics()
        except Exception as exc:
            figure_error = translate_ts_error(exc)
        return ResidualDiagnosticView(
            effective_nobs=nobs,
            lags=lags,
            figure=figure,
            figure_error=figure_error,
        )

    def residual_test_table(self, result: Any, *, lags: int) -> pd.DataFrame:
        """执行残差检验并隐藏底层结果对象的属性访问。"""
        return run_residual_diagnostics(_best_result(result), lags=lags)


class SARIMAXAdapter(_TsResultAdapter):
    """承载手动和自动 SARIMAX 的模型特有配置、视图和模拟能力。"""

    model_name = "SARIMAX"
    config_types = (SARIMAXConfig, AutoSARIMAXConfig)

    def result_view(self, result: Any) -> EstimationResultView:
        """将 SARIMAX 结果转换为通用估计视图。"""
        return build_sarimax_result_view(result)

    def select_result(
        self,
        result: Any,
        selection: str | tuple[str, Any],
    ) -> Any:
        """按信息准则或候选模型重新选择 SARIMAX 结果。"""
        return _select_auto_sarimax_result(result, selection)

    def simulate(self, result: Any, request: SimulationRequest) -> Any:
        """按稳定模拟请求生成纯 SARIMAX 模拟路径比较结果。"""
        return build_sarimax_simulation_comparison(
            _best_result(result),
            n_paths=request.n_paths,
            seed=request.seed,
            confidence_level=request.confidence_level,
            acf_lags=request.acf_lags,
        )


class RDLAdapter(_TsResultAdapter):
    """承载固定传递函数加 SARIMAX 误差的 RDL 配置和结果视图。"""

    model_name = "RDL"
    config_types = (RDLConfig, AutoRDLConfig)

    def result_view(self, result: Any) -> EstimationResultView:
        """将 RDL 结果转换为通用估计视图。"""
        return build_rdl_result_view(result)

    def select_result(
        self,
        result: Any,
        selection: str | tuple[str, Any],
    ) -> Any:
        """按信息准则或候选模型重新选择 RDL 误差结果。"""
        return _select_auto_sarimax_result(result, selection)


class ARDLAdapter(_TsResultAdapter):
    """承载标准 ARDL 的模型特有配置和结果视图。"""

    model_name = "ARDL"
    config_types = (ARDLConfig, AutoARDLConfig)

    def result_view(self, result: Any) -> EstimationResultView:
        """将标准 ARDL 结果转换为通用估计视图。"""
        return build_ardl_result_view(result)

    def select_result(
        self,
        result: Any,
        selection: str | tuple[str, Any],
    ) -> Any:
        """拒绝标准 ARDL 不支持的页面候选覆盖操作。"""
        del result, selection
        raise ValueError("当前 ARDL 结果不支持重新选择候选模型")


class DynamicRegressionAdapter(_TsResultAdapter):
    """按配置或结果选择具体模型 adapter，供统一页面工作流使用。"""

    _adapters = (SARIMAXAdapter(), RDLAdapter(), ARDLAdapter())

    @classmethod
    def _adapter_for(cls, options: Any) -> _TsResultAdapter:
        for adapter in cls._adapters:
            if isinstance(options, adapter.config_types):
                return adapter
        raise TypeError(f"不支持的动态回归配置：{type(options).__name__}")

    @classmethod
    def _adapter_for_result(cls, result: Any) -> _TsResultAdapter:
        best = _best_result(result)
        if getattr(best, "model_type", None) == "ARDL":
            return cls._adapters[2]
        if getattr(best, "distributed_lag_names", ()):
            return cls._adapters[1]
        return cls._adapters[0]

    def fit(
        self,
        inputs: ModelingInput,
        options: Any,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Any:
        """将拟合请求路由到配置所属的模型 adapter。"""
        return self._adapter_for(options).fit(
            inputs,
            options,
            progress_callback=progress_callback,
        )

    def result_view(self, result: Any) -> EstimationResultView:
        """将结果视图请求路由到结果所属的模型 adapter。"""
        return self._adapter_for_result(result).result_view(result)

    def select_result(
        self,
        result: Any,
        selection: str | tuple[str, Any],
    ) -> Any:
        """将结果选择请求路由到结果所属的模型 adapter。"""
        return self._adapter_for_result(result).select_result(result, selection)


__all__ = [
    "ARDLAdapter",
    "DynamicRegressionAdapter",
    "RDLAdapter",
    "SARIMAXAdapter",
    "is_automatic_config",
]
