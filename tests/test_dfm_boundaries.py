from pathlib import Path
from io import BytesIO

import pandas as pd

from dashboard.models.DFM.prep import (
    ExportService,
    StatsService,
    load_mappings_once,
    prepare_dfm_data_simple,
)
from dashboard.models.DFM.prep.parallel import parallel_process_frequencies
from dashboard.models.DFM.prep.ui.components import (
    render_value_replacement_section,
)
from dashboard.models.DFM.train.ui.components import FileUploaderComponent
from dashboard.models.DFM.train.training.config import TrainingConfig
from dashboard.models.DFM.train.utils.data_utils import load_and_validate_data


def test_dfm_public_surface_contains_only_active_paths():
    assert callable(load_mappings_once)
    assert callable(prepare_dfm_data_simple)
    assert callable(parallel_process_frequencies)
    assert callable(render_value_replacement_section)
    assert FileUploaderComponent.__name__ == "FileUploaderComponent"
    assert StatsService.__name__ == "StatsService"
    assert ExportService.__name__ == "ExportService"


def test_training_page_does_not_modify_import_path_or_import_dead_status_ui():
    source = Path(
        "dashboard/models/DFM/train/ui/pages/model_training_page.py"
    ).read_text(encoding="utf-8")

    assert "sys.path" not in source
    assert "TrainingStatusComponent" not in source
    assert "TrainModelConfig" not in source
    assert "_TRAIN_UI_IMPORT_ERROR_MESSAGE" not in source


def test_dfm_has_no_empty_base_or_wrapper_layers():
    obsolete_files = (
        "dashboard/models/DFM/ui/base.py",
        "dashboard/models/DFM/train/utils/state_manager.py",
        "dashboard/models/DFM/prep/ui/state_keys.py",
        "dashboard/models/DFM/decomp/utils/logging_config.py",
    )
    for file_name in obsolete_files:
        assert not Path(file_name).exists()

    service_source = Path(
        "dashboard/models/DFM/prep/services/ui_backend_service.py"
    ).read_text(encoding="utf-8")
    assert "class UIBackendService" not in service_source
    assert "def transform_variables" in service_source


def test_prep_parallel_config_only_describes_the_active_frequency_pipeline():
    source = Path("dashboard/models/DFM/prep/config.py").read_text(
        encoding="utf-8"
    )
    for obsolete_name in (
        "enable_missing_parallel",
        "min_columns_for_missing_parallel",
        "enable_sheet_parallel",
        "min_sheets_for_parallel",
        "sheet_backend",
        "should_parallelize_missing",
        "should_parallelize_sheets",
    ):
        assert obsolete_name not in source


def test_mapping_cache_uses_uploaded_content_fingerprint(monkeypatch):
    from dashboard.models.DFM.prep import api

    mapping_frame = pd.DataFrame(
        {
            "指标名称": ["指标A"],
            "类型": ["增长"],
            "行业": ["工业"],
            "频率": ["周度"],
            "单位": ["%"],
            "性质": ["流量"],
            "预测变量": ["是"],
            "发布日期": [1],
        }
    )
    calls = []

    def fake_read_excel(file_obj, sheet_name):
        calls.append((file_obj.getvalue(), sheet_name))
        return mapping_frame.copy()

    api._MAPPING_CACHE.clear()
    monkeypatch.setattr(api.pd, "read_excel", fake_read_excel)

    first = api.load_mappings_once(BytesIO(b"same workbook"))
    second = api.load_mappings_once(BytesIO(b"same workbook"))

    assert first["status"] == second["status"] == "success"
    assert len(calls) == 1
    assert second["message"] == "从缓存加载映射表"


def test_training_data_stays_in_memory():
    data = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [3.0, 4.0]},
        index=pd.date_range("2025-01-03", periods=2, freq="W-FRI"),
    )
    config = TrainingConfig(
        data=data,
        training_start="2025-01-03",
        train_end="2025-01-03",
        validation_start="2025-01-10",
        validation_end="2025-01-10",
        selected_indicators=["A"],
    )

    validated, variables = load_and_validate_data(config.data, ["A"])

    assert variables == ["A"]
    assert validated.equals(data)
    assert validated is not data
    assert "data_path" not in TrainingConfig.__dataclass_fields__


def test_dfm_ui_has_no_temp_file_or_state_helper_factories():
    prep_api = Path("dashboard/models/DFM/prep/api.py").read_text(encoding="utf-8")
    config_builder = Path(
        "dashboard/models/DFM/train/ui/utils/config_builder.py"
    ).read_text(encoding="utf-8")

    assert "NamedTemporaryFile" not in prep_api
    assert "NamedTemporaryFile" not in config_builder
    assert not Path("dashboard/models/DFM/ui/state.py").exists()
