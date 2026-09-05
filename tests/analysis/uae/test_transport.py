"""Tests for the IMF PortWatch 交通物流 panel (霍尔木兹通道 + UAE 港口)."""

from io import BytesIO
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from htfa.monitoring.uae.transport import renderer
from htfa.monitoring.uae.transport.charts import (
    DUBAI_AIR_CARGO_TITLE,
    HORMUZ_CALLS_TITLE,
    US_UAE_AIR_TITLE,
    build_dual_axis_figure,
    build_multi_series_figure,
    UAE_PORT_VOLUME_TITLE,
)
from htfa.monitoring.uae.transport.data import (
    DUBAI_AIR_EXPORT_AWBS,
    DUBAI_AIR_EXPORT_TOTAL,
    DUBAI_AIR_IMPORT_AWBS,
    DUBAI_AIR_IMPORT_TOTAL,
    US_UAE_AIR_FREIGHT,
    US_UAE_AIR_PASSENGERS,
    HORMUZ_TOTAL_CALLS,
    HORMUZ_TANKER_CALLS,
    UAE_PORT_EXPORT_TOTAL,
    UAE_PORT_IMPORT_TOTAL,
    UAE_PORT_TANKER_EXPORT,
    UAE_PORT_TANKER_IMPORT,
    anchor_last_month,
    latest_complete_month,
    load_transport_data,
)

_INDICATOR_HEADERS = [
    "阿联酋:港口进口总量:当月值",
    "阿联酋:港口出口总量:当月值",
    "阿联酋:港口油轮进口量:当月值",
    "阿联酋:港口油轮出口量:当月值",
    "霍尔木兹:过境总次数:当月值",
    "霍尔木兹:油轮过境次数:当月值",
]
# 与写表器一致：港口货量 4 列、海峡过境次数 2 列（2026-03 战争断崖形状）
_CALLS_SERIES = [30 + index for index in range(13)]
_TON_SERIES = [20_000_000 + index * 1_000_000 for index in range(13)]
_DOTT_HEADERS = [
    US_UAE_AIR_PASSENGERS,
    US_UAE_AIR_FREIGHT,
]


def _indicator_sheet_rows(
    *,
    title: str,
    indicators: list[str],
    frequency: str,
    units: list[str],
    source: str,
    dates: pd.DatetimeIndex,
    values: list[list[float]],
) -> pd.DataFrame:
    metadata = [
        [title, *([None] * len(indicators))],
        ["指标名称", *indicators],
        ["频率", *([frequency] * len(indicators))],
        ["单位", *units],
        ["来源", *([source] * len(indicators))],
        ["更新时间", *(["2026-08-18"] * len(indicators))],
    ]
    rows = metadata + [
        [date, *row_values] for date, row_values in zip(dates, values)
    ]
    return pd.DataFrame(rows)


def _series_values(
    base: float,
    *,
    step: float = 1,
    crash_at: int | None = None,
) -> list[float]:
    values = [base + offset * step for offset in range(13)]
    if crash_at is not None:
        values[crash_at] = values[crash_at] * 0.02  # 战争月断崖 -98%
    return values


