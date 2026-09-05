import ast
from pathlib import Path

import pandas as pd

from htfa.models.dfm.prep import processor as processor_module
from htfa.models.dfm.prep.processor import DataPreparationProcessor
from htfa.models.dfm.decomp.core.impact_analyzer import (
    DataRelease,
    ImpactAnalyzer,
    ImpactResult,
)
from htfa.models.dfm.decomp.core.model_loader import SavedNowcastData
from htfa.models.dfm.train.training.config import TrainingConfig
from htfa.models.dfm.train.utils.data_utils import load_and_validate_data
from htfa.models.dfm.utils.parallel_config import ParallelConfig


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


def test_training_page_public_entry_only_orchestrates_sections():
    path = Path(
        "htfa/models/dfm/train/ui/pages/model_training_page.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    entry = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_dfm_model_training_page"
    )

    assert entry.end_lineno - entry.lineno < 40
    assert len(entry.body) <= 10


def test_variable_transformer_has_one_active_batch_entry():
    source = Path(
        "htfa/models/dfm/prep/modules/variable_transformer.py"
    ).read_text(encoding="utf-8")

    assert "def transform_dataframe(" not in source
    assert "def get_transform_summary(" not in source


def test_news_impact_pipeline_uses_saved_nowcast_data_directly(monkeypatch):
    analyzer = ImpactAnalyzer(SavedNowcastData())

    def calculate(release):
        return ImpactResult(
            release=release,
            impact_on_target=1.0,
            kalman_weight=0.5,
        )

    monkeypatch.setattr(analyzer, "calculate_single_release_impact", calculate)
    releases = [
        DataRelease(
            timestamp=pd.Timestamp("2025-06-30"),
            variable_name="inside",
            observed_value=1.0,
            expected_value=0.0,
        ),
        DataRelease(
            timestamp=pd.Timestamp("2025-07-01"),
            variable_name="outside",
            observed_value=1.0,
            expected_value=0.0,
        ),
    ]

    result = analyzer.analyze_sequential_impacts(
        releases,
        pd.Timestamp("2025-06-15"),
    )

    assert [item.release.variable_name for item in result.individual_impacts] == [
        "inside"
    ]
    assert not Path(
        "htfa/models/dfm/decomp/core/nowcast_extractor.py"
    ).exists()


def test_frequency_alignment_honors_disabled_parallel_config(monkeypatch):
    processor = object.__new__(DataPreparationProcessor)
    processor.enable_freq_alignment = True
    processor.parallel_config = ParallelConfig(enabled=False)
    processor.data_start_date = None
    processor.data_end_date = None
    processor.target_freq = "W-FRI"
    processor.enable_borrowing = True
    processor.removal_log = []

    captured = {}

    def fake_process_frequencies(**kwargs):
        captured.update(kwargs)
        return {"monthly": pd.DataFrame()}, {}, []

    monkeypatch.setattr(
        processor_module,
        "parallel_process_frequencies",
        fake_process_frequencies,
    )

    processor._step5_smart_missing_detection_and_align(
        {"monthly": {"combined": pd.DataFrame({"A": [1.0]})}}
    )

    assert captured["n_jobs"] == 1


def test_frequency_alignment_uses_threshold_before_parallel(monkeypatch):
    processor = object.__new__(DataPreparationProcessor)
    processor.enable_freq_alignment = True
    processor.parallel_config = ParallelConfig(
        enabled=True,
        n_jobs=2,
        min_variables_for_parallel=2,
    )
    processor.data_start_date = None
    processor.data_end_date = None
    processor.target_freq = "W-FRI"
    processor.enable_borrowing = True
    processor.removal_log = []

    captured = {}

    def fake_process_frequencies(**kwargs):
        captured.update(kwargs)
        return {}, {}, []

    monkeypatch.setattr(
        processor_module,
        "parallel_process_frequencies",
        fake_process_frequencies,
    )

    processor._step5_smart_missing_detection_and_align(
        {"monthly": {"combined": pd.DataFrame({"A": [1.0]})}}
    )

    assert captured["n_jobs"] == 1
