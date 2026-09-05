"""数据探索页面共享的会话级解析结果。"""

from __future__ import annotations

from typing import Any

from htfa.exploration.core.data_source import (
    ExploreDataset,
    fingerprint_uploaded_file,
    load_explore_dataset,
)
from htfa.app.state.shared_dataset import get_shared_dataset_file

DATASET_STATE_KEY = "exploration.dataset.parsed"
DATASET_DEPENDENT_WIDGET_KEYS = (
    "bivariate_table_select",
)


def get_explore_dataset(st_obj, file_input: Any) -> ExploreDataset | None:
    """按内容指纹复用一次契约解析结果。"""
    state = st_obj.session_state
    if file_input is None:
        file_input = get_shared_dataset_file()
    if file_input is None:
        cached = state.get(DATASET_STATE_KEY)
        return cached if isinstance(cached, ExploreDataset) else None

    fingerprint = fingerprint_uploaded_file(file_input)
    cached = state.get(DATASET_STATE_KEY)
    if (
        isinstance(cached, ExploreDataset)
        and cached.fingerprint == fingerprint
    ):
        return cached

    dataset = load_explore_dataset(file_input)
    for key in DATASET_DEPENDENT_WIDGET_KEYS:
        state.pop(key, None)
    state[DATASET_STATE_KEY] = dataset
    return dataset


__all__ = [
    "DATASET_DEPENDENT_WIDGET_KEYS",
    "DATASET_STATE_KEY",
    "get_explore_dataset",
]
