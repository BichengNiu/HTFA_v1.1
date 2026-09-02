from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
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


def _navigate_to_univariate_overview(app) -> None:
    """通过侧边栏进入“数据探索 → 单变量分析”。"""
    next(
        button
        for button in app.sidebar.button
        if button.label == "数据探索"
    ).click()
    app.run()
    next(
        button
        for button in app.sidebar.button
        if button.label == "单变量分析"
    ).click()
    app.run()


def _upload_model_file(
    app, name: str, content: bytes, mime: str = "text/csv"
) -> None:
    _navigate_to_sarimax(app)
    uploader = next(
        element
        for element in app.file_uploader
        if element.key == "model_analysis.sarimax.upload.uploader"
    )
    uploader.upload(name, content, mime)
    app.run()
    _by_key(app.button, "sarimax_start_processing_button").click()
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


def test_sarimax_handoff_keeps_selected_sheet_and_target_variables(
    monkeypatch, tmp_path
):
    """独立页交接后，工作表、时间列和目标变量保持同一数据集身份。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    workbook = tmp_path / "handoff-sheets.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "monthly_date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "monthly_target": [1, 2, 3],
            }
        ).to_excel(writer, sheet_name="月表", index=False)
        pd.DataFrame(
            {
                "daily_date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "daily_period": pd.date_range("2020-01-02", periods=3, freq="D"),
                "daily_target": [4, 5, 6],
            }
        ).to_excel(writer, sheet_name="日表", index=False)

    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _upload_model_file(
        source,
        workbook.name,
        workbook.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    _by_key(source.button, "sarimax_start_processing_button").click()
    source.run()
    _by_key(source.selectbox, "sarimax_model_preview_sheet").select("日表")
    source.run()
    assert not any(
        item.key == "sarimax_target_select" for item in source.selectbox
    )
    _by_key(source.selectbox, "sarimax_model_preview_time_column").select(
        "daily_period"
    )
    source.run()
    assert not any(
        item.key == "sarimax_target_select" for item in source.selectbox
    )
    _by_key(source.button, "sarimax_start_processing_button").click()
    source.run()
    assert _by_key(source.selectbox, "sarimax_target_select").options == [
        "daily_target"
    ]

    url = source.get("link_button")[0].proto.url
    standalone = AppTest.from_file(
        PROJECT_ROOT / "app.py", default_timeout=60
    )
    standalone.query_params = parse_qs(urlparse(url).query)
    standalone.run()

    assert not standalone.exception
    assert _by_key(
        standalone.selectbox, "sarimax_model_preview_sheet"
    ).value == "日表"
    assert _by_key(
        standalone.selectbox, "sarimax_model_preview_time_column"
    ).options == ["无", "daily_date", "daily_period", "daily_target"]
    assert _by_key(
        standalone.selectbox, "sarimax_model_preview_time_column"
    ).value == "daily_period"
    target_box = _by_key(standalone.selectbox, "sarimax_target_select")
    assert target_box.options == ["daily_target"]
    assert target_box.value == "daily_target"


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


def test_model_library_is_shared_with_standalone_and_keeps_current_result(
    monkeypatch,
):
    """独立页保存的模型可回到原页使用，删除不清除当前拟合结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _upload_model_file(source, "library.csv", _sample_csv())
    _by_key(source.button, "sarimax_fit_button").click()
    source.run()
    assert not source.exception

    url = source.get("link_button")[0].proto.url
    standalone = AppTest.from_file(
        PROJECT_ROOT / "app.py", default_timeout=60
    )
    standalone.query_params = parse_qs(urlparse(url).query)
    standalone.run()
    assert not standalone.exception
    markdown_values = [item.value for item in standalone.markdown]
    assert markdown_values.index("**预测结果**") < markdown_values.index(
        "**保存结果**"
    )
    assert any("加入模型库" == item.label for item in standalone.button)
    assert any(
        "在新标签页打开动态回归模型" == item.label
        for item in standalone.get("link_button")
    )
    _by_key(
        standalone.button,
        next(
            item.key
            for item in standalone.button
            if item.key.startswith("model_library_save_")
        ),
    ).click()
    standalone.run()
    assert not standalone.exception
    assert any("模型库" in item.value for item in standalone.sidebar.markdown)
    assert any("SARIMAX" in item.label for item in standalone.sidebar.expander)

    source.run()
    assert any("SARIMAX" in item.label for item in source.sidebar.expander)
    _navigate_to_univariate_overview(source)
    assert not source.sidebar.expander
    _navigate_to_sarimax(source)
    assert any("SARIMAX" in item.label for item in source.sidebar.expander)

    delete_button = _by_key(
        standalone.button,
        next(
            item.key
            for item in standalone.button
            if item.key.startswith("model_library_delete_")
        ),
    )
    delete_button.click()
    standalone.run()
    assert not standalone.exception
    assert not any("SARIMAX" in item.label for item in standalone.sidebar.expander)
    assert (
        standalone.session_state["model_analysis.sarimax.fitted_result"]
        is not None
    )

    save_key = next(
        item.key
        for item in standalone.button
        if item.key.startswith("model_library_save_")
    )
    _by_key(standalone.button, save_key).click()
    standalone.run()
    clear_button = _by_key(standalone.button, "model_library_clear_button")
    assert clear_button.disabled
    _by_key(standalone.checkbox, "model_library.clear_confirm").set_value(True)
    standalone.run()
    _by_key(standalone.button, "model_library_clear_button").click()
    standalone.run()
    assert not standalone.exception
    assert not standalone.sidebar.expander
    assert (
        standalone.session_state["model_analysis.sarimax.fitted_result"]
        is not None
    )


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
