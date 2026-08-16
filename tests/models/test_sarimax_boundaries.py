"""SARIMAX 模块边界测试：导航、路由、权限与 UI 入口结构。"""

from __future__ import annotations

import ast
from pathlib import Path

from dashboard.auth.permission_builder import PermissionTreeBuilder
from dashboard.navigation_config import GRANULAR_PERMISSION_MAP, MODULE_CONFIG

SUB_MODULE = "单变量模型"
EXPECTED_TABS = ("SARIMAX 模型",)
EXPECTED_PERMISSION_CODES = (
    "model_analysis.univariate_ts",
    "model_analysis.univariate_ts.sarimax",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SECTION_FUNCTIONS = (
    "render_data_overview_section",
    "render_training_section",
    "render_analysis_section",
    "render_forecast_section",
)


def test_navigation_config_registers_univariate_ts_submodule():
    sub_modules = GRANULAR_PERMISSION_MAP["模型分析"]["sub_modules"]
    assert SUB_MODULE in sub_modules
    assert sub_modules[SUB_MODULE]["code"] == "model_analysis.univariate_ts"
    assert tuple(sub_modules[SUB_MODULE]["tabs"]) == EXPECTED_TABS

    assert MODULE_CONFIG["模型分析"][SUB_MODULE] == list(EXPECTED_TABS)


def test_permission_display_names_generated_automatically():
    builder = PermissionTreeBuilder()
    assert (
        builder.get_permission_display_name("model_analysis.univariate_ts")
        == "模型分析 - 单变量模型"
    )
    assert (
        builder.get_permission_display_name("model_analysis.univariate_ts.sarimax")
        == "模型分析 - 单变量模型 - SARIMAX 模型"
    )


def test_sarimax_permission_codes_are_unique():
    codes = list(EXPECTED_PERMISSION_CODES)
    assert len(set(codes)) == len(codes)
    dfm_tabs = GRANULAR_PERMISSION_MAP["模型分析"]["sub_modules"]["DFM 模型"]["tabs"]
    assert not set(codes).intersection(set(dfm_tabs.values()))


def test_content_router_dispatches_univariate_ts_submodule():
    source = (
        PROJECT_ROOT
        / "dashboard/core/ui/components/content_router.py"
    ).read_text(encoding="utf-8")

    assert '"单变量模型"' in source
    assert "render_sarimax_model_page" in source
    assert "SARIMAX 模型" in source
    assert "_render_model_submodule_tabs" in source


def test_sarimax_pages_expose_public_render_entries():
    pages_init = (
        PROJECT_ROOT / "dashboard/models/SARIMAX/ui/pages/__init__.py"
    ).read_text(encoding="utf-8")
    assert "render_sarimax_model_page" in pages_init

    model_init = (
        PROJECT_ROOT / "dashboard/models/SARIMAX/__init__.py"
    ).read_text(encoding="utf-8")
    assert "render_sarimax_model_page" in model_init

    sections_init = (
        PROJECT_ROOT / "dashboard/models/SARIMAX/ui/pages/sections/__init__.py"
    ).read_text(encoding="utf-8")
    for function in SECTION_FUNCTIONS:
        assert function in sections_init


def test_sarimax_main_page_only_orchestrates_sections():
    """主页面只做四环节编排，不直接 import Ts。"""
    path = PROJECT_ROOT / "dashboard/models/SARIMAX/ui/pages/sarimax_page.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    entry = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_sarimax_model_page"
    )
    assert entry.end_lineno - entry.lineno < 30
    assert len(entry.body) <= 12
    for child in ast.walk(entry):
        if isinstance(child, ast.ImportFrom) and child.module and "Ts" in child.module:
            raise AssertionError("sarimax_page 直接导入了 Ts，统计调用必须走 core 层")


def test_section_entry_functions_do_not_import_ts_directly():
    """环节入口函数只做编排，统计计算必须集中在 core/modeling.py。"""
    for section in (
        "training_section.py",
        "analysis_section.py",
        "forecast_section.py",
    ):
        path = PROJECT_ROOT / "dashboard/models/SARIMAX/ui/pages/sections" / section
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("render_"):
                continue
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.ImportFrom)
                    and child.module
                    and "Ts" in child.module
                ):
                    raise AssertionError(
                        f"{section} 的 render_ 函数直接导入了 Ts，"
                        "统计调用必须走 core 层"
                    )
    # 数据概览接线（sections/__init__.py 与 overview_bridge.py）不直接 import Ts：
    # 绘图能力在独立组件包 data_overview（ui/chart_panel.py 收口）。
    for wiring_path in (
        "dashboard/models/SARIMAX/ui/pages/sections/__init__.py",
        "dashboard/models/SARIMAX/ui/overview_bridge.py",
    ):
        tree = ast.parse(
            (PROJECT_ROOT / wiring_path).read_text(encoding="utf-8")
        )
        for child in ast.walk(tree):
            if (
                isinstance(child, ast.ImportFrom)
                and child.module
                and "Ts" in child.module
            ):
                raise AssertionError(
                    f"{wiring_path} 直接导入了 Ts，绘图调用必须走 data_overview 组件"
                )


def test_univariate_ts_tab_renders_without_exception(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()

    model_button = next(
        button
        for button in app.sidebar.button
        if button.label == "模型分析"
    )
    model_button.click()
    app.run()

    sub_button = next(
        button
        for button in app.sidebar.button
        if button.label == SUB_MODULE
    )
    sub_button.click()
    app.run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == list(EXPECTED_TABS)
