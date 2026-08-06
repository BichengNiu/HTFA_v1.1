"""多变量分析结果到表格、指标和下载内容的纯转换。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DTW_MIXED_TYPE_COLUMNS = (
    "DTW距离",
    "对齐路径长度",
    "标准化DTW距离",
)
LEAD_LAG_COLUMN_MAPPING = {
    "target_variable": "目标变量",
    "candidate_variable": "候选变量",
    "k_kl": "最优滞后(KL)",
    "kl_at_k_kl": "最小KL散度",
    "notes": "备注",
}


def format_dtw_results(
    backend_results: list[dict[str, Any]],
    paths: dict[str, dict[str, Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """将 DTW 后端结果转换为稳定的读者表格记录。"""
    constrained = bool(params["enable_window_constraint"])
    radius = params["radius"] if constrained else "N/A"
    formatted = []

    for result in backend_results:
        comparison = result.get("对比变量", "Unknown")
        distance = result.get("DTW距离", "Error")
        path = paths.get(comparison, {}).get("path") or []
        valid_distance = (
            isinstance(distance, (int, float))
            and not np.isnan(distance)
            and np.isfinite(distance)
        )
        if valid_distance:
            path_length = len(path) if path else "N/A"
            normalized = (
                round(float(distance) / path_length, 4)
                if isinstance(path_length, int) and path_length > 0
                else "Error"
            )
            formatted.append(
                {
                    "变量名": comparison,
                    "窗口约束": "启用" if constrained else "禁用",
                    "Radius": radius,
                    "DTW距离": round(float(distance), 4),
                    "对齐路径长度": path_length,
                    "标准化DTW距离": normalized,
                    "分析状态": "计算成功",
                }
            )
            continue

        formatted.append(
            {
                "变量名": comparison,
                "窗口约束": "启用" if constrained else "禁用",
                "Radius": radius,
                "DTW距离": "Error",
                "对齐路径长度": "Error",
                "标准化DTW距离": "Error",
                "分析状态": "计算失败",
            }
        )

    return formatted


def prepare_dtw_display(
    results: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 Arrow 安全展示表和用于指标计算的有效结果。"""
    results_df = pd.DataFrame(results)
    if results_df.empty:
        return results_df, results_df

    valid = results_df[results_df["标准化DTW距离"] != "Error"].copy()
    errors = results_df[results_df["标准化DTW距离"] == "Error"].copy()
    if not valid.empty:
        valid = valid.sort_values("标准化DTW距离")
        ordered = pd.concat([valid, errors], ignore_index=True)
    else:
        ordered = results_df

    display = ordered.copy()
    for column in DTW_MIXED_TYPE_COLUMNS:
        if column in display.columns:
            display[column] = display[column].astype(str).astype(object)
    return display, valid


def prepare_lead_lag_display(results: pd.DataFrame) -> pd.DataFrame:
    """移除内部对象并生成稳定排序的 Lead-Lag 展示表。"""
    display = results.drop(
        columns=["full_kl_divergence_df"],
        errors="ignore",
    ).rename(columns=LEAD_LAG_COLUMN_MAPPING)

    if "最小KL散度" in display.columns:
        display = display.copy()
        display["最小KL散度"] = display["最小KL散度"].round(4)
        display = display.sort_values(
            by="最小KL散度",
            ascending=True,
            na_position="last",
        ).reset_index(drop=True)
    return display


def encode_csv_with_bom(frame: pd.DataFrame) -> bytes:
    """生成只包含一个 UTF-8 BOM 的 Excel 友好 CSV。"""
    return frame.to_csv(index=False).encode("utf-8-sig")


__all__ = [
    "encode_csv_with_bom",
    "format_dtw_results",
    "prepare_dtw_display",
    "prepare_lead_lag_display",
]
