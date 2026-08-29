from __future__ import annotations

import pytest

from dashboard.models.DFM.decomp.core.model_loader import ModelLoader
from dashboard.models.DFM.decomp.utils.exceptions import ModelLoadError
from dashboard.models.DFM.decomp.utils.validators import validate_model_data
from dashboard.models.DFM.results.ui.pages.domain import DFMMetadataAccessor


def _metadata() -> dict:
    return {
        "selected_variables": ["A", "B"],
        "model_params": {"k_factors": 2, "algorithm": "classical"},
        "var_industry_map": {"A": "行业一", "B": "行业二"},
        "training_start_date": "2025-01-01",
        "train_end_date": "2025-06-30",
        "validation_start_date": "2025-07-01",
        "validation_end_date": "2025-12-31",
    }


def test_metadata_accessor_reads_canonical_training_fields() -> None:
    accessor = DFMMetadataAccessor(_metadata())

    assert accessor.training_info.n_variables == 2
    assert accessor.training_info.n_factors == 2
    assert accessor.training_info.n_industries == 2
    assert accessor.is_ddfm is False


def test_metadata_accessor_does_not_accept_removed_alias_fields() -> None:
    accessor = DFMMetadataAccessor(
        {
            "best_variables": ["A"],
            "best_params": {"k_factors": 1, "algorithm": "classical"},
        }
    )

    with pytest.raises(KeyError, match="selected_variables"):
        accessor.training_info
    with pytest.raises(KeyError, match="model_params"):
        accessor.is_ddfm


def test_model_loader_requires_algorithm_in_model_params() -> None:
    loader = ModelLoader()
    loader._metadata = {"model_params": {"algorithm": "deep_learning"}}
    assert loader.detect_model_type() == "deep_learning"

    loader._metadata = {"algorithm": "deep_learning"}
    with pytest.raises(ModelLoadError, match="model_params.algorithm"):
        loader.detect_model_type()


def test_model_data_validation_reports_empty_metadata_without_raising() -> None:
    valid, errors = validate_model_data(None, None)

    assert valid is False
    assert "元数据为空" in errors
