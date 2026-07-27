"""多变量分析页面的纯参数与结果签名契约。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from dashboard.explore.core.series_utils import fingerprint_dataframe


def parse_dtw_alignment_mode(choice: str) -> tuple[bool, bool]:
    """将 DTW 对齐选项转换为频率对齐和时点对齐开关。"""
    modes = {
        "freq_align_strict": (True, True),
        "freq_align_loose": (True, False),
        "no_align": (False, False),
    }
    try:
        return modes[choice]
    except KeyError as exc:
        raise ValueError(f"不支持的 DTW 对齐模式: {choice}") from exc


def build_dtw_backend_options(params: dict[str, Any]) -> dict[str, Any]:
    """从唯一的 UI 参数对象构造 DTW 后端选项。"""
    constrained = bool(params["enable_window_constraint"])
    radius = params.get("radius")
    if constrained and radius is None:
        raise ValueError("启用窗口约束时必须提供 radius")

    return {
        "window_type_param": (
            "固定大小窗口 (Radius约束)" if constrained else "无限制"
        ),
        "window_size_param": radius if constrained else None,
        "dist_metric_display_param": "欧氏距离",
        "enable_freq_alignment": bool(params["enable_alignment"]),
        "freq_agg_method": params["agg_method"],
        "strict_alignment": bool(params["strict_alignment"]),
        "standardization_method": params["standardization_method"],
    }


def build_dtw_result_signature(
    data: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[Any, ...]:
    """覆盖数据与所有计算参数的 DTW 结果签名。"""
    return (
        fingerprint_dataframe(data),
        params["target_series"],
        tuple(params["comparison_series"]),
        bool(params["enable_window_constraint"]),
        params.get("radius"),
        bool(params["enable_alignment"]),
        bool(params["strict_alignment"]),
        params["agg_method"],
        params["standardization_method"],
    )


def build_lead_lag_result_signature(
    data: pd.DataFrame,
    target_variable: str,
    candidate_variables: list[str],
    config: dict[str, Any],
) -> tuple[Any, ...]:
    """覆盖数据、变量和统计配置的 Lead-Lag 结果签名。"""
    return (
        fingerprint_dataframe(data),
        target_variable,
        tuple(candidate_variables),
        int(config["max_lags"]),
        bool(config["standardize_for_kl"]),
        config["standardization_method"],
        bool(config["enable_frequency_alignment"]),
        config.get("target_frequency"),
        config["freq_agg_method"],
    )


__all__ = [
    "build_dtw_backend_options",
    "build_dtw_result_signature",
    "build_lead_lag_result_signature",
    "parse_dtw_alignment_mode",
]
