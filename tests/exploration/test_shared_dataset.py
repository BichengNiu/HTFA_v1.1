import io
from types import SimpleNamespace

import pandas as pd

from htfa.data.file_content import file_fingerprint
from htfa.data.tabular import load_dataframe
from htfa.app.state.shared_dataset import (
    clear_shared_dataset,
    export_shared_dataset_snapshot,
    get_shared_dataset_data,
    get_shared_dataset_file,
    get_shared_dataset_raw_rows,
    render_shared_dataset_uploader,
    restore_shared_dataset_snapshot,
)
from htfa.app.state import shared_dataset


class UploadedBytes(io.BytesIO):
    """最小化模拟 Streamlit UploadedFile 的测试对象。"""

    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name

    def getvalue(self) -> bytes:
        return super().getvalue()


def test_shared_csv_loader_parses_first_column_as_time():
    uploaded = UploadedBytes(
        "date,value\n2025-01-31,1.5\n2025-02-28,2.5\n".encode(),
        "shared.csv",
    )

    result = load_dataframe(uploaded.getvalue(), uploaded.name)

    assert result.columns.tolist() == ["date", "value"]
    assert pd.api.types.is_datetime64_any_dtype(result["date"])
    assert result["value"].tolist() == [1.5, 2.5]


def _economic_workbook_bytes() -> bytes:
    """构造最小合法经济工作簿，供共享协议边界测试使用。"""
    content = io.BytesIO()
    source = pd.DataFrame(
        {
            "指标名称": ["阿联酋:GDP:现价"],
            "类型": ["金额"],
            "行业": ["宏观"],
            "数据来源": ["测试来源"],
            "预测变量": ["是"],
        }
    )
    data = pd.DataFrame(
        [
            ["来源", "测试来源"],
            ["指标名称", "阿联酋:GDP:现价"],
            ["频率", "月"],
            ["单位", "亿元"],
            ["来源", "测试来源"],
            ["更新时间", "2026-09-05"],
            ["2026-08-31", 123.0],
        ]
    )
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        source.to_excel(writer, sheet_name="指标字典", index=False)
        data.to_excel(writer, sheet_name="月度_测试", index=False, header=False)
    return content.getvalue()


def test_shared_xlsx_loader_rejects_economic_workbook_in_tabular_protocol(
    monkeypatch,
):
    state: dict = {}
    _use_session_state(monkeypatch, state)
    uploader = _Uploader(
        UploadedBytes(_economic_workbook_bytes(), "阿联酋.xlsx")
    )

    result = render_shared_dataset_uploader(uploader, protocol="tabular")

    assert result["has_data"] is False
    assert uploader.errors
    assert "经济工作簿" in uploader.errors[-1]


def test_shared_xlsx_loader_accepts_economic_workbook_in_explicit_protocol(
    monkeypatch,
):
    state: dict = {}
    _use_session_state(monkeypatch, state)
    uploader = _Uploader(
        UploadedBytes(_economic_workbook_bytes(), "阿联酋.xlsx")
    )

    result = render_shared_dataset_uploader(uploader, protocol="economic")

    assert result["has_data"] is True
    assert uploader.errors == []
    assert shared_dataset.get_shared_dataset_protocol() == "economic"
    assert get_shared_dataset_data() is None
    assert export_shared_dataset_snapshot() is None


def test_shared_file_fingerprint_changes_when_content_changes():
    first = UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv")
    second = UploadedBytes(b"date,value\n2025-01-31,2\n", "data.csv")

    assert file_fingerprint(first.getvalue()) != file_fingerprint(second.getvalue())


class _Uploader:
    def __init__(self, uploaded_file=None, *, clear_clicked: bool = False):
        self.uploaded_file = uploaded_file
        self.clear_clicked = clear_clicked
        self.captions: list[str] = []
        self.errors: list[str] = []
        self.successes: list[str] = []

    def markdown(self, *_args, **_kwargs):
        pass

    def file_uploader(self, *_args, **_kwargs):
        return self.uploaded_file

    def button(self, *_args, **_kwargs):
        return self.clear_clicked

    def caption(self, text: str):
        self.captions.append(text)

    def success(self, text: str, *_args, **_kwargs):
        self.successes.append(text)

    def error(self, text: str, *_args, **_kwargs):
        self.errors.append(text)

    def warning(self, *_args, **_kwargs):
        pass


