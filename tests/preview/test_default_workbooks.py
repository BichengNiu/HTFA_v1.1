from pathlib import Path

import pandas as pd

from dashboard.preview.core.workbook_parser import normalize_indicator_name
from dashboard.preview.modules.uae.loader import UAELoader


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_uae_template_loads_only_dictionary_registered_indicators():
    template_path = PROJECT_ROOT / "data" / "阿联酋.xlsx"
    loaded = UAELoader().load_and_process_data([template_path])

    dictionary = pd.read_excel(template_path, sheet_name="指标字典")
    registered = {
        normalize_indicator_name(name)
        for name in dictionary["指标名称"].dropna()
    }
    excel_file = pd.ExcelFile(template_path)
    try:
        sheet_indicators = set()
        for sheet_name in excel_file.sheet_names[1:]:
            raw = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                header=None,
                nrows=2,
            )
            if raw.shape[0] < 2:
                continue
            sheet_indicators.update(
                normalize_indicator_name(name)
                for name in raw.iloc[1, 1:].dropna()
            )
    finally:
        excel_file.close()

    unregistered = sheet_indicators - registered

    assert loaded.module_name == "uae"
    assert loaded.indicator_metadata_map
    assert any(not frame.empty for frame in loaded.dataframes.values())
    assert unregistered
    assert set(loaded.indicator_metadata_map) == registered
    assert set(loaded.indicator_metadata_map).isdisjoint(unregistered)
