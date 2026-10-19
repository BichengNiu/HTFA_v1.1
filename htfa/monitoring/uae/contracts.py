"""阿联酋监测的纯数据契约。

本模块不依赖 Streamlit，供数据适配、计算、诊断和 UI 共同使用。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class ProvenanceKind(str, Enum):
    """指标来源类型。"""

    REAL = "真实数据"


class EvidenceClass(str, Enum):
    """诊断证据类型。"""

    ACCOUNTING = "核算事实"


@dataclass(frozen=True)
class DataProvenance:
    """单个语义指标的数据来源和覆盖口径。"""

    indicator_id: str
    display_name: str
    kind: ProvenanceKind
    source: str
    frequency: str
    unit: str
    coverage: str
    as_of: str


@dataclass(frozen=True)
class EvidenceItem:
    """诊断中的一条可审计证据。"""

    label: str
    value: float | str
    unit: str
    evidence_class: EvidenceClass
    as_of: str


@dataclass(frozen=True)
class UAEDataBundle:
    """已发布序列及其可追溯来源的监测数据集。"""

    series_by_id: Mapping[str, pd.Series]
    provenance_by_id: Mapping[str, DataProvenance]

    def require_ids(self, indicator_ids: set[str]) -> None:
        """一次报告全部缺失语义指标。"""

        missing = sorted(indicator_ids - set(self.series_by_id))
        if missing:
            raise ValueError("阿联酋监测缺少必需指标: " + ", ".join(missing))

    def require_series(self, indicator_id: str) -> pd.Series:
        """返回指标副本，避免调用方修改共享数据。"""

        self.require_ids({indicator_id})
        return self.series_by_id[indicator_id].copy()

    def require_provenance(self, indicator_id: str) -> DataProvenance:
        """获取单个指标的来源记录。"""

        self.require_ids({indicator_id})
        try:
            return self.provenance_by_id[indicator_id]
        except KeyError as exc:
            raise ValueError(f"指标缺少来源记录: {indicator_id}") from exc
