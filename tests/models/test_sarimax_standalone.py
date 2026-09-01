from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from Ts.TsSims import simulate_sarima


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _navigate_to_sarimax(app) -> None:
    next(
        button
        for button in app.sidebar.button
        if button.label == "模型分析"
    ).click()
    app.run()
    next(
        button
        for button in app.sidebar.button
        if button.label == "单变量模型"
    ).click()
    app.run()


def _upload_model_file(app, name: str, content: bytes) -> None:
    _navigate_to_sarimax(app)
    uploader = next(
        element
        for element in app.file_uploader
        if element.key == "model_analysis.sarimax.upload.uploader"
    )
    uploader.upload(name, content, "text/csv")
    app.run()


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def _sample_csv() -> bytes:
    rows = ["date,value,policy"]
    simulated = simulate_sarima(
        n=60,
        order=(1, 0, 0),
        ar=[0.6],
        seed=42,
    )
    rows.extend(
        f"{2020 + offset // 12}-{offset % 12 + 1:02d}-01,"
        f"{float(value):.6f},{(offset + 1) / 10:.1f}"
        for offset, value in enumerate(simulated.data)
    )
    return ("\n".join(rows) + "\n").encode("utf-8")


def test_sarimax_model_opens_independent_tab_with_editable_inputs(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _upload_model_file(source, "model.csv", _sample_csv())

    _by_key(source.multiselect, "sarimax_exog_select").set_value(["policy"])
    source.run()
    _by_key(source.number_input, "sarimax_p").set_value(2)
    source.run()

    launchers = source.get("link_button")
    assert len(launchers) == 1
    url = launchers[0].proto.url
    assert "model.csv" not in url
    assert "date,value,policy" not in url
    query = parse_qs(urlparse(url).query)
    assert query["view"] == ["sarimax-model"]
    assert "handoff" in query

    standalone = AppTest.from_file(
        PROJECT_ROOT / "app.py", default_timeout=60
    )
    standalone.query_params = query
    standalone.run()

    assert not source.exception
    assert not standalone.exception
    assert not standalone.sidebar.button
    assert _by_key(
        standalone.multiselect, "sarimax_exog_select"
    ).value == ["policy"]
    assert _by_key(standalone.number_input, "sarimax_p").value == 2
    assert _by_key(
        standalone.number_input,
        "sarimax_model_preview_variable_name_row",
    ).value == 1
    assert _by_key(
        standalone.number_input,
        "sarimax_model_preview_data_start_row",
    ).value == 2
    assert all(
        item.key == "sarimax_exog_operators" for item in standalone.dataframe
    )

    _by_key(standalone.number_input, "sarimax_p").set_value(3)
    standalone.run()
    assert _by_key(source.number_input, "sarimax_p").value == 2


def test_sarimax_handoff_token_is_reused_and_payload_is_opaque(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _upload_model_file(source, "stable.csv", _sample_csv())

    first_url = source.get("link_button")[0].proto.url
    source.run()
    second_url = source.get("link_button")[0].proto.url

    assert second_url == first_url
    assert "stable.csv" not in first_url
    assert "2020-01-01" not in first_url


def test_sarimax_handoff_copies_fitted_diagnostics_and_forecast_results(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _upload_model_file(source, "fitted.csv", _sample_csv())
    _by_key(source.button, "sarimax_fit_button").click()
    source.run()
    assert not source.exception
    assert source.dataframe

    assert any(item.value == "**残差诊断图**" for item in source.markdown)
    forecast_button = _by_key(source.button, "sarimax_forecast_button")
    forecast_button.click()
    source.run()
    assert not source.exception
    assert any(item.value == "**预测结果**" for item in source.markdown)

    url = source.get("link_button")[0].proto.url
    standalone = AppTest.from_file(
        PROJECT_ROOT / "app.py", default_timeout=60
    )
    standalone.query_params = parse_qs(urlparse(url).query)
    standalone.run()

    assert not standalone.exception
    assert standalone.dataframe
    assert any(item.value == "**残差诊断图**" for item in standalone.markdown)
    assert any(item.value == "**预测结果**" for item in standalone.markdown)

    source_forecast = source.session_state["model_analysis.sarimax.forecast"]
    standalone_forecast = standalone.session_state[
        "model_analysis.sarimax.forecast"
    ]
    assert standalone_forecast is not source_forecast
    assert standalone_forecast.prediction is not source_forecast.prediction

    _by_key(standalone.number_input, "sarimax_p").set_value(3)
    standalone.run()
    assert _by_key(source.number_input, "sarimax_p").value == 1
    assert standalone.session_state["model_analysis.sarimax.fitted_result"] is not source.session_state[
        "model_analysis.sarimax.fitted_result"
    ]


def test_invalid_sarimax_handoff_has_no_main_navigation(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60)
    app.query_params = {
        "view": ["sarimax-model"],
        "handoff": ["invalid-token"],
    }
    app.run()

    assert not app.exception
    assert any("链接已失效" in item.value for item in app.error)
    assert not app.sidebar
