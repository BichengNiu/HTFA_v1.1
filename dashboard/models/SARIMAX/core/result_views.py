"""模型族结果到通用估计视图的转换实现。"""

from __future__ import annotations

from typing import Any

import numpy as np

from dashboard.models.common.contracts import EstimationResultView
from dashboard.models.SARIMAX.core.modeling import (
    build_auto_sarimax_criterion_table,
    format_sarimax_order,
)


def _best_result(result: Any) -> Any:
    """取得自动选阶结果的最佳拟合对象。"""
    return getattr(result, "best_result", result)


def _float_attribute(result: Any, best: Any, name: str) -> float:
    value = getattr(result, name, getattr(best, name, np.nan))
    return float(value)


def _candidate_labels(result: Any) -> tuple[str, ...]:
    """返回自动 SARIMAX/RDL 候选表中的用户可读模型标签。"""
    seasonal_orders = getattr(result, "candidate_seasonal_orders", ())
    return tuple(
        format_sarimax_order(
            order,
            seasonal_orders[index] if index < len(seasonal_orders) else None,
        )
        for index, order in enumerate(result.candidate_orders)
    )


def _candidate_selection_value(result: Any, labels: tuple[str, ...]) -> str | None:
    """返回当前候选是否偏离所选准则的最优模型。"""
    if not labels:
        return None
    current_order = tuple(getattr(result, "best_order", ()))
    current_seasonal = getattr(result, "best_seasonal_order", None)
    current_index = None
    for index, order in enumerate(getattr(result, "candidate_orders", ())):
        seasonal = (
            result.candidate_seasonal_orders[index]
            if index < len(getattr(result, "candidate_seasonal_orders", ()))
            else None
        )
        if tuple(order) == current_order and (
            current_seasonal is None or seasonal == current_seasonal
        ):
            current_index = index
            break
    if current_index is None:
        return None
    criterion = getattr(result, "selection_criterion", "aic")
    values = np.asarray(result.criterion_table[criterion], dtype=float)
    finite = np.isfinite(values)
    criterion_index = (
        int(np.where(finite, values, np.inf).argmin())
        if finite.any()
        else None
    )
    return (
        None
        if current_index == criterion_index
        else labels[current_index]
    )


def _build_base_result_view(
    result: Any,
    *,
    default_model_name: str,
) -> EstimationResultView:
    """构建不含模型族选阶信息的通用估计视图。"""
    best = _best_result(result)
    return EstimationResultView(
        model_name=str(getattr(best, "model_type", default_model_name)),
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
    )


def _build_auto_sarimax_view(
    result: Any,
    *,
    default_model_name: str,
) -> EstimationResultView:
    """构建 SARIMAX 及 RDL 自动选阶结果视图。"""
    best = _best_result(result)
    labels = _candidate_labels(result)
    attempted = getattr(result, "n_attempted", None) or len(
        getattr(result, "candidate_results", ())
    )
    successful = len(getattr(result, "candidate_results", ()))
    return EstimationResultView(
        model_name=str(getattr(best, "model_type", default_model_name)),
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
        metadata={
            "selection_criterion": getattr(result, "selection_criterion", None),
            "search_metadata": getattr(result, "search_metadata", {}),
        },
        selection_title="自动选阶结果",
        selection_message=(
            f"候选评估完成：共尝试 {attempted} 个，成功 {successful} 个，"
            f"失败 {max(0, attempted - successful)} 个。"
        ),
        selection_table=build_auto_sarimax_criterion_table(result),
        selected_label=format_sarimax_order(
            result.best_order,
            getattr(result, "best_seasonal_order", None),
        ),
        selection_options=("aic", "bic", "hqic", "aicc"),
        selection_value=getattr(result, "selection_criterion", "aic"),
        selection_help="从上方结果表中选择一个信息准则，采用该列最小值对应的模型。",
        candidate_options=labels,
        candidate_value=_candidate_selection_value(result, labels),
        candidate_help="默认按左侧准则选择最优模型；选择具体模型后将直接采用该候选。",
    )


def _build_auto_ardl_view(result: Any) -> EstimationResultView:
    """构建标准 ARDL 自动选阶结果视图。"""
    best = _best_result(result)
    criterion = getattr(result, "selection_criterion", "bic")
    table = result.criterion_table.copy()
    return EstimationResultView(
        model_name=str(getattr(best, "model_type", "ARDL")),
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
        metadata={
            "selection_criterion": criterion,
            "search_method": getattr(result, "search_method", None),
        },
        selection_title="自动选阶结果",
        selection_message=f"候选评估完成：共评估 {len(table)} 个 ARDL 候选模型。",
        selection_table=table.rename(
            columns={
                "criterion": str(criterion).upper(),
                "target_lags": "目标滞后",
                "input_lags": "输入滞后",
            }
        ),
        selected_label=(
            f"最优 ARDL：目标滞后 {result.ar_lags}；"
            f"输入滞后 {result.distributed_lags}"
        ),
    )


def build_sarimax_result_view(result: Any) -> EstimationResultView:
    """转换 SARIMAX 结果，包含其自动选阶展示信息。"""
    if getattr(result, "candidate_orders", None) is not None:
        return _build_auto_sarimax_view(result, default_model_name="SARIMAX")
    return _build_base_result_view(result, default_model_name="SARIMAX")


def build_rdl_result_view(result: Any) -> EstimationResultView:
    """转换 RDL 结果，保留其 SARIMAX 误差阶数搜索展示信息。"""
    if getattr(result, "candidate_orders", None) is not None:
        return _build_auto_sarimax_view(result, default_model_name="RDL")
    return _build_base_result_view(result, default_model_name="RDL")


def build_ardl_result_view(result: Any) -> EstimationResultView:
    """转换标准 ARDL 结果，包含其自动滞后搜索展示信息。"""
    if hasattr(result, "criterion_table") and hasattr(result, "ar_lags"):
        return _build_auto_ardl_view(result)
    return _build_base_result_view(result, default_model_name="ARDL")


__all__ = [
    "build_ardl_result_view",
    "build_rdl_result_view",
    "build_sarimax_result_view",
]