def _workbook_bytes() -> bytes:
    """构造含 13 个月（2024-05 至 2025-05，新→旧排列）的 PortWatch 模拟工作簿。

    2025-02（新→旧序列第 4 行 = 升序 index 9）模拟战争开始月：
    各指标断崖 -98%。吨位指标按百万阶梯递增。
    """

    dates = pd.date_range("2024-05-31", periods=13, freq="ME")
    frame = pd.DataFrame(
        {
            "日期": dates[::-1],
            _INDICATOR_HEADERS[0]: _series_values(
                120_000_000, step=1_000_000, crash_at=9
            )[::-1],
            _INDICATOR_HEADERS[1]: _series_values(
                80_000_000, step=1_000_000, crash_at=9
            )[::-1],
            _INDICATOR_HEADERS[2]: _series_values(
                60_000_000, step=1_000_000, crash_at=9
            )[::-1],
            _INDICATOR_HEADERS[3]: _series_values(
                40_000_000, step=1_000_000, crash_at=9
            )[::-1],
            _INDICATOR_HEADERS[4]: _series_values(60, crash_at=9)[::-1],
            _INDICATOR_HEADERS[5]: _series_values(40, crash_at=9)[::-1],
        }
    )
    metadata = pd.DataFrame(
        [
            ["IMF PortWatch", *([None] * 6)],
            ["指标名称", *_INDICATOR_HEADERS],
            ["频率", *("月",) * 6],
            ["单位", "吨", "吨", "吨", "吨", "艘次", "艘次"],
            ["来源", *("IMF PortWatch (HDX mirror)",) * 6],
            ["更新时间", *("2026-08-18",) * 6],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            frame.rename(columns={"日期": 0}).set_axis(range(7), axis=1),
        ],
        ignore_index=True,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        rows.to_excel(
            writer,
            sheet_name="月度_PortWatch",
            header=False,
            index=False,
        )
        _indicator_sheet_rows(
            title="Dubai Customs Airway Bill Details",
            indicators=[
                DUBAI_AIR_IMPORT_TOTAL,
                DUBAI_AIR_EXPORT_TOTAL,
                DUBAI_AIR_IMPORT_AWBS,
                DUBAI_AIR_EXPORT_AWBS,
            ],
            frequency="月",
            units=["吨", "吨", "张", "张"],
            source="Dubai Customs Airway Bill Details",
            dates=dates,
            values=[
                [40_000 + index * 10, 10_000 + index * 10,
                 10_000 + index * 10, 8_000 + index * 10]
                for index in range(13)
            ],
        ).to_excel(
            writer,
            sheet_name="月度_迪拜海关航空",
            header=False,
            index=False,
        )
        _indicator_sheet_rows(
            title="US DOT T-100 美国↔阿联酋月度航空指标",
            indicators=_DOTT_HEADERS,
            frequency="月",
            units=["人次", "磅"],
            source="US DOT BTS T-100 International Segment (All Carriers)",
            dates=dates,
            values=[
                [120_000 + index * 1_000, 2_000_000 + index * 10_000]
                for index in range(13)
            ],
        ).to_excel(
            writer,
            sheet_name="月度_DOTT100",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_loader_reads_requested_portwatch_indicators() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        UAE_PORT_IMPORT_TOTAL,
        UAE_PORT_EXPORT_TOTAL,
        UAE_PORT_TANKER_IMPORT,
        UAE_PORT_TANKER_EXPORT,
        HORMUZ_TOTAL_CALLS,
        HORMUZ_TANKER_CALLS,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    # 战争月（2025-02）：油轮过境断崖至 2% 水平（40+9=49 → 0.98）
    assert data.values.loc["2025-02-28", HORMUZ_TANKER_CALLS] == pytest.approx(
        49 * 0.02
    )
    assert data.values.loc["2025-05-31", UAE_PORT_IMPORT_TOTAL] == pytest.approx(
        132_000_000
    )
    assert {item.unit for item in data.metadata.values()} == {
        "艘次",
        "吨",
        "张",
        "人次",
        "磅",
    }
    assert {
        item.source
        for item in data.metadata.values()
        if item.sheet_name == "月度_PortWatch"
    } == {
        "IMF PortWatch (HDX mirror)"
    }
    assert data.monthly_values.columns.tolist() == [
        UAE_PORT_IMPORT_TOTAL,
        UAE_PORT_EXPORT_TOTAL,
        UAE_PORT_TANKER_IMPORT,
        UAE_PORT_TANKER_EXPORT,
        HORMUZ_TOTAL_CALLS,
        HORMUZ_TANKER_CALLS,
        DUBAI_AIR_IMPORT_AWBS,
        DUBAI_AIR_EXPORT_AWBS,
        DUBAI_AIR_IMPORT_TOTAL,
        DUBAI_AIR_EXPORT_TOTAL,
        US_UAE_AIR_PASSENGERS,
        US_UAE_AIR_FREIGHT,
    ]
    assert data.load_errors == {}


def test_latest_complete_month_requires_all_requested_indicators() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")

    assert latest_complete_month(data.values) == pd.Timestamp("2025-05-31")

    partial = data.values.copy()
    partial.loc["2025-05-31", HORMUZ_TANKER_CALLS] = float("nan")
    assert latest_complete_month(partial) == pd.Timestamp("2025-04-30")


def test_anchor_last_month_skips_the_in_progress_month() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")

    # 数据最新月（2025-05）正是“今天”所在月 → 尚未过完，锚定 2025-04
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-05-18")
    ) == pd.Period("2025-04", freq="M")
    # 月度数据已完整（今天已进入 2025-06）→ 直接取 2025-05
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-06-01")
    ) == pd.Period("2025-05", freq="M")
    assert anchor_last_month(
        data.values, today=pd.Timestamp("2025-07-15")
    ) == pd.Period("2025-05", freq="M")


