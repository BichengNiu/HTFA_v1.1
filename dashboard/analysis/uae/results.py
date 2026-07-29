"""阿联酋宏观监测服务的结构化输出。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from dashboard.analysis.uae.contracts import (
    DataProvenance,
    DiagnosticResult,
    ProvenanceKind,
)


@dataclass(frozen=True)
class MetricSnapshot:
    """页面顶部的一个结果指标。"""

    label: str
    value: float
    unit: str
    period: str
    provenance_kind: ProvenanceKind
    help_text: str = ""


@dataclass(frozen=True)
class MacroPanelResult:
    """一个宏观结果系统的完整页面数据。"""

    key: str
    title: str
    headline: DiagnosticResult
    metrics: tuple[MetricSnapshot, ...]
    series_groups: Mapping[str, pd.DataFrame]
    decomposition_tables: Mapping[str, pd.DataFrame]
    provenance: Mapping[str, DataProvenance]
    methodology_notes: tuple[str, ...]

    @property
    def uses_simulated_data(self) -> bool:
        return any(item.is_simulated for item in self.provenance.values())


@dataclass(frozen=True)
class MonitoringDashboardResult:
    """总览和各详细结果系统。"""

    panels: Mapping[str, MacroPanelResult]

    def require_panel(self, key: str) -> MacroPanelResult:
        try:
            return self.panels[key]
        except KeyError as exc:
            raise ValueError(f"未知的阿联酋监测页面: {key}") from exc

