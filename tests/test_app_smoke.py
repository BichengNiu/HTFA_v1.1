from io import BytesIO
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _prepared_dfm_workbook() -> tuple[str, bytes, str]:
    output = BytesIO()
    dates = pd.date_range("2025-01-01", periods=12, freq="MS")
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame({"date": dates, "A": range(12)}).to_excel(
            writer, sheet_name="数据", index=False
        )
        pd.DataFrame(
            {
                "指标名称": ["A"],
                "行业": ["金融"],
                "单位": ["点"],
                "频率": ["M"],
                "预测变量": ["是"],
            }
        ).to_excel(writer, sheet_name="映射", index=False)
    return (
        "prepared-dfm.xlsx",
        output.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def test_browser_tab_uses_platform_name() -> None:
    assert 'page_title="金轩监测"' in APP_PATH.read_text(encoding="utf-8")


def test_public_entry_renders_navigation_without_exception():
    from htfa.models.univariate.common.model_library import MODEL_LIBRARY_TOKEN_KEY

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert MODEL_LIBRARY_TOKEN_KEY not in app.session_state
    assert [button.label for button in app.sidebar.button] == [
        "数据预览",
        "模型分析",
        "监测分析",
        "数据探索",
    ]
    assert any("金轩监测" in markdown.value for markdown in app.markdown)
    assert any(
        "中国驻阿联酋大使馆经商处" in markdown.value
        for markdown in app.markdown
    )
    assert any(
        "国家发展改革委国家信息中心" in markdown.value
        for markdown in app.markdown
    )
    assert any("金轩监测" in markdown.value for markdown in app.sidebar.markdown)


def test_model_library_is_not_initialized_outside_model_analysis():
    from htfa.models.univariate.common.model_library import MODEL_LIBRARY_TOKEN_KEY

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    next(
        button
        for button in app.sidebar.button
        if button.label == "数据探索"
    ).click()
    app.run()

    assert not app.exception
    assert not app.sidebar.expander
    assert MODEL_LIBRARY_TOKEN_KEY not in app.session_state


def test_monitoring_sidebar_routes_industrial_and_uae_without_exception():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    next(
        button
        for button in app.sidebar.button
        if button.label == "监测分析"
    ).click()
    app.run()
    next(button for button in app.sidebar.button if button.label == "工业").click()
    app.run()
    assert not app.exception

    next(button for button in app.sidebar.button if button.label == "阿联酋").click()
    app.run()
    assert not app.exception


def test_navigation_reaches_dfm_pages_without_exception():
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

    train_uploader = next(
        item for item in app.file_uploader if item.key == "train_excel_upload"
    )
    train_uploader.upload(*_prepared_dfm_workbook())
    app.run()
    assert not app.exception