def _use_session_state(monkeypatch, state: dict) -> None:
    monkeypatch.setattr(shared_dataset, "st", SimpleNamespace(session_state=state))


def test_missing_uploader_value_keeps_current_session_file(monkeypatch):
    state: dict = {}
    _use_session_state(monkeypatch, state)
    first = _Uploader(UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv"))
    render_shared_dataset_uploader(first)
    original_data = get_shared_dataset_data()

    returned = render_shared_dataset_uploader(_Uploader())

    assert returned["has_data"] is True
    assert get_shared_dataset_file() is not None
    assert get_shared_dataset_file().name == "data.csv"
    assert get_shared_dataset_data() is original_data


def test_explicit_clear_removes_asset_and_dependent_state(monkeypatch):
    state: dict = {
        "unrelated_model.fitted_result": object(),
        "model_analysis.sarimax.fitted_result": object(),
        "workspace.pages.exploration.univariate.inputs": {"x": 1},
    }
    _use_session_state(monkeypatch, state)
    render_shared_dataset_uploader(
        _Uploader(UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv"))
    )

    returned = render_shared_dataset_uploader(_Uploader(clear_clicked=True))

    assert returned["has_data"] is False
    assert get_shared_dataset_file() is None
    assert get_shared_dataset_data() is None
    assert state["unrelated_model.fitted_result"] is not None
    assert state["model_analysis.sarimax.fitted_result"] is not None
    assert "workspace.pages.exploration.univariate.inputs" not in state


def test_new_file_does_not_clear_unrelated_model_state(monkeypatch):
    state: dict = {"model_analysis.sarimax.fitted_result": "keep-sarimax"}
    _use_session_state(monkeypatch, state)
    first = UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv")
    render_shared_dataset_uploader(_Uploader(first))
    state["unrelated_model.fitted_result"] = "keep-for-same-file"
    state["unrelated_model.target_select"] = "value"

    render_shared_dataset_uploader(
        _Uploader(UploadedBytes(b"date,value\n2025-01-31,1\n", "renamed.csv"))
    )
    assert state["unrelated_model.fitted_result"] == "keep-for-same-file"

    render_shared_dataset_uploader(
        _Uploader(UploadedBytes(b"date,value\n2025-01-31,2\n", "data.csv"))
    )
    assert state["unrelated_model.fitted_result"] == "keep-for-same-file"
    assert state["unrelated_model.target_select"] == "value"
    assert state["model_analysis.sarimax.fitted_result"] == "keep-sarimax"
    clear_shared_dataset()


def test_invalid_shared_file_clears_data_without_success_fallback(monkeypatch):
    state: dict = {}
    _use_session_state(monkeypatch, state)
    valid = _Uploader(UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv"))
    render_shared_dataset_uploader(valid)
    assert get_shared_dataset_data() is not None

    invalid = _Uploader(
        UploadedBytes(
            b"date,value\n2025-01-31,1,unexpected\n",
            "invalid.csv",
        )
    )
    returned = render_shared_dataset_uploader(invalid)

    assert returned["has_data"] is True
    assert get_shared_dataset_data() is None
    assert get_shared_dataset_raw_rows() == [
        ["date", "value"],
        ["2025-01-31", "1", "unexpected"],
    ]
    assert invalid.errors == [
        "共享数据集读取失败：第 2 行超过变量名行的列数"
    ]
    assert invalid.successes == []


def test_shared_dataset_snapshot_restores_file_and_selected_sheet(monkeypatch):
    source_state: dict = {}
    _use_session_state(monkeypatch, source_state)
    render_shared_dataset_uploader(
        _Uploader(UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv"))
    )
    snapshot = export_shared_dataset_snapshot()

    assert snapshot is not None
    target_state: dict = {}
    _use_session_state(monkeypatch, target_state)
    restore_shared_dataset_snapshot(snapshot)

    restored = get_shared_dataset_file()
    assert restored is not None
    assert restored.name == "data.csv"
    assert restored.getvalue() == b"date,value\n2025-01-31,1\n"
    assert get_shared_dataset_data().columns.tolist() == ["date", "value"]
