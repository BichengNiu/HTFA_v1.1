from __future__ import annotations

from contextlib import nullcontext
from io import BytesIO


class _Tab:
    def __init__(self, is_open: bool) -> None:
        self.open = is_open

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class _TabsHost:
    def __init__(self, open_index: int = 0) -> None:
        self.open_index = open_index
        self.calls: list[tuple[list[str], dict]] = []
        self.errors: list[str] = []

    def tabs(self, labels, **kwargs):
        self.calls.append((list(labels), kwargs))
        return [_Tab(index == self.open_index) for index, _ in enumerate(labels)]

    def error(self, message: str) -> None:
        self.errors.append(message)


def test_high_frequency_topics_only_calls_the_open_topic(monkeypatch) -> None:
    from htfa.monitoring.uae import report

    called: list[str] = []

    def renderer(name):
        def _render(_st_obj, _payload):
            called.append(name)
            return {"status": "success"}

        return _render

    monkeypatch.setattr(
        report,
        "TOPIC_RENDERERS",
        (
            ("oil", "石油", renderer("oil")),
            ("finance", "金融", renderer("finance")),
            ("property", "房地产", renderer("property")),
        ),
    )
    host = _TabsHost(open_index=1)

    result = report.render_high_frequency_topics(host, (b"workbook", "uae.xlsx"))

    assert called == ["finance"]
    assert set(result) == {"finance"}
    assert host.calls[0][1] == {
        "key": "analysis.uae.high_frequency.active_topic",
        "on_change": "rerun",
    }


def test_preview_renderer_only_renders_the_open_tab(monkeypatch) -> None:
    import streamlit as st

    from htfa.data.economic_workbook.shared.renderer import EconomicWorkbookRenderer

    class _Reader:
        def get_state_namespace(self) -> str:
            return "economic_workbook.uae"

    host = _TabsHost(open_index=0)
    renderer = EconomicWorkbookRenderer(_Reader(), module_title="测试")
    rendered: list[str] = []
    monkeypatch.setattr(renderer, "_has_any_data", lambda: True)
    monkeypatch.setattr(renderer, "_render_overview_tab", lambda: rendered.append("overview"))
    monkeypatch.setattr(
        renderer,
        "_render_time_series_tab",
        lambda frequency: rendered.append(frequency),
    )
    monkeypatch.setattr(st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(st, "tabs", host.tabs)

    renderer.render_main_content()

    assert rendered == ["overview"]
    assert host.calls[0][1]["on_change"] == "rerun"


def test_uae_monitoring_only_renders_the_open_top_level_tab(monkeypatch) -> None:
    from htfa.monitoring.uae import renderer

    class _MonitoringHost(_TabsHost):
        def spinner(self, _label):
            return nullcontext()

        def container(self, **_kwargs):
            return nullcontext()

        def info(self, _message: str) -> None:
            return None

    class _Dashboard:
        panels = {"growth": object()}

    upload = BytesIO(b"workbook")
    upload.name = "uae.xlsx"
    host = _MonitoringHost(open_index=0)
    rendered: list[tuple[str, ...]] = []
    monkeypatch.setattr(renderer, "get_shared_dataset_file", lambda: upload)
    monkeypatch.setattr(renderer, "_render_report_header", lambda *_args: None)
    monkeypatch.setattr(renderer, "_latest_high_frequency_month", lambda *_args: None)
    monkeypatch.setattr(
        renderer,
        "_build_monitoring_dashboard_cached",
        lambda *_args: _Dashboard(),
    )
    monkeypatch.setattr(
        renderer,
        "_render_growth_tab",
        lambda _st, _dashboard, titles: rendered.append(tuple(titles)),
    )
    monkeypatch.setattr(
        renderer,
        "render_high_frequency_topics",
        lambda *_args: (_ for _ in ()).throw(AssertionError("hidden tab rendered")),
    )

    result = renderer.render_uae_monitoring(host)

    assert rendered == [renderer.GROWTH_OVERVIEW_GROUPS]
    assert result["high_frequency"] == {}
    assert host.calls[0][1]["on_change"] == "rerun"


def test_uploaded_excel_never_enters_high_frequency_data_path(monkeypatch) -> None:
    """高频标签页始终只读 DuckDB，不能因共享上传文件而解析工作簿。"""

    from htfa.monitoring.uae import renderer

    class _MonitoringHost(_TabsHost):
        def spinner(self, _label):
            return nullcontext()

        def container(self, **_kwargs):
            return nullcontext()

    upload = BytesIO(b"workbook")
    upload.name = "uae.xlsx"
    host = _MonitoringHost(open_index=2)
    payloads: list[tuple[bytes | None, str]] = []
    monkeypatch.setattr(renderer, "get_shared_dataset_file", lambda: upload)
    monkeypatch.setattr(renderer, "_render_report_header", lambda *_args: None)
    monkeypatch.setattr(
        renderer,
        "_build_monitoring_dashboard_cached",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("high-frequency view parsed Excel")
        ),
    )
    monkeypatch.setattr(
        renderer,
        "render_high_frequency_topics",
        lambda _st, payload: payloads.append(payload) or {},
    )

    result = renderer.render_uae_monitoring(host)

    assert result["status"] == "duckdb_only"
    assert payloads == [(None, "uae.duckdb")]


def test_government_finance_loader_is_cached_by_database_snapshot(monkeypatch) -> None:
    from htfa.monitoring.uae.government_finance import renderer

    calls: list[str] = []

    def load():
        calls.append("loaded")
        return {"source": "uae.duckdb"}

    renderer._load_government_finance_cached.clear()
    monkeypatch.setattr(renderer, "load_government_finance_from_duckdb", load)

    first = renderer._load_government_finance_cached("db-snapshot")
    second = renderer._load_government_finance_cached("db-snapshot")

    assert first == second
    assert calls == ["loaded"]


def test_government_finance_defers_extended_charts_by_default(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import pandas as pd

    from htfa.monitoring.uae.government_finance import renderer

    host = MagicMock()
    host.spinner.return_value = nullcontext()
    host.container.return_value = nullcontext()
    host.expander.return_value = nullcontext()
    host.toggle.return_value = False
    data = SimpleNamespace(values=pd.DataFrame({"value": [1.0]}))
    monkeypatch.setattr(
        "htfa.monitoring.uae.duckdb_reader.database_snapshot_key",
        lambda: "db-snapshot",
    )
    monkeypatch.setattr(renderer, "latest_complete_month", lambda _: pd.Timestamp("2026-08-31"))
    monkeypatch.setattr(renderer, "_load_government_finance_cached", lambda _: data)
    monkeypatch.setattr(renderer, "_render_finance_metrics", lambda *_args: None)
    monkeypatch.setattr(renderer, "_render_quad_finance_charts", lambda *_args: None)
    monkeypatch.setattr(
        renderer,
        "_render_business_activity_charts",
        lambda *_args: (_ for _ in ()).throw(AssertionError("extended charts rendered")),
    )
    monkeypatch.setattr(
        renderer,
        "_render_labor_employment_charts",
        lambda *_args: (_ for _ in ()).throw(AssertionError("extended charts rendered")),
    )

    result = renderer.render_government_finance_section(host, None, None)

    assert result["status"] == "success"
    host.toggle.assert_called_once()
