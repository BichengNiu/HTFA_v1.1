"""SARIMAX UI 端到端流程测试（AppTest 驱动完整工作流）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from Ts.TsSims import simulate_sarima

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _navigate_to_sarimax(app) -> None:
    """通过侧边栏导航到「模型分析 → 单变量时间序列 → SARIMAX 模型」。"""
    model_button = next(
        button for button in app.sidebar.button if button.label == "模型分析"
    )
    model_button.click()
    app.run()
    sub_button = next(
        button for button in app.sidebar.button if button.label == "单变量时间序列"
    )
    sub_button.click()
    app.run()


def _sample_csv() -> tuple[str, bytes, str]:
    """生成带日期列的 AR(1) 模拟数据 CSV。"""
    simulated = simulate_sarima(n=60, order=(1, 0, 0), ar=[0.6], seed=42)
    index = pd.date_range("2020-01-01", periods=60, freq="MS")
    frame = pd.DataFrame(
        {"date": index.strftime("%Y-%m-%d"), "value": simulated.data}
    )
    return (
        "sample.csv",
        frame.to_csv(index=False).encode("utf-8"),
        "text/csv",
    )


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def test_full_workflow_via_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

    # 导航结果：单 tab「SARIMAX 模型」，页内四环节标题与引导信息齐全
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["SARIMAX 模型"]
    title_texts = " ".join(element.value for element in app.markdown)
    assert "① 数据导入" in title_texts
    assert "② 模型训练" in title_texts
    assert "③ 模型分析" in title_texts
    assert "④ 模型预测" in title_texts
    info_texts = " ".join(element.value for element in app.info)
    assert "完成「① 数据导入」后可配置并拟合模型" in info_texts
    assert "完成「② 模型训练」后可查看模型分析结果" in info_texts

    # ① 数据导入：上传文件后出现成功提示与数据预览
    app.file_uploader[0].upload(*_sample_csv())
    app.run()
    assert not app.exception
    assert any("已加载" in element.value for element in app.success)
    assert any(element.key == "sarimax_target_select" for element in app.selectbox)

    # ② 模型训练：默认手动配置 (1,0,1)，拟合按钮可用并执行
    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    fit_button.click()
    app.run()
    assert not app.exception
    metrics = {element.label: element.value for element in app.metric}
    assert "AIC" in metrics and "BIC" in metrics and "对数似然" in metrics
    assert any("已收敛" in element.value for element in app.success)

    # ③ 模型分析：残差检验运行后出现结果表与下载按钮
    _by_key(app.button, "sarimax_diag_button").click()
    app.run()
    assert not app.exception
    assert any("残差自相关" in str(element.value) for element in app.dataframe)
    assert any(element.key == "sarimax_diag_download" for element in app.download_button)

    # ④ 模型预测：生成预测后出现预测表与下载按钮
    forecast_button = _by_key(app.button, "sarimax_forecast_button")
    assert not forecast_button.disabled
    forecast_button.click()
    app.run()
    assert not app.exception
    assert any(
        list(element.value.columns) == ["预测值", "下界", "上界"]
        for element in app.dataframe
    )
    assert any(
        element.key == "sarimax_forecast_download" for element in app.download_button
    )


def test_auto_mode_workflow_via_ui(monkeypatch):
    """自动选阶模式：切换配置方式、缩小搜索范围后拟合出候选表。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

    app.file_uploader[0].upload(*_sample_csv())
    app.run()
    assert not app.exception

    # 切换到自动选阶，并把范围缩到 4 个组合
    _by_key(app.radio, "sarimax_mode_radio").set_value(
        "自动选阶（AutoSARIMAX）"
    )
    app.run()
    assert not app.exception
    _by_key(app.number_input, "sarimax_auto_p_max").set_value(1)
    _by_key(app.number_input, "sarimax_auto_q_max").set_value(1)
    _by_key(app.number_input, "sarimax_auto_d_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_P_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_Q_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_D_max").set_value(0)
    app.run()
    assert not app.exception
    assert any("网格搜索将尝试 4 个模型组合" in c.value for c in app.caption)

    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    fit_button.click()
    app.run()
    assert not app.exception
    assert any("最优模型" in m.value for m in app.markdown)
    assert any(
        "模型" in element.value.columns for element in app.dataframe
    )
    metrics = {element.label: element.value for element in app.metric}
    assert "AIC" in metrics
