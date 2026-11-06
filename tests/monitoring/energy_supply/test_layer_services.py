"""Behavior at the new storage, calculation and presentation boundaries."""

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from htfa.monitoring.energy_supply.contracts import DashboardQuery
from htfa.monitoring.energy_supply.data import portwatch_windows, storage
from htfa.monitoring.energy_supply.processing import (
    ais_history,
    dashboard_service,
    field_catalog,
    vessel_display,
)
from htfa.monitoring.energy_supply.ui.cache_policy import snapshot_cache


def _database(path, value):
    with storage.job_database(path):
        storage.initialize()
        storage.set_meta("test_value", value)
    return path


def test_maintenance_cannot_open_a_different_database_for_writing(tmp_path):
    candidate = _database(tmp_path / "candidate.duckdb", 1)
    other = tmp_path / "other.duckdb"
    with storage.job_database(candidate):
        with pytest.raises(RuntimeError, match="候选数据库"):
            with storage.connect(other):
                pytest.fail("The wrong database was opened")
    assert not other.exists()


def test_raw_catalog_storage_does_not_load_business_review_documents(tmp_path):
    with storage.job_database(tmp_path / "catalog.duckdb"):
        storage.initialize()
        with patch.object(
            storage, "read_json", side_effect=AssertionError("Unexpected enrichment")
        ):
            storage.save_catalog(
                "ports", [{"portid": "port1", "name": "Raw source name"}]
            )
            assert storage.load_catalog("ports") == [
                {"portid": "port1", "name": "Raw source name"}
            ]


def test_ui_cache_isolates_databases_and_invalidates_replaced_snapshot(tmp_path):
    first = _database(tmp_path / "first.duckdb", 1)
    second = _database(tmp_path / "second.duckdb", 2)
    calls = []

    @snapshot_cache(max_entries=8)
    def read_value():
        calls.append(True)
        return storage.meta("test_value")

    try:
        with patch.object(storage, "DB_PATH", first):
            assert read_value() == read_value() == 1
        with patch.object(storage, "DB_PATH", second):
            assert read_value() == 2
        with storage.job_database(first):
            storage.set_meta("test_value", 3)
        with patch.object(storage, "DB_PATH", first):
            assert read_value() == 3
        assert len(calls) == 3
    finally:
        read_value.clear()


def test_vessel_translation_cache_isolates_snapshot_documents(tmp_path):
    for name, chinese in (("one", "一港"), ("two", "二港")):
        database = _database(tmp_path / f"{name}.duckdb", 1)
        with storage.job_database(database):
            storage.put_binary_document(
                "data/vessel_destinations_zh.json",
                storage.encode({chinese: ["ALPHA PORT"]}).encode(),
                "application/json",
            )
        with patch.object(storage, "DB_PATH", database):
            assert vessel_display.destination_text("ALPHA PORT") == chinese


def test_different_ui_queries_with_matching_arguments_have_separate_caches(tmp_path):
    database = _database(tmp_path / "queries.duckdb", 1)

    @snapshot_cache(max_entries=8)
    def port_result(day):
        return {"kind": "ports", "day": day}

    @snapshot_cache(max_entries=8)
    def vessel_result(day):
        return {"kind": "vessels", "day": day}

    with patch.object(storage, "DB_PATH", database):
        assert port_result("2026-01-01")["kind"] == "ports"
        assert vessel_result("2026-01-01")["kind"] == "vessels"
        port_result.clear()
        assert vessel_result("2026-01-01")["kind"] == "vessels"
    port_result.clear()
    vessel_result.clear()


