"""阿联酋经济监测模块。"""

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    DataProvenance,
    DiagnosticResult,
    EvidenceClass,
    EvidenceItem,
    ProvenanceKind,
    UAEDataBundle,
)
from dashboard.analysis.uae.renderer import render_uae_monitoring

__all__ = [
    "ConfidenceLevel",
    "DataProvenance",
    "DiagnosticResult",
    "EvidenceClass",
    "EvidenceItem",
    "ProvenanceKind",
    "UAEDataBundle",
    "render_uae_monitoring",
]
