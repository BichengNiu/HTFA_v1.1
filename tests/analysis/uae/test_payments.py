"""Tests for the CBUAE payment-flow charts."""

from io import BytesIO

import pandas as pd
import pytest

from tests.analysis.uae._helpers import report_source

from htfa.monitoring.uae.government_finance.payments import (
    PAYMENT_SHEET,
    PAYMENT_LABELS,
    payment_display_values,
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


def test_payment_download_keeps_cumulative_inputs_without_filling_missing_months():
    index = pd.to_datetime(["2025-11-30", "2026-01-31", "2026-02-28",
                            "2026-04-30", "2026-05-31"])
    values = pd.DataFrame({CUSTOMER_TRANSFERS_NUMBER_DISPLAY: [110, 10, 25, 60, 80],
                           CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: [1100, 100, 250, 600, 800]},
                          index=index)
    frame = payment_display_values(
        values, series=(CUSTOMER_TRANSFERS_NUMBER_DISPLAY, CUSTOMER_TRANSFERS_AMOUNT_DISPLAY),
        last_month=pd.Period("2026-05", freq="M"),
    )
    assert frame.loc["2026-01-31", "转账笔数"] == 10
    assert frame.loc["2026-02-28", "转账笔数"] == 15
    assert pd.isna(frame.loc["2026-04-30", "转账笔数"])
    assert pd.isna(frame.loc["2026-04-30", "转账笔数（上月累计）"])
    assert frame.loc["2026-05-31", "转账笔数"] == 20
    assert frame.loc["2026-05-31", "转账笔数（年内累计）"] == 80
    assert frame.loc["2026-05-31", "转账笔数（上月累计）"] == 60


def test_payment_baseline_matches_month_start_labels_and_rejects_duplicate_months():
    values = pd.DataFrame({CUSTOMER_TRANSFERS_NUMBER_DISPLAY: [10, 25, 40],
                           CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: [100, 250, 400]},
                          index=pd.date_range("2026-01-01", periods=3, freq="MS"))
    frame = payment_display_values(
        values, series=(CUSTOMER_TRANSFERS_NUMBER_DISPLAY, CUSTOMER_TRANSFERS_AMOUNT_DISPLAY),
        last_month=pd.Period("2026-03", freq="M"),
    )
    assert frame.loc["2026-02-01", "转账笔数"] == 15
    assert frame.loc["2026-02-01", "转账笔数（上月累计）"] == 10
    values.index = pd.to_datetime(["2026-01-01", "2026-01-31", "2026-02-28"])
    with pytest.raises(ValueError, match="同月重复"):
        cumulative_to_monthly(values)


def _data_lines(figure):
    return [
        line
        for axis in figure.axes
        for line in axis.get_lines()
        if line.get_label() and not line.get_label().startswith("_")
    ]


def test_payment_loader_reads_mixed_units_and_four_indicators() -> None:
    data = load_payment_data(report_source(_workbook_bytes()))

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
            report_source(_workbook_bytes(missing_indicator=CHEQUES_AMOUNT)),
        )


def test_payment_loader_rejects_invalid_numeric_value() -> None:
    with pytest.raises(ValueError, match="不是数值"):
        from htfa.data.economic_workbook.tables import TableWorkbook
        from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
        from htfa.monitoring.uae.government_finance.payments import PAYMENT_INDICATORS

        with pd.ExcelFile(BytesIO(_workbook_bytes(invalid_amount=True))) as book:
            raw = book.parse(PAYMENT_SHEET, header=None)
        tables = TableWorkbook([PAYMENT_SHEET], lambda _name: raw)
        parse_target_sheet(
            tables, sheet_name=PAYMENT_SHEET,
            targets=tuple((label, indicator) for label, indicator, _ in PAYMENT_INDICATORS),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in PAYMENT_INDICATORS},
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
    data = load_payment_data(report_source(_workbook_bytes()))

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
        PAYMENT_LABELS[number_label],
        PAYMENT_LABELS[amount_label],
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
