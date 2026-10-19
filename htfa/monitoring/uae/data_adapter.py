"""把 DuckDB 发布快照转换为阿联酋监测语义数据。"""

from __future__ import annotations

import pandas as pd

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source

from htfa.monitoring.uae.contracts import (
    DataProvenance,
    ProvenanceKind,
    UAEDataBundle,
)
from htfa.monitoring.uae.indicator_catalog import (
    INDICATOR_SPECS,
    UAE_SIGNATURE_IDS,
)
from htfa.data.economic_workbook.core.workbook_parser import parse_economic_workbook

UAE_ANALYSIS_INDICATOR_NAMES = frozenset(
    spec.indicator_name for spec in INDICATOR_SPECS
)


def load_real_uae_bundle(source: PublishedUAEData) -> UAEDataBundle:
    """读取已发布的 DuckDB 数据并校验指标协议。"""

    try:
        parsed = parse_economic_workbook(
            require_published_source(source),
            module_name="uae_monitoring",
            indicator_allowlist=UAE_ANALYSIS_INDICATOR_NAMES,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(
            "当前数据不是可识别的阿联酋监测快照；"
            f"数据协议校验失败：{exc}"
        ) from exc

    available = {
        name: frame[name]
        for frame in parsed.dataframes.values()
        for name in frame.columns
    }
    metadata_map = parsed.indicator_metadata_map
    resolved: dict[str, pd.Series] = {}
    provenance: dict[str, DataProvenance] = {}

    for spec in INDICATOR_SPECS:
        indicator_name = spec.indicator_name
        if indicator_name not in available:
            continue

        metadata = metadata_map[indicator_name]
        resolved[spec.indicator_id] = (
            available[indicator_name].dropna().copy()
        )
        provenance[spec.indicator_id] = DataProvenance(
            indicator_id=spec.indicator_id,
            display_name=spec.display_name,
            kind=ProvenanceKind.REAL,
            source=metadata.sheet_source,
            frequency=metadata.frequency,
            unit=metadata.unit,
            coverage=spec.coverage,
            as_of=metadata.updated_at,
        )

    missing_signature = sorted(UAE_SIGNATURE_IDS - set(resolved))
    if missing_signature:
        raise ValueError(
            "当前数据不是可识别的阿联酋监测快照；缺少: "
            + ", ".join(missing_signature)
        )

    return UAEDataBundle(
        series_by_id=resolved,
        provenance_by_id=provenance,
    )
