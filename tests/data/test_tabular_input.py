from io import BytesIO

import pandas as pd
import pytest

from htfa.data.tabular_input import read_tabular_file


def _ordinary_workbook() -> BytesIO:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
                "value": [0, 2],
            }
        ).to_excel(writer, index=False, sheet_name="月度")
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01"]),
                "other": [3],
            }
        ).to_excel(writer, index=False, sheet_name="补充")
    output.seek(0)
    output.name = "普通表格.xlsx"
    return output


def _economic_workbook_marker() -> BytesIO:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "指标名称": ["指标A"],
                "类型": ["指数"],
                "行业": ["金融"],
                "数据来源": ["Wind"],
                "预测变量": ["是"],
            }
        ).to_excel(writer, index=False, sheet_name="指标字典")
    output.seek(0)
    output.name = "经济工作簿.xlsx"
    return output


def test_ordinary_excel_protocol_keeps_zero_and_reads_each_nonempty_sheet():
    tables, metadata = read_tabular_file(_ordinary_workbook())

    assert list(tables) == ["月度", "补充"]
    assert tables["月度"]["value"].tolist() == [0, 2]
    assert metadata == {}


def test_ordinary_protocol_rejects_economic_workbook_without_fallback():
    with pytest.raises(ValueError, match="经济工作簿输入协议"):
        read_tabular_file(_economic_workbook_marker())
