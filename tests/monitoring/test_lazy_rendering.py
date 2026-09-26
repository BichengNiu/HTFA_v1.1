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


def test_high_frequency_topics_render_all_sections_in_order(monkeypatch) -> None:
    from htfa.monitoring.uae import report

    called: list[str] = []

    def renderer(name):
        def _render(_st_obj):
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

    result = report.render_high_frequency_topics(host)

    assert called == ["oil", "finance", "property"]
    assert set(result) == {"oil", "finance", "property"}
    assert host.calls == []


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


def test_high_frequency_tab_never_reads_shared_workbook(monkeypatch) -> None:
    from htfa.monitoring.uae import renderer

    class _MonitoringHost(_TabsHost):
        def spinner(self, _label):
            return nullcontext()

        def container(self, **_kwargs):
            return nullcontext()

        def info(self, _message: str) -> None:
            return None

    host = _MonitoringHost(open_index=2)
    monkeypatch.setattr(
        renderer,
        "get_shared_dataset_file",
        lambda: (_ for _ in ()).throw(AssertionError("shared workbook accessed")),
    )
    monkeypatch.setattr(renderer, "_render_report_header", lambda *_args: None)
    monkeypatch.setattr(
        renderer,
        "_source_payload",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Excel payload read")),
    )
    monkeypatch.setattr(
        renderer,
        "_build_monitoring_dashboard_cached",
        lambda *_args: (_ for _ in ()).throw(AssertionError("workbook parsed")),
    )

    def render_topics(_st_obj):
        return {"oil": object()}

    monkeypatch.setattr(renderer, "render_high_frequency_topics", render_topics)
    result = renderer.render_uae_monitoring(host)

    assert result["source"] == "uae.duckdb"
