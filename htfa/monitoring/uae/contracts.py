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
    SIMULATED = "模拟数据"


class EvidenceClass(str, Enum):
    """诊断证据类型。"""

    ACCOUNTING = "核算事实"


class ConfidenceLevel(str, Enum):
    """诊断置信度。"""

    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


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
    note: str = ""

    @property
    def is_simulated(self) -> bool:
        """是否为运行时模拟数据。"""

        return self.kind is ProvenanceKind.SIMULATED


@dataclass(frozen=True)
class EvidenceItem:
    """诊断中的一条可审计证据。"""

    label: str
    value: float | str
    unit: str
    evidence_class: EvidenceClass
    provenance_kind: ProvenanceKind
    as_of: str
    note: str = ""


@dataclass(frozen=True)
class DiagnosticResult:
    """确定性诊断引擎的输出。"""

    title: str
    summary: str
    confidence: ConfidenceLevel
    confidence_reasons: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    limitation: str

    @property
    def uses_simulated_data(self) -> bool:
        """诊断是否使用了模拟证据。"""

        return any(
            item.provenance_kind is ProvenanceKind.SIMULATED
            for item in self.evidence
        )


@dataclass(frozen=True)
class UAEDataBundle:
    """真实和模拟序列合并后的监测数据集。"""

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

    def is_simulated(self, indicator_id: str) -> bool:
        """指标是否为模拟序列。"""

        return self.require_provenance(indicator_id).is_simulated
