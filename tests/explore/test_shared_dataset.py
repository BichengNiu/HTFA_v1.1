import io
from types import SimpleNamespace
import warnings

import pandas as pd

from data_overview.core.file_parsing import file_fingerprint, load_dataframe
from dashboard.core.ui.utils.shared_dataset import (
    clear_shared_dataset,
    export_shared_dataset_snapshot,
    get_shared_dataset_data,
    get_shared_dataset_file,
    get_shared_dataset_raw_rows,
    render_shared_dataset_uploader,
    restore_shared_dataset_snapshot,
)
from dashboard.core.ui.utils import shared_dataset


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


def test_shared_xlsx_loader_keeps_indicator_names_without_date_warning():
    content = io.BytesIO()
    source = pd.DataFrame(
        {
            "指标名称": ["阿联酋:GDP:现价", "阿联酋:GDP:不变价"],
            "类型": ["金额", "金额"],
        }
    )
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        source.to_excel(writer, sheet_name="指标字典", index=False)
    uploaded = UploadedBytes(content.getvalue(), "阿联酋.xlsx")

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = load_dataframe(uploaded.getvalue(), uploaded.name)

    assert result["指标名称"].tolist() == source["指标名称"].tolist()
    assert not pd.api.types.is_datetime64_any_dtype(result["指标名称"])


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
