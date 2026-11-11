"""Data access belongs to a feature, never a top-level shared layer."""
import ast
import importlib.util
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from htfa.models.dfm.data.workbooks import read_training_tables
from htfa.models.univariate.common.contracts.dataset import ModelDataset
from htfa.models.univariate.data.datasets import build_model_dataset
from tooling.source_tree import python_sources

ROOT = Path(__file__).resolve().parents[1]


def test_root_data_and_processing_layers_are_removed():
    for name in ('data', 'processing'):
        assert not (ROOT / 'htfa' / name).exists()
        assert importlib.util.find_spec('htfa.' + name) is None
    for feature in ('preview', 'exploration', 'models/dfm', 'models/univariate',
                    'monitoring/industrial', 'monitoring/uae', 'monitoring/energy_supply'):
        assert (ROOT / 'htfa' / feature / 'data').is_dir(), feature
    for source in python_sources(ROOT / 'htfa'):
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            modules = [node.module or ''] if isinstance(node, ast.ImportFrom) else (
                [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            )
            assert not any(module == old or module.startswith(old + '.')
                           for module in modules for old in ('htfa.data', 'htfa.processing')), source


def test_model_dataset_is_owned_by_models_and_preserves_valid_zero():
    frame = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=2), 'value': [0.0, 1.0]})
    result = build_model_dataset(frame, 'input.csv', 'content-and-settings')
    assert isinstance(result, ModelDataset)
    assert result.frame['value'].tolist() == [0.0, 1.0]
    assert result.time_column == 'date'
    assert result.fingerprint == 'content-and-settings'


def test_dfm_reader_owns_prepared_workbook_schema_validation():
    file_input = BytesIO()
    file_input.name = 'prepared.xlsx'
    with pd.ExcelWriter(file_input, engine='openpyxl') as writer:
        pd.DataFrame({'date': ['2025-01-01'], 'value': [0.0]}).to_excel(writer, sheet_name='data', index=False)
    file_input.seek(0)
    with pytest.raises(ValueError, match='Excel'):
        read_training_tables(file_input)
