"""SARIMAX 模块边界测试：导航、路由、权限与 UI 入口结构。"""

from __future__ import annotations

import ast
from pathlib import Path

from htfa.app.navigation.config import MODULE_CONFIG

SUB_MODULE = "单变量模型"
EXPECTED_TABS = ("SARIMAX", "RDL", "ARDL")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

SECTION_FUNCTIONS = (
    "render_training_section",
    "render_analysis_section",
    "render_forecast_section",
)


def test_navigation_config_registers_univariate_ts_submodule():
    assert MODULE_CONFIG["模型分析"][SUB_MODULE] == list(EXPECTED_TABS)


def test_content_router_dispatches_univariate_ts_submodule():
    source = (
        PROJECT_ROOT
        / "htfa/app/ui/components/content_router.py"
    ).read_text(encoding="utf-8")

    assert '"单变量模型"' in source
    assert "render_sarimax_model_page" in source
    assert "render_rdl_model_page" in source
    assert "render_ardl_model_page" in source
    assert '"SARIMAX"' in source
    assert '"RDL"' in source
    assert '"ARDL"' in source
    assert "_render_model_submodule_tabs" in source


def test_sarimax_pages_expose_public_render_entries():
    pages_init = (
        PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/pages/__init__.py"
    ).read_text(encoding="utf-8")
    assert "render_sarimax_model_page" in pages_init
    assert "render_rdl_model_page" in pages_init
    assert "render_ardl_model_page" in pages_init

    sections_init = (
        PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/pages/sections/__init__.py"
    ).read_text(encoding="utf-8")
    for function in SECTION_FUNCTIONS:
        assert function in sections_init


def test_model_tabs_have_isolated_state_and_widget_namespaces():
    """三个同级模型 Tab 不共享上传、控件或结果缓存命名空间。"""
    from htfa.models.univariate.sarimax.ui.state import (
        ARDL_SCOPE,
        RDL_SCOPE,
        SARIMAX_SCOPE,
    )

    scopes = (SARIMAX_SCOPE, RDL_SCOPE, ARDL_SCOPE)
    assert tuple(scope.family for scope in scopes) == ("SARIMAX", "RDL", "ARDL")
    assert len({scope.namespace for scope in scopes}) == 3
    assert len({scope.data_key_prefix for scope in scopes}) == 3
    assert not set(SARIMAX_SCOPE.widget_keys) & set(RDL_SCOPE.widget_keys)
    assert not set(SARIMAX_SCOPE.widget_keys) & set(ARDL_SCOPE.widget_keys)
    assert not set(RDL_SCOPE.widget_keys) & set(ARDL_SCOPE.widget_keys)


def test_forecast_planning_module_has_no_ui_or_ts_dependency():
    """预测规划保持为可独立测试的纯 core 模块。"""
    import ast

    from htfa.models.univariate.sarimax.core import forecast_planning

    tree = ast.parse(Path(forecast_planning.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(module.lower().startswith("streamlit") for module in imported_modules)
    assert not any(module.startswith("Ts") for module in imported_modules)
    assert not any(module.lower().startswith("matplotlib") for module in imported_modules)


def test_downstream_result_publication_is_not_owned_by_page_sections():
    result_keys = (
        "forecast",
        "forecast_signature",
        "diagnostics_table",
        "diagnostics_signature",
    )
    for filename in ("analysis_section.py", "forecast_section.py"):
        source = (
            PROJECT_ROOT
            / "htfa/models/univariate/sarimax/ui/pages/sections"
            / filename
        ).read_text(encoding="utf-8")
        for key in result_keys:
            assert f'state.set("{key}"' not in source
        assert "store_downstream_result" in source


def test_model_family_implementations_are_split_from_facades():
    """模型族拟合和参数控件必须由各自 module 承担。"""
    core_modeling = (
        PROJECT_ROOT / "htfa/models/univariate/sarimax/core/modeling.py"
    ).read_text(encoding="utf-8")
    options_facade = (
        PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/model_options.py"
    ).read_text(encoding="utf-8")

    assert "from Ts.TsModels" not in core_modeling
    assert "def fit_sarimax" not in core_modeling
    assert "def fit_rdl" not in core_modeling
    assert "def fit_ardl" not in core_modeling
    assert "def _render_manual_config" not in options_facade
    assert "def _render_rdl_config" not in options_facade
    assert "def _render_ardl_config" not in options_facade
    for module in (
        "sarimax_modeling.py",
        "rdl_modeling.py",
        "ardl_modeling.py",
        "model_options_sarimax.py",
        "model_options_rdl.py",
        "model_options_ardl.py",
    ):
        assert (PROJECT_ROOT / "htfa/models/univariate/sarimax" / (
            "core" if module.endswith("modeling.py") else "ui"
        ) / module).exists()


def test_forecast_and_training_pages_consume_stable_seams():
    """页面编排不得读取底层拟合结果的模型属性。"""
    for filename in ("training_section.py", "forecast_section.py"):
        source = (
            PROJECT_ROOT
            / "htfa/models/univariate/sarimax/ui/pages/sections"
            / filename
        ).read_text(encoding="utf-8")
        for leaked_detail in (
            "best_result(",
            "best.nobs",
            "best.exog_names",
            "best.dates",
            "best.order",
            "best.seasonal_order",
        ):
            assert leaked_detail not in source


def test_sarimax_main_page_only_orchestrates_sections():
    """主页面只做四环节编排，不直接 import Ts。"""
    path = PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/pages/sarimax_page.py"
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
        path = PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/pages/sections" / section
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
    # 模型页接线不直接 import Ts；绘图能力在独立组件包 data_overview 中。
    for wiring_path in (
        "htfa/models/univariate/sarimax/ui/pages/sections/__init__.py",
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


def test_analysis_section_uses_the_model_diagnostic_seam():
    """分析页不得读取 Ts 结果属性或直接调用诊断实现。"""
    path = PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/pages/sections/analysis_section.py"
    source = path.read_text(encoding="utf-8")

    assert "ModelWorkflow" in source
    assert "residual_diagnostics" in source
    assert "residual_test_table" in source
    for leaked_detail in (
        "best_result(",
        ".residuals",
        ".plot_diagnostics(",
        "run_residual_diagnostics(",
    ):
        assert leaked_detail not in source


def test_univariate_ts_tab_renders_without_exception():
    from streamlit.testing.v1 import AppTest

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