def test_port_volume_figure_has_four_lines() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_multi_series_figure(
        data.values,
        columns=(
            UAE_PORT_IMPORT_TOTAL,
            UAE_PORT_EXPORT_TOTAL,
            UAE_PORT_TANKER_IMPORT,
            UAE_PORT_TANKER_EXPORT,
        ),
        title=UAE_PORT_VOLUME_TITLE,
        unit="吨",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    assert len(figure.axes) == 1
    axis = figure.axes[0]
    lines = [line for line in axis.get_lines() if not line.get_label().startswith("_")]
    assert len(lines) == 4
    assert lines[0].get_ydata()[-1] == pytest.approx(132_000_000)


def test_port_volume_figure_can_display_million_tons_without_scientific_notation() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")
    columns = (
        UAE_PORT_IMPORT_TOTAL,
        UAE_PORT_EXPORT_TOTAL,
        UAE_PORT_TANKER_IMPORT,
        UAE_PORT_TANKER_EXPORT,
    )
    display = data.values.astype(float).copy()
    display.loc[:, list(columns)] = display.loc[:, list(columns)] / 1_000_000

    figure = build_multi_series_figure(
        display,
        columns=columns,
        title=UAE_PORT_VOLUME_TITLE,
        unit="百万吨",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    figure.canvas.draw()
    axis = figure.axes[0]
    assert axis.get_lines()[0].get_ydata()[-1] == pytest.approx(132)
    assert all("e" not in label.get_text().lower() for label in axis.get_yticklabels())


def test_hormuz_legend_uses_requested_total_calls_label() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_multi_series_figure(
        data.values,
        columns=(HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
        title=HORMUZ_CALLS_TITLE,
        unit="艘次",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
        legend_labels=(
            "霍尔木兹海峡过境总次数",
            "霍尔木兹海峡油轮过境次数",
        ),
    )

    legend = figure.axes[0].get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        "霍尔木兹海峡过境总次数",
        "霍尔木兹海峡油轮过境次数",
    ]


def test_hormuz_calls_figure_has_two_lines() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_multi_series_figure(
        data.values,
        columns=(HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
        title=HORMUZ_CALLS_TITLE,
        unit="艘次",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    assert len(figure.axes) == 1
    lines = [
        line for line in figure.axes[0].get_lines()
        if not line.get_label().startswith("_")
    ]
    assert len(lines) == 2


def test_hormuz_calls_figure_marks_war_start_with_red_dashed_line() -> None:
    from matplotlib.colors import to_rgba

    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    dates = pd.date_range("2024-12-31", periods=20, freq="ME")
    values = pd.DataFrame(
        {
            HORMUZ_TOTAL_CALLS: [100] * 20,
            HORMUZ_TANKER_CALLS: [80] * 20,
        },
        index=dates,
    )
    figure = build_multi_series_figure(
        values,
        columns=(HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
        title=HORMUZ_CALLS_TITLE,
        unit="艘次",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=pd.Period("2026-07", freq="M"),
    )

    expected = to_rgba(REFERENCE_LINE_COLOR)
    axis = figure.axes[0]
    war_lines = [
        line
        for line in axis.get_lines()
        if tuple(to_rgba(line.get_color())) == pytest.approx(expected)
    ]
    assert war_lines
    assert all(line.get_linestyle() == "--" for line in war_lines)
    assert any("<- 战争 ->" == text.get_text() for text in axis.texts)


def test_hormuz_calls_figure_skips_war_line_before_march_2026() -> None:
    from matplotlib.colors import to_rgba

    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_multi_series_figure(
        data.values,
        columns=(HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
        title=HORMUZ_CALLS_TITLE,
        unit="艘次",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    expected = to_rgba(REFERENCE_LINE_COLOR)
    axis = figure.axes[0]
    assert not [
        line
        for line in axis.get_lines()
        if tuple(to_rgba(line.get_color())) == pytest.approx(expected)
    ]
    assert not any("<- 战争 ->" == text.get_text() for text in axis.texts)


def test_dubai_air_figure_combines_awbs_and_total_on_two_axes() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.monthly_values.index.max().to_period("M")

    columns = (
        DUBAI_AIR_IMPORT_AWBS,
        DUBAI_AIR_EXPORT_AWBS,
        DUBAI_AIR_IMPORT_TOTAL,
        DUBAI_AIR_EXPORT_TOTAL,
    )
    figure = build_dual_axis_figure(
        data.monthly_values,
        columns=columns,
        left_columns=(DUBAI_AIR_IMPORT_AWBS, DUBAI_AIR_EXPORT_AWBS),
        right_columns=(DUBAI_AIR_IMPORT_TOTAL, DUBAI_AIR_EXPORT_TOTAL),
        title=DUBAI_AIR_CARGO_TITLE,
        units={
            DUBAI_AIR_IMPORT_AWBS: "张",
            DUBAI_AIR_EXPORT_AWBS: "张",
            DUBAI_AIR_IMPORT_TOTAL: "吨",
            DUBAI_AIR_EXPORT_TOTAL: "吨",
        },
        source_text="Dubai Customs Airway Bill Details",
        last_month=last_month,
        legend_labels=columns,
    )

    assert len(figure.axes) == 2
    assert len(
        [line for line in figure.axes[0].get_lines() if not line.get_label().startswith("_")]
    ) == 2
    assert len(
        [line for line in figure.axes[1].get_lines() if not line.get_label().startswith("_")]
    ) == 2

    assert figure.axes[0].get_ylabel() == "万张"
    assert figure.axes[1].get_ylabel() == "万吨"


def test_us_uae_air_figure_draws_passenger_and_freight_lines() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.monthly_values.index.max().to_period("M")
    columns = (US_UAE_AIR_PASSENGERS, US_UAE_AIR_FREIGHT)

    figure = build_dual_axis_figure(
        data.monthly_values,
        columns=columns,
        left_columns=(US_UAE_AIR_PASSENGERS,),
        right_columns=(US_UAE_AIR_FREIGHT,),
        title=US_UAE_AIR_TITLE,
        units={
            US_UAE_AIR_PASSENGERS: "人次",
            US_UAE_AIR_FREIGHT: "磅",
        },
        source_text="US DOT BTS T-100 International Segment (All Carriers)",
        last_month=last_month,
        legend_labels=columns,
    )

    assert len(figure.axes) == 2
    assert len(
        [line for line in figure.axes[0].get_lines() if not line.get_label().startswith("_")]
    ) == 1
    assert len(
        [line for line in figure.axes[1].get_lines() if not line.get_label().startswith("_")]
    ) == 1
    assert figure.axes[0].get_ylabel() == "万人次"
    assert figure.axes[1].get_ylabel() == "万磅"
    legend = figure.axes[0].get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        "美国—阿联酋航空旅客",
        "美国—阿联酋航空货运",
    ]


def test_section_renders_two_charts_and_explanation(monkeypatch) -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    monkeypatch.setattr(
        renderer,
        "load_transport_data",
        lambda content, file_name, **kwargs: data,
    )
    st_obj = MagicMock()
    metric_columns = tuple(MagicMock() for _ in range(4))
    left, right = MagicMock(), MagicMock()

    def _columns(n, gap=None):
        return metric_columns if n == 4 else (left, right)

    st_obj.columns.side_effect = _columns
    render_calls = []
    original_render = renderer._render_chart

    def _capture_render(*args, **kwargs):
        render_calls.append(kwargs)
        return original_render(*args, **kwargs)

    monkeypatch.setattr(renderer, "_render_chart", _capture_render)

    result = renderer.render_transport_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    assert result["as_of"] == "2025-05"
    calls = [call[0] for call in st_obj.method_calls]
    assert calls.count("divider") == 1
    assert calls.count("subheader") == 1
    assert st_obj.subheader.call_args.args[0] == "交通物流"
    assert st_obj.metric.call_count == 8
    assert [call.args[0] for call in st_obj.metric.call_args_list] == [
        "阿联酋港口进口量",
        "阿联酋港口出口量",
        "霍尔木兹过境总次数",
        "霍尔木兹油轮过境次数",
        "迪拜航空货运运单数",
        "迪拜航空货运总量",
        "美国—阿联酋航空旅客",
        "美国—阿联酋航空货运",
    ]
    assert all(
        "环比" in call.kwargs["delta"] and "同比" in call.kwargs["delta"]
        for call in st_obj.metric.call_args_list
    )
    assert st_obj.columns.call_args.kwargs["gap"] == "small"
    assert st_obj.columns.call_count == 4
    assert left.pyplot.call_count == 2
    assert right.pyplot.call_count == 2
    assert left.download_button.call_count == 2
    assert right.download_button.call_count == 2
    assert st_obj.pyplot.call_count == 0
    assert st_obj.expander.call_count == 1
    assert st_obj.expander.call_args.kwargs["expanded"] is True
    assert render_calls[0]["builder_kwargs"]["unit"] == "百万吨"
    assert render_calls[0]["chart_values"].loc[
        "2025-05-31", UAE_PORT_IMPORT_TOTAL
    ] == pytest.approx(132)
    assert render_calls[0]["download_values"].loc[
        "2025-05-31", UAE_PORT_IMPORT_TOTAL
    ] == 132_000_000
    assert render_calls[1]["builder_kwargs"]["legend_labels"] == (
        "霍尔木兹海峡过境总次数",
        "霍尔木兹海峡油轮过境次数",
    )


def test_section_loader_failure_shows_error_and_returns_error_status(
    monkeypatch,
) -> None:
    def _explode(*args, **kwargs):
        raise ValueError("月度_PortWatch 缺少霍尔木兹指标")

    monkeypatch.setattr(renderer, "load_transport_data", _explode)
    st_obj = MagicMock()

    result = renderer.render_transport_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "error"
    assert st_obj.error.call_count == 1
    assert st_obj.pyplot.call_count == 0


def test_cell_failure_warns_cell_and_keeps_other_chart(monkeypatch) -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    monkeypatch.setattr(
        renderer,
        "load_transport_data",
        lambda content, file_name, **kwargs: data,
    )
    st_obj = MagicMock()
    metric_columns = tuple(MagicMock() for _ in range(4))
    left, right = MagicMock(), MagicMock()

    def _columns(n, gap=None):
        return metric_columns if n == 4 else (left, right)

    st_obj.columns.side_effect = _columns

    original_render = renderer._render_chart

    def _fail_left(
        st_obj,
        data,
        last_month,
        title,
        figure_builder,
        download_columns,
        **kwargs,
    ):
        if title == UAE_PORT_VOLUME_TITLE:
            raise KeyError("阿联酋港口货量列缺失")
        return original_render(
            st_obj,
            data,
            last_month,
            title=title,
            figure_builder=figure_builder,
            download_columns=download_columns,
            **kwargs,
        )

    monkeypatch.setattr(renderer, "_render_chart", _fail_left)

    result = renderer.render_transport_section(
        st_obj,
        b"workbook",
        "test.xlsx",
    )

    assert result["status"] == "success"
    assert left.warning.call_count == 1
    assert right.warning.call_count == 0
    assert right.pyplot.call_count == 2
    assert right.download_button.call_count == 2
    assert st_obj.error.call_count == 0


def test_figures_accept_ts_ndarray_axes(monkeypatch) -> None:
    from htfa.monitoring.uae.transport import charts

    original_plot_series = charts.plot_series

    def plot_series_with_array_axis(*args, **kwargs):
        figure, axis = original_plot_series(*args, **kwargs)
        return figure, np.asarray([axis], dtype=object)

    monkeypatch.setattr(
        "htfa.monitoring.uae.transport.charts.plot_series",
        plot_series_with_array_axis,
    )
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure1 = build_multi_series_figure(
        data.values,
        columns=(
            UAE_PORT_IMPORT_TOTAL,
            UAE_PORT_EXPORT_TOTAL,
            UAE_PORT_TANKER_IMPORT,
            UAE_PORT_TANKER_EXPORT,
        ),
        title=UAE_PORT_VOLUME_TITLE,
        unit="吨",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )
    figure2 = build_multi_series_figure(
        data.values,
        columns=(HORMUZ_TOTAL_CALLS, HORMUZ_TANKER_CALLS),
        title=HORMUZ_CALLS_TITLE,
        unit="艘次",
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )
    assert len(figure1.axes) == 1
    assert len(figure2.axes) == 1