def test_catalog_build_is_fresh_explicit_and_never_writes_catalogs(tmp_path):
    documents = (
        "GULF_REVIEW_2026-10-03.json",
        "FINAL_REVIEW_2026-10-04.json",
        "data/asset_public_metadata.json",
        "data/gem_historical_production.json",
        "data/production_recheck.json",
        "CONTINUATION_EVIDENCE_2026-10-01.json",
        "GEM_RECONCILIATION_2026-09-30.json",
        "data/coordinate_recheck.json",
    )
    evidence = {path: storage.read_json(path) for path in documents}
    reference = field_catalog.build_catalog()
    with storage.job_database(tmp_path / "review.duckdb"):
        storage.initialize()
        for path, value in evidence.items():
            storage.put_binary_document(
                path, storage.encode(value).encode(), "application/json"
            )
        first = field_catalog.build_catalog()
        assert first == reference
        first[0]["name"] = "modified by the caller"
        assert field_catalog.build_catalog() == reference
        assert storage.load_catalog("assets") == []


def test_derived_event_failure_rolls_back_archive_and_revisions(tmp_path):
    row = {
        "mmsi": "123456789",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "lat": 26.5,
        "lon": 56.5,
        "source": "regression",
        "category": "tanker",
    }
    with storage.job_database(tmp_path / "archive.duckdb"):
        storage.initialize()
        with patch(
            "htfa.monitoring.energy_supply.processing.sea_tracking.update_events",
            side_effect=RuntimeError("event failure"),
        ):
            with pytest.raises(RuntimeError, match="event failure"):
                ais_history.archive_reports([row])
        with storage.connect() as connection:
            assert (
                connection.execute("SELECT count(*) FROM ais_reports").fetchone()[0]
                == 0
            )
        assert storage.revision("ais") == storage.revision("sea") == 0


def test_display_preparation_never_collects_or_writes():
    with (
        patch(
            "htfa.monitoring.energy_supply.data.portwatch_client.query",
            side_effect=AssertionError("Unexpected network request"),
        ),
        patch(
            "htfa.monitoring.energy_supply.data.openwaters_client.urlopen",
            side_effect=AssertionError("Unexpected network request"),
        ),
        patch.object(
            storage, "save_catalog", side_effect=AssertionError("Unexpected write")
        ),
    ):
        context = dashboard_service.load_context()
        state = dashboard_service.prepare_snapshot(context, DashboardQuery())
    assert state.assets == context.assets
    assert state.selected_day == context.newest_day


def test_chart_adapter_arguments_match_the_installed_ts_signature():
    from Ts.TsPlots import plot_series

    from htfa.monitoring.energy_supply.ui import charts

    parameters = inspect.signature(plot_series).parameters
    tree = ast.parse(Path(charts.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "plot_series"
    ]
    assert calls
    for call in calls:
        assert all(keyword.arg in parameters for keyword in call.keywords)


@pytest.mark.parametrize(
    "kind, node, metric",
    [
        ("ports", "port1", "portcalls"),
        ("chokepoints", "chokepoint1", "n_total"),
    ],
)
def test_portwatch_windows_verify_complete_pages_before_saving(
    tmp_path, kind, node, metric
):
    from datetime import date

    day = date(2026, 1, 1)
    valid = {"ObjectId": 1, "date": day.isoformat(), "portid": node, metric: 0}
    with storage.job_database(tmp_path / "window.duckdb"):
        storage.initialize()
        responses = [{"count": 1}, {"features": [{"attributes": valid}]}, {"count": 1}]
        with patch.object(portwatch_windows.pw, "query", side_effect=responses):
            rows, receipt = portwatch_windows.fetch_window(
                kind, (node,), day, day, force=True
            )
        assert rows[0][metric] == 0
        assert receipt["count_verified"]
        revision = storage.revision(kind)
        invalid = {**valid, metric: -1}
        with patch.object(
            portwatch_windows.pw,
            "query",
            side_effect=[
                {"count": 1},
                {"features": [{"attributes": invalid}]},
            ],
        ):
            with pytest.raises(portwatch_windows.DownloadError, match="非负数值"):
                portwatch_windows.fetch_window(kind, (node,), day, day, force=True)
        assert (
            storage.cached_portwatch_observations(kind, (node,), day, day)[0][metric]
            == 0
        )
        assert storage.revision(kind) == revision
