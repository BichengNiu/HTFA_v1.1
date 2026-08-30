"""通用模型工作流状态生命周期测试。"""

from __future__ import annotations

from dashboard.models.common.state import ModelStateLifecycle


class Store:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class Session:
    def __init__(self):
        self.session_state = {"keep": "value", "input": 1, "button": True}


def test_lifecycle_clears_fit_and_downstream_results_by_dependency():
    store = Store()
    for key in ("fit", "fit_signature", "diag", "diag_signature", "forecast"):
        store.set(key, object())
    lifecycle = ModelStateLifecycle(
        store=store,
        fit_result_keys=("fit", "fit_signature"),
        downstream_result_keys=("diag", "diag_signature", "forecast"),
        widget_keys=("input", "button"),
    )

    lifecycle.clear_downstream_results()
    assert store.get("fit") is not None
    assert store.get("diag") is None
    assert store.get("forecast") is None

    lifecycle.clear_fit_results()
    assert all(store.get(key) is None for key in ("fit", "fit_signature"))
    assert all(store.get(key) is None for key in ("diag", "diag_signature", "forecast"))


def test_lifecycle_publishes_fit_and_invalidates_downstream_results():
    store = Store()
    lifecycle = ModelStateLifecycle(
        store=store,
        fit_result_keys=("fit", "fit_signature"),
        downstream_result_keys=("forecast",),
        widget_keys=(),
    )
    store.set("forecast", "stale")

    lifecycle.store_fit_result("new-fit", "new-signature")

    assert store.values == {
        "forecast": None,
        "fit": "new-fit",
        "fit_signature": "new-signature",
    }


def test_lifecycle_clears_only_declared_widgets():
    store = Store()
    session = Session()
    lifecycle = ModelStateLifecycle(
        store=store,
        fit_result_keys=("fit",),
        downstream_result_keys=("forecast",),
        widget_keys=("input", "button"),
    )

    lifecycle.clear_widget_state(session, keys=("button",))

    assert "button" not in session.session_state
    assert session.session_state["input"] == 1
    assert session.session_state["keep"] == "value"
