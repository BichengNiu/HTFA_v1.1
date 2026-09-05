"""阿联酋宏观监测服务的结构化输出。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.contracts import (
    DataProvenance,
    DiagnosticResult,
)


@dataclass(frozen=True)
class MacroPanelResult:
    """一个宏观结果系统的完整页面数据。"""

    key: str
    title: str
    headline: DiagnosticResult
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
    unavailable_panels: Mapping[str, str]

    def require_panel(self, key: str) -> MacroPanelResult:
        try:
            return self.panels[key]
        except KeyError as exc:
            reason = self.unavailable_panels.get(key)
            if reason:
                raise ValueError(f"阿联酋监测页面数据不足: {reason}") from exc
            raise ValueError(f"未知的阿联酋监测页面: {key}") from exc
