"""把正式工作簿解析结果转换为阿联酋监测语义数据。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.analysis.uae.contracts import (
    DataProvenance,
    ProvenanceKind,
    UAEDataBundle,
)
from dashboard.analysis.uae.indicator_catalog import (
    INDICATOR_SPECS,
    UAE_SIGNATURE_IDS,
)
from dashboard.analysis.uae.simulation import merge_runtime_simulation
from dashboard.preview.core.workbook_parser import parse_preview_workbook

DEFAULT_UAE_WORKBOOK = Path("data") / "阿联酋.xlsx"


def load_real_uae_bundle(file_input: Any) -> UAEDataBundle:
    """读取真实工作簿；不生成模拟数据。"""

    try:
        parsed = parse_preview_workbook(
            file_input,
            module_name="uae_monitoring",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(
            "当前文件不是可识别的阿联酋监测工作簿；"
            f"工作簿协议校验失败：{exc}"
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
        matches = [alias for alias in spec.aliases if alias in available]
        if len(matches) > 1:
            raise ValueError(
                f"指标{spec.indicator_id}匹配到多个真实序列: "
                + ", ".join(matches)
            )
        if not matches:
            continue

        workbook_name = matches[0]
        metadata = metadata_map[workbook_name]
        resolved[spec.indicator_id] = (
            available[workbook_name].dropna().copy()
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
            note=f"工作簿指标：{workbook_name}",
        )

    missing_signature = sorted(UAE_SIGNATURE_IDS - set(resolved))
    if missing_signature:
        raise ValueError(
            "当前文件不是可识别的阿联酋监测工作簿；缺少: "
            + ", ".join(missing_signature)
        )

    return UAEDataBundle(
        series_by_id=resolved,
        provenance_by_id=provenance,
    )


def load_runtime_uae_bundle(
    file_input: Any,
) -> UAEDataBundle:
    """加载真实数据，并仅为缺失指标补充运行时模拟序列。"""

    return merge_runtime_simulation(load_real_uae_bundle(file_input))
