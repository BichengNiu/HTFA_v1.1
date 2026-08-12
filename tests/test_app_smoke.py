from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_production_entry_renders_login_without_exception(monkeypatch):
    monkeypatch.setenv("HTFA_DEBUG_MODE", "false")

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert len(app.text_input) == 2


def test_explicit_debug_entry_renders_navigation_without_exception(monkeypatch):
    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert len(app.sidebar.button) == 5


def test_debug_navigation_reaches_dfm_pages_without_exception(monkeypatch):
    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    model_button = next(
        button
        for button in app.sidebar.button
        if button.label == "\u6a21\u578b\u5206\u6790"
    )
    model_button.click()
    app.run()

    dfm_button = next(
        button
        for button in app.sidebar.button
        if button.label == "DFM \u6a21\u578b"
    )
    dfm_button.click()
    app.run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "\u6570\u636e\u51c6\u5907",
        "\u6a21\u578b\u8bad\u7ec3",
        "\u6a21\u578b\u5206\u6790",
        "\u5f71\u54cd\u5206\u89e3",
    ]
