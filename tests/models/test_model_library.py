from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from htfa.models.univariate.common.model_library import (
    ModelContext,
    ModelLibrary,
    ModelLibraryStore,
)


@dataclass
class MutableModel:
    values: list[int]


class UncopyableModel:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot copy")


def _context(dataset_fingerprint: str = "dataset-1") -> ModelContext:
    return ModelContext(
        dataset_fingerprint=dataset_fingerprint,
        mode="手动配置",
        target="target",
        exog_names=("input",),
        training_range=("2020-01-01", "2023-12-01"),
        preprocessing=("去零",),
        missing_value_method="无",
        response_log=False,
        exog_log_names=(),
    )


def test_save_keeps_a_deep_copy_and_exposes_provenance() -> None:
    library = ModelLibrary()
    model = MutableModel([1])
    saved_at = datetime(2026, 9, 2, 10, 30, tzinfo=timezone.utc)

    record = library.save(
        model,
        family="SARIMAX",
        signature="signature-1",
        context=_context(),
        label="GDP baseline",
        saved_at=saved_at,
    )
    model.values.append(2)

    assert len(library.records) == 1
    assert record.model_object.values == [1]
    assert record.label == "GDP baseline"
    assert record.family == "SARIMAX"
    assert record.signature == "signature-1"
    assert record.context == _context()
    assert record.saved_at == saved_at


def test_same_signature_replaces_object_but_preserves_identity_and_label() -> None:
    library = ModelLibrary()
    first = library.save(
        MutableModel([1]),
        family="RDL",
        signature="signature-1",
        context=_context(),
        label="kept alias",
        saved_at=datetime(2026, 9, 2, 10, 30, tzinfo=timezone.utc),
    )

    second = library.save(
        MutableModel([2]),
        family="RDL",
        signature="signature-1",
        context=_context("dataset-2"),
        label="new alias is ignored on update",
        saved_at=datetime(2026, 9, 2, 11, 30, tzinfo=timezone.utc),
    )

    assert second.record_id == first.record_id
    assert second.label == "kept alias"
    assert second.model_object.values == [2]
    assert second.context.dataset_fingerprint == "dataset-2"
    assert second.saved_at.hour == 11
    assert len(library.records) == 1


def test_save_without_label_generates_a_readable_default() -> None:
    library = ModelLibrary()

    record = library.save(
        MutableModel([1]),
        family="ARDL",
        signature="signature-1",
        context=_context(),
        saved_at=datetime(2026, 9, 2, 11, 30, tzinfo=timezone.utc),
    )

    assert record.label == "ARDL | target | 2026-09-02 11:30"


def test_failed_save_does_not_replace_existing_record() -> None:
    library = ModelLibrary()
    existing = library.save(
        MutableModel([1]),
        family="SARIMAX",
        signature="signature-1",
        context=_context(),
        label="existing",
    )

    with pytest.raises(RuntimeError, match="cannot copy"):
        library.save(
            UncopyableModel(),
            family="SARIMAX",
            signature="signature-1",
            context=_context(),
            label="broken",
        )

    current = library.records[0]
    assert current.record_id == existing.record_id
    assert current.label == "existing"
    assert current.model_object.values == [1]


def test_delete_and_clear_only_affect_the_model_library() -> None:
    library = ModelLibrary()
    first = library.save(
        MutableModel([1]),
        family="SARIMAX",
        signature="signature-1",
        context=_context(),
    )
    second = library.save(
        MutableModel([2]),
        family="ARDL",
        signature="signature-2",
        context=_context(),
    )

    assert library.delete(first.record_id) is True
    assert [record.record_id for record in library.records] == [second.record_id]
    assert library.delete(first.record_id) is False

    library.clear()
    assert library.records == ()


def test_same_library_identifier_shares_records_and_other_identifier_isolated() -> None:
    store = ModelLibraryStore()
    first_token = store.create()
    second_token = store.create()
    first_library = store.get(first_token)
    same_library = store.get(first_token)
    other_library = store.get(second_token)

    assert first_library is same_library
    assert first_library is not other_library

    first_library.save(
        MutableModel([1]),
        family="SARIMAX",
        signature="signature-1",
        context=_context(),
    )

    assert len(same_library.records) == 1
    assert other_library.records == ()


def test_store_reset_clears_process_local_libraries() -> None:
    store = ModelLibraryStore()
    token = store.create()
    assert store.get(token) is not None

    store.reset()

    assert store.get(token) is None


def test_model_library_rejects_unsupported_model_family() -> None:
    with pytest.raises(ValueError, match="模型族"):
        ModelLibrary().save(
            MutableModel([1]),
            family="DFM",
            signature="signature-1",
            context=_context(),
        )
