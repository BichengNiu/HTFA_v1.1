from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_browser_tab_uses_platform_name() -> None:
    assert 'page_title="经世"' in APP_PATH.read_text(encoding="utf-8")


def test_public_entry_renders_navigation_without_exception():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert [button.label for button in app.sidebar.button] == [
        "数据预览",
        "模型分析",
        "监测分析",
        "数据探索",
    ]
    assert any("经世" in markdown.value for markdown in app.markdown)
    assert any(
        "国家信息中心经济预测部政策仿真实验室" in markdown.value
        for markdown in app.markdown
    )
    assert any("经世" in markdown.value for markdown in app.sidebar.markdown)
    assert any(
        "@版权所有：国家信息中心经济预测部政策仿真实验室 牛碧珵"
        in markdown.value
        for markdown in app.sidebar.markdown
    )


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
