"""阿联酋宏观监测服务的结构化输出。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.contracts import (
    DataProvenance,
    EvidenceItem,
)


@dataclass(frozen=True)
class MacroPanelResult:
    """宏观图表结果，分别提供绘图数据与包含计算输入的下载数据。"""

    key: str
    evidence: tuple[EvidenceItem, ...]
    limitation: str
    series_groups: Mapping[str, pd.DataFrame]
    download_groups: Mapping[str, pd.DataFrame]
    provenance: Mapping[str, DataProvenance]
    methodology_notes: tuple[str, ...]
