from __future__ import annotations

from types import SimpleNamespace

from htfa.app.navigation import manager
from htfa.workspace import SessionWorkspace


def _install_state(monkeypatch, state: dict[str, object]) -> None:
    monkeypatch.setattr(manager, "st", SimpleNamespace(session_state=state))


def test_main_module_change_snapshots_active_page_before_navigation(monkeypatch) -> None:
    state: dict[str, object] = {
        manager.MAIN_MODULE_KEY: "数据探索",
        manager.SUB_MODULE_KEY: "单变量分析",
        "exploration.variable": "GDP",
    }
    SessionWorkspace(state).begin_page(
        "exploration.univariate", keys=("exploration.variable",)
    )
    _install_state(monkeypatch, state)

    manager.set_current_main_module("模型分析")

    assert state["workspace.pages.exploration.univariate.inputs"] == {
        "exploration.variable": "GDP"
    }
    assert state[manager.MAIN_MODULE_KEY] == "模型分析"
    assert state[manager.SUB_MODULE_KEY] is None


def test_sub_module_change_snapshots_active_page_and_same_value_is_a_noop(monkeypatch) -> None:
    state: dict[str, object] = {
        manager.MAIN_MODULE_KEY: "数据探索",
        manager.SUB_MODULE_KEY: "单变量分析",
        "exploration.variable": "GDP",
    }
    SessionWorkspace(state).begin_page(
        "exploration.univariate", keys=("exploration.variable",)
    )
    _install_state(monkeypatch, state)

    manager.set_current_sub_module("多变量分析")
    after_change = dict(state)
    manager.set_current_sub_module("多变量分析")

    assert state["workspace.pages.exploration.univariate.inputs"] == {
        "exploration.variable": "GDP"
    }
    assert state[manager.SUB_MODULE_KEY] == "多变量分析"
    assert state == after_change
