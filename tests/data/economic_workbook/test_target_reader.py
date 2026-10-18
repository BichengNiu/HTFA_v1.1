"""Mixed-unit sheets share validation without relaxing duplicate policies."""

import pandas as pd
import pytest

from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.data.economic_workbook.tables import TableWorkbook


def raw_sheet():
    return pd.DataFrame([
        ["混合表", None, None],
        ["指标名称", "数量指标", "金额指标"],
        ["频率", "月", "月"],
        ["单位", "笔", "百万AED"],
        ["来源", "官方", "官方"],
        ["更新时间", "2026-01-31", "2026-01-31"],
        ["2025-12-31", 10, 100.0],
        ["2026-01-31", 0, 110.0],
    ])


def parse(raw, **options):
    tables = TableWorkbook(["混合表"], lambda _name: raw.copy(deep=True))
    return parse_target_sheet(
        tables, sheet_name="混合表", targets=(("数量", "数量指标"), ("金额", "金额指标")),
        allowed_frequencies={"月"}, expected_unit={"数量": "笔", "金额": "百万AED"},
        **options,
    )


def test_mixed_units_keep_column_order_metadata_and_zero_semantics():
    values, metadata = parse(raw_sheet())
    assert values.columns.tolist() == ["数量", "金额"]
    assert values.iloc[0].tolist() == [10, 100]
    assert pd.isna(values.iloc[1, 0])
    assert [item.unit for item in metadata.values()] == ["笔", "百万AED"]
    with_zero, _ = parse(raw_sheet(), zero_is_missing=False)
    assert with_zero.iloc[1, 0] == 0


@pytest.mark.parametrize("row, column, value, message", [
    (2, 1, "日", "频率应为"),
    (3, 2, "美元", "单位应为"),
    (4, 1, None, "来源不能为空"),
    (6, 1, "not numeric", "不是数值"),
    (6, 0, "not a date", "日期无效"),
    (7, 0, "2025-12-31", "重复日期"),
    (1, 1, "other", "缺少指标"),
])
def test_mixed_units_preserve_all_input_validation(row, column, value, message):
    raw = raw_sheet()
    raw.iloc[row, column] = value
    with pytest.raises(ValueError, match=message):
        parse(raw)


def test_strict_duplicates_rejects_an_incompatible_copy_as_well():
    raw = raw_sheet()
    raw[3] = raw[1]
    raw.iloc[3, 3] = "other unit"
    # CBUAE selects its unique compatible column; DED and DLD reject any copy.
    values, _ = parse(raw)
    assert values.iloc[0, 0] == 10
    with pytest.raises(ValueError, match="重复目标指标"):
        parse(raw, strict_duplicates=True)
    raw.iloc[3, 3] = "笔"
    with pytest.raises(ValueError, match="重复目标指标"):
        parse(raw)
