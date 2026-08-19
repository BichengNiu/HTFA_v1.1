"""Tests for the IMF PortWatch 交通物流 panel (霍尔木兹通道 + UAE 港口)."""

from io import BytesIO
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from dashboard.analysis.uae.transport import renderer
from dashboard.analysis.uae.transport.charts import (
    HORMUZ_CHANNEL_TITLE,
    PORT_LINKAGE_TITLE,
    build_hormuz_channel_figure,
    build_port_linkage_figure,
)
from dashboard.analysis.uae.transport.data import (
    HORMUZ_CAPACITY,
    HORMUZ_TANKER_CALLS,
    HORMUZ_TANKER_CAPACITY,
    UAE_PORT_CALLS,
    anchor_last_month,
    latest_complete_month,
    load_transport_data,
)

_INDICATOR_HEADERS = [
    "霍尔木兹:油轮过境次数:当月值",
    "阿联酋:港口到港总次数:当月值",
    "霍尔木兹:载货容量:当月值",
    "霍尔木兹:油轮载货容量:当月值",
]
# 与写表器一致：艘次 2 列、吨 2 列（2026-03 战争断崖形状）
_CALLS_SERIES = [30 + index for index in range(13)]
_TON_SERIES = [20_000_000 + index * 1_000_000 for index in range(13)]


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
            _INDICATOR_HEADERS[0]: _series_values(60, crash_at=9)[::-1],
            _INDICATOR_HEADERS[1]: _series_values(2_000, crash_at=9)[::-1],
            _INDICATOR_HEADERS[2]: _series_values(
                120_000_000, step=1_000_000, crash_at=9
            )[::-1],
            _INDICATOR_HEADERS[3]: _series_values(
                80_000_000, step=1_000_000, crash_at=9
            )[::-1],
        }
    )
    metadata = pd.DataFrame(
        [
            ["IMF PortWatch", None, None, None, None],
            ["指标名称", *_INDICATOR_HEADERS],
            ["频率", *("月",) * 4],
            ["单位", "艘次", "艘次", "吨", "吨"],
            ["来源", *("IMF PortWatch (HDX mirror)",) * 4],
            ["更新时间", *("2026-08-18",) * 4],
        ]
    )
    rows = pd.concat(
        [
            metadata,
            frame.rename(columns={"日期": 0}).set_axis(range(5), axis=1),
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
    return buffer.getvalue()


def test_loader_reads_four_portwatch_indicators() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")

    assert data.values.columns.tolist() == [
        HORMUZ_TANKER_CALLS,
        UAE_PORT_CALLS,
        HORMUZ_CAPACITY,
        HORMUZ_TANKER_CAPACITY,
    ]
    assert data.values.index.max() == pd.Timestamp("2025-05-31")
    # 战争月（2025-02）：油轮过境断崖至 2% 水平（60+9=69 → 1.38）
    assert data.values.loc["2025-02-28", HORMUZ_TANKER_CALLS] == pytest.approx(
        69 * 0.02
    )
    # 最新月（2025-05）：油轮容量 80M + 12×1M = 92M 吨
    assert data.values.loc["2025-05-31", HORMUZ_TANKER_CAPACITY] == pytest.approx(
        92_000_000
    )
    assert {item.unit for item in data.metadata.values()} == {"艘次", "吨"}
    assert {item.source for item in data.metadata.values()} == {
        "IMF PortWatch (HDX mirror)"
    }


def test_latest_complete_month_requires_all_four_indicators() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")

    assert latest_complete_month(data.values) == pd.Timestamp("2025-05-31")

    partial = data.values.copy()
    partial.loc["2025-05-31", HORMUZ_TANKER_CAPACITY] = float("nan")
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


def test_hormuz_channel_figure_dual_axis() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_hormuz_channel_figure(
        data.values,
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    assert len(figure.axes) == 2
    axis, right_axis = figure.axes
    assert axis.get_title() == HORMUZ_CHANNEL_TITLE
    assert axis.get_ylim()[0] == 0
    assert right_axis.get_ylim()[0] == 0
    # 左轴 1 条（过境艘次）、右轴 2 条（总容量/油轮容量，折为百万吨）
    left_lines = [line for line in axis.get_lines() if not line.get_label().startswith("_")]
    right_lines = [
        line for line in right_axis.get_lines() if not line.get_label().startswith("_")
    ]
    assert len(left_lines) == 1
    assert len(right_lines) == 2
    # 最新月油轮容量 80M+12×1M = 92M 吨 → 图 92 百万吨
    tanker_line = next(line for line in right_lines if "油轮容量" in line.get_label())
    assert tanker_line.get_ydata()[-1] == pytest.approx((80_000_000 + 12 * 1_000_000) / 1_000_000)
    # 模板图例挂在参考轴（主轴）上
    legend_labels = {text.get_text() for text in axis.get_legend().get_texts()}
    assert len(legend_labels) == 3
    assert any("载货" in label for label in legend_labels)
    assert any("油轮容量" in label for label in legend_labels)
    assert any("过境" in label for label in legend_labels)
    assert any("IMF PortWatch" in text.get_text() for text in figure.texts)


def _war_window_values() -> pd.DataFrame:
    """构造覆盖 2026-03 战争起点的 PortWatch 月度模拟数据（2024-12 至 2026-07）。

    2026-03（升序 index 15）油轮容量断崖 -98%，用于验证战争基准线。
    """

    dates = pd.date_range("2024-12-31", periods=20, freq="ME")
    calls = [60 + index for index in range(20)]
    capacity = [80_000_000 + index * 1_000_000 for index in range(20)]
    calls[15] = calls[15] * 0.02
    capacity[15] = capacity[15] * 0.02
    frame = pd.DataFrame(
        {
            "日期": dates,
            _INDICATOR_HEADERS[0]: calls,
            _INDICATOR_HEADERS[1]: [2_000 + index for index in range(20)],
            _INDICATOR_HEADERS[2]: [
                120_000_000 + index * 1_000_000 for index in range(20)
            ],
            _INDICATOR_HEADERS[3]: capacity,
        }
    )
    metadata = pd.DataFrame(
        [
            ["IMF PortWatch", None, None, None, None],
            ["指标名称", *_INDICATOR_HEADERS],
            ["频率", *("月",) * 4],
            ["单位", "艘次", "艘次", "吨", "吨"],
            ["来源", *("IMF PortWatch (HDX mirror)",) * 4],
            ["更新时间", *("2026-08-18",) * 4],
        ]
    )
    rows = pd.concat(
        [metadata, frame.rename(columns={"日期": 0}).set_axis(range(5), axis=1)],
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
    return load_transport_data(buffer.getvalue(), file_name="war.xlsx").values


def test_hormuz_channel_figure_marks_war_start_with_red_dashed_line() -> None:
    from matplotlib.colors import to_rgba

    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    values = _war_window_values()
    last_month = pd.Period("2026-07", freq="M")

    figure = build_hormuz_channel_figure(
        values,
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
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


def test_hormuz_channel_figure_skips_war_line_before_march_2026() -> None:
    from matplotlib.colors import to_rgba

    from Ts.TsPlots.style import REFERENCE_LINE_COLOR

    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_hormuz_channel_figure(
        data.values,
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


def test_port_linkage_figure_dual_axis() -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure = build_port_linkage_figure(
        data.values,
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )

    assert len(figure.axes) == 2
    axis, right_axis = figure.axes
    assert axis.get_title() == PORT_LINKAGE_TITLE
    left_lines = [line for line in axis.get_lines() if not line.get_label().startswith("_")]
    right_lines = [
        line for line in right_axis.get_lines() if not line.get_label().startswith("_")
    ]
    assert len(left_lines) == 1
    assert len(right_lines) == 1
    assert left_lines[0].get_ydata()[-1] == pytest.approx(2_012)
    assert right_lines[0].get_ydata()[-1] == pytest.approx(92.0)
    # 模板图例挂在参考轴（主轴）上
    legend_labels = {text.get_text() for text in axis.get_legend().get_texts()}
    assert len(legend_labels) == 2


def test_section_renders_two_charts_and_explanation(monkeypatch) -> None:
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    monkeypatch.setattr(
        renderer,
        "_load_transport_cached",
        lambda content, file_name: data,
    )
    st_obj = MagicMock()
    left, right = MagicMock(), MagicMock()
    st_obj.columns.return_value = (left, right)

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
    assert st_obj.columns.call_args.kwargs["gap"] == "small"
    assert left.pyplot.call_count == 1
    assert right.pyplot.call_count == 1
    assert left.download_button.call_count == 1
    assert right.download_button.call_count == 1
    assert st_obj.pyplot.call_count == 0
    assert st_obj.expander.call_count == 1


def test_section_loader_failure_shows_error_and_returns_error_status(
    monkeypatch,
) -> None:
    def _explode(*args, **kwargs):
        raise ValueError("月度_PortWatch 缺少霍尔木兹指标")

    monkeypatch.setattr(renderer, "_load_transport_cached", _explode)
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
        "_load_transport_cached",
        lambda content, file_name: data,
    )
    st_obj = MagicMock()
    left, right = MagicMock(), MagicMock()
    st_obj.columns.return_value = (left, right)

    original_render = renderer._render_chart

    def _fail_left(st_obj, data, last_month, title, figure_builder, download_columns):
        if title == HORMUZ_CHANNEL_TITLE:
            raise KeyError("霍尔木兹容量列缺失")
        return original_render(
            st_obj,
            data,
            last_month,
            title=title,
            figure_builder=figure_builder,
            download_columns=download_columns,
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
    assert right.pyplot.call_count == 1
    assert right.download_button.call_count == 1
    assert st_obj.error.call_count == 0


def test_figures_accept_ts_ndarray_axes(monkeypatch) -> None:
    from dashboard.analysis.uae.transport import charts

    original_plot_series = charts.plot_series

    def plot_series_with_array_axis(*args, **kwargs):
        figure, axis = original_plot_series(*args, **kwargs)
        return figure, np.asarray([axis], dtype=object)

    monkeypatch.setattr(
        "dashboard.analysis.uae.transport.charts.plot_series",
        plot_series_with_array_axis,
    )
    data = load_transport_data(_workbook_bytes(), file_name="test.xlsx")
    last_month = data.values.index.max().to_period("M")

    figure1 = build_hormuz_channel_figure(
        data.values,
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )
    figure2 = build_port_linkage_figure(
        data.values,
        source_text="IMF PortWatch (HDX mirror)",
        last_month=last_month,
    )
    assert len(figure1.axes) == 2
    assert len(figure2.axes) == 2