import io
import warnings

import pandas as pd

from dashboard.core.ui.utils.shared_dataset import (
    fingerprint_file,
    load_shared_dataframe,
)


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

    result = load_shared_dataframe(uploaded)

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
        result = load_shared_dataframe(uploaded)

    assert result["指标名称"].tolist() == source["指标名称"].tolist()
    assert not pd.api.types.is_datetime64_any_dtype(result["指标名称"])


def test_shared_file_fingerprint_changes_when_content_changes():
    first = UploadedBytes(b"date,value\n2025-01-31,1\n", "data.csv")
    second = UploadedBytes(b"date,value\n2025-01-31,2\n", "data.csv")

    assert fingerprint_file(first) != fingerprint_file(second)
