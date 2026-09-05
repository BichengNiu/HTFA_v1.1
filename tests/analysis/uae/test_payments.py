"""Tests for the CBUAE payment-flow charts."""

from io import BytesIO

import pandas as pd
import pytest

from htfa.monitoring.uae.government_finance.payments import (
    CHEQUES_AMOUNT,
    CHEQUES_AMOUNT_DISPLAY,
    CHEQUES_NUMBER,
    CHEQUES_NUMBER_DISPLAY,
    CUSTOMER_TRANSFERS_AMOUNT,
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
    CUSTOMER_TRANSFERS_NUMBER,
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
    build_cheques_figure,
    build_customer_transfers_figure,
    cumulative_to_monthly,
    load_payment_data,
)


def _workbook_bytes(
    *,
    missing_indicator: str | None = None,
    invalid_amount: bool = False,
) -> bytes:
    dates = pd.date_range("2023-01-31", periods=40, freq="ME")
    indicators = [
        CUSTOMER_TRANSFERS_NUMBER,
        CUSTOMER_TRANSFERS_AMOUNT,
        CHEQUES_NUMBER,
        CHEQUES_AMOUNT,
    ]
    metadata = pd.DataFrame(
        [
            ["CBUAE", *([None] * len(indicators))],
            ["指标名称", *indicators],
            ["频率", *(["月"] * len(indicators))],
            ["单位", "笔", "百万迪拉姆", "张", "百万迪拉姆"],
            ["来源", *(["CBUAE"] * len(indicators))],
            ["更新时间", *(["2026-08-21"] * len(indicators))],
        ]
    )
    data = pd.DataFrame(
        {
            "日期": dates,
            CUSTOMER_TRANSFERS_NUMBER: range(1_000, 1_040),
            CUSTOMER_TRANSFERS_AMOUNT: range(200_000, 200_040),
            CHEQUES_NUMBER: range(200, 240),
            CHEQUES_AMOUNT: range(200_000, 200_040),
        }
    )
    if missing_indicator is not None:
        metadata.iloc[1, indicators.index(missing_indicator) + 1] = "缺失指标"
    if invalid_amount:
        data[CUSTOMER_TRANSFERS_AMOUNT] = data[
            CUSTOMER_TRANSFERS_AMOUNT
        ].astype(object)
        data.loc[5, CUSTOMER_TRANSFERS_AMOUNT] = "not-a-number"
    rows = pd.concat(
        [
            metadata,
            data.rename(columns={"日期": 0}).set_axis(
                range(len(indicators) + 1), axis=1
            ),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name="月度_CBUAE",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def _data_lines(figure):
    return [
        line
        for axis in figure.axes
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]


def test_payment_loader_reads_mixed_units_and_four_indicators() -> None:
    data = load_payment_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
        CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
        CHEQUES_NUMBER_DISPLAY,
        CHEQUES_AMOUNT_DISPLAY,
    ]
    assert data.values.index.max() == pd.Timestamp("2026-04-30")
    assert data.metadata[CUSTOMER_TRANSFERS_NUMBER_DISPLAY].unit == "笔"
    assert data.metadata[CUSTOMER_TRANSFERS_AMOUNT_DISPLAY].unit == "百万迪拉姆"
    assert data.metadata[CHEQUES_NUMBER_DISPLAY].unit == "张"
    assert data.metadata[CHEQUES_AMOUNT_DISPLAY].source == "CBUAE"


def test_payment_loader_rejects_missing_indicator() -> None:
    with pytest.raises(ValueError, match="缺少指标"):
        load_payment_data(
            _workbook_bytes(missing_indicator=CHEQUES_AMOUNT),
            file_name="test.xlsx",
        )


def test_payment_loader_rejects_invalid_numeric_value() -> None:
    with pytest.raises(ValueError, match="不是数值"):
        load_payment_data(
            _workbook_bytes(invalid_amount=True),
            file_name="test.xlsx",
        )


def test_cumulative_to_monthly_resets_in_january_and_rejects_gaps() -> None:
    values = pd.DataFrame(
        {
            CUSTOMER_TRANSFERS_NUMBER_DISPLAY: [100, 120, 140, 180, 210],
            CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: [1_000, 1_200, 1_400, 1_800, 2_100],
        },
        index=pd.to_datetime(
            [
                "2023-12-31",
                "2024-01-31",
                "2024-02-29",
                "2024-04-30",
                "2024-05-31",
            ]
        ),
    )

    monthly = cumulative_to_monthly(values)

    assert pd.isna(monthly.iloc[0]).all()
    assert monthly.loc["2024-01-31", CUSTOMER_TRANSFERS_NUMBER_DISPLAY] == 120
    assert monthly.loc["2024-02-29", CUSTOMER_TRANSFERS_NUMBER_DISPLAY] == 20
    assert pd.isna(
        monthly.loc["2024-04-30", CUSTOMER_TRANSFERS_NUMBER_DISPLAY]
    )
    assert monthly.loc["2024-05-31", CUSTOMER_TRANSFERS_NUMBER_DISPLAY] == 30


@pytest.mark.parametrize(
    ("builder", "number_label", "amount_label", "number_unit"),
    [
        (
            build_customer_transfers_figure,
            CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
            CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
            "笔",
        ),
        (
            build_cheques_figure,
            CHEQUES_NUMBER_DISPLAY,
            CHEQUES_AMOUNT_DISPLAY,
            "张",
        ),
    ],
)
def test_payment_figures_render_two_series_with_dual_units(
    builder,
    number_label: str,
    amount_label: str,
    number_unit: str,
) -> None:
    data = load_payment_data(_workbook_bytes(), file_name="test.xlsx")

    figure = builder(
        data.values,
        title="支付测试（当月值）",
        source_text="CBUAE",
        last_month=pd.Period("2026-04", freq="M"),
        units={
            number_label: number_unit,
            amount_label: "百万迪拉姆",
        },
    )

    assert len(figure.axes) == 2
    lines = _data_lines(figure)
    assert {line.get_label() for line in lines} == {
        number_label,
        amount_label,
    }
    assert {len(line.get_xdata()) for line in lines} == {37}
    axis_labels = {axis.get_ylabel() for axis in figure.axes}
    assert any(label.endswith(number_unit) for label in axis_labels)
    assert any(label.endswith("万亿迪拉姆") for label in axis_labels)
    if builder is build_customer_transfers_figure:
        assert {
            text.get_text() for text in figure.axes[0].get_legend().get_texts()
        } == {"转账笔数（左轴）", "转账金额（右轴）"}
    assert any(text.get_text() == "数据来源：阿联酋央行" for text in figure.texts)
    assert any(
        text.get_text() == "<- 战争 ->"
        for axis in figure.axes
        for text in axis.texts
    )
