"""工厂与组件级测试：默认配置、双实例隔离、数据源切换。"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pandas as pd

from htfa.data.tabular import TabularFileSnapshot, build_overview_dataset
from htfa.ui_shared.data_overview import DataOverview, create_data_overview
from htfa.ui_shared.data_overview.ui import data_source as data_source_module
from htfa.ui_shared.data_overview.ui.data_source import BuiltinDataSource
from htfa.ui_shared.data_overview.ui.widget_keys import overview_widget_keys


class _FakeSource:
    """内存数据源（不渲染控件，直接提供数据）。"""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def render_uploader(self, st_obj, *, compact=False):
        return {"has_data": True}

    def snapshot(self):
        return TabularFileSnapshot(
            file_name="fake.csv",
            fingerprint="fp-1",
            sheets=None,
            sheet=None,
            raw_rows=[["date", "a"], ["2020-01-01", 1]],
            frame=self._frame,
        )

    def load_data(
        self, *, variable_name_row=0, data_start_row=1, time_column=None
    ):
        assert variable_name_row == 0
        assert data_start_row == 1
        assert time_column is None
        return self._frame

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


def test_data_overview_can_disable_preview():
    """组件可只处理数据输入，不渲染变量、表格和图形预览。"""
    component = DataOverview(
        key_prefix="sarimax_model",
        state_namespace="model_analysis.sarimax",
        show_preview=False,
    )

    assert component.config.show_preview is False


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


class _UploadedFile(io.BytesIO):
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


class _Uploader:
    def __init__(self, uploaded_file):
        self.uploaded_file = uploaded_file
        self.captions: list[str] = []

    def markdown(self, *_args, **_kwargs):
        pass

    def file_uploader(self, *_args, **_kwargs):
        return self.uploaded_file

    def caption(self, text: str):
        self.captions.append(text)

    def error(self, *_args, **_kwargs):
        raise AssertionError("有效文件不应触发读取错误")


def test_builtin_data_source_uses_snapshot_for_render_and_load(monkeypatch):
    """内置数据源的渲染和加载均通过同一快照协议。"""
    monkeypatch.setattr(
        data_source_module,
        "st",
        SimpleNamespace(session_state={}),
    )
    uploader = _Uploader(
        _UploadedFile(
            b"date,value\n2025-01-31,1\n2025-02-28,2\n",
            "data.csv",
        )
    )
    source = BuiltinDataSource("test.snapshot")

    result = source.render_uploader(uploader, compact=True)
    loaded = source.load_data()

    assert result["has_data"] is True
    assert loaded is not None
    assert loaded["value"].tolist() == [1, 2]
    assert source.snapshot() is not None
    assert source.snapshot().row_count == 3
