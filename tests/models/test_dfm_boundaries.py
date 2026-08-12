import ast
from pathlib import Path

import pandas as pd

from dashboard.models.DFM.train.training.config import TrainingConfig
from dashboard.models.DFM.train.utils.data_utils import load_and_validate_data


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
        "dashboard/models/DFM/train/ui/pages/model_training_page.py"
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
        "dashboard/models/DFM/prep/modules/variable_transformer.py"
    ).read_text(encoding="utf-8")

    assert "def transform_dataframe(" not in source
    assert "def get_transform_summary(" not in source
