"""工厂与组件级测试：默认配置、双实例隔离、数据源切换。"""

from __future__ import annotations

import pandas as pd

from data_overview import DataOverview, create_data_overview
from data_overview.core.dataset import build_overview_dataset
from data_overview.ui.data_source import BuiltinDataSource
from data_overview.ui.widget_keys import overview_widget_keys


class _FakeSource:
    """内存数据源（不渲染控件，直接提供数据）。"""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def render_uploader(self, st_obj, *, compact=False):
        return {"has_data": True}

    def current_data(self):
        return self._frame

    def load_data(
        self, *, variable_name_row=0, data_start_row=1, time_column=None
    ):
        assert variable_name_row == 0
        assert data_start_row == 1
        assert time_column is None
        return self._frame

    def row_count(self):
        return len(self._frame)

    def current_fingerprint(self):
        return "fp-1"

    def current_name(self):
        return "fake.csv"

    def sheets(self):
        return None

    def current_sheet(self):
        return None

    def select_sheet(self, sheet):
        pass


def _frame():
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
            "a": range(12),
        }
    )


def test_default_instance_uses_sarimax_keys():
    """默认实例使用 SARIMAX 页面约定的键前缀和状态命名空间。"""
    component = DataOverview()
    assert component.widget_keys == overview_widget_keys("sarimax")
    assert component.config.key_prefix == "sarimax"
    assert component.config.state_namespace == "model_analysis.sarimax"
    assert isinstance(component.data_source, BuiltinDataSource)


def test_factory_returns_callable():
    """create_data_overview 返回可调用渲染函数（绑定配置）。"""
    render = create_data_overview(key_prefix="dfm", state_namespace="x.dfm")
    assert callable(render)
    assert "dfm_preview_vars" in overview_widget_keys("dfm")


def test_two_instances_isolated_keys():
    """双实例（不同前缀）widget 键完全隔离。"""
    a = DataOverview(key_prefix="sarimax", state_namespace="ns.a")
    b = DataOverview(key_prefix="dfm", state_namespace="ns.b")
    assert not set(a.widget_keys) & set(b.widget_keys)
    assert a.state.namespace != b.state.namespace


def test_custom_dataset_builder():
    """自定义 dataset_builder 返回任意对象（鸭子类型）。"""
    calls = []

    def builder(frame, name, fingerprint):
        calls.append((name, fingerprint))
        return build_overview_dataset(frame, name, fingerprint)

    component = DataOverview(
        key_prefix="x", state_namespace="ns.x", dataset_builder=builder
    )
    assert component.config.dataset_builder is builder


def test_data_source_injection():
    """注入外部数据源后组件使用它而非内置上传器。"""
    source = _FakeSource(_frame())
    component = DataOverview(key_prefix="x", state_namespace="ns.x", data_source=source)
    assert component.data_source is source
