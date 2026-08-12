"""工业指标权重分组映射。"""

from typing import Dict, List, Tuple

import pandas as pd


def build_weights_mapping(
    df_weights: pd.DataFrame,
    target_columns: List[str],
) -> Dict[str, Dict]:
    """构建指标到分类与权重行的映射。"""
    weights_mapping = {}
    for _, row in df_weights.iterrows():
        indicator_name = row["指标名称"]
        if pd.notna(indicator_name) and indicator_name in target_columns:
            weights_mapping[indicator_name] = {
                "出口依赖": row["出口依赖"],
                "上中下游": row["上中下游"],
                "三大产业": row.iloc[1] if len(row) > 1 else None,
                "weights_row": row,
            }
    return weights_mapping


def categorize_indicators(
    weights_mapping: Dict[str, Dict],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]]]:
    """按出口依赖、产业链位置和三大产业对指标分类。"""
    export_groups: Dict[str, List[str]] = {}
    stream_groups: Dict[str, List[str]] = {}
    industry_groups: Dict[str, List[str]] = {}

    for indicator, info in weights_mapping.items():
        for field, groups in (
            ("出口依赖", export_groups),
            ("上中下游", stream_groups),
            ("三大产业", industry_groups),
        ):
            category = info[field]
            if pd.notna(category):
                groups.setdefault(category, []).append(indicator)

    return export_groups, stream_groups, industry_groups


__all__ = ["build_weights_mapping", "categorize_indicators"]
